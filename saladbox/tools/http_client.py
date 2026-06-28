"""HTTP client tool for making API requests."""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from saladbox.tools.base import BaseTool


class HttpClientTool(BaseTool):
    """Make HTTP requests to external APIs."""

    @property
    def name(self) -> str:
        return "http_client"

    @property
    def description(self) -> str:
        return (
            "Make HTTP requests (GET, POST, PUT, DELETE, PATCH) to any URL. "
            "Useful for calling APIs, fetching web content, or testing endpoints. "
            "Supports custom headers and JSON request bodies."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"],
                    "description": "HTTP method",
                },
                "url": {
                    "type": "string",
                    "description": "The URL to request",
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers as key-value pairs",
                },
                "body": {
                    "type": "object",
                    "description": "Request body (will be sent as JSON)",
                },
                "params": {
                    "type": "object",
                    "description": "Query parameters as key-value pairs",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30)",
                },
            },
            "required": ["method", "url"],
        }

    async def execute(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        timeout: int = 30,
    ) -> str:
        if not url.startswith(("http://", "https://")):
            return "Error: URL must start with http:// or https://"

        method = method.upper()
        request_headers = headers or {}
        request_headers.setdefault("User-Agent", "Saladbox/1.0")

        try:
            async with aiohttp.ClientSession() as session:
                request_kwargs = {
                    "headers": request_headers,
                    "params": params,
                    "timeout": aiohttp.ClientTimeout(total=timeout),
                }

                if body and method in ["POST", "PUT", "PATCH"]:
                    request_kwargs["json"] = body

                async with session.request(method, url, **request_kwargs) as resp:
                    response_headers = dict(resp.headers)

                    try:
                        response_body = await resp.json()
                        body_str = json.dumps(response_body, indent=2)
                    except (json.JSONDecodeError, aiohttp.ContentTypeError):
                        body_str = await resp.text()
                        if len(body_str) > 2000:
                            body_str = body_str[:2000] + "\n... (truncated)"

                    result = [
                        f"**Status:** {resp.status} {resp.reason}",
                        f"**URL:** {resp.url!s}",
                        "\n**Headers:**",
                    ]

                    for key, value in list(response_headers.items())[:10]:
                        result.append(f"  {key}: {value}")

                    result.append(f"\n**Body:**\n{body_str}")

                    return "\n".join(result)

        except aiohttp.ClientError as e:
            return f"HTTP error: {e!s}"
        except Exception as e:
            return f"Unexpected error: {e!s}"
