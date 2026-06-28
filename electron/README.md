# Electron Frontend — Context File

> This directory contains the Electron-based multi-window desktop interface for the Saladbox personal assistant. It communicates with the Python backend over HTTP (`127.0.0.1:8765`).

---

## Architecture

Electron runs in a multi-process architecture:
1. **Main Process (`main.js`)**: Node.js — manages app lifecycle, spawns Python backend subprocess, handles system tray, defines IPC listeners that proxy to the HTTP API.
2. **Preload Script (`preload.js`)**: Sandboxed bridge — exposes `window.saladbox` API using `contextBridge`.
3. **Renderer Process (`renderer.js` / `dashboard.js`)**: Standard web apps loaded in BrowserWindow.

---

## `main.js`  *(706 lines)*
**Purpose**: Electron main process — application lifecycle, Python backend management, IPC routing, system tray, global shortcuts.

### Python Backend Management
| Function | What it does |
|----------|--------------|
| `getPythonPath()` | Returns venv Python in dev mode (`../.venv/bin/python`), or bundled Python in production (`process.resourcesPath/python/bin/python`) |
| `getSaladboxPath()` | Returns project root in dev (`../`), or resources path in production |
| `startPythonBackend()` | Spawns `python -m saladbox --http --port 8765` as child process. Pipes stdout/stderr. Polls `/health` endpoint every 500ms up to 30 attempts. |
| `stopPythonBackend()` | Kills the Python child process |
| `checkServerReady(maxAttempts=30)` | HTTP GET `/health` with 1s timeout, retries every 500ms |

### Window Management
| Function | What it does |
|----------|--------------|
| `createWindow()` | Creates 1000×700 BrowserWindow with `contextIsolation: true`, loads `index.html`. External links open in default browser. On macOS, close button hides window instead of quitting. |
| `createTray()` | System tray with icon. Context menu: Show, New Chat, Settings, Quit. |

### Global Shortcuts
* `CmdOrCtrl+Shift+S` — Show/focus the main window

### IPC Handlers (ipcMain.handle)
All IPC handlers proxy to the Python HTTP API:

| IPC Channel | HTTP Request | Description |
|------------|-------------|-------------|
| `api:chat` | `POST /chat` | Send message with optional images, conversation ID |
| `api:models` | `GET /models` | Get model configuration |
| `api:tools` | `GET /tools` | List tools |
| `api:config` | `GET /config` | Get non-sensitive config |
| `api:ollama-models` | `GET http://localhost:11434/api/tags` | Direct to Ollama API |
| `api:openrouter-models` | `GET https://openrouter.ai/api/v1/models` | Direct to OpenRouter API |
| `api:mcp-servers` | `GET /mcp/servers` | List MCP servers |
| `api:mcp-add` | `POST /mcp/add` | Add MCP server |
| `api:mcp-remove` | `POST /mcp/remove` | Remove MCP server |
| `api:mcp-toggle` | `POST /mcp/toggle` | Toggle MCP server |
| `api:setup-status` | `GET /setup/status` | Setup wizard state |
| `api:setup-run` | `POST /setup/run` | Run setup |
| `api:image-gen-config` | `GET /image-gen/config` | Image gen settings |
| `api:image-gen-update` | `POST /image-gen/update` | Update image gen |
| `api:hf-token` | `POST /hf/token` | Save HuggingFace token |
| `api:hf-status` | `GET /hf/status` | HF token status |
| `api:notifications-poll` | `GET /notifications/poll` | Poll notifications |
| `api:conversations` | `GET /api/dashboard/conversations` | List conversations |
| `api:conversation` | `GET /api/dashboard/messages` | Get conversation messages |
| `api:conversation-delete` | `POST /api/conversations/{id}/delete` | Delete conversation |
| `dialog:open-file` | - | Native file picker dialog |
| `dialog:open-folder` | - | Native folder picker dialog |
| `app:get-version` | - | Returns Electron app version |
| `app:quit` | - | Quit application |
| `app:open-external` | - | Opens URL in system browser |

### Helper: `apiRequest(path, method, body)`
Wraps Node.js `http.request` for JSON API calls to the Python backend. Returns parsed JSON response.

---

## `preload.js`  *(55 lines)*
**Purpose**: Secure bridge between renderer and main process using `contextBridge.exposeInMainWorld('saladbox', {...})`.

**Exposed methods**: All IPC channels above are exposed as promise-returning functions on `window.saladbox`.

**Event listeners**:
* `onNewChat(callback)` — Listens for `new-chat` event from tray menu
* `onOpenSettings(callback)` — Listens for `open-settings` event from tray menu

**Navigation helpers**:
* `openChat()` — Navigate to `index.html`
* `openDashboard()` — Navigate to `dashboard.html`

---

## `index.html`  *(~40KB)*
**Purpose**: Main chat interface HTML.

Features:
* Markdown rendering with syntax highlighting
* Code block copy buttons
* Message input with file/image attachment support
* Voice recording UI (base64 WebM → backend transcription)
* Settings modal (model selection, tool toggles, MCP config)
* Conversation sidebar (history, search)
* Setup wizard overlay for first-run

---

## `renderer.js`  *(78KB, ~2000+ lines)*
**Purpose**: Chat UI logic — the largest file in the Electron app.

Key responsibilities:
* **Message rendering**: Markdown parsing, code syntax highlighting, image embedding
* **Chat management**: Send messages via `window.saladbox.chat()`, render streaming chunks
* **Conversation history**: Load/switch/delete conversations via sidebar
* **Settings panels**: Model switcher, tool toggles, MCP server management
* **Voice input**: MediaRecorder → base64 WebM → POST to `/api/transcribe`
* **File attachments**: File picker → read as base64 → send as images
* **Notification polling**: Periodic poll of `/notifications/poll` (every 10s)
* **Keyboard shortcuts**: Enter to send, Shift+Enter for newline
* **Auto-scroll**: Scroll to bottom on new messages
* **Image display**: Renders `![](...)` markdown images, screenshots from `/screenshots/` path

---

## `styles.css`  *(~56KB)*
**Purpose**: Complete CSS for the chat interface.

Design tokens:
* Dark theme with CSS custom properties
* Glassmorphism effects (backdrop-filter)
* Smooth animations and transitions
* Responsive layout
* Code block styling with language badges
* Message bubbles with role-based coloring

---

## `dashboard.html`  *(~10KB)*
**Purpose**: Dashboard/admin HTML layout.

Sections: Stats cards, conversation list, message viewer, settings panels.

---

## `dashboard.js`  *(~16KB)*
**Purpose**: Dashboard logic.

Key features:
* **Stats display**: Total conversations, messages, messages-per-day chart
* **Conversation browser**: Paginated list with search
* **Message viewer**: View individual conversation messages
* **Settings management**: Same settings panels as chat interface

---

## `dashboard.css`  *(~19KB)*
**Purpose**: Dashboard-specific styling.

---

## `banner.js`  *(~3KB)*
**Purpose**: Terminal banner and styled logging for the main process startup sequence.

Functions: `printBanner()`, `printSection(title)`, `printStatus(label, value, type)`.

---

## `setup.js`  *(~3KB)*
**Purpose**: Setup wizard integration for the Electron app.

---

## `package.json`
**Dependencies**: `electron` (main), plus build tooling.

**Scripts**:
* `start` — `electron .`
* `dev` — `electron . --dev`
* `build` — `electron-builder` for production builds

---

## `assets/`
Contains app icons: `icon.png`, `trayTemplate.png`, `icon.icns` (macOS), `icon.ico` (Windows).
