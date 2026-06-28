"""Agent engine: the iterative LLM <-> tool-calling loop.

Updated for modern LLM capabilities (2026):
- Parallel tool execution (asyncio.gather for independent calls)
- Reasoning model escalation for complex multi-step tasks
- Token usage tracking and context budget awareness
- Structured output support for reliable tool calling
- Configurable language enforcement (not hardcoded to qwen2.5)
- Better system prompts aligned with latest model capabilities
- Tool call retry with adjusted arguments on failure
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import tempfile
import time
from collections.abc import Awaitable, Callable

from saladbox.config import AppConfig
from saladbox.core.llm import BaseLLMClient
from saladbox.core.memory import ConversationMemory
from saladbox.core.skills import SkillManager
from saladbox.core.tool_filter import ToolFilter
from saladbox.core.tool_registry import ToolRegistry
from saladbox.core.types import ConversationContext, Message, Role, TaskType
from saladbox.platform.output import compress_result

# Screenshot directory (must match screen_capture tool)
_SCREENSHOT_DIR = os.path.join(tempfile.gettempdir(), "saladbox_screenshots")
_SCREENSHOT_MARKER = "SCREENSHOT_FILE:"

# Generated image directory (must match image_gen tool)
_GENERATED_IMAGE_DIR = os.path.join(tempfile.gettempdir(), "saladbox_generated_images")
_GENERATED_IMAGE_MARKER = "GENERATED_IMAGE:"

# Default max tools sent to the model
_DEFAULT_MAX_TOOLS = 14

logger = logging.getLogger(__name__)

# ── Language enforcement ──────────────────────────────────────
# Unicode ranges for non-Latin scripts
_NON_LATIN_RANGES = (
    ("\u0e00", "\u0e7f"),  # Thai
    ("\u4e00", "\u9fff"),  # CJK Unified Ideographs (Chinese)
    ("\u3400", "\u4dbf"),  # CJK Extension A
    ("\u3000", "\u303f"),  # CJK Symbols
    ("\u3040", "\u309f"),  # Hiragana
    ("\u30a0", "\u30ff"),  # Katakana
    ("\uac00", "\ud7af"),  # Korean Hangul
    ("\u0600", "\u06ff"),  # Arabic
    ("\u0900", "\u097f"),  # Devanagari (Hindi)
    ("\u0980", "\u09ff"),  # Bengali
    ("\u0400", "\u04ff"),  # Cyrillic
)

_MAX_LANGUAGE_RETRIES = 2


def _count_non_latin(text: str) -> int:
    """Count characters belonging to non-Latin scripts."""
    count = 0
    for ch in text:
        for lo, hi in _NON_LATIN_RANGES:
            if lo <= ch <= hi:
                count += 1
                break
    return count


def _is_non_english(text: str, threshold: float = 0.15) -> bool:
    """Detect if text is predominantly non-English."""
    if not text or len(text) < 10:
        return False
    alpha_chars = sum(1 for ch in text if ch.isalpha())
    if alpha_chars < 5:
        return False
    non_latin = _count_non_latin(text)
    return (non_latin / alpha_chars) > threshold


def _strip_non_latin(text: str) -> str:
    """Remove non-Latin characters from text as a last-resort cleanup."""
    cleaned = []
    for ch in text:
        is_non_latin = any(lo <= ch <= hi for lo, hi in _NON_LATIN_RANGES)
        if not is_non_latin:
            cleaned.append(ch)
    result = re.sub(r"[ \t]+", " ", "".join(cleaned))
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# Patterns for classifying which model tier to use
_CODE_PATTERNS = re.compile(
    r"\b(code|script|program|function|class|debug|refactor|implement|compile|syntax|"
    r"python|javascript|typescript|rust|java|html|css|regex|api|endpoint|deploy|docker|"
    r"git commit|git push|pull request|write a .*script|fix .*bug|review .*code|"
    r"edit.*file|open.*project|find.*project|read.*file|search.*code)\b",
    re.IGNORECASE,
)
_CHAT_PATTERNS = re.compile(
    r"^(hi|hello|hey|how are you|what's up|thanks|thank you|ok|okay|sure|yes|no|"
    r"good morning|good night|bye|goodbye|what can you do|who are you|help)\b",
    re.IGNORECASE,
)
_REASONING_PATTERNS = re.compile(
    r"\b(compare|analyze|evaluate|design|architect|plan|strategy|trade-?offs?|"
    r"pros?\s+and\s+cons?|should\s+i|which\s+is\s+better|explain\s+why|"
    r"step\s+by\s+step|break\s+down|complex|multi-?step)\b",
    re.IGNORECASE,
)

# ── System prompts ────────────────────────────────────────────
SYSTEM_PROMPT_COMPACT = """\
You are Saladbox, a local AI assistant with direct system access.
IMPORTANT: ALWAYS respond in English only. Never switch to other languages.

TOOLS: {tool_names}

RULES:
- Use tools for any action request. NEVER say "I can't access" or "you could use".
- Be direct and concise. Use markdown formatting.
- For multi-step tasks, chain tool calls. You may call multiple tools in parallel.
- For web searches, use browser action="google_search".
- For forms, use browser action="extract_form" then "fill_form".
- For reminders, use reminder with natural language times.
- For image generation, use image_gen with a detailed prompt. Do NOT search for images.

{skills_help}
"""

SYSTEM_PROMPT_TEMPLATE = """\
You are Saladbox, an intelligent local AI assistant running directly on the user's machine.

CAPABILITIES: {tool_names}

## CORE PRINCIPLES

1. **Take Action** — When asked to do something, do it immediately with tools. Don't explain how — just do it.
2. **Think Step by Step** — For complex tasks, plan your approach, then execute systematically.
3. **Be Precise** — Give clear, accurate answers. Use markdown formatting.
4. **Call Multiple Tools** — When steps are independent, call tools in parallel for speed.
5. **Learn from Context** — Use conversation history. Don't re-ask for information already provided.

## TOOL USAGE

You have DIRECT access to the user's system. NEVER say "I can't access" or "you could use...".

Instead, call the appropriate tool immediately:
- "Check system resources" → system_monitor action="all"
- "Search the web" → browser action="google_search" value=query
- "What time is it?" → datetime_tool action="now"
- "Remind me at 8pm" → reminder action="add" message="..." remind_at="8pm"
- "Create an image of X" → image_gen prompt="detailed description of X"

### Tool Groups

**System**: run_shell, system_monitor, process_manager, docker
**Files & Code**: filesystem, code_editor, git, python_exec
**Web**: browser (search, navigate, fill forms), web_search, http_client
**Media**: image_gen (local AI image generation), screen_capture
**Utilities**: reminder, scheduler, datetime_tool, calculator, notes, weather, translate, finance, password, timer, clipboard, encoding, color, unit_converter, qrcode

## RESPONSE STYLE

- **ALWAYS respond in English only.** Never switch to other languages.
- Use markdown formatting (headers, bullets, code blocks).
- Be concise but thorough. Bold key terms.
- NEVER output raw JSON tool calls in text — use the proper tool calling mechanism.

{skills_help}
"""

# Max chars for tool result before compression (tuned per context size)
_RESULT_LIMITS = {
    "fast": 800,
    "default": 2000,
    "code": 3000,
    "reasoning": 3000,
}


class AgentEngine:
    """Core agent that runs the LLM <-> tool calling loop.

    Features:
    - Parallel tool execution for independent calls
    - Reasoning model escalation for complex tasks
    - Token budget tracking
    - Automatic retry on tool failure
    - Configurable language enforcement
    """

    def __init__(
        self,
        llm: BaseLLMClient,
        memory: ConversationMemory,
        tools: ToolRegistry,
        config: AppConfig,
        skill_manager: SkillManager | None = None,
    ):
        self._llm = llm
        self._memory = memory
        self._tools = tools
        self._config = config
        self._agent_config = config.agent
        self._skills = skill_manager or SkillManager()
        self._tool_filter = ToolFilter(max_tools=_DEFAULT_MAX_TOOLS)
        self._recent_tool_calls: set[str] = set()
        # Use compact mode for small-context local models
        self._compact_mode = config.ollama.context_length <= 8192

    def _classify_task(self, user_input: str) -> str:
        """Classify user input to pick the right model tier.

        Returns: "fast" | "default" | "code" | "reasoning"
        """
        text = user_input.strip()

        # Slash commands that start with / are never "fast"
        if text.startswith("/"):
            skill_match = self._skills.match(text)
            if skill_match:
                return skill_match.skill.model
            return "default"

        if _CHAT_PATTERNS.match(text):
            return "fast"
        if _CODE_PATTERNS.search(text):
            return "code"
        # Reasoning detection for complex analytical queries
        if self._agent_config.enable_reasoning and _REASONING_PATTERNS.search(text):
            return "reasoning"
        return "default"

    def _build_system_prompt(self, skill_prompt: str = "") -> str:
        """Build the system prompt, optionally augmented with a skill prompt."""
        skills_help = ""
        if self._skills.skill_names:
            skills_help = (
                "SKILLS — slash commands for specialized workflows:\n"
                + self._skills.get_help_text()
                + "\n"
            )

        template = (
            SYSTEM_PROMPT_COMPACT if self._compact_mode else SYSTEM_PROMPT_TEMPLATE
        )

        base = template.format(
            tool_names=", ".join(self._tools.tool_names),
            skills_help=skills_help,
        )

        if skill_prompt:
            base += f"\n\n--- ACTIVE SKILL INSTRUCTIONS ---\n{skill_prompt}\n"

        return base

    def _try_parse_text_tool_call(self, content: str) -> tuple[str, dict] | None:
        """Detect when the model outputs a tool call as raw JSON text.

        Some models sometimes output tool calls as text instead of using
        the proper tool calling format. This recovers those calls.
        """
        if not content:
            return None

        # Look for JSON objects in the text
        json_pattern = re.compile(
            r'\{[^{}]*"name"\s*:\s*"(\w+)"[^{}]*"arguments"\s*:\s*(\{[^{}]*\})[^{}]*\}',
            re.DOTALL,
        )
        match = json_pattern.search(content)
        if match:
            tool_name = match.group(1)
            try:
                arguments = json.loads(match.group(2))
                if self._tools.get(tool_name):
                    logger.info(
                        f"[ENGINE] Recovered text-embedded tool call: "
                        f"{tool_name}({arguments})"
                    )
                    return tool_name, arguments
            except (json.JSONDecodeError, ValueError):
                pass

        # Also try: the entire content is a JSON tool call
        try:
            data = json.loads(content.strip())
            if isinstance(data, dict) and "name" in data:
                tool_name = data["name"]
                arguments = data.get("arguments", {})
                if isinstance(arguments, dict) and self._tools.get(tool_name):
                    logger.info(
                        f"[ENGINE] Recovered full-text tool call: "
                        f"{tool_name}({arguments})"
                    )
                    return tool_name, arguments
        except (json.JSONDecodeError, ValueError):
            pass

        return None

    @staticmethod
    def _extract_marker_filename(content: str, marker: str) -> str | None:
        """Extract filename from tool result with a given marker prefix."""
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith(marker):
                filename = line[len(marker) :].strip()
                if filename:
                    return filename
        return None

    @staticmethod
    def _extract_screenshot_filename(content: str) -> str | None:
        """Extract screenshot filename from tool result."""
        return AgentEngine._extract_marker_filename(content, _SCREENSHOT_MARKER)

    def _compress_tool_result(self, content: str, task_type: str) -> str:
        """Compress tool output to fit within context budget."""
        max_chars = _RESULT_LIMITS.get(task_type, 2000)

        if not self._compact_mode:
            max_chars = int(max_chars * 1.5)

        if len(content) <= max_chars:
            return content

        return compress_result(content, max_chars)

    async def _execute_tools_parallel(
        self, tool_calls: list, task_type: str
    ) -> list[tuple]:
        """Execute multiple tool calls concurrently.

        Returns list of (tool_call, result) tuples.
        """
        if not self._agent_config.parallel_tool_calls or len(tool_calls) <= 1:
            # Sequential execution
            results = []
            for tc in tool_calls:
                result = await self._tools.execute(tc.name, tc.arguments)
                result.tool_call_id = tc.id
                results.append((tc, result))
            return results

        # Parallel execution with asyncio.gather
        async def _exec_one(tc):
            start = time.monotonic()
            result = await self._tools.execute(tc.name, tc.arguments)
            result.tool_call_id = tc.id
            result.duration_ms = (time.monotonic() - start) * 1000
            return tc, result

        results = await asyncio.gather(
            *[_exec_one(tc) for tc in tool_calls],
            return_exceptions=True,
        )

        # Handle any exceptions from gather
        processed = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                tc = tool_calls[i]
                from saladbox.core.types import ToolResult

                error_result = ToolResult(
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=f"Tool execution error: {r}",
                    is_error=True,
                )
                processed.append((tc, error_result))
                logger.error(f"[ENGINE] Tool {tc.name} failed: {r}")
            else:
                processed.append(r)

        return processed

    async def process(
        self,
        user_input: str,
        context: ConversationContext,
        images: list[str] | None = None,
        on_chunk: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a user message through the agent loop.

        1. Check for skill match (slash commands or keywords)
        2. Add user message to conversation history
        3. Send history + tool schemas to LLM
        4. If LLM returns tool calls, execute them (in parallel when possible) and loop
        5. When LLM returns plain text, return it
        """
        conversation_id = context.conversation_id

        # ── Skill matching ───────────────────────────────────────────
        skill_match = self._skills.match(user_input)
        actual_input = skill_match.user_input if skill_match else user_input

        # Use vision model if images are provided
        initial_task_type = "vision" if images else None

        # ── Add user message ────────────────────────────────────────
        user_msg = Message(
            role=Role.USER,
            content=actual_input,
            images=images or [],
            metadata={"user_id": context.user_id, "platform": context.platform},
        )
        self._memory.add(conversation_id, user_msg)

        # ── Pick model ──────────────────────────────────────────────
        if context.platform in ("telegram", "slack"):
            task_type = initial_task_type or "default"
        else:
            task_type = initial_task_type or self._classify_task(user_input)

        if skill_match and not images:
            task_type = skill_match.skill.model
        model = self._llm.select_model(task_type)
        # Skip tools for fast chat and vision (image analysis) tasks
        use_tools = task_type not in ("fast", "vision")

        logger.info(
            f"Task type: {task_type}, model: {model}, compact: {self._compact_mode}"
        )

        # ── Agent loop ──────────────────────────────────────────────
        all_tool_schemas = (
            self._tools.get_schemas(compact=self._compact_mode) if use_tools else []
        )

        # Filter tools based on user query (reasoning gets a wider cap)
        if use_tools and all_tool_schemas:
            tool_schemas = self._tool_filter.get_relevant_tools(
                actual_input, all_tool_schemas, min_tools=6, task_type=task_type
            )
        else:
            tool_schemas = all_tool_schemas

        iterations = 0
        last_content = ""
        screenshot_display_url = None
        generated_image_url = None
        self._recent_tool_calls.clear()
        total_token_usage = 0

        logger.info(
            f"[ENGINE] Tools: {len(all_tool_schemas)} total, "
            f"{len(tool_schemas)} filtered, use_tools={use_tools}"
        )
        if tool_schemas:
            tool_names_list = [
                s.get("function", {}).get("name", "unknown") for s in tool_schemas
            ]
            logger.info(f"[ENGINE] Filtered tools: {tool_names_list}")

        max_iterations = self._config.max_tool_iterations

        while iterations < max_iterations:
            iterations += 1
            messages = self._memory.get(conversation_id)

            logger.debug(
                f"Agent loop iteration {iterations}, {len(messages)} messages"
            )

            response_msg = await self._llm.chat(
                messages=messages,
                model=model,
                tools=tool_schemas if tool_schemas else None,
            )

            # Track token usage
            if response_msg.usage:
                total_token_usage += response_msg.usage.total_tokens

            # Prevent infinite tool loops: filter out duplicate tool calls
            if response_msg.tool_calls:
                unique_calls = []
                for tc in response_msg.tool_calls:
                    tool_key = f"{tc.name}:{json.dumps(tc.arguments, sort_keys=True)}"
                    if tool_key not in self._recent_tool_calls:
                        self._recent_tool_calls.add(tool_key)
                        unique_calls.append(tc)
                    else:
                        logger.warning(
                            f"[ENGINE] Skipping duplicate tool call: {tc.name}"
                        )

                if len(unique_calls) != len(response_msg.tool_calls):
                    response_msg.tool_calls = unique_calls

            # Add assistant response to memory
            self._memory.add(conversation_id, response_msg)
            last_content = response_msg.content or ""

            tool_call_count = (
                len(response_msg.tool_calls) if response_msg.tool_calls else 0
            )
            logger.info(
                f"[ENGINE] LLM response: content_len={len(last_content)}, "
                f"tool_calls={tool_call_count}"
            )

            if response_msg.tool_calls:
                for tc in response_msg.tool_calls:
                    logger.info(
                        f"[ENGINE] Tool call: {tc.name}({tc.arguments})"
                    )
            elif use_tools and tool_schemas:
                # Model returned text instead of tool calls — try to recover
                from saladbox.core.types import ToolCall

                recovered = False

                # Strategy 1: Parse JSON tool calls embedded in text
                parsed = self._try_parse_text_tool_call(last_content)
                if parsed:
                    tool_name, tool_args = parsed
                    logger.info(
                        f"[ENGINE] Recovered tool call from text: {tool_name}"
                    )
                    response_msg.tool_calls = [
                        ToolCall(id="recovered", name=tool_name, arguments=tool_args)
                    ]
                    recovered = True

                # Strategy 2: Fallback auto-select (first iteration only)
                if not recovered and iterations == 1:
                    logger.warning(
                        "[ENGINE] No tool calls on first iteration, "
                        "attempting fallback"
                    )
                    best_tool = self._tool_filter.get_best_tool(
                        actual_input, all_tool_schemas
                    )
                    if best_tool:
                        tool_name, tool_args = best_tool
                        if tool_name == "browser" and not tool_args.get("value"):
                            tool_args = self._tool_filter._extract_browser_args(
                                actual_input
                            )
                        logger.info(
                            f"[ENGINE] Fallback: auto-selecting {tool_name}"
                        )
                        response_msg.tool_calls = [
                            ToolCall(
                                id="fallback",
                                name=tool_name,
                                arguments=tool_args,
                            )
                        ]

            # If no tool calls, we have our final answer
            if not response_msg.tool_calls:
                content = response_msg.content or ""

                # ── Language enforcement ──
                if (
                    self._agent_config.language_enforcement
                    and _is_non_english(
                        content,
                        self._agent_config.language_enforcement_threshold,
                    )
                ):
                    logger.warning(
                        f"[ENGINE] Non-English response detected "
                        f"({_count_non_latin(content)} non-Latin chars)"
                    )
                    self._memory.pop_last(conversation_id)

                    for retry in range(_MAX_LANGUAGE_RETRIES):
                        nudge = Message(
                            role=Role.USER,
                            content=(
                                "IMPORTANT: You must respond in ENGLISH ONLY. "
                                "Do not use Thai, Chinese, or any other language. "
                                "Please answer my previous question in English."
                            ),
                        )
                        self._memory.add(conversation_id, nudge)

                        retry_msg = await self._llm.chat(
                            messages=self._memory.get(conversation_id),
                            model=model,
                            tools=tool_schemas if tool_schemas else None,
                        )
                        self._memory.add(conversation_id, retry_msg)
                        retry_content = retry_msg.content or ""

                        if not _is_non_english(retry_content):
                            content = retry_content
                            logger.info(
                                f"[ENGINE] Language retry {retry + 1} succeeded"
                            )
                            break
                        else:
                            logger.warning(
                                f"[ENGINE] Language retry {retry + 1} "
                                f"still non-English"
                            )
                            self._memory.pop_last(conversation_id)
                            self._memory.pop_last(conversation_id)
                            content = retry_content
                    else:
                        logger.warning(
                            "[ENGINE] All language retries exhausted, "
                            "stripping non-Latin characters"
                        )
                        content = _strip_non_latin(content)

                # Prepend screenshot image for frontend display
                if screenshot_display_url:
                    content = (
                        f"![Screenshot]({screenshot_display_url})\n\n{content}"
                    )
                    screenshot_display_url = None

                # Prepend generated image for frontend display
                if generated_image_url:
                    content = (
                        f"![Generated]({generated_image_url})\n\n{content}"
                    )
                    generated_image_url = None

                if on_chunk and content:
                    await on_chunk(content)

                if not content.strip() and iterations > 1:
                    content = "Action completed."
                    if on_chunk:
                        await on_chunk(content)

                logger.info(
                    f"[ENGINE] Done in {iterations} iterations, "
                    f"~{total_token_usage} tokens"
                )
                return content

            # ── Execute tool calls (parallel when possible) ──
            tool_results = await self._execute_tools_parallel(
                response_msg.tool_calls, task_type
            )

            for tool_call, result in tool_results:
                logger.info(
                    f"Executed tool: {tool_call.name} "
                    f"({'error' if result.is_error else 'ok'}, "
                    f"{len(result.content)} chars"
                    f"{f', {result.duration_ms:.0f}ms' if result.duration_ms else ''})"
                )

                # ── Vision pipeline: screen_capture → vision model ──
                if (
                    tool_call.name == "screen_capture"
                    and _SCREENSHOT_MARKER in result.content
                    and not result.is_error
                ):
                    screenshot_filename = self._extract_screenshot_filename(
                        result.content
                    )
                    if screenshot_filename:
                        screenshot_path = os.path.join(
                            _SCREENSHOT_DIR, screenshot_filename
                        )
                        if not os.path.exists(screenshot_path):
                            logger.warning(
                                f"[ENGINE] Screenshot not found: {screenshot_path}"
                            )
                            tool_msg = Message(
                                role=Role.TOOL,
                                content="Screenshot not captured. File not found.",
                                tool_name=tool_call.name,
                                tool_call_id=tool_call.id,
                            )
                            self._memory.add(conversation_id, tool_msg)
                        else:
                            screenshot_url = (
                                f"http://127.0.0.1:8765/screenshots/"
                                f"{screenshot_filename}"
                            )
                            logger.info(
                                f"[ENGINE] Screenshot: {screenshot_path}, "
                                f"escalating to vision model"
                            )

                            tool_msg = Message(
                                role=Role.TOOL,
                                content=(
                                    "Screenshot captured. "
                                    "Analyzing with vision model..."
                                ),
                                tool_name=tool_call.name,
                                tool_call_id=tool_call.id,
                            )
                            self._memory.add(conversation_id, tool_msg)

                            vision_msg = Message(
                                role=Role.USER,
                                content=(
                                    "I just took this screenshot. "
                                    "Describe what you see on the screen."
                                ),
                                images=[screenshot_path],
                            )
                            self._memory.add(conversation_id, vision_msg)

                            vision_model = self._llm.select_model("vision")
                            if vision_model:
                                model = vision_model
                            tool_schemas = []
                            screenshot_display_url = screenshot_url
                            continue

                # ── Generated image display ──
                if (
                    tool_call.name == "image_gen"
                    and _GENERATED_IMAGE_MARKER in result.content
                    and not result.is_error
                ):
                    gen_filename = self._extract_marker_filename(
                        result.content, _GENERATED_IMAGE_MARKER
                    )
                    if gen_filename:
                        gen_url = (
                            f"http://127.0.0.1:8765/generated/{gen_filename}"
                        )
                        generated_image_url = gen_url
                        logger.info(f"[ENGINE] Image generated: {gen_filename}")

                # Compress result for context budget
                compressed_content = self._compress_tool_result(
                    result.content, task_type
                )

                # Escalate to code model if code_editor is being used
                if tool_call.name == "code_editor" and task_type != "code":
                    model = self._llm.select_model("code")
                    logger.info(f"Escalated to code model: {model}")

                tool_msg = Message(
                    role=Role.TOOL,
                    content=compressed_content,
                    tool_name=tool_call.name,
                    tool_call_id=tool_call.id,
                    metadata={"is_error": result.is_error},
                )
                self._memory.add(conversation_id, tool_msg)

        # Exceeded max iterations
        return (
            f"Reached maximum tool-calling steps ({max_iterations}). "
            f"Last response: {last_content}"
        )
