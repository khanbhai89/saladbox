"""Shared HTTP utilities for tools that make web requests.

Provides a reusable async HTTP client with:
- httpx with HTTP/2 support (looks more like a real browser)
- Full browser-like headers (sec-fetch, referer, etc.)
- User-agent rotation
- CAPTCHA/block detection
"""

from __future__ import annotations

import logging
import random
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Modern Chrome user agents
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

# Sites known to aggressively block bots
_BLOCKED_DOMAINS = {
    "tripadvisor.com", "yelp.com", "indeed.com", "zillow.com",
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "pinterest.com", "glassdoor.com",
}

# CAPTCHA/block detection patterns
_BLOCK_PATTERNS = [
    "captcha", "are you a robot", "not a robot", "verify you are human",
    "access denied", "access to this page has been denied",
    "please verify", "security check", "bot detection",
    "cf-browser-verification", "challenge-platform",
    "just a moment", "checking your browser", "ray id",
    "blocked", "forbidden", "unusual traffic",
]

# Module-level shared client
_client: Optional[httpx.AsyncClient] = None


def _get_browser_headers(url: str = "") -> dict[str, str]:
    """Full browser-like headers that pass bot detection."""
    ua = random.choice(_USER_AGENTS)
    origin = ""
    if url:
        try:
            parsed = urlparse(url)
            origin = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass

    # Note: Do NOT set Accept-Encoding — httpx handles decompression internally.
    # Setting it manually causes raw compressed bytes in the response.
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Referer": origin if origin else "https://www.google.com/",
    }


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            max_redirects=5,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _client


def is_blocked(html: str) -> bool:
    """Check if response HTML indicates a CAPTCHA or bot block."""
    if not html or len(html) < 50:
        return False
    lower = html[:3000].lower()
    matches = sum(1 for p in _BLOCK_PATTERNS if p in lower)
    return matches >= 2


def is_blocked_domain(url: str) -> bool:
    """Check if a URL belongs to a known bot-blocking domain."""
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        return any(blocked in domain for blocked in _BLOCKED_DOMAINS)
    except Exception:
        return False


async def fetch_url(
    url: str,
    timeout: int = 15,
    headers: Optional[dict[str, str]] = None,
) -> tuple[int, str]:
    """Fetch a URL and return (status_code, text_content).

    Returns (0, error_message) on failure.
    Returns (403, "blocked") if CAPTCHA/bot detection is detected.
    """
    try:
        client = await _get_client()
        req_headers = _get_browser_headers(url)
        if headers:
            req_headers.update(headers)

        resp = await client.get(
            url,
            timeout=httpx.Timeout(float(timeout)),
            headers=req_headers,
        )
        text = resp.text

        # Detect CAPTCHA/block pages
        if is_blocked(text):
            logger.debug(f"Bot block detected on {url}")
            return 403, "blocked"

        return resp.status_code, text
    except httpx.HTTPError as e:
        return 0, f"HTTP error: {e}"
    except Exception as e:
        return 0, f"Fetch error: {e}"


async def fetch_json(
    url: str,
    timeout: int = 15,
    headers: Optional[dict[str, str]] = None,
) -> tuple[int, Any]:
    """Fetch a URL and parse JSON response.

    Returns (status_code, parsed_json) or (0, error_string) on failure.
    """
    try:
        client = await _get_client()
        req_headers = _get_browser_headers(url)
        req_headers["Accept"] = "application/json"
        if headers:
            req_headers.update(headers)

        resp = await client.get(
            url,
            timeout=httpx.Timeout(float(timeout)),
            headers=req_headers,
        )
        data = resp.json()
        return resp.status_code, data
    except httpx.HTTPError as e:
        return 0, f"HTTP error: {e}"
    except Exception as e:
        return 0, f"JSON fetch error: {e}"


async def cleanup():
    """Close the shared client. Call on app shutdown."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
