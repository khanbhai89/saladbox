"""Docker container management tool."""

from __future__ import annotations

import asyncio

from saladbox.tools.base import BaseTool


class DockerTool(BaseTool):
    """Manage Docker containers and images."""

    @property
    def name(self) -> str:
        return "docker"

    @property
    def description(self) -> str:
        return (
            "Manage Docker containers and images. List, start, stop, remove containers, "
            "view logs, execute commands in containers, and manage images. Requires Docker CLI."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "ps",
                        "ps_all",
                        "images",
                        "start",
                        "stop",
                        "restart",
                        "rm",
                        "logs",
                        "exec",
                        "run",
                        "pull",
                        "rmi",
                        "inspect",
                        "stats",
                        "prune",
                    ],
                    "description": "Docker operation to perform",
                },
                "container": {
                    "type": "string",
                    "description": "Container name or ID",
                },
                "image": {
                    "type": "string",
                    "description": "Image name (e.g., 'nginx:latest')",
                },
                "command": {
                    "type": "string",
                    "description": "Command to execute in container",
                },
                "options": {
                    "type": "string",
                    "description": "Additional docker options (e.g., '-d -p 8080:80')",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines to show (default: 50)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        container: str | None = None,
        image: str | None = None,
        command: str | None = None,
        options: str | None = None,
        lines: int = 50,
    ) -> str:
        try:
            if action == "ps":
                return await self._run_docker(
                    [
                        "ps",
                        "--format",
                        "table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}",
                    ]
                )

            elif action == "ps_all":
                return await self._run_docker(
                    [
                        "ps",
                        "-a",
                        "--format",
                        "table {{.Names}}\t{{.Status}}\t{{.Image}}",
                    ]
                )

            elif action == "images":
                return await self._run_docker(
                    ["images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"]
                )

            elif action == "start":
                if not container:
                    return "Error: 'container' required for start action"
                return await self._run_docker(["start", container])

            elif action == "stop":
                if not container:
                    return "Error: 'container' required for stop action"
                return await self._run_docker(["stop", container])

            elif action == "restart":
                if not container:
                    return "Error: 'container' required for restart action"
                return await self._run_docker(["restart", container])

            elif action == "rm":
                if not container:
                    return "Error: 'container' required for rm action"
                return await self._run_docker(["rm", "-f", container])

            elif action == "logs":
                if not container:
                    return "Error: 'container' required for logs action"
                return await self._run_docker(["logs", "--tail", str(lines), container])

            elif action == "exec":
                if not container or not command:
                    return "Error: 'container' and 'command' required for exec action"
                return await self._run_docker(["exec", container, "sh", "-c", command])

            elif action == "run":
                if not image:
                    return "Error: 'image' required for run action"
                opts = options.split() if options else []
                return await self._run_docker(
                    ["run"] + opts + [image] + ([command] if command else [])
                )

            elif action == "pull":
                if not image:
                    return "Error: 'image' required for pull action"
                return await self._run_docker(["pull", image])

            elif action == "rmi":
                if not image:
                    return "Error: 'image' required for rmi action"
                return await self._run_docker(["rmi", "-f", image])

            elif action == "inspect":
                if not container:
                    return "Error: 'container' required for inspect action"
                return await self._run_docker(
                    ["inspect", "--format", "{{json .}}", container]
                )

            elif action == "stats":
                return await self._run_docker(
                    [
                        "stats",
                        "--no-stream",
                        "--format",
                        "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}",
                    ]
                )

            elif action == "prune":
                return await self._run_docker(["system", "prune", "-f"])

            else:
                return f"Unknown action: {action}"

        except FileNotFoundError:
            return "Error: Docker CLI not found. Please install Docker."
        except Exception as e:
            return f"Error: {e!s}"

    async def _run_docker(self, args: list[str]) -> str:
        proc = await asyncio.create_subprocess_exec(
            "docker",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        output = stdout.decode(errors="replace") if stdout else ""
        error = stderr.decode(errors="replace") if stderr else ""

        if proc.returncode != 0:
            if error:
                return f"Docker error: {error.strip()}"
            return f"Docker command failed with code {proc.returncode}"

        if len(output) > 3000:
            output = output[:3000] + "\n... (truncated)"

        return output.strip() or "Command completed successfully"
