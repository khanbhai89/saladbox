"""Notes and knowledge storage tool."""

from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime

from saladbox.tools.base import BaseTool


class NotesTool(BaseTool):
    """Store and retrieve notes, creating a simple knowledge base."""

    def __init__(self):
        self.notes_dir = os.path.expanduser("~/.saladbox/notes")
        os.makedirs(self.notes_dir, exist_ok=True)
        self.index_file = os.path.join(self.notes_dir, "_index.json")
        self._load_index()

    def _load_index(self) -> dict:
        if os.path.exists(self.index_file):
            try:
                with open(self.index_file) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _save_index(self, index: dict) -> None:
        with open(self.index_file, "w") as f:
            json.dump(index, f, indent=2)

    @property
    def name(self) -> str:
        return "notes"

    @property
    def description(self) -> str:
        return (
            "Store and retrieve notes for persistent memory. Create notes to remember "
            "information across conversations. Use tags to organize notes. Search notes "
            "by content or tags. Great for user preferences, facts, and reference material."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "get", "list", "search", "delete", "tag"],
                    "description": "Note operation to perform",
                },
                "title": {
                    "type": "string",
                    "description": "Note title (for add, get, delete actions)",
                },
                "content": {
                    "type": "string",
                    "description": "Note content (for add action)",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags for the note",
                },
                "query": {
                    "type": "string",
                    "description": "Search query (for search action)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of notes to return (default: 10)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        title: str | None = None,
        content: str | None = None,
        tags: str | None = None,
        query: str | None = None,
        limit: int = 10,
    ) -> str:
        if action == "add":
            if not title or not content:
                return "Error: title and content required for add action"
            return self._add_note(title, content, tags)
        elif action == "get":
            if not title:
                return "Error: title required for get action"
            return self._get_note(title)
        elif action == "list":
            return self._list_notes(tags, limit)
        elif action == "search":
            if not query:
                return "Error: query required for search action"
            return self._search_notes(query, limit)
        elif action == "delete":
            if not title:
                return "Error: title required for delete action"
            return self._delete_note(title)
        elif action == "tag":
            if not title or not tags:
                return "Error: title and tags required for tag action"
            return self._tag_note(title, tags)
        else:
            return f"Unknown action: {action}"

    def _add_note(self, title: str, content: str, tags: str | None) -> str:
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
        note_file = os.path.join(self.notes_dir, f"{safe_title}.json")

        tag_list = []
        if tags:
            tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]

        note_data = {
            "title": title,
            "content": content,
            "tags": tag_list,
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat(),
        }

        index = self._load_index()
        index[title] = {
            "file": f"{safe_title}.json",
            "tags": tag_list,
            "created": note_data["created"],
            "preview": content[:100] + "..." if len(content) > 100 else content,
        }
        self._save_index(index)

        with open(note_file, "w") as f:
            json.dump(note_data, f, indent=2)

        return f"Note '{title}' saved successfully with tags: {', '.join(tag_list) if tag_list else 'none'}"

    def _get_note(self, title: str) -> str:
        index = self._load_index()

        for note_title, note_info in index.items():
            if note_title.lower() == title.lower():
                note_file = os.path.join(self.notes_dir, note_info["file"])
                try:
                    with open(note_file) as f:
                        note_data = json.load(f)
                    tags_str = ", ".join(note_data.get("tags", []))
                    return (
                        f"**{note_data['title']}**\n"
                        f"Tags: {tags_str or 'none'}\n"
                        f"Created: {note_data['created']}\n"
                        f"Modified: {note_data['modified']}\n\n"
                        f"{note_data['content']}"
                    )
                except (OSError, json.JSONDecodeError) as e:
                    return f"Error reading note: {e!s}"

        return f"Note '{title}' not found"

    def _list_notes(self, tags: str | None, limit: int) -> str:
        index = self._load_index()

        if not index:
            return "No notes found. Use 'add' action to create a note."

        filter_tags = []
        if tags:
            filter_tags = [t.strip().lower() for t in tags.split(",")]

        notes = []
        for title, info in index.items():
            if filter_tags and not any(t in info.get("tags", []) for t in filter_tags):
                continue
            notes.append((title, info))

        notes = sorted(notes, key=lambda x: x[1].get("created", ""), reverse=True)[
            :limit
        ]

        if not notes:
            return f"No notes found with tags: {tags}"

        result = [f"**Notes ({len(notes)} of {len(index)}):**\n"]
        for title, info in notes:
            tags_str = ", ".join(info.get("tags", []))
            result.append(f"- **{title}**")
            if tags_str:
                result.append(f"  Tags: {tags_str}")
            result.append(f"  Preview: {info.get('preview', '')}")
            result.append("")

        return "\n".join(result)

    def _search_notes(self, query: str, limit: int) -> str:
        index = self._load_index()

        if not index:
            return "No notes to search."

        query_lower = query.lower()
        matches = []

        for title, info in index.items():
            score = 0
            if query_lower in title.lower():
                score += 10
            if query_lower in info.get("preview", "").lower():
                score += 5
            if any(query_lower in t for t in info.get("tags", [])):
                score += 3

            if score > 0:
                matches.append((title, info, score))

        if not matches:
            return f"No notes matching '{query}'"

        matches.sort(key=lambda x: x[2], reverse=True)
        matches = matches[:limit]

        result = [f"**Search results for '{query}':**\n"]
        for title, info, score in matches:
            tags_str = ", ".join(info.get("tags", []))
            result.append(f"- **{title}**")
            if tags_str:
                result.append(f"  Tags: {tags_str}")
            result.append(f"  Preview: {info.get('preview', '')}")
            result.append("")

        return "\n".join(result)

    def _delete_note(self, title: str) -> str:
        index = self._load_index()

        for note_title, note_info in list(index.items()):
            if note_title.lower() == title.lower():
                note_file = os.path.join(self.notes_dir, note_info["file"])
                with contextlib.suppress(OSError):
                    os.remove(note_file)

                del index[note_title]
                self._save_index(index)
                return f"Note '{note_title}' deleted successfully"

        return f"Note '{title}' not found"

    def _tag_note(self, title: str, tags: str) -> str:
        index = self._load_index()

        for note_title, note_info in index.items():
            if note_title.lower() == title.lower():
                note_file = os.path.join(self.notes_dir, note_info["file"])
                try:
                    with open(note_file) as f:
                        note_data = json.load(f)

                    new_tags = [t.strip().lower() for t in tags.split(",") if t.strip()]
                    existing_tags = note_data.get("tags", [])

                    for tag in new_tags:
                        if tag not in existing_tags:
                            existing_tags.append(tag)

                    note_data["tags"] = existing_tags
                    note_data["modified"] = datetime.now().isoformat()

                    with open(note_file, "w") as f:
                        json.dump(note_data, f, indent=2)

                    note_info["tags"] = existing_tags
                    self._save_index(index)

                    return f"Added tags to '{note_title}': {', '.join(new_tags)}"
                except (OSError, json.JSONDecodeError) as e:
                    return f"Error updating note: {e!s}"

        return f"Note '{title}' not found"
