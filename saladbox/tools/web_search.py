"""Web search tool with multi-source search and smart result extraction.

Optimized for local models:
- Compact, structured results that fit small context windows
- HTML scraping for real search results (not just instant answers)
- Multiple search providers with automatic fallback
- CAPTCHA/block detection — skips blocked sites gracefully
- Result deduplication and relevance ranking
"""

from __future__ import annotations

import re
import logging
from html import unescape
from urllib.parse import quote_plus, urlparse, unquote

from saladbox.platform.http import fetch_url, fetch_json, is_blocked_domain, is_blocked
from saladbox.platform.output import ToolOutput
from saladbox.tools.base import BaseTool

logger = logging.getLogger(__name__)


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", html)
    return unescape(text).strip()


def _extract_domain(url: str) -> str:
    """Extract readable domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        return domain
    except Exception:
        return url[:40]


class WebSearchTool(BaseTool):
    """Search the web using multiple providers with smart result extraction."""

    max_output_chars = 1800

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for current information and facts. "
            "Returns structured results with titles, URLs, and snippets. "
            "Use search_type='deep' to also fetch page content from top results. "
            "Supports: instant (quick facts), web (full search), deep (search + extract)."
        )

    @property
    def compact_description(self) -> str:
        return "Search the web. Types: instant (quick facts), web (search results), deep (search + read pages)."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "search_type": {
                    "type": "string",
                    "enum": ["instant", "web", "deep"],
                    "description": "instant=quick facts, web=search results (default), deep=search + read top pages",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5, max: 10)",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        search_type: str = "web",
        num_results: int = 5,
    ) -> str:
        if not query.strip():
            return "Error: Empty search query"

        num_results = max(1, min(int(num_results) if num_results else 5, 10))

        if search_type == "instant":
            return await self._instant_answer(query)
        elif search_type == "deep":
            return await self._deep_search(query, num_results)
        else:
            return await self._web_search(query, num_results)

    async def _instant_answer(self, query: str) -> str:
        """Quick factual answer from DuckDuckGo API."""
        encoded = quote_plus(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

        status, data = await fetch_json(url)
        if status != 200 or isinstance(data, str):
            return await self._web_search(query, 3)

        output = ToolOutput(summary=f"Search: {query}", source="DuckDuckGo")

        if data.get("AbstractText"):
            output.summary = data["AbstractText"][:300]
            if data.get("AbstractURL"):
                output.action_hint = f"Source: {data['AbstractURL']}"

        elif data.get("Answer"):
            output.summary = str(data["Answer"])[:300]

        elif data.get("Definition"):
            output.summary = data["Definition"][:300]

        else:
            # No instant answer, fall back to web search
            return await self._web_search(query, 3)

        # Add related topics as structured data
        for topic in (data.get("RelatedTopics") or [])[:3]:
            if isinstance(topic, dict) and "Text" in topic:
                output.data.append({
                    "topic": topic["Text"][:100],
                    "url": topic.get("FirstURL", ""),
                })

        return self.format_output(output.render())

    async def _web_search(self, query: str, num_results: int) -> str:
        """Full web search using DuckDuckGo HTML scraping."""
        results = await self._scrape_duckduckgo(query, num_results)

        if not results:
            # Fallback to DuckDuckGo lite
            results = await self._scrape_ddg_lite(query, num_results)

        if not results:
            return f"No results found for '{query}'. Try a different search term."

        output = ToolOutput(
            summary=f"Found {len(results)} results for '{query}'",
            source="Web Search",
        )

        for r in results[:num_results]:
            output.data.append({
                "title": r["title"],
                "url": r["url"],
                "snippet": r.get("snippet", "")[:150],
            })

        return self.format_output(output.render())

    async def _deep_search(self, query: str, num_results: int) -> str:
        """Search + visit top results to extract content."""
        # Step 1: Get search results
        results = await self._scrape_duckduckgo(query, max(num_results, 6))
        if not results:
            results = await self._scrape_ddg_lite(query, max(num_results, 6))

        if not results:
            return f"No results found for '{query}'."

        # Step 2: Filter out known-blocked domains, prioritize scrapable sites
        scrapable = []
        blocked = []
        for r in results:
            if is_blocked_domain(r["url"]):
                blocked.append(r)
            else:
                scrapable.append(r)

        # Try scrapable sites first, fill in with blocked sites info
        to_visit = scrapable[:4]
        enriched = []

        for r in to_visit:
            try:
                status, html = await fetch_url(r["url"], timeout=10)
                if status == 200 and html and not is_blocked(html):
                    content = self._extract_page_content(html)
                    if len(content) > 50:
                        enriched.append({
                            "title": r["title"],
                            "url": r["url"],
                            "content": content[:400],
                        })
                        continue

                # Page was blocked or empty — use snippet
                enriched.append({
                    "title": r["title"],
                    "url": r["url"],
                    "content": r.get("snippet", "Page blocked by bot detection"),
                })
            except Exception:
                enriched.append({
                    "title": r["title"],
                    "url": r["url"],
                    "content": r.get("snippet", "Could not load page"),
                })

            if len(enriched) >= 3:
                break

        # Add blocked sites with their snippets (no visit attempted)
        for r in blocked[:2]:
            if len(enriched) >= num_results:
                break
            enriched.append({
                "title": r["title"],
                "url": r["url"],
                "content": r.get("snippet", "") or f"Visit {_extract_domain(r['url'])} directly for details",
            })

        output = ToolOutput(
            summary=f"Deep search for '{query}' — {len(enriched)} results",
            source="Deep Search",
        )

        for e in enriched:
            output.data.append({
                "title": e["title"],
                "site": _extract_domain(e["url"]),
                "url": e["url"],
                "content": e["content"],
            })

        return self.format_output(output.render(max_chars=2400))

    async def _scrape_duckduckgo(self, query: str, num_results: int) -> list[dict]:
        """Scrape DuckDuckGo HTML search results."""
        encoded = quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"

        status, html = await fetch_url(url, timeout=10)
        if status != 200 or not html:
            return []

        results = []
        seen_urls = set()

        # Parse result blocks
        result_blocks = re.findall(
            r'<div class="result[^"]*">(.*?)</div>\s*</div>',
            html, re.DOTALL
        )

        if not result_blocks:
            # Fallback: find links more broadly
            result_blocks = re.findall(
                r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
                r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div)',
                html, re.DOTALL
            )
            for href, title, snippet in result_blocks[:num_results]:
                clean_url = self._clean_ddg_url(href)
                if clean_url and clean_url not in seen_urls:
                    seen_urls.add(clean_url)
                    results.append({
                        "title": _strip_html(title)[:120],
                        "url": clean_url,
                        "snippet": _strip_html(snippet)[:200],
                    })
            return results

        for block in result_blocks[:num_results * 2]:
            # Extract link
            link_match = re.search(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not link_match:
                continue

            raw_url = link_match.group(1)
            title = _strip_html(link_match.group(2))

            clean_url = self._clean_ddg_url(raw_url)
            if not clean_url or clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            # Extract snippet
            snippet = ""
            snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</(?:a|span|div)', block, re.DOTALL)
            if snippet_match:
                snippet = _strip_html(snippet_match.group(1))

            results.append({
                "title": title[:120],
                "url": clean_url,
                "snippet": snippet[:200],
            })

            if len(results) >= num_results:
                break

        return results

    async def _scrape_ddg_lite(self, query: str, num_results: int) -> list[dict]:
        """Fallback: DuckDuckGo Lite (simpler HTML, more reliable)."""
        encoded = quote_plus(query)
        url = f"https://lite.duckduckgo.com/lite/?q={encoded}"

        status, html = await fetch_url(url, timeout=10)
        if status != 200 or not html:
            return []

        results = []
        seen = set()

        # DDG Lite has a simpler structure
        links = re.findall(
            r'<a[^>]*rel="nofollow"[^>]*href="([^"]*)"[^>]*class="result-link"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )

        if not links:
            links = re.findall(
                r'<a[^>]*href="(https?://[^"]*)"[^>]*>(.*?)</a>',
                html, re.DOTALL
            )

        for href, title in links:
            if href.startswith("https://duckduckgo.com") or href in seen:
                continue
            if "ad_provider" in href or "y.js" in href:
                continue
            seen.add(href)

            results.append({
                "title": _strip_html(title)[:120],
                "url": href,
                "snippet": "",
            })
            if len(results) >= num_results:
                break

        return results

    def _clean_ddg_url(self, raw_url: str) -> str:
        """Clean a DuckDuckGo redirect URL to get the actual URL."""
        if not raw_url:
            return ""
        # DDG wraps URLs like //duckduckgo.com/l/?uddg=https%3A%2F%2F...
        if "uddg=" in raw_url:
            match = re.search(r"uddg=([^&]+)", raw_url)
            if match:
                return unquote(match.group(1))
        if raw_url.startswith("//"):
            return "https:" + raw_url
        if raw_url.startswith("http"):
            return raw_url
        return ""

    def _extract_page_content(self, html: str) -> str:
        """Extract readable text content from an HTML page."""
        # Remove script and style
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<header[^>]*>.*?</header>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Try to find main content
        main_match = re.search(
            r"<(?:main|article)[^>]*>(.*?)</(?:main|article)>",
            html, re.DOTALL | re.IGNORECASE
        )
        if main_match:
            html = main_match.group(1)

        # Strip remaining tags
        text = _strip_html(html)

        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text
