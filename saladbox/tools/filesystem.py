"""Filesystem operations tool."""

from __future__ import annotations

import glob as glob_mod
import os
from pathlib import Path

from saladbox.tools.base import BaseTool

# Directories that should never be directly read/written/deleted
_BLOCKED_PATHS = frozenset({
    "/etc/shadow", "/etc/passwd", "/etc/sudoers",
    "/private/etc/shadow", "/private/etc/passwd",
})

# Patterns that indicate sensitive files
_SENSITIVE_PATTERNS = frozenset({
    ".ssh/id_rsa", ".ssh/id_ed25519", ".aws/credentials",
    ".gnupg/", ".env",
})


class FileSystemTool(BaseTool):
    """Read, write, list, and search files on the local filesystem."""

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return (
            "Perform filesystem operations: read files, write files, list directories, "
            "search with glob patterns, create directories, and delete files."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "list", "search", "mkdir", "delete", "info"],
                    "description": "The filesystem action to perform",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory path",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (for 'write' action)",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (for 'search' action)",
                },
            },
            "required": ["action", "path"],
        }

    async def execute(
        self,
        action: str,
        path: str = "",
        content: str = "",
        pattern: str = "",
    ) -> str:
        # Accept 'pattern' as alias for 'path' when path is missing (LLM sometimes sends pattern)
        if not path and pattern:
            path = pattern
            pattern = ""
        if not path:
            return "Missing required argument: provide 'path' (or 'pattern') for the file or directory."
        path = os.path.expanduser(path)
        # Map Linux-style /home/... to the actual user home (e.g. on macOS: /home/laptop -> ~/laptop)
        if path == "/home" or path.startswith("/home/"):
            path = os.path.join(os.path.expanduser("~"), path[6:].lstrip("/")) or os.path.expanduser("~")

        # Resolve to canonical path to prevent traversal via symlinks or ../
        resolved = str(Path(path).resolve())

        # Block access to known sensitive system paths
        if resolved in _BLOCKED_PATHS:
            return f"Access denied: '{path}' is a protected system file."
        for pattern in _SENSITIVE_PATTERNS:
            if pattern in resolved and action in ("read", "write", "delete"):
                return f"Access denied: '{path}' matches a sensitive file pattern. Use run_shell if you really need this."

        match action:
            case "read":
                return self._read(path)
            case "write":
                return self._write(path, content)
            case "list":
                return self._list(path)
            case "search":
                return self._search(path, pattern)
            case "mkdir":
                return self._mkdir(path)
            case "delete":
                return self._delete(path)
            case "info":
                return self._info(path)
            case _:
                return f"Unknown action: {action}"

    def _read(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"File not found: {path}"
        if not p.is_file():
            return f"Not a file: {path}"
        try:
            text = p.read_text(errors="replace")
            if len(text) > 8000:
                return text[:8000] + f"\n... (truncated, total {len(text)} chars)"
            return text
        except Exception as e:
            return f"Error reading file: {e}"

    def _write(self, path: str, content: str) -> str:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            return f"Written {len(content)} chars to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def _list(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"Directory not found: {path}"
        if not p.is_dir():
            return f"Not a directory: {path}"
        try:
            entries = sorted(p.iterdir())
            lines = []
            for entry in entries[:100]:
                kind = "dir" if entry.is_dir() else "file"
                size = entry.stat().st_size if entry.is_file() else 0
                lines.append(f"  [{kind}] {entry.name}" + (f" ({size} bytes)" if size else ""))
            result = f"Contents of {path} ({len(entries)} items):\n" + "\n".join(lines)
            if len(entries) > 100:
                result += f"\n... and {len(entries) - 100} more items"
            return result
        except Exception as e:
            return f"Error listing directory: {e}"

    def _search(self, path: str, pattern: str) -> str:
        if not pattern:
            return "Pattern is required for search action"
        try:
            full_pattern = os.path.join(path, pattern)
            matches = glob_mod.glob(full_pattern, recursive=True)
            if not matches:
                return f"No matches for pattern '{pattern}' in {path}"
            result = f"Found {len(matches)} matches:\n"
            for m in matches[:50]:
                result += f"  {m}\n"
            if len(matches) > 50:
                result += f"  ... and {len(matches) - 50} more"
            return result
        except Exception as e:
            return f"Error searching: {e}"

    def _mkdir(self, path: str) -> str:
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return f"Created directory: {path}"
        except Exception as e:
            return f"Error creating directory: {e}"

    def _delete(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"Path not found: {path}"
        try:
            if p.is_file():
                p.unlink()
                return f"Deleted file: {path}"
            else:
                return "Use 'run_shell' with 'rm -rf' for directory deletion (safety measure)"
        except Exception as e:
            return f"Error deleting: {e}"

    def _info(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"Path not found: {path}"
        stat = p.stat()
        return (
            f"Path: {path}\n"
            f"Type: {'directory' if p.is_dir() else 'file'}\n"
            f"Size: {stat.st_size} bytes\n"
            f"Modified: {stat.st_mtime}\n"
            f"Permissions: {oct(stat.st_mode)}"
        )
