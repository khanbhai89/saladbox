"""Screen capture tool for taking screenshots using macOS screencapture.

Returns a structured result with a file path marker so the engine can:
1. Pass the image to a vision model for analysis
2. Serve the image to the frontend for display
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import time

from saladbox.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Persistent directory for screenshots (served by HTTP adapter)
SCREENSHOT_DIR = os.path.join(tempfile.gettempdir(), "saladbox_screenshots")


class ScreenCaptureTool(BaseTool):
    name = "screen_capture"
    description = (
        "Capture a screenshot of the screen. Returns the captured image for "
        "vision analysis. Use this when the user asks to see their screen, "
        "take a screenshot, or analyze what's on screen."
    )
    compact_description = "Take a screenshot of the screen for vision analysis."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["capture", "clipboard"],
                    "description": "capture = take screenshot for analysis, clipboard = copy to clipboard",
                },
                "region": {
                    "type": "string",
                    "description": "Region as 'x,y,width,height' (optional, full screen if omitted)",
                },
            },
        }

    async def execute(
        self, action: str = "capture", region: str = "", **kwargs
    ) -> str:
        try:
            if action == "clipboard":
                return await self._capture_to_clipboard()
            return await self._capture_screen(region)
        except Exception as e:
            logger.exception("Screen capture failed")
            return f"Error: {e}"

    async def _capture_screen(self, region: str = "") -> str:
        """Capture screen and save to persistent temp directory.

        Returns a structured result with SCREENSHOT_FILE: marker so the
        engine can detect it, pass to vision model, and serve to frontend.
        """
        # Ensure screenshot directory exists
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)

        # Clean up old screenshots (older than 1 hour)
        self._cleanup_old_screenshots()

        cmd = ["screencapture", "-x"]  # -x = no sound

        if region:
            cmd.extend(["-R", region])

        filename = f"screenshot_{int(time.time())}.png"
        save_path = os.path.join(SCREENSHOT_DIR, filename)
        cmd.append(save_path)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return f"Error capturing screen: {result.stderr}"

        if not os.path.exists(save_path):
            return "Error: Screenshot file was not created"

        file_size = os.path.getsize(save_path)

        # Return structured result — engine detects SCREENSHOT_FILE: marker
        return (
            f"SCREENSHOT_FILE:{filename}\n"
            f"Screenshot captured successfully ({file_size:,} bytes). "
            f"The image is ready for vision analysis."
        )

    async def _capture_to_clipboard(self) -> str:
        result = subprocess.run(
            ["screencapture", "-c", "-x"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return f"Error capturing to clipboard: {result.stderr}"

        return "Screenshot copied to clipboard successfully."

    def _cleanup_old_screenshots(self, max_age_seconds: int = 3600) -> None:
        """Remove screenshots older than max_age_seconds."""
        try:
            now = time.time()
            for f in os.listdir(SCREENSHOT_DIR):
                fpath = os.path.join(SCREENSHOT_DIR, f)
                if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > max_age_seconds:
                    os.remove(fpath)
        except OSError:
            pass
