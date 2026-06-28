"""Network utility and diagnostics tool."""

from __future__ import annotations

import subprocess
import aiohttp
from saladbox.tools.base import BaseTool


class NetworkTool(BaseTool):
    """Diagnose network latency and retrieve public IP / location information."""

    @property
    def name(self) -> str:
        return "network"

    @property
    def description(self) -> str:
        return (
            "Diagnose internet connectivity and retrieve network information. "
            "Actions: 'ping' (ping a hostname/IP to test latency), "
            "'ip_info' (retrieve current public IP, ISP, and geo-location details)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["ping", "ip_info"],
                    "description": "Network tool action to perform",
                },
                "host": {
                    "type": "string",
                    "description": "Host to ping (for 'ping' action, defaults to '8.8.8.8')",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        host: str = "8.8.8.8",
    ) -> str:
        if action == "ping":
            return self._ping(host)
        elif action == "ip_info":
            return await self._ip_info()
        return f"Unknown action: {action}"

    def _ping(self, host: str) -> str:
        # Prevent shell injection by validating the host string
        # Simple check: allow alphanumeric characters, dots, dashes
        if not host or not all(c.isalnum() or c in ".-" for c in host):
            return "Error: Invalid host name provided."

        try:
            res = subprocess.run(
                ["ping", "-c", "3", "-t", "3", host],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode != 0:
                return f"Ping failed for host {host}:\n{res.stderr.strip() or res.stdout.strip()}"
            return f"**Ping Results for {host}**\n\n{res.stdout.strip()}"
        except subprocess.TimeoutExpired:
            return f"Error: Ping command to {host} timed out."
        except Exception as e:
            return f"Error executing ping: {e}"

    async def _ip_info(self) -> str:
        url = "https://ipinfo.io/json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        return f"Error: ipinfo.io returned HTTP status {resp.status}"
                    data = await resp.json()
                    
                    return (
                        f"**Public IP Information**\n"
                        f"- IP Address: `{data.get('ip')}`\n"
                        f"- Hostname: `{data.get('hostname', 'N/A')}`\n"
                        f"- City: `{data.get('city')}`\n"
                        f"- Region: `{data.get('region')}`\n"
                        f"- Country: `{data.get('country')}`\n"
                        f"- Location (Lat, Long): `{data.get('loc')}`\n"
                        f"- Organisation/ISP: `{data.get('org')}`\n"
                        f"- Timezone: `{data.get('timezone')}`"
                    )
        except Exception as e:
            return f"Error retrieving public IP info: {e}"
