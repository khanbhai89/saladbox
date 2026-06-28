"""Configuration loader: merges config.yaml with .env secrets.

Updated for 2026 LLM landscape:
- Modern model defaults (Qwen3, Llama 4, Claude Sonnet 4)
- Structured output and reasoning support
- Parallel tool execution config
- Token budget management
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


@dataclass
class OllamaConfig:
    host: str = "http://localhost:11434"
    default_model: str = "qwen3:14b"
    code_model: str = "qwen3:14b"
    fast_model: str = "qwen3:8b"
    fallback_model: str = "qwen3:8b"
    vision_model: str = "qwen2.5vl:latest"
    reasoning_model: str = "qwen3:14b"  # For complex multi-step tasks
    timeout: int = 300  # Increased for thinking models
    context_length: int = 40960  # Qwen3 supports 128K natively; keep budget-aware
    structured_output: bool = True  # Use JSON mode for tool calls when supported
    keep_alive: str = "10m"  # Keep warm longer between calls


@dataclass
class OpenRouterConfig:
    enabled: bool = False
    api_key: str = ""
    default_model: str = "anthropic/claude-sonnet-4-5"
    code_model: str = "anthropic/claude-sonnet-4-5"
    fast_model: str = "openai/gpt-5.4-mini"
    fallback_model: str = "openai/gpt-5.4-mini"
    reasoning_model: str = "anthropic/claude-opus-4-7"  # Best available reasoning
    base_url: str = "https://openrouter.ai/api/v1"
    site_url: str = "https://github.com/saladbox"
    app_name: str = "saladbox"


@dataclass
class SlackConfig:
    enabled: bool = False
    bot_token: str = ""
    app_token: str = ""


@dataclass
class TelegramConfig:
    enabled: bool = False
    token: str = ""
    allowed_user_ids: list[int] = field(default_factory=list)


@dataclass
class MCPServerEntry:
    """Configuration for a single MCP server."""

    name: str = ""
    command: str = ""  # e.g. "npx", "uvx", "node", "python3"
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass
class ImageGenConfig:
    """Configuration for image generation."""

    enabled: bool = True
    backend: str = "mflux"  # "mflux" | "drawthings"
    model: str = "schnell"  # "schnell" | "dev"
    quantize: int = 4  # 4 or 8 bit quantization
    default_width: int = 1024
    default_height: int = 1024
    default_steps: int = 2
    drawthings_url: str = "http://localhost:7860"


@dataclass
class HuggingFaceConfig:
    """Configuration for HuggingFace Hub integration."""

    token: str = ""  # HF_TOKEN from env


@dataclass
class WhisperConfig:
    """Configuration for speech-to-text via faster-whisper."""

    enabled: bool = True
    model_size: str = "base"  # "tiny", "base", "small", "medium", "large-v3"
    device: str = "auto"  # "auto", "cpu", "cuda"
    compute_type: str = "int8"  # "int8", "float16", "float32"
    language: str = ""  # empty = auto-detect, or "en", "es", etc.


@dataclass
class SkillsConfig:
    """Configuration for the skills system."""

    enabled: bool = True
    directory: str = ""  # path to skills YAML files (default: <project_root>/skills)


@dataclass
class AgentConfig:
    """Configuration for the agent engine behavior."""

    max_tool_iterations: int = 15  # Increased for complex multi-step tasks
    parallel_tool_calls: bool = True  # Execute independent tool calls concurrently
    enable_reasoning: bool = True  # Use reasoning model for complex tasks
    enable_retry: bool = True  # Retry failed tool calls with adjusted args
    max_retries: int = 2
    language_enforcement: bool = True  # Force English responses (for local models)
    language_enforcement_threshold: float = 0.15  # Non-Latin char ratio threshold
    context_budget_ratio: float = 0.75  # Use up to 75% of context for history
    # Extended / interleaved thinking (Claude Opus 4.7+, Qwen3)
    extended_thinking: bool = True   # Enable thinking for reasoning-tier models
    thinking_budget_tokens: int = 8000  # Max tokens for internal reasoning steps
    qwen3_fast_no_think: bool = True  # Pass /no_think to Qwen3 fast model


@dataclass
class AppConfig:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    image_gen: ImageGenConfig = field(default_factory=ImageGenConfig)
    huggingface: HuggingFaceConfig = field(default_factory=HuggingFaceConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    tools: dict[str, bool] = field(
        default_factory=lambda: {
            "shell": True,
            "python_exec": True,
            "browser": True,
            "filesystem": True,
            "system_monitor": True,
            "scheduler": True,
            "process_manager": True,
            "code_editor": True,
            "screen_capture": True,
        }
    )
    mcp_servers: list[MCPServerEntry] = field(default_factory=list)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    max_tool_iterations: int = 15
    log_level: str = "INFO"


def load_config(config_path: str | None = None) -> AppConfig:
    """Load configuration from YAML file and environment variables."""
    # Load .env file
    project_root = Path(__file__).parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Load YAML config
    if config_path is None:
        config_path = str(project_root / "config.yaml")

    raw: dict = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            raw = yaml.safe_load(f) or {}

    # Build OllamaConfig
    ollama_raw = raw.get("ollama", {})
    ollama = OllamaConfig(
        host=ollama_raw.get("host", OllamaConfig.host),
        default_model=ollama_raw.get("default_model", OllamaConfig.default_model),
        code_model=ollama_raw.get("code_model", OllamaConfig.code_model),
        fast_model=ollama_raw.get("fast_model", OllamaConfig.fast_model),
        fallback_model=ollama_raw.get("fallback_model", OllamaConfig.fallback_model),
        vision_model=ollama_raw.get("vision_model", OllamaConfig.vision_model),
        reasoning_model=ollama_raw.get("reasoning_model", OllamaConfig.reasoning_model),
        timeout=ollama_raw.get("timeout", OllamaConfig.timeout),
        context_length=ollama_raw.get("context_length", OllamaConfig.context_length),
        structured_output=ollama_raw.get(
            "structured_output", OllamaConfig.structured_output
        ),
        keep_alive=ollama_raw.get("keep_alive", OllamaConfig.keep_alive),
    )

    # Build OpenRouterConfig (API key from env)
    openrouter_raw = raw.get("openrouter", {})
    openrouter = OpenRouterConfig(
        enabled=openrouter_raw.get("enabled", False),
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        default_model=openrouter_raw.get(
            "default_model", OpenRouterConfig.default_model
        ),
        code_model=openrouter_raw.get("code_model", OpenRouterConfig.code_model),
        fast_model=openrouter_raw.get("fast_model", OpenRouterConfig.fast_model),
        fallback_model=openrouter_raw.get(
            "fallback_model", OpenRouterConfig.fallback_model
        ),
        reasoning_model=openrouter_raw.get(
            "reasoning_model", OpenRouterConfig.reasoning_model
        ),
        base_url=openrouter_raw.get("base_url", OpenRouterConfig.base_url),
        site_url=openrouter_raw.get("site_url", OpenRouterConfig.site_url),
        app_name=openrouter_raw.get("app_name", OpenRouterConfig.app_name),
    )

    # Build SlackConfig (tokens from env)
    slack_raw = raw.get("slack", {})
    slack = SlackConfig(
        enabled=slack_raw.get("enabled", False),
        bot_token=os.getenv("SLACK_BOT_TOKEN", ""),
        app_token=os.getenv("SLACK_APP_TOKEN", ""),
    )

    # Build TelegramConfig (token from env)
    telegram_raw = raw.get("telegram", {})
    telegram = TelegramConfig(
        enabled=telegram_raw.get("enabled", False),
        token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        allowed_user_ids=telegram_raw.get("allowed_user_ids", []),
    )

    # Tools config
    tools = raw.get("tools", {})
    default_tools = AppConfig().tools
    merged_tools = {**default_tools, **tools}

    # MCP servers config
    mcp_servers: list[MCPServerEntry] = []
    for name, server_raw in (raw.get("mcp_servers") or {}).items():
        if isinstance(server_raw, dict):
            mcp_servers.append(
                MCPServerEntry(
                    name=name,
                    command=server_raw.get("command", ""),
                    args=server_raw.get("args", []),
                    env=server_raw.get("env", {}),
                    enabled=server_raw.get("enabled", True),
                )
            )

    # Skills config
    skills_raw = raw.get("skills", {})
    skills_config = SkillsConfig(
        enabled=skills_raw.get("enabled", True),
        directory=skills_raw.get("directory", ""),
    )

    # Image generation config
    image_gen_raw = raw.get("image_gen", {})
    image_gen_config = ImageGenConfig(
        enabled=image_gen_raw.get("enabled", True),
        backend=image_gen_raw.get("backend", "mflux"),
        model=image_gen_raw.get("model", "schnell"),
        quantize=image_gen_raw.get("quantize", 4),
        default_width=image_gen_raw.get("default_width", 1024),
        default_height=image_gen_raw.get("default_height", 1024),
        default_steps=image_gen_raw.get("default_steps", 2),
        drawthings_url=image_gen_raw.get("drawthings_url", "http://localhost:7860"),
    )

    # HuggingFace config (token from env)
    huggingface_config = HuggingFaceConfig(
        token=os.getenv("HF_TOKEN", ""),
    )

    # Whisper (speech-to-text) config
    whisper_raw = raw.get("whisper", {})
    whisper_config = WhisperConfig(
        enabled=whisper_raw.get("enabled", True),
        model_size=whisper_raw.get("model_size", "base"),
        device=whisper_raw.get("device", "auto"),
        compute_type=whisper_raw.get("compute_type", "int8"),
        language=whisper_raw.get("language", ""),
    )

    # Agent behavior config
    agent_raw = raw.get("agent", {})
    agent_config = AgentConfig(
        max_tool_iterations=agent_raw.get("max_tool_iterations", 15),
        parallel_tool_calls=agent_raw.get("parallel_tool_calls", True),
        enable_reasoning=agent_raw.get("enable_reasoning", True),
        enable_retry=agent_raw.get("enable_retry", True),
        max_retries=agent_raw.get("max_retries", 2),
        language_enforcement=agent_raw.get("language_enforcement", True),
        language_enforcement_threshold=agent_raw.get(
            "language_enforcement_threshold", 0.15
        ),
        context_budget_ratio=agent_raw.get("context_budget_ratio", 0.75),
        extended_thinking=agent_raw.get("extended_thinking", True),
        thinking_budget_tokens=agent_raw.get("thinking_budget_tokens", 8000),
        qwen3_fast_no_think=agent_raw.get("qwen3_fast_no_think", True),
    )

    return AppConfig(
        ollama=ollama,
        openrouter=openrouter,
        slack=slack,
        telegram=telegram,
        image_gen=image_gen_config,
        huggingface=huggingface_config,
        whisper=whisper_config,
        agent=agent_config,
        tools=merged_tools,
        mcp_servers=mcp_servers,
        skills=skills_config,
        max_tool_iterations=raw.get(
            "max_tool_iterations", agent_config.max_tool_iterations
        ),
        log_level=raw.get("log_level", "INFO"),
    )
