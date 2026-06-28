# Saladbox – AI‑Powered Personal Assistant

![Saladbox Logo](media/saladbox_pastel_icon_clean_1778976592244.png)

**Saladbox** is a cross‑platform AI‑assistant that lives on your desktop (via Electron) and can be driven through chat platforms such as Telegram, Slack, or a simple CLI.  It combines a powerful LLM engine, a rich toolbox of native tools, and a flexible scheduling system that lets you orchestrate actions (e.g., open a browser at a specific time, send reminders, run background processes).

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Running the Application](#running-the-application)
  - [Development Mode (Hot‑reload)](#development-mode-hot‑reload)
  - [Production Build](#production-build)
- [Backend‑Only Usage (Headless)](#backend‑only-usage-headless)
- [Tool Set & Examples](#tool-set--examples)
- [Scheduling & Background Jobs](#scheduling--background-jobs)
- [Branding & UI Customisation](#branding--ui-customisation)
- [Contributing](#contributing)
- [License](#license)

---

## Features

- **Multi‑platform UI** – Electron front‑end works on macOS, Linux, and Windows.
- **Chat adapters** – Telegram, Slack, and a CLI adapter (useful for debugging or headless use).
- **Rich toolbox** – Browser automation (Playwright), clipboard, file‑system, image generation, code execution, reminders, scheduling, process manager and many more.
- **Background task orchestration** – Schedule any tool call (e.g. `browser.navigate` or `open_url`) to run later, with optional payloads (`execute_prompt`).
- **Persisted chat history** – SQLite storage with per‑conversation tables.
- **Token‑aware memory** – Keeps the conversation within LLM context limits.
- **Extensible skill system** – Drop‑in Python modules under `saladbox/skills/`.
- **Responsive, modern UI** – Minimalist pastel / dark‑mode ready design with transparent backgrounds.
- **Open‑source friendly** – All code is pure Python/JavaScript, no proprietary services required (Ollama can be swapped with OpenRouter, OpenAI, etc.).

---

## Architecture Overview

```
┌─────────────────────┐      ┌─────────────────────┐
│   Electron Front‑end│      │   Python Backend    │
│  (renderer.js)      │◀────▶│  core/engine.py     │
│  UI + HTTP API      │      │  adapters/…         │
└─────────────────────┘      └─────────────────────┘
          ▲                           ▲
          │ HTTP (localhost:8765)     │
          │                           │
          ▼                           ▼
   HTTPAdapter (core)          Tool Registry
   (saladbox.adapters.http)   (browser, reminder, …)
```

- **Electron** serves a static UI and forwards chat requests to the Python backend over a local HTTP server (`localhost:8765`).
- **Python backend** hosts the **AgentEngine** which drives the LLM, manages memory, registers tools, and orchestrates scheduled jobs via `APScheduler`.
- **Adapters** translate messages from external platforms (Telegram, Slack, CLI) into a unified internal format.
- **Tools** are small self‑contained classes (`BaseTool` subclasses) that expose a JSON schema for the LLM and an `execute` coroutine.
- **Scheduler** (`saladbox/tools/scheduler.py`) stores jobs in SQLite and triggers tool execution at the appropriate time, optionally feeding a prompt back to the engine.

---

## Prerequisites

| Item | Minimum version | Notes |
|------|----------------|-------|
| **Node.js** | 18.x (LTS) | Required for Electron. |
| **npm** | 9.x | Bundles Electron, Vite, etc. |
| **Python** | 3.9+ (3.10 recommended) | Used for the core engine and tools. |
| **pip** | latest | Install Python dependencies. |
| **Playwright browsers** | – | Install via `playwright install` after installing Python deps. |
| **SQLite3** | – | Bundled with Python, used for chat storage and scheduler. |
| **xclip** (Linux only) | – | Clipboard tool fallback – install with `sudo apt install xclip`. |

---

## Installation

```bash
# 1️⃣ Clone the repository
git clone https://github.com/your‑org/saladbox.git
cd saladbox

# 2️⃣ Install Node dependencies (for the Electron UI)
npm install

# 3️⃣ Create a Python virtual environment & install backend deps
python3 -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 4️⃣ Install Playwright browsers (required for the BrowserTool)
playwright install
```

> **Tip:** On Linux, you may need additional system libraries for Playwright. Run `playwright install-deps` to pull them automatically.

---

## Running the Application

### Development Mode (Hot‑reload)

```bash
# In one terminal – start the Python backend (auto‑restarts on code change)
cd saladbox
source .venv/bin/activate
python -m saladbox.app   # or `python -m saladbox` depending on entry‑point

# In another terminal – launch the Electron UI (auto‑restarts on front‑end changes)
npm run dev
```

The UI will open at `http://localhost:8765`.  You can now chat via the UI, Telegram, or the CLI.

### Production Build

```bash
# Build the Electron app for your platform
npm run build   # creates a packaged .app (mac) / .exe (win) / AppImage (linux)
```

The bundled binary includes the Python virtual‑env and starts the backend automatically.

---

## Backend‑Only Usage (Headless)

If you only need the AI engine (e.g., to embed Saladbox in another service), you can run the backend without the Electron UI:

```bash
# Start the HTTP API only (no UI)
cd saladbox
source .venv/bin/activate
python -m saladbox.app --no‑ui   # <-- add a flag if you have implemented it
```

Now you can POST JSON payloads to `http://localhost:8765/chat`:

```json
{
  "conversation_id": "demo",
  "message": "What is the weather in Berlin?",
  "platform": "cli"
}
```

The response will contain the LLM reply and any tool calls that were executed.

---

## Tool Set & Examples

| Tool | Primary Actions | Example Prompt |
|------|----------------|----------------|
| **browser** | `navigate`, `google_search`, `click`, `type`, `fill_form`, `screenshot` | `In 10 seconds, open https://news.ycombinator.com and take a screenshot.` |
| **open_url** | Open a URL or perform a site‑specific search (passive, opens user's default browser) | `Open the latest cat video on YouTube.` |
| **reminder** | `add`, `list`, `remove`, `snooze` (can include `execute_prompt`) | `Remind me to drink water in 5 minutes.` |
| **scheduler** | Create cron‑style or interval jobs that invoke any tool | `Schedule a daily 9 am briefing that runs "browser.google_search" with query "tech news".` |
| **clipboard** | `read`, `write`, `clear` | `Copy the string "Hello world" to the clipboard.` |
| **process_manager** | `start`, `stop`, `output`, `list` | `Start a background process "myserver" with command "python -m http.server 8000".` |

All tools expose a JSON schema, so the LLM knows exactly what arguments are required.  The schema lives in each tool’s `parameters` property.

---

## Scheduling & Background Jobs

The **SchedulerTool** (`saladbox/tools/scheduler.py`) wraps `APScheduler`.  You can schedule a job via a chat command or programmatically:

```json
{
  "action": "schedule",
  "tool": "browser",
  "tool_action": "navigate",
  "value": "https://example.com",
  "run_at": "in 2 minutes"
}
```

If you also provide an `execute_prompt`, the engine will feed that prompt back to the LLM when the timer fires, enabling complex chains (e.g., *"remind me to open the report and then read the first paragraph"*).

---

## Branding & UI Customisation

- **Icons** – Replace `media/saladbox_pastel_icon_clean_*.png` with your own transparent PNGs (max 512 × 512).  The file `saladbox/app.py` automatically picks the best‑resolution icon for the system tray.
- **Colours & Themes** – The CSS lives under `electron/src/styles/`.  Update the HSL colour tokens in `variables.css` to match your brand palette.
- **Dark‑mode support** – The UI uses CSS media queries (`prefers-color-scheme`) so it adapts automatically.
- **Transparent background** – Set `background: transparent;` on the main container if you want a floating‑window look.

---

## Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/awesome‑thing`).
3. Follow the coding style – keep Python type hints, doc‑strings, and Pylint clean.
4. Add or update tests in `tests/`.
5. Submit a Pull Request.

All contributions are welcome – UI tweaks, new tools, performance improvements, or documentation updates.

---

## License

This project is licensed under the **MIT License** – see `LICENSE` for details.

---

Enjoy building with Saladbox! If you run into any issues, feel free to open an issue on GitHub or join the community chat.
