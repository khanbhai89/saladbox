# Saladbox Core — Context File

> This directory is the brain of the application. It contains the agent loop, LLM providers, memory management, tool orchestration, MCP integration, skill system, and speech services.

---

## `__init__.py`
**Purpose**: Re-exports all shared types from `types.py` so consumers can write `from saladbox.core import Message, Role`.

**Exports**: `ConversationContext`, `Message`, `Role`, `TaskType`, `TokenUsage`, `ToolCall`, `ToolCategory`, `ToolResult`.

---

## `types.py`  *(100 lines)*
**Purpose**: Central type definitions used across the entire codebase.

### Enums
| Enum | Values | Usage |
|------|--------|-------|
| `Role` (StrEnum) | `user`, `assistant`, `system`, `tool` | Message role in conversation history |
| `TaskType` (StrEnum) | `fast`, `default`, `code`, `vision`, `reasoning` | Model tier selection |
| `ToolCategory` (StrEnum) | `system`, `files`, `code`, `web`, `media`, `utility`, `data` | Tool grouping for filtering/display |

### Dataclasses (all use `slots=True`)
| Class | Fields | Usage |
|-------|--------|-------|
| `ToolCall` | `id: str`, `name: str`, `arguments: dict` | LLM-requested tool invocation |
| `ToolResult` | `tool_call_id`, `name`, `content: str`, `is_error: bool`, `duration_ms: float` | Return value after tool execution |
| `TokenUsage` | `prompt_tokens`, `completion_tokens`, `total_tokens` | Per-call token tracking |
| `Message` | `role: Role`, `content: str`, `images: list[str]`, `tool_calls: list[ToolCall]`, `tool_name`, `tool_call_id`, `metadata: dict`, `usage: TokenUsage` | Single conversation message |
| `ConversationContext` | `conversation_id: str`, `user_id: str`, `channel_id`, `platform: str` | Request origin metadata |

### Type Aliases
* `ToolSchemaList = list[dict[str, Any]]`
* `MessageList = list[Message]`

---

## `engine.py`  *(761 lines)*
**Purpose**: The core agent loop — receives user input, calls the LLM, executes tools, and returns final text.

### Class: `AgentEngine`
**Constructor args**: `llm: BaseLLMClient`, `memory: ConversationMemory`, `tools: ToolRegistry`, `config: AppConfig`, `skill_manager: SkillManager | None`

**Internal state**:
* `_tool_filter: ToolFilter` — Filters tools per query (default cap: 14)
* `_recent_tool_calls: set[str]` — Prevents infinite duplicate tool loops
* `_compact_mode: bool` — `True` when `context_length <= 8192` (uses shorter system prompts)

### Key Methods

| Method | Signature | What it does |
|--------|-----------|--------------|
| `process()` | `async (user_input, context, images?, on_chunk?) -> str` | **Main entry point.** Runs the full agent loop: skill match → classify task → select model → LLM chat → tool execution → language enforcement → return text. |
| `_classify_task()` | `(user_input) -> "fast"\|"default"\|"code"\|"reasoning"` | Pattern-matches user text against regex sets: `_CHAT_PATTERNS` → fast, `_CODE_PATTERNS` → code, `_REASONING_PATTERNS` → reasoning. |
| `_build_system_prompt()` | `(skill_prompt?) -> str` | Builds system prompt from `SYSTEM_PROMPT_TEMPLATE` or `SYSTEM_PROMPT_COMPACT`, injecting tool names and skill help text. |
| `_execute_tools_parallel()` | `async (tool_calls, task_type) -> list[tuple]` | If `parallel_tool_calls` is enabled and multiple calls exist, wraps them in `asyncio.gather`. Catches per-tool exceptions. |
| `_try_parse_text_tool_call()` | `(content) -> tuple[str, dict] \| None` | Recovery: when LLM outputs a tool call as raw JSON text instead of structured function call, parses and recovers it. |
| `_compress_tool_result()` | `(content, task_type) -> str` | Truncates tool output. Limits: fast=800, default=2000, code/reasoning=3000 chars. Multiplied ×1.5 when not in compact mode. |

### Agent Loop Flow (inside `process()`)
1. Check skill match (slash commands / keyword triggers).
2. Add user message to `ConversationMemory`.
3. Classify task type → select model via `LLM.select_model()`.
4. Filter tool schemas down from 35+ to ~14 relevant ones.
5. **While iterations < max (15)**:
   - Send history + tool schemas to LLM.
   - If LLM returns tool calls → deduplicate → execute (parallel or sequential) → compress results → add to memory → loop.
   - If LLM returns text → check for embedded JSON tool calls (recovery) → check language → return.
6. Special escalation paths:
   - `screen_capture` result → switches to vision model, sends screenshot as image.
   - `code_editor` usage → escalates to code model.
   - `image_gen` result → prepends `![Generated](url)` markdown to response.

### Constants
* `_SCREENSHOT_DIR`, `_GENERATED_IMAGE_DIR` — Temp directories for media files.
* `_DEFAULT_MAX_TOOLS = 14` — Default tool filter cap.
* `_MAX_LANGUAGE_RETRIES = 2` — Retry count for English enforcement.
* `_RESULT_LIMITS` — `{"fast": 800, "default": 2000, "code": 3000, "reasoning": 3000}`.

---

## `llm.py`  *(503 lines)*
**Purpose**: Provides two LLM client implementations behind a common abstract interface.

### Abstract Class: `BaseLLMClient`
| Method | Returns | Description |
|--------|---------|-------------|
| `chat(messages, model?, tools?, json_mode?, thinking?, thinking_budget?)` | `Message` | Send conversation + optional tools, get response |
| `stream(messages, model?)` | `AsyncIterator[str]` | Token-by-token streaming (no tool calling) |
| `select_model(task_type)` | `str` | Map task type to model name string |

### Class: `OllamaClient` *(extends BaseLLMClient)*
* Wraps `ollama.AsyncClient` for local model inference.
* **Retry**: 3 attempts with exponential backoff on `ConnectionError`/`TimeoutError`.
* **Fallback**: If primary model fails, automatically retries with `fallback_model`.
* **Qwen3 `/no_think`**: For fast-tier queries, appends `/no_think` to the system prompt to disable chain-of-thought overhead. Controlled by `agent.qwen3_fast_no_think` config.
* **`<think>` stripping**: Strips `<think>...</think>` tags from reasoning model output using regex.
* **Token tracking**: Reads `eval_count` and `prompt_eval_count` from Ollama response.
* **Image handling**: Reads local file paths, converts to base64, and sends as `images` array.

### Class: `OpenRouterClient` *(extends BaseLLMClient)*
* Wraps `openai.AsyncOpenAI` pointed at `https://openrouter.ai/api/v1`.
* **Extended thinking**: For Claude Opus 4.7+ and Sonnet 4.5+ models, passes `extra_body.thinking.budget_tokens` (capped at 16K).
* **Parallel tool calls**: Sets `parallel_tool_calls=True` in API request.
* **Token tracking**: Reads `response.usage` including `completion_tokens_details.reasoning_tokens`.

### Factory Function
```python
def create_llm_client(ollama_config, openrouter_config, agent_config?) -> BaseLLMClient
```
Returns `OpenRouterClient` if OpenRouter is enabled and has an API key, otherwise `OllamaClient`.

---

## `memory.py`  *(141 lines)*
**Purpose**: Per-conversation message buffer with token-aware sliding window.

### Class: `ConversationMemory`
**Constructor**: `max_messages: int = 80`, `max_tokens: int = 24000`

| Method | What it does |
|--------|--------------|
| `get(conversation_id) -> list[Message]` | Returns full history copy |
| `add(conversation_id, message)` | Appends message, then trims if over limits |
| `update_system(conversation_id, content)` | Replaces content of the system prompt (index 0) |
| `pop_last(conversation_id) -> Message\|None` | Removes last message (used for language retry). Never removes system prompt. |
| `clear(conversation_id)` | Deletes entire conversation |
| `get_token_estimate(conversation_id) -> int` | Estimates tokens using `chars / 3.5` |

**Trimming rules**:
1. If message count > `max_messages` (80): keep system prompt (index 0) + last 79 messages.
2. If token estimate > `max_tokens`: iteratively pop the second message (preserving system prompt at index 0 and the most recent 3 messages).

**Individual message cap**: `_MAX_MESSAGE_CHARS = 100,000` — truncates any single message exceeding this.

---

## `tool_filter.py`  *(894 lines)*
**Purpose**: Semantic tool filtering to avoid sending all 35+ tool schemas to the LLM.

### Class: `ToolFilter`
**Constructor**: `max_tools: int = 14`

| Method | What it does |
|--------|--------------|
| `score_relevance(query, tool_name) -> float` | Scores a tool using keyword matching (primary ×3, secondary ×1) and regex pattern matching (×5). Each score is multiplied by a per-tool `weight`. |
| `get_relevant_tools(query, all_tools, min_tools=6, task_type="default") -> list[dict]` | Returns top scoring tools. For `reasoning` task type, cap is raised by 4. Always includes essential tools (`run_shell`, `filesystem`, `web_search`, `open_url`). |
| `get_best_tool(query, all_tools) -> tuple[str, dict]\|None` | Returns the single highest-scoring tool + default args (used as fallback when LLM doesn't call any tool on first iteration). |

### Data structures
* `TOOL_KEYWORDS` — Dict mapping each tool name to `{primary: [...], secondary: [...], weight: float}`. Used for substring keyword matching.
* `RECOGNITION_PATTERNS` — Dict mapping tool names to lists of regex patterns for more precise matching.

### Tool weights (notable)
* `open_url`: 3.0 (highest), `browser`: 2.5, `image_gen`: 2.5, `screen_capture`: 2.5, `reminder`: 2.0

---

## `tool_registry.py`  *(516 lines)*
**Purpose**: Central registry mapping tool names to `BaseTool` instances, generating schemas, normalizing arguments, and executing tools.

### Class: `ToolRegistry`
| Method | What it does |
|--------|--------------|
| `register(tool)` | Adds a tool by name |
| `get(name) -> BaseTool\|None` | Lookup by name |
| `tool_names -> list[str]` | All registered names |
| `get_schemas(compact?, strict?) -> list[dict]` | Generates JSON schemas for all tools. `strict=True` adds `additionalProperties: false`. |
| `is_mcp_tool(name) -> bool` | Checks if tool is an `MCPTool` instance |
| `execute(name, arguments) -> ToolResult` | Normalizes args → calls `tool.execute(**kwargs)` → returns `ToolResult` with timing |

### Function: `_normalize_arguments(tool_name, arguments) -> dict`
Massive switch-case (by tool name) that coerces and filters LLM-provided arguments:
* Coerces integers with min/max bounds (e.g., `timeout` clamped 1–600).
* Normalizes commands from list→string.
* Maps alternate argument names (e.g., `url` → `value` for browser navigate).
* Strips unknown keys so only expected kwargs reach `execute()`.

---

## `chat_store.py`  *(342 lines)*
**Purpose**: Thread-safe SQLite persistence for all conversations and messages.

### Class: `ChatStore`
**Database path**: `data/chats.db` (relative to project root).
**SQLite pragmas**: `journal_mode=WAL`, `foreign_keys=ON`.

### Schema
```sql
conversations(id TEXT PK, platform TEXT, user_id, channel_id, title, created_at, updated_at, metadata JSON)
messages(id TEXT PK, conversation_id FK, role TEXT, content TEXT, platform, user_id, tool_name, tool_call_id, metadata JSON, created_at)
```
**Indexes**: `messages.conversation_id`, `messages.created_at`, `conversations.platform`, `conversations.updated_at`.

| Method | What it does |
|--------|--------------|
| `save_message(...)` | Upserts conversation, inserts message, auto-generates title from first user message (first 80 chars). Thread-safe via `threading.Lock`. |
| `delete_conversation(id)` | Cascading delete of messages + conversation row |
| `get_conversations(platform?, limit, offset)` | Lists conversations with message counts and last user/assistant messages |
| `get_messages(conversation_id, limit, offset)` | Ordered message list |
| `search_messages(query, platform?, limit)` | `LIKE %query%` search across all messages |
| `get_stats()` | Returns: total conversations, total messages, per-platform breakdown, messages-per-day (30 days), role breakdown, recent activity (7 days), avg messages per conversation |

---

## `mcp_client.py`  *(453 lines)*
**Purpose**: Model Context Protocol client — starts external tool servers as subprocesses and communicates via JSON-RPC 2.0 over stdio.

### Class: `MCPServerConnection`
Manages a single MCP server subprocess lifecycle.

| Method | What it does |
|--------|--------------|
| `start()` | Spawns subprocess, starts stdout reader task, performs `initialize` handshake + `notifications/initialized` notification |
| `stop()` | Terminates process (SIGTERM → wait 5s → SIGKILL), cancels pending futures |
| `list_tools() -> list[dict]` | Sends `tools/list` request, caches raw tool definitions |
| `call_tool(name, args) -> str` | Sends `tools/call` request (120s timeout), parses MCP content blocks (text, image, resource) into a single string |

**I/O**: Messages are newline-delimited JSON. Responses are matched by `id` field to pending `asyncio.Future` objects.

### Class: `MCPTool` *(extends BaseTool)*
Wraps an MCP-discovered tool to look like a native Saladbox tool. `execute(**kwargs)` forwards to `MCPServerConnection.call_tool()`.

### Class: `MCPManager`
| Method | What it does |
|--------|--------------|
| `start_servers(configs)` | Starts all enabled servers concurrently via `asyncio.gather`, discovers tools, creates `MCPTool` wrappers. Handles name conflicts with server prefix. |
| `stop_all()` | Stops all servers, clears tool list |
| `tools -> list[MCPTool]` | All discovered MCP tools |

---

## `skills.py`  *(217 lines)*
**Purpose**: Loads reusable prompt-workflow templates from YAML files and matches them against user input.

### Class: `Skill`
Fields: `name`, `description`, `prompt` (system prompt injection), `model` (tier override), `slash_command` (e.g., `/review`), `triggers` (keyword list), `tools_required`.

Matching priority: slash command exact prefix → keyword regex.

### Class: `SkillManager`
| Method | What it does |
|--------|--------------|
| `load_skills(dir)` | Scans `*.yaml` and `*.yml` files, parses each into a `Skill` |
| `match(user_input) -> SkillMatch\|None` | Slash commands checked first, then keyword triggers |
| `get_help_text() -> str` | Formatted list of all skills for system prompt injection |

### YAML skill file format
```yaml
name: review
description: "Code review workflow"
prompt: "You are a code reviewer. Analyze the code..."
model: code
slash_command: /review
triggers: ["review this code", "code review"]
tools_required: [code_editor, git]
```

---

## `whisper_service.py`  *(114 lines)*
**Purpose**: Local speech-to-text using `faster-whisper` (CTranslate2).

### Class: `WhisperService`
**Lazy loading**: The model is only loaded on the first transcription request (~150 MB+ RAM).

| Method | What it does |
|--------|--------------|
| `transcribe_base64_webm(audio_base64) -> str` | Decodes base64 → converts WebM to mono 16kHz WAV via `pydub` (requires ffmpeg) → runs `faster-whisper` transcription → returns text. Cleans up temp files. |
| `_ensure_model()` | Loads `WhisperModel(model_size, device, compute_type)` on first call |

**Config options**: `model_size` (tiny/base/small/medium/large-v3), `device` (auto/cpu/cuda), `compute_type` (int8/float16/float32), `language` (auto-detect or specific).
