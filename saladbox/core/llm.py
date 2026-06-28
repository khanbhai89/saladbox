"""LLM client wrappers for Ollama and OpenRouter.

Updated April 2026:
- OpenAI SDK v2 (openai>=2.0) — new import paths, response shapes
- Extended / interleaved thinking for Claude Opus 4.7+ via OpenRouter
- Qwen3 dual-mode thinking: /no_think in system prompt for fast tier
- Token usage tracking (prompt / completion / reasoning tokens)
- Retry with exponential backoff via tenacity
- keep_alive configuration for Ollama
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from ollama import AsyncClient
# openai v2: same surface, some internals changed
from openai import AsyncOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from saladbox.config import OllamaConfig, OpenRouterConfig
from saladbox.core.types import Message, Role, TaskType, TokenUsage, ToolCall

logger = logging.getLogger(__name__)

# Qwen3 "no-think" suffix — append to system prompt to disable chain-of-thought
# This makes fast/simple queries much quicker with Qwen3 models
_QWEN3_NO_THINK = "/no_think"
_QWEN3_MODEL_PREFIX = "qwen3"

# Claude models that support extended thinking via the OpenRouter extra_body param
_CLAUDE_THINKING_MODELS = ("claude-opus-4", "claude-sonnet-4")


def _is_qwen3(model: str) -> bool:
    return model.lower().startswith(_QWEN3_MODEL_PREFIX)


def _supports_extended_thinking(model: str) -> bool:
    """True for Claude Opus/Sonnet 4.x models that support interleaved thinking."""
    return any(m in model.lower() for m in _CLAUDE_THINKING_MODELS)


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        model: str | None = None,
        tools: list[dict] | None = None,
        json_mode: bool = False,
        thinking: bool = False,
        thinking_budget: int = 8000,
    ) -> Message:
        """Send messages and return the response as a Message."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream a response token-by-token (no tool calling)."""
        ...

    @abstractmethod
    def select_model(self, task_type: str) -> str:
        """Pick a model name based on task type."""
        ...


class OllamaClient(BaseLLMClient):
    """Async wrapper around the Ollama API.

    Supports:
    - Structured output (JSON format mode)
    - keep_alive management
    - Qwen3 /no_think system prompt for fast queries
    - Token usage tracking from eval_count
    - <think> tag stripping from reasoning model output
    """

    def __init__(self, config: OllamaConfig, agent_config=None):
        self._client = AsyncClient(host=config.host)
        self._config = config
        self._agent_config = agent_config

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[Message],
        model: str | None = None,
        tools: list[dict] | None = None,
        json_mode: bool = False,
        thinking: bool = False,
        thinking_budget: int = 8000,
    ) -> Message:
        model = model or self._config.default_model
        ollama_messages = self._to_ollama_format(messages, model=model, thinking=thinking)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": ollama_messages,
            "keep_alive": self._config.keep_alive,
        }

        if tools:
            kwargs["tools"] = tools
            logger.info(f"[OLLAMA] {len(tools)} tools → model={model}")

        if json_mode and self._config.structured_output:
            kwargs["format"] = "json"

        start = time.monotonic()
        try:
            response = await self._client.chat(**kwargs)
            elapsed = time.monotonic() - start
            logger.info(f"[OLLAMA] {model} responded in {elapsed:.1f}s")
            return self._from_ollama_response(response)
        except Exception as e:
            logger.warning(f"[OLLAMA] Error with {model}: {e}")
            if model != self._config.fallback_model:
                logger.info(f"[OLLAMA] Falling back to {self._config.fallback_model}")
                kwargs["model"] = self._config.fallback_model
                response = await self._client.chat(**kwargs)
                return self._from_ollama_response(response)
            raise

    async def stream(
        self,
        messages: list[Message],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        model = model or self._config.default_model
        ollama_messages = self._to_ollama_format(messages, model=model)

        stream = await self._client.chat(
            model=model,
            messages=ollama_messages,
            stream=True,
            keep_alive=self._config.keep_alive,
        )
        async for chunk in stream:
            content = chunk.get("message", {}).get("content", "")
            if content:
                yield content

    def select_model(self, task_type: str) -> str:
        mapping: dict[str, str] = {
            TaskType.CODE: self._config.code_model,
            TaskType.FAST: self._config.fast_model,
            TaskType.VISION: self._config.vision_model,
            TaskType.DEFAULT: self._config.default_model,
            TaskType.REASONING: self._config.reasoning_model,
            # String fallbacks for backward compatibility
            "code": self._config.code_model,
            "fast": self._config.fast_model,
            "vision": self._config.vision_model,
            "default": self._config.default_model,
            "reasoning": self._config.reasoning_model,
        }
        return mapping.get(task_type, self._config.default_model)

    def _inject_qwen3_no_think(
        self, messages: list[dict[str, Any]], model: str
    ) -> list[dict[str, Any]]:
        """Append /no_think to the system prompt for Qwen3 fast-tier queries.

        Qwen3 models default to reasoning (thinking) mode. For simple/fast
        queries we disable it to skip the chain-of-thought overhead.
        """
        if not _is_qwen3(model):
            return messages
        use_no_think = (
            self._agent_config is not None
            and getattr(self._agent_config, "qwen3_fast_no_think", True)
            and model == self._config.fast_model
        )
        if not use_no_think:
            return messages

        result = []
        injected = False
        for msg in messages:
            if msg.get("role") == "system" and not injected:
                content = msg.get("content", "")
                if _QWEN3_NO_THINK not in content:
                    msg = {**msg, "content": content + f"\n\n{_QWEN3_NO_THINK}"}
                injected = True
            result.append(msg)
        if not injected:
            # No system message — prepend one
            result = [{"role": "system", "content": _QWEN3_NO_THINK}] + result
        return result

    def _to_ollama_format(
        self,
        messages: list[Message],
        model: str = "",
        thinking: bool = False,
    ) -> list[dict[str, Any]]:
        ollama_msgs: list[dict[str, Any]] = []
        for msg in messages:
            entry: dict[str, Any] = {
                "role": msg.role.value,
                "content": msg.content or "",
            }
            if msg.images:
                images: list[str] = []
                for img in msg.images:
                    if img.startswith("data:"):
                        if ";base64," in img:
                            images.append(img.split(";base64,", 1)[1])
                        else:
                            images.append(img)
                    elif img.startswith(("/", "~")):
                        try:
                            import base64
                            with open(img, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode()
                            images.append(b64)
                        except OSError as e:
                            logger.warning(f"[OLLAMA] Image read failed {img}: {e}")
                            entry["content"] += f"\n[Image not found: {img}]"
                    else:
                        images.append(img)
                if images:
                    entry["images"] = images
            if msg.role.value == "tool" and msg.tool_name:
                entry["tool_name"] = msg.tool_name
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {"function": {"name": tc.name, "arguments": tc.arguments}}
                    for tc in msg.tool_calls
                ]
            ollama_msgs.append(entry)

        # Qwen3 /no_think injection for fast model
        if model:
            ollama_msgs = self._inject_qwen3_no_think(ollama_msgs, model)
        return ollama_msgs

    def _from_ollama_response(self, response: Any) -> Message:
        msg = response.message if hasattr(response, "message") else response.get("message", response)

        content: str = (msg.content if hasattr(msg, "content") else msg.get("content", "")) or ""

        # Strip <think>...</think> from Qwen3 / other reasoning models
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        raw_tool_calls = (
            msg.tool_calls if hasattr(msg, "tool_calls") else msg.get("tool_calls")
        ) or []

        tool_calls: list[ToolCall] = []
        for tc in raw_tool_calls:
            if hasattr(tc, "function"):
                func = tc.function
                name = func.name if hasattr(func, "name") else func.get("name", "")
                raw_args = func.arguments if hasattr(func, "arguments") else func.get("arguments", {})
            else:
                func = tc.get("function", {})
                name = func.get("name", "")
                raw_args = func.get("arguments", {})

            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args) or {}
                except (json.JSONDecodeError, TypeError):
                    raw_args = {}
            elif not isinstance(raw_args, dict):
                raw_args = {}

            tool_calls.append(ToolCall(id=str(uuid.uuid4())[:8], name=name, arguments=raw_args))

        if tool_calls:
            logger.info(f"[OLLAMA] Tool calls: {[tc.name for tc in tool_calls]}")

        # Token usage from eval_count / prompt_eval_count
        usage = None
        eval_count = getattr(response, "eval_count", None) or (
            response.get("eval_count") if isinstance(response, dict) else None
        )
        prompt_eval = getattr(response, "prompt_eval_count", None) or (
            response.get("prompt_eval_count") if isinstance(response, dict) else None
        )
        if eval_count is not None or prompt_eval is not None:
            usage = TokenUsage(
                prompt_tokens=prompt_eval or 0,
                completion_tokens=eval_count or 0,
                total_tokens=(prompt_eval or 0) + (eval_count or 0),
            )

        return Message(role=Role.ASSISTANT, content=content, tool_calls=tool_calls, usage=usage)


class OpenRouterClient(BaseLLMClient):
    """Async wrapper around OpenRouter (OpenAI-compatible) API.

    Updated for openai v2 SDK:
    - Same surface: AsyncOpenAI, chat.completions.create
    - Extended thinking for Claude Opus 4.7+ via extra_body
    - parallel_tool_calls enabled
    - Token usage from response.usage (includes reasoning_tokens in v2)
    """

    def __init__(self, config: OpenRouterConfig, agent_config=None):
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            default_headers={
                "HTTP-Referer": config.site_url,
                "X-Title": config.app_name,
            },
        )
        self._config = config
        self._agent_config = agent_config

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def chat(
        self,
        messages: list[Message],
        model: str | None = None,
        tools: list[dict] | None = None,
        json_mode: bool = False,
        thinking: bool = False,
        thinking_budget: int = 8000,
    ) -> Message:
        model = model or self._config.default_model
        openai_messages = self._to_openai_format(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = True

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        # Extended thinking for Claude Opus 4.7+ and Sonnet 4.5+
        # Passed via extra_body for OpenRouter (they forward it to Anthropic)
        if thinking and _supports_extended_thinking(model):
            actual_budget = min(thinking_budget, 16000)
            kwargs["extra_body"] = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": actual_budget,
                }
            }
            logger.info(
                f"[OPENROUTER] Extended thinking enabled: budget={actual_budget} tokens"
            )

        try:
            response = await self._client.chat.completions.create(**kwargs)
            return self._from_openai_response(response)
        except Exception as e:
            logger.warning(f"[OPENROUTER] Error with {model}: {e}")
            if model != self._config.fallback_model:
                logger.info(f"[OPENROUTER] Falling back to {self._config.fallback_model}")
                kwargs["model"] = self._config.fallback_model
                # Disable extended thinking for fallback
                kwargs.pop("extra_body", None)
                response = await self._client.chat.completions.create(**kwargs)
                return self._from_openai_response(response)
            raise

    async def stream(
        self,
        messages: list[Message],
        model: str | None = None,
    ) -> AsyncIterator[str]:
        model = model or self._config.default_model
        openai_messages = self._to_openai_format(messages)

        stream = await self._client.chat.completions.create(
            model=model,
            messages=openai_messages,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def select_model(self, task_type: str) -> str:
        mapping: dict[str, str] = {
            TaskType.CODE: self._config.code_model,
            TaskType.FAST: self._config.fast_model,
            TaskType.DEFAULT: self._config.default_model,
            TaskType.REASONING: self._config.reasoning_model,
            # String fallbacks
            "code": self._config.code_model,
            "fast": self._config.fast_model,
            "default": self._config.default_model,
            "reasoning": self._config.reasoning_model,
        }
        return mapping.get(task_type, self._config.default_model)

    def _to_openai_format(self, messages: list[Message]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for msg in messages:
            entry: dict[str, Any] = {
                "role": msg.role.value,
                "content": msg.content or "",
            }
            if msg.role == Role.TOOL and msg.tool_name:
                entry["name"] = msg.tool_name
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id or str(uuid.uuid4())[:8],
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            result.append(entry)
        return result

    def _from_openai_response(self, response: Any) -> Message:
        choice = response.choices[0]
        msg = choice.message
        content = msg.content or ""
        tool_calls: list[ToolCall] = []

        if msg.tool_calls:
            for tc in msg.tool_calls:
                raw_args = tc.function.arguments or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        # openai v2: usage still at response.usage with prompt/completion tokens
        # reasoning_tokens may be in usage.completion_tokens_details
        usage = None
        if response.usage:
            reasoning_tokens = 0
            # v2 SDK: completion_tokens_details is a CompletionTokensDetails object
            details = getattr(response.usage, "completion_tokens_details", None)
            if details:
                reasoning_tokens = getattr(details, "reasoning_tokens", 0) or 0
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
                total_tokens=response.usage.total_tokens or 0,
            )
            if reasoning_tokens:
                logger.info(f"[OPENROUTER] Reasoning tokens used: {reasoning_tokens}")

        return Message(role=Role.ASSISTANT, content=content, tool_calls=tool_calls, usage=usage)


# Legacy alias
LLMClient = OllamaClient


def create_llm_client(
    ollama_config: OllamaConfig,
    openrouter_config: OpenRouterConfig,
    agent_config=None,
) -> BaseLLMClient:
    """Factory: create the appropriate LLM client based on config."""
    if openrouter_config.enabled and openrouter_config.api_key:
        return OpenRouterClient(openrouter_config, agent_config=agent_config)
    return OllamaClient(ollama_config, agent_config=agent_config)
