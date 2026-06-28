"""Entry point: python -m saladbox"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from saladbox.config import load_config
from saladbox.app import Application


def main():
    parser = argparse.ArgumentParser(description="saladbox - Local AI assistant")
    parser.add_argument("--setup", action="store_true", help="Run setup wizard")
    parser.add_argument("--version", action="store_true", help="Show version")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Start HTTP API server (for Electron/desktop)",
    )
    parser.add_argument(
        "--port", type=int, default=8765, help="HTTP server port (default: 8765)"
    )
    args = parser.parse_args()

    if args.version:
        from saladbox import __version__

        print(f"saladbox {__version__}")
        return

    project_root = Path(__file__).parent.parent

    if args.setup:
        from saladbox.setup_wizard import run_setup

        run_setup(project_root)
        return

    from saladbox.setup_wizard import maybe_run_setup

    maybe_run_setup(project_root)

    config = load_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    app = Application(config, http_mode=args.http, http_port=args.port)

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nShutdown.")
        sys.exit(0)


if __name__ == "__main__":
    main()
