"""URL parsing and manipulation tool."""

from __future__ import annotations

from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
from typing import Optional

from saladbox.tools.base import BaseTool


class URLTool(BaseTool):
    """Parse, build, and manipulate URLs."""

    @property
    def name(self) -> str:
        return "url"

    @property
    def description(self) -> str:
        return (
            "Parse URLs into components, build URLs from parts, extract query parameters, "
            "and manipulate URL components. Useful for web scraping, API work, and link analysis."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "parse",
                        "build",
                        "query",
                        "extract_domain",
                        "join",
                        "is_valid",
                    ],
                    "description": "URL operation to perform",
                },
                "url": {
                    "type": "string",
                    "description": "URL to process",
                },
                "scheme": {
                    "type": "string",
                    "description": "URL scheme (http, https, etc.)",
                },
                "host": {
                    "type": "string",
                    "description": "Host/domain name",
                },
                "port": {
                    "type": "integer",
                    "description": "Port number",
                },
                "path": {
                    "type": "string",
                    "description": "URL path",
                },
                "query": {
                    "type": "string",
                    "description": "Query string or parameters",
                },
                "fragment": {
                    "type": "string",
                    "description": "URL fragment (after #)",
                },
                "base_url": {
                    "type": "string",
                    "description": "Base URL for joining",
                },
                "relative_url": {
                    "type": "string",
                    "description": "Relative URL to join with base",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        url: Optional[str] = None,
        scheme: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        path: Optional[str] = None,
        query: Optional[str] = None,
        fragment: Optional[str] = None,
        base_url: Optional[str] = None,
        relative_url: Optional[str] = None,
    ) -> str:
        if action == "parse":
            if not url:
                return "Error: 'url' required for parse action"
            return self._parse_url(url)

        elif action == "build":
            return self._build_url(scheme, host, port, path, query, fragment)

        elif action == "query":
            if not url:
                return "Error: 'url' required for query action"
            return self._parse_query(url)

        elif action == "extract_domain":
            if not url:
                return "Error: 'url' required for extract_domain action"
            return self._extract_domain(url)

        elif action == "join":
            if not base_url or not relative_url:
                return "Error: 'base_url' and 'relative_url' required for join action"
            return self._join_urls(base_url, relative_url)

        elif action == "is_valid":
            if not url:
                return "Error: 'url' required for is_valid action"
            return self._validate_url(url)

        else:
            return f"Unknown action: {action}"

    def _parse_url(self, url: str) -> str:
        try:
            parsed = urlparse(url)

            result = ["**URL Components**\n"]
            result.append(f"Scheme: {parsed.scheme or 'none'}")
            result.append(f"Host: {parsed.hostname or 'none'}")
            result.append(f"Port: {parsed.port or 'default'}")
            result.append(f"Path: {parsed.path or '/'}")
            result.append(f"Query: {parsed.query or 'none'}")
            result.append(f"Fragment: {parsed.fragment or 'none'}")

            if parsed.username or parsed.password:
                result.append(f"Username: {parsed.username or 'none'}")
                result.append(f"Password: {'***' if parsed.password else 'none'}")

            return "\n".join(result)

        except Exception as e:
            return f"Error parsing URL: {str(e)}"

    def _build_url(
        self,
        scheme: Optional[str],
        host: Optional[str],
        port: Optional[int],
        path: Optional[str],
        query: Optional[str],
        fragment: Optional[str],
    ) -> str:
        if not host:
            return "Error: 'host' required to build URL"

        scheme = scheme or "https"
        path = path or "/"

        netloc = host
        if port:
            netloc = f"{host}:{port}"

        built_url = urlunparse((scheme, netloc, path, "", query or "", fragment or ""))

        return f"Built URL: {built_url}"

    def _parse_query(self, url: str) -> str:
        try:
            parsed = urlparse(url)

            if not parsed.query:
                return "No query parameters found in URL"

            params = parse_qs(parsed.query)

            result = ["**Query Parameters**\n"]

            for key, values in sorted(params.items()):
                if len(values) == 1:
                    result.append(f"- `{key}`: {values[0]}")
                else:
                    result.append(f"- `{key}`: {', '.join(values)}")

            result.append(f"\n**Full Query String:**\n{parsed.query}")

            return "\n".join(result)

        except Exception as e:
            return f"Error parsing query: {str(e)}"

    def _extract_domain(self, url: str) -> str:
        try:
            parsed = urlparse(url)

            if not parsed.hostname:
                if not url.startswith(("http://", "https://")):
                    parsed = urlparse(f"https://{url}")

            hostname = parsed.hostname or url

            parts = hostname.split(".")

            if len(parts) >= 2:
                domain = ".".join(parts[-2:])
                subdomain = ".".join(parts[:-2]) if len(parts) > 2 else "none"
            else:
                domain = hostname
                subdomain = "none"

            return (
                f"**Domain Analysis**\n"
                f"Hostname: {hostname}\n"
                f"Domain: {domain}\n"
                f"Subdomain: {subdomain}\n"
                f"TLD: {parts[-1] if parts else 'none'}"
            )

        except Exception as e:
            return f"Error extracting domain: {str(e)}"

    def _join_urls(self, base_url: str, relative_url: str) -> str:
        try:
            from urllib.parse import urljoin

            joined = urljoin(base_url, relative_url)

            return f"**URL Join Result**\nBase: {base_url}\nRelative: {relative_url}\nResult: {joined}"

        except Exception as e:
            return f"Error joining URLs: {str(e)}"

    def _validate_url(self, url: str) -> str:
        issues = []

        if not url:
            return "Invalid: URL is empty"

        try:
            parsed = urlparse(url)

            if not parsed.scheme:
                issues.append("Missing scheme (http:// or https://)")
            elif parsed.scheme not in ("http", "https", "ftp", "file"):
                issues.append(f"Unusual scheme: {parsed.scheme}")

            if not parsed.hostname:
                issues.append("Missing hostname")
            else:
                if " " in parsed.hostname:
                    issues.append("Hostname contains spaces")
                if not any(c.isalpha() for c in parsed.hostname):
                    issues.append("Hostname appears invalid")

            if issues:
                return (
                    f"**URL Validation**\nStatus: Potentially invalid\nIssues:\n- "
                    + "\n- ".join(issues)
                )
            else:
                return f"**URL Validation**\nStatus: Valid\nURL: {url}"

        except Exception as e:
            return f"Invalid: {str(e)}"
