"""macOS System Control Tool."""

from __future__ import annotations

import subprocess
from saladbox.tools.base import BaseTool


class SystemControlTool(BaseTool):
    """Control system parameters like volume, mute, and send OS notifications."""

    @property
    def name(self) -> str:
        return "system_control"

    @property
    def description(self) -> str:
        return (
            "Control macOS system settings. Actions: "
            "'volume' (get or set output volume 0-100), "
            "'mute' (get, mute, unmute, or toggle muted status), "
            "'notify' (show a native desktop alert)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["volume", "mute", "notify"],
                    "description": "System action to perform",
                },
                "value": {
                    "type": "string",
                    "description": "For 'volume': integer 0-100. For 'mute': 'on', 'off', 'toggle', or 'status'.",
                },
                "title": {
                    "type": "string",
                    "description": "Title of the desktop notification",
                },
                "message": {
                    "type": "string",
                    "description": "Message body of the desktop notification",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        value: str = "",
        title: str = "Saladbox",
        message: str = "",
    ) -> str:
        if action == "volume":
            return self._volume(value)
        elif action == "mute":
            return self._mute(value)
        elif action == "notify":
            if not message:
                return "Error: 'message' is required for notifications."
            return self._notify(title, message)
        return f"Unknown action: {action}"

    def _run_osa(self, script: str) -> tuple[int, str]:
        """Run an AppleScript command via osascript."""
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.returncode, res.stdout.strip()
        except Exception as e:
            return 1, str(e)

    def _volume(self, value: str) -> str:
        if not value:
            # Get current volume settings
            code, out = self._run_osa("output volume of (get volume settings)")
            if code != 0:
                return f"Error getting system volume: {out}"
            return f"Current system volume is: {out}%"
        
        try:
            vol = int(value)
            if not (0 <= vol <= 100):
                return "Error: Volume must be an integer between 0 and 100."
        except ValueError:
            return f"Error: Invalid volume value '{value}'. Must be an integer."

        code, out = self._run_osa(f"set volume output volume {vol}")
        if code != 0:
            return f"Error setting volume: {out}"
        return f"Successfully set system volume to {vol}%"

    def _mute(self, value: str) -> str:
        target = value.lower() if value else "status"
        
        if target == "status":
            code, out = self._run_osa("output muted of (get volume settings)")
            if code != 0:
                return f"Error getting mute status: {out}"
            return f"System mute is currently: {'ON' if out == 'true' else 'OFF'}"
            
        elif target == "on":
            code, out = self._run_osa("set volume with output muted")
            if code != 0:
                return f"Error muting system: {out}"
            return "System successfully muted."
            
        elif target == "off":
            code, out = self._run_osa("set volume without output muted")
            if code != 0:
                return f"Error unmuting system: {out}"
            return "System successfully unmuted."
            
        elif target == "toggle":
            code, out = self._run_osa("set volume output muted (not (output muted of (get volume settings)))")
            if code != 0:
                return f"Error toggling mute: {out}"
            # Check new status
            _, status = self._run_osa("output muted of (get volume settings)")
            return f"System mute toggled. Current status: {'ON' if status == 'true' else 'OFF'}"
            
        return f"Error: Invalid mute option '{value}'. Choose from: 'on', 'off', 'toggle', 'status'."

    def _notify(self, title: str, message: str) -> str:
        # Escape double quotes
        clean_title = title.replace('"', '\\"')
        clean_msg = message.replace('"', '\\"')
        
        script = f'display notification "{clean_msg}" with title "{clean_title}"'
        code, out = self._run_osa(script)
        if code != 0:
            return f"Error displaying notification: {out}"
        return "Notification displayed successfully."
