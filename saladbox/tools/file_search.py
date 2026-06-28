"""High-performance local file indexing and full-text search tool using SQLite."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from saladbox.tools.base import BaseTool

# Directories to skip entirely
_EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".claude",
    "__pycache__",
    "saladbox.egg-info",
}

# Text file extensions to index
_TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".html", ".css", ".md", ".json", ".yaml", ".yml",
    ".txt", ".sh", ".toml", ".ini", ".cfg", ".sql", ".rs", ".go", ".c", ".cpp",
    ".h", ".java", ".xml", ".csv"
}

# Maximum file size to index (1 MB)
_MAX_FILE_SIZE = 1 * 1024 * 1024

class FileSearchTool(BaseTool):
    """Index directories and search file contents locally using SQLite."""

    def __init__(self):
        super().__init__()
        # Store index in data directory
        os.makedirs("data", exist_ok=True)
        self.db_path = "data/file_index.db"
        self._init_db()

    @property
    def name(self) -> str:
        return "file_search"

    @property
    def description(self) -> str:
        return (
            "Index files in a directory and perform fast full-text searches. "
            "Actions: 'index' (recursively index text files), "
            "'search' (search for a phrase or keyword in indexed file contents), "
            "'status' (get summary of the current index)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["index", "search", "status"],
                    "description": "The search action to perform",
                },
                "directory": {
                    "type": "string",
                    "description": "Root directory to index (required for 'index' action)",
                },
                "query": {
                    "type": "string",
                    "description": "Search keyword or text query (required for 'search' action)",
                },
            },
            "required": ["action"],
        }

    def _init_db(self):
        """Initialise SQLite database tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Primary file metadata table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS indexed_files (
                path TEXT PRIMARY KEY,
                filename TEXT,
                last_modified REAL,
                size INTEGER
            )
            """
        )
        
        # Determine FTS support (FTS5 -> FTS4 -> Standard fallback)
        self.fts_version = "standard"
        try:
            cursor.execute("CREATE VIRTUAL TABLE fts_test USING fts5(content)")
            cursor.execute("DROP TABLE fts_test")
            self.fts_version = "fts5"
        except sqlite3.OperationalError:
            try:
                cursor.execute("CREATE VIRTUAL TABLE fts_test USING fts4(content)")
                cursor.execute("DROP TABLE fts_test")
                self.fts_version = "fts4"
            except sqlite3.OperationalError:
                pass

        if self.fts_version == "fts5":
            cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts5(
                    path, filename, content, tokenize='porter unicode61'
                )
                """
            )
        elif self.fts_version == "fts4":
            cursor.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_index USING fts4(
                    path, filename, content, tokenize=porter
                )
                """
            )
        else:
            # Fallback standard table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS fts_index (
                    path TEXT PRIMARY KEY,
                    filename TEXT,
                    content TEXT
                )
                """
            )
            
        conn.commit()
        conn.close()

    def _is_binary(self, filepath: str) -> bool:
        """Check if file is binary by looking for null bytes."""
        try:
            with open(filepath, "rb") as f:
                chunk = f.read(1024)
                return b"\x00" in chunk
        except Exception:
            return True

    async def execute(
        self,
        action: str,
        directory: str = "",
        query: str = "",
    ) -> str:
        if action == "status":
            return self._status()
        elif action == "index":
            if not directory:
                return "Error: 'directory' is required for the 'index' action."
            return self._index(directory)
        elif action == "search":
            if not query:
                return "Error: 'query' is required for the 'search' action."
            return self._search(query)
        return f"Unknown action: {action}"

    def _status(self) -> str:
        """Get database indexing stats."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), SUM(size) FROM indexed_files")
        count, total_size = cursor.fetchone()
        conn.close()
        
        size_str = f"{total_size / 1024 / 1024:.2f} MB" if total_size else "0 Bytes"
        return (
            f"**File Index Status**\n"
            f"- Total Files Indexed: {count or 0}\n"
            f"- Total Size Indexed: {size_str}\n"
            f"- Search Engine: {self.fts_version.upper()}"
        )

    def _index(self, directory: str) -> str:
        """Walk directory and build/update index."""
        dir_path = Path(os.path.expanduser(directory)).resolve()
        if not dir_path.is_dir():
            return f"Error: Directory '{directory}' does not exist."

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        indexed_count = 0
        skipped_count = 0
        
        for root, dirs, files in os.walk(str(dir_path)):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIRS]
            
            for file in files:
                filepath = os.path.join(root, file)
                path_obj = Path(filepath)
                
                # Check extension and size rules
                if path_obj.suffix.lower() not in _TEXT_EXTENSIONS:
                    skipped_count += 1
                    continue
                    
                try:
                    stat = path_obj.stat()
                    if stat.st_size > _MAX_FILE_SIZE:
                        skipped_count += 1
                        continue
                        
                    # Check db if file is already up to date
                    cursor.execute("SELECT last_modified, size FROM indexed_files WHERE path = ?", (filepath,))
                    row = cursor.fetchone()
                    if row and row[0] == stat.st_mtime and row[1] == stat.st_size:
                        continue
                        
                    # Verify text file
                    if self._is_binary(filepath):
                        skipped_count += 1
                        continue
                        
                    # Read text content
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        # Index first 200KB of file max to prevent DB bloat
                        content = f.read(200 * 1024)
                        
                    # Update DB (untrack existing first)
                    cursor.execute("DELETE FROM indexed_files WHERE path = ?", (filepath,))
                    if self.fts_version in ("fts5", "fts4"):
                        cursor.execute("DELETE FROM fts_index WHERE path = ?", (filepath,))
                    else:
                        cursor.execute("DELETE FROM fts_index WHERE path = ?", (filepath,))
                        
                    cursor.execute(
                        "INSERT INTO indexed_files (path, filename, last_modified, size) VALUES (?, ?, ?, ?)",
                        (filepath, file, stat.st_mtime, stat.st_size)
                    )
                    
                    if self.fts_version in ("fts5", "fts4"):
                        cursor.execute(
                            "INSERT INTO fts_index (path, filename, content) VALUES (?, ?, ?)",
                            (filepath, file, content)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO fts_index (path, filename, content) VALUES (?, ?, ?)",
                            (filepath, file, content)
                        )
                    
                    indexed_count += 1
                    
                except Exception:
                    skipped_count += 1
                    
        conn.commit()
        conn.close()
        
        return (
            f"**Indexing Completed**\n"
            f"- Directory: `{dir_path}`\n"
            f"- New/Updated files indexed: {indexed_count}\n"
            f"- Non-indexed/skipped files: {skipped_count}"
        )

    def _search(self, query: str) -> str:
        """Search contents of indexed files."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        results = []
        
        if self.fts_version in ("fts5", "fts4"):
            # Use SQLite full text search matching
            cursor.execute(
                """
                SELECT path, filename, content 
                FROM fts_index 
                WHERE fts_index MATCH ? 
                LIMIT 30
                """,
                (query,)
            )
            results = cursor.fetchall()
        else:
            # Fallback to standard LIKE matching
            cursor.execute(
                """
                SELECT path, filename, content 
                FROM fts_index 
                WHERE content LIKE ? OR filename LIKE ? 
                LIMIT 30
                """,
                (f"%{query}%", f"%{query}%")
            )
            results = cursor.fetchall()
            
        conn.close()
        
        if not results:
            return f"No results found for query: '{query}'"
            
        # Format results with context snippets
        output = [f"### Search Results for: '{query}' (showing up to 30 matches)\n"]
        
        for path, filename, content in results:
            # Find context snippets in the file content
            lines = content.splitlines()
            matches = []
            for i, line in enumerate(lines):
                if query.lower() in line.lower():
                    # Show line number and trimmed content
                    matches.append(f"  Line {i+1}: {line.strip()[:100]}")
                    if len(matches) >= 3: # limit to 3 snippets per file
                        break
            
            snippets_str = "\n".join(matches) if matches else "  (Filename matched)"
            output.append(f"- **{filename}** — `{path}`\n{snippets_str}\n")
            
        return "\n".join(output)
