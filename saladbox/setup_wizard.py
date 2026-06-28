"""First-run setup wizard for saladbox configuration (v0.2)."""

from __future__ import annotations

import os
from pathlib import Path


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def print_header():
    clear_screen()
    print("=" * 60)
    print("  SALADBOX SETUP WIZARD")
    print("=" * 60)
    print()


def prompt(prompt_text: str, default: str = "") -> str:
    if default:
        result = input(f"{prompt_text} [{default}]: ").strip()
        return result if result else default
    return input(f"{prompt_text}: ").strip()


def prompt_yes_no(prompt_text: str, default: bool = False) -> bool:
    default_str = "Y/n" if default else "y/N"
    result = input(f"{prompt_text} [{default_str}]: ").strip().lower()
    if not result:
        return default
    return result in ("y", "yes", "true", "1")


def prompt_choice(prompt_text: str, choices: list[str], default: int = 0) -> int:
    print(f"\n{prompt_text}")
    for i, choice in enumerate(choices):
        marker = ">" if i == default else " "
        print(f"  {marker} {i + 1}. {choice}")

    while True:
        result = input(f"Select [1-{len(choices)}] (default {default + 1}): ").strip()
        if not result:
            return default
        try:
            idx = int(result) - 1
            if 0 <= idx < len(choices):
                return idx
        except ValueError:
            pass
        print("Invalid choice, try again.")


def check_ollama() -> bool:
    import subprocess

    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_ollama_models() -> list[str]:
    import subprocess

    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")[1:]
            models = [line.split()[0] for line in lines if line.strip()]
            return models
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def run_setup(project_root: Path) -> bool:
    print_header()
    print("Welcome to saladbox! Let's set up your configuration.\n")

    env_path = project_root / ".env"
    config_path = project_root / "config.yaml"

    env_vars: dict[str, str] = {}
    config_updates: dict = {}

    # LLM Provider Selection
    print("-" * 60)
    print("STEP 1: LLM Provider")
    print("-" * 60)

    ollama_available = check_ollama()
    ollama_status = "available" if ollama_available else "not found"
    print(f"\nOllama status: {ollama_status}")

    provider_idx = prompt_choice(
        "Choose your LLM provider:",
        [
            f"Ollama (local) {'- recommended' if ollama_available else '- requires installation'}",
            "OpenRouter (cloud API)",
            "Both (switchable via config)",
        ],
        default=0 if ollama_available else 1,
    )

    if provider_idx == 0:
        config_updates["openrouter"] = {"enabled": False}
        print("\nUsing Ollama for local inference.")

        models = get_ollama_models()
        if models:
            print(f"\nAvailable models: {', '.join(models[:8])}")
            if len(models) > 8:
                print(f"  ... and {len(models) - 8} more")

        print("\nRecommended models (April 2026):")
        print("  qwen3:14b     — best general-purpose, dual think/no-think mode")
        print("  qwen3:8b      — fast & lightweight, think mode optional")
        print("  qwen3:32b     — highest quality (requires 24 GB RAM)")
        print("  llama4:scout  — Meta Llama 4 Scout, 10M context window")
        print("  llama4:maverick — Meta Llama 4 Maverick 128E MoE")
        default_model = prompt("Default model", "qwen3:14b")
        config_updates["ollama"] = {
            "default_model": default_model,
            "code_model": prompt("Code model", default_model),
            "fast_model": prompt("Fast model (for chat)", "qwen3:8b"),
            "reasoning_model": prompt("Reasoning model (complex tasks)", default_model),
            "context_length": 32768,
        }

    elif provider_idx == 1:
        config_updates["openrouter"] = {"enabled": True}
        print("\nUsing OpenRouter for cloud inference.")
        print("\nGet your API key at: https://openrouter.ai/keys")
        api_key = prompt("OpenRouter API key")
        if api_key:
            env_vars["OPENROUTER_API_KEY"] = api_key

        print("\nPopular models (April 2026):")
        print("  - anthropic/claude-sonnet-4-5    (best value — fast + smart)")
        print("  - anthropic/claude-opus-4-7      (most capable, extended thinking)")
        print("  - openai/gpt-5.4                 (OpenAI flagship)")
        print("  - openai/gpt-5.4-mini            (fast & cheap)")
        print("  - google/gemini-3.1-pro-preview  (Google frontier, 2M context)")
        print("  - meta-llama/llama-4-maverick    (best open-source)")

        default_model = prompt(
            "Default model", "anthropic/claude-sonnet-4-5"
        )
        config_updates["openrouter"].update(
            {
                "default_model": default_model,
                "code_model": prompt("Code model", default_model),
                "fast_model": prompt("Fast model (for chat)", "openai/gpt-5.4-mini"),
                "reasoning_model": prompt(
                    "Reasoning model (for complex tasks)", "anthropic/claude-opus-4-7"
                ),
            }
        )

        if ollama_available:
            config_updates["ollama"] = {"enabled": False}

    else:
        print("\nConfiguring both providers.")

        print("\n--- OpenRouter ---")
        print("Get your API key at: https://openrouter.ai/keys")
        api_key = prompt("OpenRouter API key")
        if api_key:
            env_vars["OPENROUTER_API_KEY"] = api_key

        config_updates["openrouter"] = {"enabled": False}

        if ollama_available:
            models = get_ollama_models()
            if models:
                print(f"\nOllama models: {', '.join(models[:8])}")

            default_model = prompt("Ollama default model", "qwen3:14b")
            config_updates["ollama"] = {
                "default_model": default_model,
                "code_model": prompt("Ollama code model", default_model),
                "fast_model": prompt("Ollama fast model", "qwen3:8b"),
                "reasoning_model": prompt("Ollama reasoning model", default_model),
                "context_length": 40960,
            }

    # Messaging Platforms
    print_header()
    print("-" * 60)
    print("STEP 2: Messaging Platforms")
    print("-" * 60)

    print("\nConfigure integrations (you can skip and add later)")

    if prompt_yes_no("\nEnable Telegram bot?", False):
        print("\nGet your bot token from @BotFather on Telegram")
        token = prompt("Telegram bot token")
        if token:
            env_vars["TELEGRAM_BOT_TOKEN"] = token
            config_updates["telegram"] = {"enabled": True}

            user_ids = prompt(
                "Allowed Telegram user IDs (comma-separated, empty for all)", ""
            )
            if user_ids:
                config_updates["telegram"]["allowed_user_ids"] = [
                    int(u.strip()) for u in user_ids.split(",") if u.strip().isdigit()
                ]

    if prompt_yes_no("\nEnable Slack bot?", False):
        print("\nYou need both tokens from Slack API:")
        print("  - Bot token (xoxb-...)")
        print("  - App token (xapp-...)")
        bot_token = prompt("Slack bot token")
        app_token = prompt("Slack app token")
        if bot_token:
            env_vars["SLACK_BOT_TOKEN"] = bot_token
        if app_token:
            env_vars["SLACK_APP_TOKEN"] = app_token
        if bot_token and app_token:
            config_updates["slack"] = {"enabled": True}

    # Tools
    print_header()
    print("-" * 60)
    print("STEP 3: Tools")
    print("-" * 60)

    print("\nAvailable tools:")
    tool_descriptions = {
        "shell": "Run shell commands",
        "python_exec": "Execute Python code",
        "browser": "Web browsing/automation",
        "filesystem": "File operations",
        "system_monitor": "System stats",
        "scheduler": "Task scheduling",
        "process_manager": "Background processes",
        "code_editor": "Code editing & project management",
        "git": "Git operations & PR creation",
        "reminder": "Reminders & notifications",
    }

    tools_config = {}
    for tool, desc in tool_descriptions.items():
        tools_config[tool] = prompt_yes_no(f"  Enable {tool}? ({desc})", True)

    config_updates["tools"] = tools_config

    # MCP Servers
    print_header()
    print("-" * 60)
    print("STEP 4: MCP Servers (Optional)")
    print("-" * 60)

    print("\nMCP (Model Context Protocol) servers add external tools.")
    print("Popular servers:")
    print("  - github: Repository operations")
    print("  - brave-search: Web search")
    print("  - filesystem: Extended file access")
    print("  - memory: Persistent memory")

    mcp_servers = {}

    if prompt_yes_no("\nWould you like to configure MCP servers?", False):
        while True:
            print("\n--- Add MCP Server ---")
            name = prompt("Server name (e.g., github, brave-search)", "")
            if not name:
                break

            print("\nCommon commands:")
            print("  - npx (Node.js packages)")
            print("  - uvx (Python packages)")
            print("  - python3 (custom scripts)")

            command = prompt("Command", "npx")
            args_str = prompt("Arguments (comma-separated)", "")
            args = [a.strip() for a in args_str.split(",") if a.strip()]

            env_vars_mcp = {}
            if prompt_yes_no("Add environment variables?", False):
                print("Enter key=value pairs (empty line to finish):")
                while True:
                    env_line = prompt("  Environment variable", "")
                    if not env_line:
                        break
                    if "=" in env_line:
                        k, v = env_line.split("=", 1)
                        env_vars_mcp[k.strip()] = v.strip()

            mcp_servers[name] = {
                "command": command,
                "args": args,
                "env": env_vars_mcp,
                "enabled": True,
            }

            if not prompt_yes_no("Add another server?", False):
                break

    if mcp_servers:
        config_updates["mcp_servers"] = mcp_servers

    # Summary & Write
    print_header()
    print("-" * 60)
    print("SETUP COMPLETE")
    print("-" * 60)

    print("\nConfiguration summary:")
    print(f"  LLM Provider: {['Ollama', 'OpenRouter', 'Both'][provider_idx]}")
    print(
        f"  Telegram: {'enabled' if config_updates.get('telegram', {}).get('enabled') else 'disabled'}"
    )
    print(
        f"  Slack: {'enabled' if config_updates.get('slack', {}).get('enabled') else 'disabled'}"
    )
    print(
        f"  Tools: {sum(1 for v in tools_config.values() if v)}/{len(tools_config)} enabled"
    )

    # Write .env file
    if env_vars:
        env_content = ""
        if env_path.exists():
            existing = {}
            for line in env_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()
            existing.update(env_vars)
            env_vars = existing

        env_content = "# saladbox environment configuration\n\n"
        if "OPENROUTER_API_KEY" in env_vars:
            env_content += f"# OpenRouter API\nOPENROUTER_API_KEY={env_vars['OPENROUTER_API_KEY']}\n\n"
        if "TELEGRAM_BOT_TOKEN" in env_vars:
            env_content += f"# Telegram Bot\nTELEGRAM_BOT_TOKEN={env_vars['TELEGRAM_BOT_TOKEN']}\n\n"
        if "SLACK_BOT_TOKEN" in env_vars:
            env_content += (
                f"# Slack Bot\nSLACK_BOT_TOKEN={env_vars['SLACK_BOT_TOKEN']}\n"
            )
            if "SLACK_APP_TOKEN" in env_vars:
                env_content += f"SLACK_APP_TOKEN={env_vars['SLACK_APP_TOKEN']}\n"
            env_content += "\n"

        env_path.write_text(env_content.strip() + "\n")
        print(f"\n  Written: {env_path}")

    # Update config.yaml
    import yaml

    if config_path.exists():
        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}
    else:
        config_data = {}

    # Deep merge
    for key, value in config_updates.items():
        if (
            isinstance(value, dict)
            and key in config_data
            and isinstance(config_data[key], dict)
        ):
            config_data[key].update(value)
        else:
            config_data[key] = value

    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
    print(f"  Updated: {config_path}")

    print("\n" + "=" * 60)
    print("  Run 'saladbox'        — CLI mode")
    print("  Run 'saladbox --http' — HTTP/Electron mode")
    print("=" * 60)

    return True


def should_run_setup(project_root: Path) -> bool:
    env_path = project_root / ".env"
    project_root / "config.yaml"

    if not env_path.exists():
        return True

    env_content = env_path.read_text()
    has_any_key = any(
        key in env_content
        for key in ["OPENROUTER_API_KEY", "TELEGRAM_BOT_TOKEN", "SLACK_BOT_TOKEN"]
    )

    return not has_any_key


def maybe_run_setup(project_root: Path) -> bool:
    if should_run_setup(project_root):
        print_header()
        print("First-time setup detected!\n")
        if prompt_yes_no("Would you like to run the setup wizard?", True):
            return run_setup(project_root)
        print("\nTip: Run 'python -m saladbox.setup' anytime to reconfigure.\n")
    return True


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    run_setup(project_root)


def _cli_main():
    """Entry point for saladbox-setup command."""
    project_root = Path(__file__).parent.parent
    run_setup(project_root)
