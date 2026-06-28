"""Encoding and hashing tool."""

from __future__ import annotations

import base64
import hashlib
import uuid as uuid_lib
import secrets
import string
from typing import Optional

from saladbox.tools.base import BaseTool


class EncodingTool(BaseTool):
    """Encoding, decoding, hashing, and UUID generation."""

    @property
    def name(self) -> str:
        return "encoding"

    @property
    def description(self) -> str:
        return (
            "Encode/decode Base64, URL-encode/decode, generate hashes (MD5, SHA), "
            "create UUIDs, and generate random strings. Useful for data transformation "
            "and security operations."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "base64_encode",
                        "base64_decode",
                        "url_encode",
                        "url_decode",
                        "html_encode",
                        "html_decode",
                        "hash",
                        "uuid",
                        "random_string",
                    ],
                    "description": "The encoding operation to perform",
                },
                "data": {
                    "type": "string",
                    "description": "Data to encode, decode, or hash",
                },
                "algorithm": {
                    "type": "string",
                    "enum": ["md5", "sha1", "sha256", "sha512"],
                    "description": "Hash algorithm (for hash action)",
                },
                "length": {
                    "type": "integer",
                    "description": "Length for random string (default: 16)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        data: Optional[str] = None,
        algorithm: str = "sha256",
        length: int = 16,
    ) -> str:
        try:
            if action == "base64_encode":
                if data is None:
                    return "Error: 'data' required for encoding"
                encoded = base64.b64encode(data.encode("utf-8")).decode("utf-8")
                return f"Base64 encoded:\n{encoded}"

            elif action == "base64_decode":
                if data is None:
                    return "Error: 'data' required for decoding"
                try:
                    decoded = base64.b64decode(data).decode("utf-8")
                    return f"Base64 decoded:\n{decoded}"
                except Exception:
                    decoded = base64.b64decode(data).hex()
                    return f"Base64 decoded (hex):\n{decoded}"

            elif action == "url_encode":
                if data is None:
                    return "Error: 'data' required for encoding"
                from urllib.parse import quote

                encoded = quote(data, safe="")
                return f"URL encoded:\n{encoded}"

            elif action == "url_decode":
                if data is None:
                    return "Error: 'data' required for decoding"
                from urllib.parse import unquote

                decoded = unquote(data)
                return f"URL decoded:\n{decoded}"

            elif action == "html_encode":
                if data is None:
                    return "Error: 'data' required for encoding"
                import html

                encoded = html.escape(data)
                return f"HTML encoded:\n{encoded}"

            elif action == "html_decode":
                if data is None:
                    return "Error: 'data' required for decoding"
                import html

                decoded = html.unescape(data)
                return f"HTML decoded:\n{decoded}"

            elif action == "hash":
                if data is None:
                    return "Error: 'data' required for hashing"
                algo = algorithm.lower()
                if algo == "md5":
                    result = hashlib.md5(data.encode("utf-8")).hexdigest()
                elif algo == "sha1":
                    result = hashlib.sha1(data.encode("utf-8")).hexdigest()
                elif algo == "sha256":
                    result = hashlib.sha256(data.encode("utf-8")).hexdigest()
                elif algo == "sha512":
                    result = hashlib.sha512(data.encode("utf-8")).hexdigest()
                else:
                    return f"Unknown algorithm: {algorithm}"
                return f"{algorithm.upper()} hash:\n{result}"

            elif action == "uuid":
                generated = str(uuid_lib.uuid4())
                return f"UUID v4: {generated}"

            elif action == "random_string":
                length = max(4, min(128, length))
                chars = string.ascii_letters + string.digits
                result = "".join(secrets.choice(chars) for _ in range(length))
                return f"Random string ({length} chars):\n{result}"

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            return f"Error: {str(e)}"
