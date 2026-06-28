# Saladbox Package — Top-Level Context File

> `saladbox` is the Python backend of the application. It provides the AI agent engine, tools, LLM integrations, and messaging adapters. Version: **0.3.0**.

---

## `__init__.py`  *(4 lines)*
**Purpose**: Package declaration and version constant.  
**Exports**: `__version__ = "0.3.0"`

---

## `__main__.py`  *(67 lines)*
**Purpose**: Entry point for `python -m saladbox`.

### CLI Arguments
| Flag | Description |
|------|-------------|
| `--setup` | Run interactive setup wizard |
| `--version` | Print version and exit |
| `--http` | Start HTTP API server (for Electron) |
| `--port N` | HTTP server port (default: 8765) |

### Startup Flow
1. Parse args.
2. Call `maybe_run_setup()` — prompts setup wizard if `.env` is missing or has no API keys.
3. `load_config()` — loads `config.yaml` + `.env` → `AppConfig`.
4. Configure `logging.basicConfig()` with level from config.
5. Create `Application(config, http_mode, port)`.
6. `asyncio.run(app.run())`.

---

## `config.py`  *(323 lines)*
**Purpose**: Configuration loader — merges `config.yaml` with `.env` secrets.

### Dataclass Hierarchy

| Config Class | Key Fields | Source |
|-------------|------------|--------|
| `OllamaConfig` | `host`, `default_model` (qwen3:14b), `code_model`, `fast_model` (qwen3:8b), `fallback_model`, `vision_model` (qwen2.5vl), `reasoning_model`, `timeout` (300s), `context_length` (40960), `structured_output`, `keep_alive` (10m) | `config.yaml → ollama` |
| `OpenRouterConfig` | `enabled`, `api_key` (from env), `default_model` (claude-sonnet-4-5), `code_model`, `fast_model` (gpt-5.4-mini), `reasoning_model` (claude-opus-4-7), `base_url` | `config.yaml → openrouter` + `OPENROUTER_API_KEY` |
| `SlackConfig` | `enabled`, `bot_token`, `app_token` | `.env` vars |
| `TelegramConfig` | `enabled`, `token`, `allowed_user_ids` | `.env` vars |
| `MCPServerEntry` | `name`, `command`, `args`, `env`, `enabled` | `config.yaml → mcp_servers` |
| `ImageGenConfig` | `enabled`, `backend` (mflux), `model` (schnell), `quantize` (4), `default_width/height` (1024), `default_steps` (2) | `config.yaml → image_gen` |
| `HuggingFaceConfig` | `token` | `HF_TOKEN` env |
| `WhisperConfig` | `enabled`, `model_size` (base), `device` (auto), `compute_type` (int8), `language` | `config.yaml → whisper` |
| `SkillsConfig` | `enabled`, `directory` | `config.yaml → skills` |
| `AgentConfig` | `max_tool_iterations` (15), `parallel_tool_calls`, `enable_reasoning`, `enable_retry`, `max_retries` (2), `language_enforcement`, `context_budget_ratio` (0.75), `extended_thinking`, `thinking_budget_tokens` (8000), `qwen3_fast_no_think` | `config.yaml → agent` |
| `AppConfig` | Aggregates all above + `tools: dict[str, bool]`, `mcp_servers`, `log_level` | Top-level |

### `load_config(config_path?) -> AppConfig`
1. Loads `.env` via `python-dotenv`.
2. Reads `config.yaml` via `pyyaml`.
3. Builds each sub-config from YAML keys, using defaults for missing values.
4. API keys always come from env vars (never from YAML).
5. Tools config: merges YAML overrides onto defaults (all major tools enabled by default).
6. MCP servers: parsed from `config.yaml → mcp_servers` dict.

---

## `app.py`  *(315 lines)*
**Purpose**: Application orchestrator — wires all components and manages the full lifecycle.

### Class: `Application`
**Constructor**: `config: AppConfig`, `http_mode: bool`, `http_port: int`

Creates all subsystems:
* `llm` — via `create_llm_client()`
* `memory` — `ConversationMemory(80 msgs, max_tokens = context_length × budget_ratio)`
* `tools` — `ToolRegistry`
* `mcp_manager` — `MCPManager`
* `skill_manager` — `SkillManager`
* `chat_store` — `ChatStore` (SQLite)
* `engine` — `AgentEngine(llm, memory, tools, config, skills)`

### `setup()` Method
1. **Register native tools**: `get_enabled_tools(config.tools)` → `registry.register_tools()`
2. **Load skills**: From `skills/` directory YAML files
3. **Create adapters** based on mode:
   - HTTP mode → `HTTPAdapter` (+ Slack/Telegram if enabled)
   - No HTTP → Slack/Telegram if enabled
   - Fallback → `CLIAdapter`
4. **Wire reminder notifications**: Connects `ReminderTool` callback to notification-capable adapters (HTTP, Telegram). Supports "execute prompt" reminders (background agent task).
5. **Configure image gen**: Applies `ImageGenConfig` to `ImageGenTool.configure()`.

### `run()` Method (async)
1. Calls `setup()`
2. Starts MCP servers (async subprocess spawning)
3. Registers `SIGINT`/`SIGTERM` handlers → sets `stop_event`
4. Starts all adapters as `asyncio.Task`s
5. **Wait behavior**:
   - Non-HTTP: waits for stop_event OR any adapter to finish (CLI exits on user command)
   - HTTP: waits for stop_event only; adapter crashes are caught via done callbacks
6. **Shutdown sequence**: Stop MCP → stop adapters → cancel tasks → close chat store

---

## `setup_wizard.py`  *(424 lines)*
**Purpose**: Interactive first-run configuration wizard (CLI-based).

### `run_setup(project_root) -> bool`
4-step wizard:
1. **LLM Provider**: Ollama (local), OpenRouter (cloud), or Both. Auto-detects Ollama availability. Prompts for model selection.
2. **Messaging Platforms**: Optional Telegram and Slack bot configuration.
3. **Tools**: Per-tool enable/disable (shell, python, browser, filesystem, etc.)
4. **MCP Servers**: Optional MCP server configuration (name, command, args, env vars).

Writes `config.yaml` (YAML) and `.env` (environment secrets). Deep-merges with existing files.

### `maybe_run_setup(project_root) -> bool`
Checks if `.env` exists and contains at least one API key. If not, prompts user to run setup wizard.

---

## Sub-Packages

| Package | README | Description |
|---------|--------|-------------|
| `saladbox/core/` | [README.md](core/README.md) | Engine, LLM clients, memory, tool registry, MCP, skills, whisper, types |
| `saladbox/tools/` | [README.md](tools/README.md) | 33 built-in tools (shell, code editor, browser, web search, etc.) |
| `saladbox/adapters/` | [README.md](adapters/README.md) | CLI, HTTP/WebSocket, Slack, Telegram adapters |
| `saladbox/platform/` | [README.md](platform/README.md) | Shared utilities: HTTP client, output formatting, NLP parsing |
