"""Text manipulation tool."""

from __future__ import annotations

import re
from collections import Counter

from saladbox.tools.base import BaseTool


class TextTool(BaseTool):
    """Text manipulation and analysis utilities."""

    @property
    def name(self) -> str:
        return "text"

    @property
    def description(self) -> str:
        return (
            "Manipulate and analyze text: case conversion, sort, unique, count, "
            "replace, trim, extract patterns, and format. Useful for text processing "
            "and data cleaning."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "upper",
                        "lower",
                        "title",
                        "capitalize",
                        "swapcase",
                        "sort",
                        "sort_reverse",
                        "unique",
                        "reverse",
                        "count",
                        "count_words",
                        "count_lines",
                        "count_chars",
                        "replace",
                        "trim",
                        "strip_empty",
                        "number_lines",
                        "extract",
                        "split",
                        "join",
                        "dedupe_lines",
                    ],
                    "description": "Text operation to perform",
                },
                "text": {
                    "type": "string",
                    "description": "Text to process",
                },
                "pattern": {
                    "type": "string",
                    "description": "Pattern for replace, extract, or split actions",
                },
                "replacement": {
                    "type": "string",
                    "description": "Replacement text for replace action",
                },
                "delimiter": {
                    "type": "string",
                    "description": "Delimiter for split or join actions (default: newline)",
                },
            },
            "required": ["action", "text"],
        }

    async def execute(
        self,
        action: str,
        text: str,
        pattern: str | None = None,
        replacement: str | None = None,
        delimiter: str | None = None,
    ) -> str:
        try:
            if action == "upper":
                return text.upper()

            elif action == "lower":
                return text.lower()

            elif action == "title":
                return text.title()

            elif action == "capitalize":
                return text.capitalize()

            elif action == "swapcase":
                return text.swapcase()

            elif action == "sort":
                lines = text.split("\n")
                return "\n".join(sorted(lines))

            elif action == "sort_reverse":
                lines = text.split("\n")
                return "\n".join(sorted(lines, reverse=True))

            elif action == "unique":
                lines = text.split("\n")
                seen = []
                for line in lines:
                    if line not in seen:
                        seen.append(line)
                return "\n".join(seen)

            elif action == "reverse":
                return text[::-1]

            elif action == "count":
                counter = Counter(text)
                most_common = counter.most_common(20)
                result = [f"Total characters: {len(text)}"]
                result.append("\nMost common characters:")
                for char, count in most_common:
                    if char.isprintable() and char != " ":
                        result.append(f"  '{char}': {count}")
                return "\n".join(result)

            elif action == "count_words":
                words = text.split()
                word_freq = Counter(word.lower().strip(".,!?;:\"'") for word in words)
                result = [f"Total words: {len(words)}"]
                result.append(f"Unique words: {len(word_freq)}")
                result.append("\nMost common words:")
                for word, count in word_freq.most_common(15):
                    result.append(f"  {word}: {count}")
                return "\n".join(result)

            elif action == "count_lines":
                lines = text.split("\n")
                non_empty = [l for l in lines if l.strip()]
                return f"Total lines: {len(lines)}\nNon-empty lines: {len(non_empty)}"

            elif action == "count_chars":
                chars = len(text)
                chars_no_space = len(
                    text.replace(" ", "").replace("\n", "").replace("\t", "")
                )
                words = len(text.split())
                lines = len(text.split("\n"))
                return (
                    f"Characters: {chars}\n"
                    f"Characters (no spaces): {chars_no_space}\n"
                    f"Words: {words}\n"
                    f"Lines: {lines}"
                )

            elif action == "replace":
                if pattern is None or replacement is None:
                    return (
                        "Error: 'pattern' and 'replacement' required for replace action"
                    )
                result = text.replace(pattern, replacement)
                count = text.count(pattern)
                return f"Replaced {count} occurrences:\n{result}"

            elif action == "trim":
                lines = text.split("\n")
                trimmed = [line.strip() for line in lines]
                return "\n".join(trimmed)

            elif action == "strip_empty":
                lines = text.split("\n")
                non_empty = [l for l in lines if l.strip()]
                return "\n".join(non_empty)

            elif action == "number_lines":
                lines = text.split("\n")
                numbered = [f"{i + 1:4}: {line}" for i, line in enumerate(lines)]
                return "\n".join(numbered)

            elif action == "extract":
                if pattern is None:
                    return "Error: 'pattern' required for extract action"
                matches = re.findall(pattern, text)
                if not matches:
                    return "No matches found"
                return f"Found {len(matches)} matches:\n" + "\n".join(
                    str(m) for m in matches[:50]
                )

            elif action == "split":
                delim = delimiter or "\n"
                parts = text.split(delim)
                result = [f"Split into {len(parts)} parts:"]
                for i, part in enumerate(parts[:20]):
                    preview = part[:50] + "..." if len(part) > 50 else part
                    result.append(f"{i + 1}. {preview}")
                return "\n".join(result)

            elif action == "join":
                delim = delimiter or " "
                lines = [l for l in text.split("\n") if l.strip()]
                return delim.join(lines)

            elif action == "dedupe_lines":
                lines = text.split("\n")
                seen = set()
                unique_lines = []
                for line in lines:
                    if line not in seen:
                        seen.add(line)
                        unique_lines.append(line)
                removed = len(lines) - len(unique_lines)
                result = "\n".join(unique_lines)
                return f"Removed {removed} duplicate lines:\n{result}"

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            return f"Error: {e!s}"
