"""Git operations tool."""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from saladbox.tools.base import BaseTool


class GitTool(BaseTool):
    """Perform git operations: init, status, add, commit, branch, checkout, push, pull, clone, create_pr."""

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return (
            "Git operations for version control. "
            "Actions: init, status, add, commit, branch, checkout, push, pull, clone, create_pr, log. "
            "Use 'create_pr' to create a GitHub pull request (requires gh CLI)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "init",
                        "status",
                        "add",
                        "commit",
                        "branch",
                        "checkout",
                        "push",
                        "pull",
                        "clone",
                        "create_pr",
                        "log",
                    ],
                    "description": "Git action to perform",
                },
                "path": {
                    "type": "string",
                    "description": "Repository path (default: current directory)",
                },
                "files": {
                    "type": "string",
                    "description": "Files to add (for 'add'), comma-separated or '.' for all",
                },
                "message": {
                    "type": "string",
                    "description": "Commit message (for 'commit') or PR title (for 'create_pr')",
                },
                "branch_name": {
                    "type": "string",
                    "description": "Branch name (for 'branch', 'checkout')",
                },
                "remote": {
                    "type": "string",
                    "description": "Remote name (default: origin)",
                },
                "url": {
                    "type": "string",
                    "description": "Repository URL (for 'clone')",
                },
                "base_branch": {
                    "type": "string",
                    "description": "Base branch for PR (default: main)",
                },
                "body": {
                    "type": "string",
                    "description": "PR body/description (for 'create_pr')",
                },
                "lines": {
                    "type": "integer",
                    "description": "Number of log lines to show (for 'log', default: 10)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        path: str = ".",
        files: str = "",
        message: str = "",
        branch_name: str = "",
        remote: str = "origin",
        url: str = "",
        base_branch: str = "main",
        body: str = "",
        lines: int = 10,
    ) -> str:
        work_dir = os.path.expanduser(path) if path else "."
        if work_dir != "." and not os.path.isdir(work_dir):
            return f"Error: Directory '{work_dir}' does not exist"

        match action:
            case "init":
                return await self._run(f"git init", work_dir)
            case "status":
                return await self._run(f"git status", work_dir)
            case "add":
                if not files:
                    files = "."
                return await self._run(f"git add {files}", work_dir)
            case "commit":
                if not message:
                    return "Error: commit message is required"
                return await self._run(f'git commit -m "{message}"', work_dir)
            case "branch":
                if branch_name:
                    return await self._run(f"git branch {branch_name}", work_dir)
                return await self._run("git branch -a", work_dir)
            case "checkout":
                if not branch_name:
                    return "Error: branch_name is required for checkout"
                return await self._run(f"git checkout {branch_name}", work_dir)
            case "push":
                cmd = f"git push {remote}"
                if branch_name:
                    cmd += f" {branch_name}"
                return await self._run(cmd, work_dir)
            case "pull":
                cmd = f"git pull {remote}"
                if branch_name:
                    cmd += f" {branch_name}"
                return await self._run(cmd, work_dir)
            case "clone":
                if not url:
                    return "Error: url is required for clone"
                return await self._run(f"git clone {url}", work_dir)
            case "create_pr":
                return await self._create_pr(work_dir, message, base_branch, body)
            case "log":
                return await self._run(f"git log --oneline -{lines}", work_dir)
            case _:
                return f"Unknown action: {action}"

    async def _run(self, command: str, cwd: str) -> str:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return "Command timed out after 60s"

        output = stdout.decode(errors="replace") if stdout else ""
        errors = stderr.decode(errors="replace") if stderr else ""

        max_len = 3000
        if len(output) > max_len:
            output = output[:max_len] + "\n... (truncated)"
        if len(errors) > max_len:
            errors = errors[:max_len] + "\n... (truncated)"

        parts = [f"Exit code: {proc.returncode}"]
        if output.strip():
            parts.append(output)
        if errors.strip():
            parts.append(f"Stderr:\n{errors}")
        return "\n".join(parts)

    async def _create_pr(
        self, cwd: str, title: str, base_branch: str, body: str
    ) -> str:
        if not title:
            return "Error: PR title (message parameter) is required"

        body_arg = ""
        if body:
            escaped_body = body.replace('"', '\\"')
            body_arg = f' --body "{escaped_body}"'

        cmd = f'gh pr create --title "{title}" --base {base_branch}{body_arg}'
        result = await self._run(cmd, cwd)

        if "https://github.com" in result:
            return f"Pull request created successfully!\n{result}"
        return result
