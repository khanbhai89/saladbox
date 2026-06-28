# Saladbox Adapters — Context File

> Adapters are the I/O layer — they receive messages from different platforms (CLI, HTTP/Electron, Slack, Telegram) and forward them to the `AgentEngine`. Each adapter extends `BaseAdapter` and implements `start()` / `stop()`.

---

## `__init__.py`
**Purpose**: Re-exports adapter classes for the `app.py` bootstrapper.

---

## `base.py`  *(78 lines)*
**Purpose**: Abstract base class all adapters extend.

### Class: `BaseAdapter`
**Constructor**: `engine: AgentEngine`, `config: AppConfig`, `chat_store: ChatStore | None`

| Method | Description |
|--------|-------------|
| `start()` | **Abstract.** Begin listening for messages. |
| `stop()` | **Abstract.** Graceful shutdown. |
| `handle_message(text, context, images?, **kwargs) -> str` | Shared pipeline: persists user message to `ChatStore` → calls `engine.process()` → persists assistant response → returns response string. |

**Key contract**: All adapters call `handle_message()` which guarantees message persistence and engine invocation in a unified way.

---

## `cli.py`  *(88 lines)*
**Purpose**: Interactive terminal REPL for local testing.

### Class: `CLIAdapter`
**Conversation ID**: Fixed as `cli:local`, platform `cli`.

| Feature | Detail |
|---------|--------|
| Input loop | `asyncio.run_in_executor` wrapping `input()` for non-blocking async |
| Special commands | `quit`/`exit` → exit, `clear` → reset memory |
| Output formatting | `strip_markdown(text)` removes `**bold**`, `` `code` ``, code fences, bullet markers. `format_response(text)` indents all lines 4 spaces. |

---

## `http.py`  *(997 lines)*
**Purpose**: Full HTTP + WebSocket server for the Electron desktop app. This is the **largest adapter** and acts as the REST API backend.

### Class: `HTTPAdapter`
**Server**: `aiohttp.web.Application` bound to `127.0.0.1:8765`.

### Complete Route Map

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | `/chat` | `handle_chat` | Main chat endpoint. Accepts `{message, images?, conversation_id, user_id, stream?}`. Supports SSE streaming via `stream: true`. |
| GET | `/ws` | `handle_websocket` | WebSocket real-time chat. Messages: `init` (set conv ID), `chat` (send message, receive chunks), `clear` (reset). |
| GET | `/health` | `handle_health` | Returns `{status: "ok", version}` |
| GET | `/models` | `handle_models` | Returns Ollama + OpenRouter model configs |
| POST | `/models/set` | `handle_set_model` | Updates model config in-memory: `{provider, type, model}` |
| GET | `/tools` | `handle_tools` | Lists all tools with enabled status |
| GET | `/config` | `handle_config` | Returns non-sensitive config (log level, iterations, platform status) |
| GET | `/mcp/servers` | `handle_mcp_servers` | Lists MCP servers (masks API keys/tokens with `***`) |
| POST | `/mcp/add` | `handle_mcp_add` | Adds MCP server: persists to `config.yaml`, restarts MCP manager |
| POST | `/mcp/remove` | `handle_mcp_remove` | Removes MCP server by name |
| POST | `/mcp/toggle` | `handle_mcp_toggle` | Enables/disables MCP server by name |
| GET | `/setup/status` | `handle_setup_status` | Returns setup wizard state (Ollama availability, installed models, env vars) |
| POST | `/setup/run` | `handle_setup_run` | Applies setup config from Electron wizard (writes `config.yaml` + `.env`) |
| GET | `/notifications/poll` | `handle_notifications_poll` | Returns and clears queued notification messages |
| POST | `/api/transcribe` | `handle_transcribe` | Accepts base64 WebM audio, transcribes via `WhisperService`, returns text |
| GET | `/api/whisper/config` | `handle_whisper_config` | Returns Whisper model configuration |
| GET | `/image-gen/config` | `handle_image_gen_config` | Returns image generation settings |
| POST | `/image-gen/update` | `handle_image_gen_update` | Updates image gen config (backend, model, quantize, resolution, steps) |
| POST | `/hf/token` | `handle_hf_token_save` | Saves HuggingFace token to `.env` and runtime |
| GET | `/hf/status` | `handle_hf_status` | Returns HF token status and checks validity via API |
| GET | `/screenshots/{filename}` | `handle_screenshot` | Serves screenshot PNG files from temp directory |
| GET | `/generated/{filename}` | `handle_generated_image` | Serves generated image files from temp directory |
| GET | `/dashboard` | `handle_dashboard_page` | Serves dashboard HTML |
| GET | `/dashboard.css` | `handle_dashboard_css` | Serves dashboard CSS |
| GET | `/dashboard.js` | `handle_dashboard_js` | Serves dashboard JS |
| GET | `/api/dashboard/stats` | `handle_dashboard_stats` | Returns `ChatStore.get_stats()` for dashboard |
| GET | `/api/dashboard/conversations` | `handle_dashboard_conversations` | Lists conversations with pagination |
| GET | `/api/dashboard/messages` | `handle_dashboard_messages` | Returns messages for a conversation |
| GET | `/api/dashboard/search` | `handle_dashboard_search` | Full-text search across messages |
| POST | `/api/conversations/{id}/delete` | `handle_conversation_delete` | Deletes conversation + messages |

### WebSocket Protocol
```jsonc
// Client → Server
{"type": "init", "conversation_id": "abc", "user_id": "user1"}
{"type": "chat", "message": "hello", "images": []}
{"type": "clear"}

// Server → Client
{"type": "ready", "conversation_id": "abc"}
{"type": "chunk", "chunk": "partial text"}
{"type": "done", "message": "full response"}
{"type": "notification", "message": "reminder text"}
{"type": "error", "error": "message"}
```

### Internal State
* `websocket_clients: list[WebSocketResponse]` — Active WS connections
* `_notification_queue: list[dict]` — Queued notifications, capped at 500
* `_whisper: WhisperService | None` — Lazy-loaded Whisper for voice transcription

### CORS
All responses include `Access-Control-Allow-Origin: *` via middleware.

---

## `slack.py`  *(~100 lines)*
**Purpose**: Slack bot using Socket Mode (real-time via App Token).

### Class: `SlackAdapter`
**Dependencies**: `slack_bolt.async_app.AsyncApp`, `slack_bolt.adapter.socket_mode.aiohttp.AsyncSocketModeHandler`.

| Feature | Detail |
|---------|--------|
| Events | Listens for `message` events and `app_mention` events |
| Context | `conversation_id = "slack:{channel}:{user}"` |
| Responses | Replies in-thread using `say(text, thread_ts)` |
| Message filtering | Ignores bot messages, empty messages, and messages with subtypes |

---

## `telegram.py`  *(~400 lines)*
**Purpose**: Telegram bot using long polling.

### Class: `TelegramAdapter`
**Dependencies**: `python-telegram-bot` (v20+ async API).

| Feature | Detail |
|---------|--------|
| Allowed users | Optional whitelist via `allowed_user_ids` config |
| Image support | Downloads Telegram photos, saves to temp dir, passes as `images` list to engine |
| Commands | `/start` (welcome), `/clear` (reset conversation), `/help` (skill list) |
| Voice messages | Downloads voice/audio messages, transcribes via `WhisperService` if available |
| Typing indicator | Sends `ChatAction.TYPING` while processing |
| Long messages | Auto-splits responses >4096 chars into multiple messages |
| Context | `conversation_id = "telegram:{chat_id}"` |
| Error handling | Sends user-friendly error message on failure |
