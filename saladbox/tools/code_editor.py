"""Code editor tool: find projects, navigate, read/edit code, search."""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import re
from pathlib import Path

from saladbox.tools.base import BaseTool

logger = logging.getLogger(__name__)

# ── Project discovery ────────────────────────────────────────────────────────

SCAN_DIRS = [
    Path.home(),
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Developer",
    Path.home() / "dev",
    Path.home() / "repos",
    Path.home() / "projects",
    Path.home() / "src",
    Path.home() / "code",
    Path.home() / "workspace",
    Path.home() / "Sites",
    Path.home() / "go" / "src",
]

PROJECT_MARKERS = [
    ".git",
    "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "requirements.txt",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml", "build.gradle", "build.gradle.kts",
    "CMakeLists.txt", "Makefile",
    "Gemfile",
    "composer.json",
    "Package.swift",
    "mix.exs",
    "pubspec.yaml",
]

LANGUAGE_MAP = {
    "pyproject.toml": "Python", "setup.py": "Python", "Pipfile": "Python",
    "requirements.txt": "Python", "setup.cfg": "Python",
    "package.json": "JavaScript/TypeScript",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java", "build.gradle": "Java/Kotlin",
    "build.gradle.kts": "Kotlin",
    "CMakeLists.txt": "C/C++", "Makefile": "C/C++",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "Package.swift": "Swift",
    "mix.exs": "Elixir",
    "pubspec.yaml": "Dart/Flutter",
}

EXTENSION_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript (React)", ".jsx": "JavaScript (React)",
    ".rs": "Rust", ".go": "Go", ".java": "Java", ".kt": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".c": "C", ".cpp": "C++", ".h": "C/C++ Header",
    ".cs": "C#", ".ex": "Elixir", ".exs": "Elixir Script",
    ".dart": "Dart", ".yaml": "YAML", ".yml": "YAML",
    ".json": "JSON", ".toml": "TOML", ".md": "Markdown",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".sh": "Shell", ".bash": "Bash", ".zsh": "Zsh",
    ".sql": "SQL",
}

# ── Project run commands (auto-detected by marker) ───────────────────────────

RUN_COMMANDS = {
    # marker → {run_type: command}
    "package.json": {
        "dev": "npm run dev",
        "start": "npm start",
        "build": "npm run build",
        "test": "npm test",
        "install": "npm install",
    },
    "pyproject.toml": {
        "dev": "python3 -m {project_name}",
        "start": "python3 -m {project_name}",
        "test": "python3 -m pytest",
        "install": "pip3 install -e .",
        "build": "python3 -m build",
    },
    "requirements.txt": {
        "start": "python3 main.py",
        "test": "python3 -m pytest",
        "install": "pip3 install -r requirements.txt",
    },
    "Cargo.toml": {
        "dev": "cargo run",
        "start": "cargo run",
        "build": "cargo build",
        "test": "cargo test",
    },
    "go.mod": {
        "dev": "go run .",
        "start": "go run .",
        "build": "go build .",
        "test": "go test ./...",
    },
    "pubspec.yaml": {
        "dev": "flutter run",
        "start": "flutter run",
        "build": "flutter build",
        "test": "flutter test",
        "install": "flutter pub get",
    },
    "Gemfile": {
        "start": "bundle exec ruby app.rb",
        "test": "bundle exec rspec",
        "install": "bundle install",
    },
    "composer.json": {
        "start": "php artisan serve",
        "test": "php artisan test",
        "install": "composer install",
    },
    "pom.xml": {
        "build": "mvn package",
        "test": "mvn test",
        "start": "mvn spring-boot:run",
    },
    "build.gradle": {
        "build": "gradle build",
        "test": "gradle test",
        "start": "gradle bootRun",
    },
    "CMakeLists.txt": {
        "build": "cmake --build build",
        "test": "ctest --test-dir build",
    },
    "Makefile": {
        "build": "make",
        "test": "make test",
        "start": "make run",
    },
    "Package.swift": {
        "build": "swift build",
        "test": "swift test",
        "start": "swift run",
    },
    "mix.exs": {
        "dev": "mix phx.server",
        "test": "mix test",
        "start": "mix run",
        "install": "mix deps.get",
    },
}

DEFAULT_IGNORES = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".env", "dist", "build", ".next", ".nuxt", "target",
    ".idea", ".vscode", "*.pyc", ".DS_Store", "*.egg-info",
    ".tox", ".mypy_cache", ".pytest_cache", "coverage",
    "vendor", "Pods", ".gradle", ".cache", ".parcel-cache",
    ".turbo", ".svelte-kit",
}

# ── Helpers ──────────────────────────────────────────────────────────────────


def _truncate(text: str, max_chars: int = 5000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... (truncated, {len(text)} total chars)"


def _is_binary(file_path: Path) -> bool:
    """Check if a file is binary by looking for null bytes."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
        return b"\x00" in chunk
    except Exception:
        return False


def _load_ignore_patterns(project_root: Path) -> list[str]:
    """Load .gitignore patterns + defaults."""
    patterns = list(DEFAULT_IGNORES)
    gitignore = project_root / ".gitignore"
    if gitignore.exists():
        try:
            for line in gitignore.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
        except Exception:
            pass
    return patterns


def _is_ignored(path: Path, root: Path, patterns: list[str]) -> bool:
    """Check if a path should be ignored."""
    name = path.name
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = name
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(rel, pattern):
            return True
        # Handle directory patterns like "build/"
        if pattern.endswith("/") and fnmatch.fnmatch(name, pattern.rstrip("/")):
            return True
    return False


def _detect_language(markers: list[str]) -> str:
    """Detect project language from found markers."""
    for marker in markers:
        if marker in LANGUAGE_MAP:
            return LANGUAGE_MAP[marker]
    return "Unknown"


async def _run_git(cwd: Path, *args: str, timeout: int = 10) -> str | None:
    """Run a git command and return stdout, or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode == 0:
            return stdout.decode(errors="replace")
        return None
    except Exception:
        return None


# ── Tool class ───────────────────────────────────────────────────────────────


class CodeEditorTool(BaseTool):
    """Find projects, navigate code, read/edit files, search codebases."""

    def __init__(self):
        self._current_project: Path | None = None
        self._project_cache: dict[str, dict] = {}
        self._edit_backups: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "code_editor"

    @property
    def description(self) -> str:
        return (
            "Work with code projects on the local machine. "
            "Actions: find_projects (discover projects on disk), "
            "open_project (set active project), project_info (language, git status), "
            "tree (directory structure), read_file (view code with line numbers), "
            "edit_file (modify code via find_replace, replace_lines, insert, delete), "
            "create_file (create a new file), "
            "search (grep/regex across project files), "
            "run (run/build/test the project), diff (show git changes), "
            "undo (revert last edit). "
            "The active project persists across calls. "
            "For coding tasks: read relevant files first, make changes, then run to verify."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "find_projects", "open_project", "project_info",
                        "tree", "read_file", "edit_file", "create_file",
                        "search", "run", "diff", "undo",
                    ],
                    "description": (
                        "The code editor action. Use 'find_projects' to discover projects, "
                        "'open_project' to set the active project, 'read_file' to view code, "
                        "'edit_file' to modify code (prefer edit_type 'find_replace'), "
                        "'create_file' to create a new file, "
                        "'search' to grep across files, 'tree' for directory structure, "
                        "'run' to run/build/test the project, 'diff' to show git changes."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "File or directory path. Can be relative to the open project "
                        "(e.g. 'src/main.py') or absolute."
                    ),
                },
                "scan_path": {
                    "type": "string",
                    "description": "For find_projects: specific directory to scan.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Starting line number (1-based) for read_file or edit_file.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Ending line number (1-based, inclusive) for read_file or edit_file.",
                },
                "edit_type": {
                    "type": "string",
                    "enum": [
                        "find_replace", "replace_lines",
                        "insert_before", "insert_after", "delete_lines",
                    ],
                    "description": (
                        "For edit_file: the edit method. 'find_replace' is recommended "
                        "(searches for exact text and replaces it, no line numbers needed)."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "New code content for replace/insert operations.",
                },
                "find": {
                    "type": "string",
                    "description": (
                        "For find_replace: exact text to find. Must match exactly once. "
                        "Include enough surrounding context to be unique."
                    ),
                },
                "replace": {
                    "type": "string",
                    "description": "For find_replace: the replacement text.",
                },
                "pattern": {
                    "type": "string",
                    "description": "For search: regex pattern to search for.",
                },
                "file_glob": {
                    "type": "string",
                    "description": "For search: file pattern filter (e.g. '*.py', '*.ts').",
                },
                "depth": {
                    "type": "integer",
                    "description": "For tree: max directory depth (default 3, max 6).",
                },
                "command": {
                    "type": "string",
                    "description": (
                        "For run action: custom command to execute (e.g. 'python app.py'). "
                        "If omitted, auto-detects based on project type."
                    ),
                },
                "run_type": {
                    "type": "string",
                    "enum": ["dev", "start", "build", "test", "install"],
                    "description": (
                        "For run action: what to run. 'dev' starts dev server, "
                        "'build' compiles, 'test' runs tests, 'install' installs deps. "
                        "Default: 'dev'."
                    ),
                },
            },
            "required": ["action"],
        }

    # ── Path resolution ──────────────────────────────────────────────────

    def _resolve_path(self, path: str) -> Path:
        """Resolve a path relative to the current project or as absolute."""
        if not path:
            if self._current_project:
                return self._current_project
            return Path.cwd()

        p = Path(os.path.expanduser(path))
        if p.is_absolute():
            return p
        if self._current_project:
            return self._current_project / p
        return Path.cwd() / p

    def _require_project(self) -> str | None:
        """Return an error string if no project is open, else None."""
        if self._current_project is None:
            return (
                "No project is open. Use action 'find_projects' to discover projects, "
                "then 'open_project' to set one as active."
            )
        return None

    # ── Main dispatch ────────────────────────────────────────────────────

    async def execute(
        self,
        action: str = "",
        path: str = "",
        scan_path: str = "",
        start_line: int = 1,
        end_line: int = 0,
        edit_type: str = "",
        content: str = "",
        find: str = "",
        replace: str = "",
        pattern: str = "",
        file_glob: str = "",
        depth: int = 3,
        command: str = "",
        run_type: str = "dev",
    ) -> str:
        try:
            match action:
                case "find_projects":
                    return await self._find_projects(scan_path)
                case "open_project":
                    return self._open_project(path)
                case "project_info":
                    return await self._project_info()
                case "tree":
                    return await self._tree(path, depth)
                case "read_file":
                    return self._read_file(path, start_line, end_line)
                case "edit_file":
                    return self._edit_file(
                        path, edit_type, content, start_line, end_line, find, replace
                    )
                case "create_file":
                    return self._create_file(path, content)
                case "search":
                    return await self._search(pattern, path, file_glob)
                case "run":
                    return await self._run(command, run_type)
                case "diff":
                    return await self._diff(path)
                case "undo":
                    return self._undo(path)
                case _:
                    return (
                        f"Unknown action: {action}. "
                        "Valid: find_projects, open_project, project_info, tree, "
                        "read_file, edit_file, create_file, search, run, diff, undo"
                    )
        except Exception as e:
            return f"Code editor error ({action}): {e}"

    # ── Action implementations ───────────────────────────────────────────

    async def _find_projects(self, scan_path: str) -> str:
        """Scan disk for code projects."""
        roots: list[Path] = []
        if scan_path:
            p = Path(os.path.expanduser(scan_path))
            if p.is_dir():
                roots = [p]
            else:
                return f"Scan path does not exist: {scan_path}"
        else:
            roots = [d for d in SCAN_DIRS if d.is_dir()]

        found: list[dict] = []
        visited: set[str] = set()

        for root in roots:
            self._scan_dir(root, found, visited, max_depth=2, current_depth=0)
            if len(found) >= 30:
                break

        if not found:
            return "No projects found. Try specifying a scan_path."

        # Sort by modification time (most recent first)
        found.sort(key=lambda p: p.get("mtime", 0), reverse=True)
        found = found[:30]

        lines = [f"Found {len(found)} project(s):\n"]
        for i, proj in enumerate(found, 1):
            lines.append(
                f"  {i}. {proj['name']} ({proj['language']})\n"
                f"     {proj['path']}"
            )

        return _truncate("\n".join(lines), 4000)

    def _scan_dir(
        self,
        directory: Path,
        found: list[dict],
        visited: set[str],
        max_depth: int,
        current_depth: int,
    ):
        """Recursively scan for projects."""
        resolved = str(directory.resolve())
        if resolved in visited or len(found) >= 30:
            return
        visited.add(resolved)

        try:
            entries = list(directory.iterdir())
        except PermissionError:
            return

        # Check if this directory is a project
        markers_found = []
        for entry in entries:
            if entry.name in PROJECT_MARKERS:
                markers_found.append(entry.name)

        if markers_found:
            try:
                mtime = directory.stat().st_mtime
            except Exception:
                mtime = 0
            found.append({
                "name": directory.name,
                "path": str(directory),
                "language": _detect_language(markers_found),
                "markers": markers_found,
                "mtime": mtime,
            })
            return  # Don't recurse into project subdirectories

        # Recurse into subdirectories
        if current_depth < max_depth:
            for entry in entries:
                if entry.is_dir() and not entry.name.startswith("."):
                    self._scan_dir(entry, found, visited, max_depth, current_depth + 1)

    def _open_project(self, path: str) -> str:
        """Set the active project."""
        if not path:
            return "Path is required for open_project."

        p = Path(os.path.expanduser(path)).resolve()
        if not p.is_dir():
            return f"Not a directory: {p}"

        self._current_project = p

        # Detect markers
        markers = [m for m in PROJECT_MARKERS if (p / m).exists()]
        language = _detect_language(markers) if markers else "Unknown"

        self._project_cache[str(p)] = {
            "language": language,
            "markers": markers,
        }

        return (
            f"Opened project: {p.name}\n"
            f"Path: {p}\n"
            f"Language: {language}\n"
            f"Markers: {', '.join(markers) if markers else 'none detected'}"
        )

    async def _project_info(self) -> str:
        """Show project metadata, key files, git status."""
        err = self._require_project()
        if err:
            return err

        root = self._current_project
        cache = self._project_cache.get(str(root), {})
        language = cache.get("language", "Unknown")
        markers = cache.get("markers", [])

        lines = [
            f"Project: {root.name}",
            f"Path: {root}",
            f"Language: {language}",
            f"Markers: {', '.join(markers) if markers else 'none'}",
            "",
        ]

        # Key files
        key_files = []
        for entry in sorted(root.iterdir()):
            name = entry.name.lower()
            if name.startswith("readme") or name.startswith("license") or \
               name == ".gitignore" or name in PROJECT_MARKERS or \
               name.endswith(".toml") or name.endswith(".cfg"):
                key_files.append(entry.name)
        if key_files:
            lines.append(f"Key files: {', '.join(key_files[:15])}")

        # Git info
        if (root / ".git").exists():
            status = await _run_git(root, "status", "--short")
            if status is not None:
                status_lines = status.strip().splitlines()
                if status_lines:
                    lines.append(f"\nGit status ({len(status_lines)} changed):")
                    for sl in status_lines[:10]:
                        lines.append(f"  {sl}")
                    if len(status_lines) > 10:
                        lines.append(f"  ... and {len(status_lines) - 10} more")
                else:
                    lines.append("\nGit: clean (no changes)")

            log = await _run_git(root, "log", "--oneline", "-5")
            if log:
                lines.append("\nRecent commits:")
                for ll in log.strip().splitlines():
                    lines.append(f"  {ll}")

            branch = await _run_git(root, "branch", "--show-current")
            if branch:
                lines.append(f"\nBranch: {branch.strip()}")

        # File count
        try:
            file_count = sum(1 for _ in root.rglob("*") if _.is_file())
            lines.append(f"\nTotal files: {file_count}")
        except Exception:
            pass

        return _truncate("\n".join(lines), 3000)

    async def _tree(self, path: str, depth: int) -> str:
        """Show directory tree."""
        err = self._require_project()
        if err:
            return err

        root = self._resolve_path(path)
        if not root.is_dir():
            return f"Not a directory: {root}"

        depth = max(1, min(depth, 6))

        # Try git ls-files for accuracy
        if (self._current_project / ".git").exists():
            git_files = await _run_git(
                self._current_project,
                "ls-files", "--cached", "--others", "--exclude-standard",
            )
            if git_files is not None:
                return self._build_tree_from_git(root, git_files, depth)

        # Fallback: manual walk
        patterns = _load_ignore_patterns(self._current_project)
        lines = [f"{root.name}/"]
        self._walk_tree(root, self._current_project, patterns, lines, depth, 0, "")

        return _truncate("\n".join(lines), 4000)

    def _build_tree_from_git(self, root: Path, git_output: str, depth: int) -> str:
        """Build tree from git ls-files output."""
        project_root = self._current_project
        try:
            rel_root = root.relative_to(project_root)
        except ValueError:
            rel_root = Path(".")

        # Filter files under the requested subdirectory
        files = []
        for line in git_output.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            p = Path(line)
            if rel_root == Path(".") or str(p).startswith(str(rel_root)):
                files.append(p)

        # Build tree structure
        tree: dict = {}
        for f in files:
            try:
                if rel_root != Path("."):
                    f = f.relative_to(rel_root)
            except ValueError:
                continue
            parts = f.parts
            if len(parts) > depth + 1:
                parts = parts[:depth + 1]
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part + "/", {})
            node[parts[-1]] = None  # leaf

        lines = [f"{root.name}/"]
        self._render_tree(tree, lines, "")
        return _truncate("\n".join(lines), 4000)

    def _render_tree(self, tree: dict, lines: list[str], prefix: str):
        """Render a tree dict into lines with box-drawing chars."""
        items = sorted(tree.keys(), key=lambda k: (not k.endswith("/"), k.lower()))
        for i, name in enumerate(items):
            is_last = i == len(items) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{name}")
            if tree[name] is not None:  # directory
                extension = "    " if is_last else "│   "
                self._render_tree(tree[name], lines, prefix + extension)

    def _walk_tree(
        self,
        directory: Path,
        project_root: Path,
        patterns: list[str],
        lines: list[str],
        max_depth: int,
        current_depth: int,
        prefix: str,
    ):
        """Manual tree walk respecting ignore patterns."""
        if current_depth >= max_depth:
            return

        try:
            entries = sorted(directory.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        except PermissionError:
            return

        visible = [e for e in entries if not _is_ignored(e, project_root, patterns)]

        for i, entry in enumerate(visible):
            is_last = i == len(visible) - 1
            connector = "└── " if is_last else "├── "
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{prefix}{connector}{entry.name}{suffix}")

            if entry.is_dir():
                extension = "    " if is_last else "│   "
                self._walk_tree(
                    entry, project_root, patterns, lines,
                    max_depth, current_depth + 1, prefix + extension,
                )

    def _read_file(self, path: str, start_line: int, end_line: int) -> str:
        """Read a file with line numbers."""
        if not path:
            err = self._require_project()
            if err:
                return err
            return "Path is required for read_file."

        file_path = self._resolve_path(path)
        if not file_path.is_file():
            return f"File not found: {file_path}"

        if _is_binary(file_path):
            return f"Binary file, cannot display: {file_path.name}"

        try:
            content = file_path.read_text(errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"

        all_lines = content.splitlines()
        total = len(all_lines)

        # Defaults
        start_line = max(1, start_line)
        if end_line <= 0:
            end_line = min(start_line + 99, total)
        end_line = min(end_line, total)

        # Detect language
        ext = file_path.suffix.lower()
        lang = EXTENSION_MAP.get(ext, ext.lstrip(".").upper() if ext else "Text")

        # Format
        selected = all_lines[start_line - 1:end_line]
        width = len(str(end_line))
        formatted = []
        for i, line in enumerate(selected, start=start_line):
            formatted.append(f"{i:>{width}} | {line}")

        header = f"File: {file_path.name} ({lang}) | Lines {start_line}-{end_line} of {total}"
        try:
            rel = file_path.relative_to(self._current_project) if self._current_project else file_path
            header = f"File: {rel} ({lang}) | Lines {start_line}-{end_line} of {total}"
        except ValueError:
            pass

        result = header + "\n" + "-" * len(header) + "\n" + "\n".join(formatted)
        return _truncate(result, 6000)

    def _edit_file(
        self,
        path: str,
        edit_type: str,
        content: str,
        start_line: int,
        end_line: int,
        find: str,
        replace_text: str,
    ) -> str:
        """Edit a file with various strategies."""
        if not path:
            return "Path is required for edit_file."

        file_path = self._resolve_path(path)
        if not file_path.is_file():
            return f"File not found: {file_path}"

        if _is_binary(file_path):
            return f"Cannot edit binary file: {file_path.name}"

        try:
            original = file_path.read_text(errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"

        match edit_type:
            case "find_replace":
                return self._do_find_replace(file_path, original, find, replace_text)
            case "replace_lines":
                return self._do_replace_lines(file_path, original, content, start_line, end_line)
            case "insert_before":
                return self._do_insert(file_path, original, content, start_line, before=True)
            case "insert_after":
                return self._do_insert(file_path, original, content, start_line, before=False)
            case "delete_lines":
                return self._do_delete_lines(file_path, original, start_line, end_line)
            case _:
                return (
                    f"Unknown edit_type: {edit_type}. "
                    "Use: find_replace, replace_lines, insert_before, insert_after, delete_lines"
                )

    def _do_find_replace(self, file_path: Path, original: str, find: str, replace_text: str) -> str:
        """Find exact text and replace it. Must match exactly once."""
        if not find:
            return "The 'find' parameter is required for find_replace."

        count = original.count(find)

        if count == 0:
            # Help the LLM: show similar lines
            lines = original.splitlines()
            find_lower = find.strip().lower()
            similar = []
            for i, line in enumerate(lines, 1):
                if any(word in line.lower() for word in find_lower.split()[:3]):
                    similar.append(f"  {i} | {line}")
                    if len(similar) >= 5:
                        break
            hint = "\n".join(similar) if similar else "  (no similar lines found)"
            return f"Text not found in {file_path.name}.\nSimilar lines:\n{hint}"

        if count > 1:
            # Show all occurrences
            positions = []
            search_from = 0
            lines = original.splitlines()
            for i, line in enumerate(lines, 1):
                if find in line or (search_from == 0 and find.split("\n")[0] in line):
                    positions.append(f"  Line {i}: {line.strip()[:80]}")
            return (
                f"Found {count} occurrences in {file_path.name}. "
                f"Please use a more unique search string.\n"
                f"Occurrences:\n" + "\n".join(positions[:10])
            )

        # Exactly one match — safe to replace
        self._edit_backups[str(file_path.resolve())] = original
        new_content = original.replace(find, replace_text, 1)
        file_path.write_text(new_content)

        return self._format_edit_result(file_path, original, new_content)

    def _do_replace_lines(
        self, file_path: Path, original: str, content: str, start: int, end: int
    ) -> str:
        """Replace lines start through end with new content."""
        lines = original.splitlines(keepends=True)
        total = len(lines)
        start = max(1, min(start, total))
        end = max(start, min(end, total)) if end > 0 else start

        self._edit_backups[str(file_path.resolve())] = original
        new_lines = content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        result_lines = lines[:start - 1] + new_lines + lines[end:]
        new_content = "".join(result_lines)
        file_path.write_text(new_content)

        return self._format_edit_result(file_path, original, new_content)

    def _do_insert(
        self, file_path: Path, original: str, content: str, line_num: int, before: bool
    ) -> str:
        """Insert content before or after a specific line."""
        lines = original.splitlines(keepends=True)
        total = len(lines)
        line_num = max(1, min(line_num, total))

        self._edit_backups[str(file_path.resolve())] = original
        new_lines = content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        idx = line_num - 1 if before else line_num

        result_lines = lines[:idx] + new_lines + lines[idx:]
        new_content = "".join(result_lines)
        file_path.write_text(new_content)

        pos = "before" if before else "after"
        return self._format_edit_result(file_path, original, new_content, f"Inserted {pos} line {line_num}")

    def _do_delete_lines(self, file_path: Path, original: str, start: int, end: int) -> str:
        """Delete lines from start to end inclusive."""
        lines = original.splitlines(keepends=True)
        total = len(lines)
        start = max(1, min(start, total))
        end = max(start, min(end, total)) if end > 0 else start

        self._edit_backups[str(file_path.resolve())] = original
        result_lines = lines[:start - 1] + lines[end:]
        new_content = "".join(result_lines)
        file_path.write_text(new_content)

        deleted_count = end - start + 1
        return self._format_edit_result(
            file_path, original, new_content, f"Deleted {deleted_count} line(s)"
        )

    def _format_edit_result(
        self, file_path: Path, old: str, new: str, action_desc: str = ""
    ) -> str:
        """Format a diff-style result showing what changed."""
        old_lines = old.splitlines()
        new_lines = new.splitlines()

        # Find the region that changed
        first_diff = 0
        for i in range(min(len(old_lines), len(new_lines))):
            if old_lines[i] != new_lines[i]:
                first_diff = i
                break
        else:
            first_diff = min(len(old_lines), len(new_lines))

        # Show context around the change
        ctx_start = max(0, first_diff - 2)
        ctx_end_old = min(len(old_lines), first_diff + 5)
        ctx_end_new = min(len(new_lines), first_diff + 5)

        name = file_path.name
        result = [f"Edited {name}"]
        if action_desc:
            result[0] += f" ({action_desc})"

        result.append(f"--- Before (lines {ctx_start+1}-{ctx_end_old}) ---")
        for i in range(ctx_start, ctx_end_old):
            result.append(f"  {i+1:>4} | {old_lines[i]}")

        result.append(f"--- After (lines {ctx_start+1}-{ctx_end_new}) ---")
        for i in range(ctx_start, ctx_end_new):
            result.append(f"  {i+1:>4} | {new_lines[i]}")

        result.append(f"\nFile now has {len(new_lines)} lines (was {len(old_lines)}).")
        return _truncate("\n".join(result), 3000)

    async def _search(self, pattern: str, path: str, file_glob: str) -> str:
        """Search for a pattern across project files."""
        err = self._require_project()
        if err:
            return err
        if not pattern:
            return "Pattern is required for search."

        root = self._current_project
        search_dir = self._resolve_path(path) if path else root

        # Try git grep first
        if (root / ".git").exists():
            args = ["grep", "-n", "--no-color", "-E", pattern]
            if file_glob:
                args.extend(["--", file_glob])
            elif path:
                args.extend(["--", str(search_dir.relative_to(root))])

            result = await _run_git(root, *args, timeout=15)
            if result is not None:
                return self._format_search_results(result, pattern)
            # git grep returns exit code 1 for "no matches"
            if result is None:
                # Check if it's just no matches vs actual error
                no_match = await _run_git(root, "grep", "-c", "-E", pattern)
                if no_match is not None and no_match.strip() == "":
                    return f"No matches for pattern: {pattern}"

        # Fallback: Python search
        return self._python_search(search_dir, root, pattern, file_glob)

    def _python_search(self, search_dir: Path, root: Path, pattern: str, file_glob: str) -> str:
        """Fallback search using Python re module."""
        patterns = _load_ignore_patterns(root)
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return f"Invalid regex pattern: {e}"

        results: dict[str, list[str]] = {}
        files_searched = 0
        max_files = 20
        max_per_file = 5

        for file_path in search_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if _is_ignored(file_path, root, patterns):
                continue
            if file_glob and not fnmatch.fnmatch(file_path.name, file_glob):
                continue
            if _is_binary(file_path):
                continue

            try:
                content = file_path.read_text(errors="replace")
            except Exception:
                continue

            matches = []
            for i, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    matches.append(f"  {i}: {line.strip()[:120]}")
                    if len(matches) >= max_per_file:
                        break

            if matches:
                try:
                    rel = str(file_path.relative_to(root))
                except ValueError:
                    rel = str(file_path)
                results[rel] = matches
                files_searched += 1
                if files_searched >= max_files:
                    break

        if not results:
            return f"No matches for pattern: {pattern}"

        return self._format_search_dict(results, pattern)

    def _format_search_results(self, git_output: str, pattern: str) -> str:
        """Format git grep output into grouped results."""
        results: dict[str, list[str]] = {}
        max_files = 20
        max_per_file = 5

        for line in git_output.strip().splitlines():
            if ":" not in line:
                continue
            # git grep format: file:line:content
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            filepath, lineno, content = parts[0], parts[1], parts[2]

            if filepath not in results:
                if len(results) >= max_files:
                    break
                results[filepath] = []
            if len(results[filepath]) < max_per_file:
                results[filepath].append(f"  {lineno}: {content.strip()[:120]}")

        return self._format_search_dict(results, pattern)

    def _format_search_dict(self, results: dict[str, list[str]], pattern: str) -> str:
        """Format search results dict into output string."""
        total_matches = sum(len(v) for v in results.values())
        lines = [f"Found {total_matches} match(es) in {len(results)} file(s) for: {pattern}\n"]

        for filepath, matches in results.items():
            lines.append(f"{filepath}:")
            lines.extend(matches)
            lines.append("")

        return _truncate("\n".join(lines), 5000)

    def _create_file(self, path: str, content: str) -> str:
        """Create a new file with content."""
        if not path:
            return "Path is required for create_file."

        file_path = self._resolve_path(path)

        if file_path.exists():
            return f"File already exists: {file_path.name}. Use edit_file to modify it."

        # Create parent directories if needed
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content or "")
        except Exception as e:
            return f"Error creating file: {e}"

        line_count = len((content or "").splitlines())
        try:
            rel = file_path.relative_to(self._current_project) if self._current_project else file_path
        except ValueError:
            rel = file_path

        return f"Created {rel} ({line_count} lines)"

    async def _run(self, command: str, run_type: str) -> str:
        """Run a project command (dev, build, test, install, or custom)."""
        err = self._require_project()
        if err:
            return err

        root = self._current_project
        run_type = run_type or "dev"

        # Detect virtualenv python if available
        venv_python = None
        for venv_dir in [".venv", "venv", "env"]:
            venv_bin = root / venv_dir / "bin" / "python"
            if venv_bin.exists():
                venv_python = str(venv_bin)
                break

        # Custom command takes priority
        if command:
            cmd = command
            # Auto-substitute python with venv python if available
            if venv_python and cmd.startswith(("python3 ", "python ")):
                cmd = venv_python + cmd[cmd.index(" "):]
        else:
            # Auto-detect from project markers
            cache = self._project_cache.get(str(root), {})
            markers = cache.get("markers", [])
            cmd = None

            for marker in markers:
                if marker in RUN_COMMANDS:
                    cmds = RUN_COMMANDS[marker]
                    cmd = cmds.get(run_type)
                    if cmd:
                        # Substitute project name
                        cmd = cmd.replace("{project_name}", root.name)
                        # Use venv python if available
                        if venv_python and cmd.startswith(("python3 ", "python ")):
                            cmd = venv_python + cmd[cmd.index(" "):]
                        elif venv_python and cmd.startswith(("pip3 ", "pip ")):
                            venv_pip = str(Path(venv_python).parent / "pip")
                            cmd = venv_pip + cmd[cmd.index(" "):]
                        break

            # Try to detect from package.json scripts
            if not cmd and (root / "package.json").exists():
                try:
                    import json
                    pkg = json.loads((root / "package.json").read_text())
                    scripts = pkg.get("scripts", {})
                    if run_type == "dev" and "dev" in scripts:
                        cmd = "npm run dev"
                    elif run_type == "start" and "start" in scripts:
                        cmd = "npm start"
                    elif run_type == "build" and "build" in scripts:
                        cmd = "npm run build"
                    elif run_type == "test" and "test" in scripts:
                        cmd = "npm test"
                except Exception:
                    pass

            if not cmd:
                # List available run types for this project
                available = []
                for marker in markers:
                    if marker in RUN_COMMANDS:
                        available.extend(RUN_COMMANDS[marker].keys())
                avail_str = ", ".join(sorted(set(available))) if available else "none detected"
                return (
                    f"Could not determine how to '{run_type}' this project.\n"
                    f"Available run types: {avail_str}\n"
                    f"Or provide a custom command."
                )

        logger.info(f"Running project command: {cmd} in {root}")

        # Execute with timeout (long-running commands get 60s of output)
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            # For dev/start commands (long-running), capture first 60s then report
            if run_type in ("dev", "start"):
                timeout = 15  # wait 15s for initial output
            else:
                timeout = 120  # build/test can take longer

            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                output = stdout.decode(errors="replace") if stdout else ""
                exit_code = proc.returncode

                result = f"Command: {cmd}\nExit code: {exit_code}\n\n"
                if output:
                    result += _truncate(output, 4000)
                else:
                    result += "(no output)"

                if exit_code != 0:
                    result += f"\n\n⚠ Command failed with exit code {exit_code}"

                return result

            except TimeoutError:
                # For dev servers: they don't exit, so capture what we have
                try:
                    proc.terminate()
                    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                    output = stdout.decode(errors="replace") if stdout else ""
                except Exception:
                    output = ""

                result = f"Command: {cmd}\n(timed out after {timeout}s — likely a running server)\n\n"
                if output:
                    result += _truncate(output, 4000)
                result += "\n\nTo keep a server running, use the process_manager tool instead."
                return result

        except Exception as e:
            return f"Error running command: {e}"

    async def _diff(self, path: str) -> str:
        """Show git diff of changes in the project."""
        err = self._require_project()
        if err:
            return err

        root = self._current_project
        if not (root / ".git").exists():
            return "Not a git repository — diff requires git."

        if path:
            file_path = self._resolve_path(path)
            try:
                rel = str(file_path.relative_to(root))
            except ValueError:
                rel = path
            # Diff for specific file
            result = await _run_git(root, "diff", "--", rel, timeout=10)
            staged = await _run_git(root, "diff", "--staged", "--", rel, timeout=10)
        else:
            # Full project diff
            result = await _run_git(root, "diff", timeout=10)
            staged = await _run_git(root, "diff", "--staged", timeout=10)

        lines = []

        if staged and staged.strip():
            lines.append("=== Staged changes ===")
            lines.append(staged.strip())

        if result and result.strip():
            if lines:
                lines.append("")
            lines.append("=== Unstaged changes ===")
            lines.append(result.strip())

        if not lines:
            # Check for untracked files
            untracked = await _run_git(root, "ls-files", "--others", "--exclude-standard")
            if untracked and untracked.strip():
                new_files = untracked.strip().splitlines()
                lines.append(f"No modifications, but {len(new_files)} untracked file(s):")
                for f in new_files[:10]:
                    lines.append(f"  + {f}")
                if len(new_files) > 10:
                    lines.append(f"  ... and {len(new_files) - 10} more")
            else:
                return "No changes detected (working tree clean)."

        return _truncate("\n".join(lines), 5000)

    def _undo(self, path: str) -> str:
        """Revert the last edit to a file."""
        if not path:
            return "Path is required for undo."

        file_path = self._resolve_path(path).resolve()
        key = str(file_path)

        if key not in self._edit_backups:
            return f"No edit history for: {file_path.name}"

        backup = self._edit_backups.pop(key)
        file_path.write_text(backup)

        lines = backup.splitlines()
        return f"Reverted {file_path.name} to previous version ({len(lines)} lines)."
