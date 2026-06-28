"""Open URLs in the user's default browser.

Use this tool when the user wants to:
- Open a website, page, or link
- Play a video on YouTube
- Watch something online
- Go to a specific URL
- Launch a web app
"""

from __future__ import annotations

import logging
import webbrowser
from urllib.parse import quote_plus

from saladbox.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Quick-launch URL templates for common sites
_SITE_TEMPLATES = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "google": "https://www.google.com/search?q={q}",
    "maps": "https://www.google.com/maps/search/{q}",
    "google_maps": "https://www.google.com/maps/search/{q}",
    "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search={q}",
    "amazon": "https://www.amazon.com/s?k={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "github": "https://github.com/search?q={q}",
    "twitter": "https://x.com/search?q={q}",
    "x": "https://x.com/search?q={q}",
    "spotify": "https://open.spotify.com/search/{q}",
    "stackoverflow": "https://stackoverflow.com/search?q={q}",
}


class OpenURLTool(BaseTool):
    """Open URLs and websites in the user's default browser."""

    @property
    def name(self) -> str:
        return "open_url"

    @property
    def description(self) -> str:
        return (
            "Open a URL or website in the user's default system browser. "
            "Use this ONLY when you want to passively open a link for the user to see. "
            "WARNING: You CANNOT interact with, click on, or read the page after opening it! "
            "If you need to click links, extract text, or play videos automatically, use the "
            "'browser' tool instead of this one.\n"
            "- Direct URL: open any URL directly\n"
            "- Site search: use site='youtube' with query to search YouTube, "
            "site='google' for Google, site='maps' for Google Maps, etc.\n"
            "Supported sites: youtube, google, maps, wikipedia, amazon, reddit, "
            "github, twitter/x, spotify, stackoverflow"
        )

    @property
    def compact_description(self) -> str:
        return (
            "Open URL in system browser (PASSIVE ONLY). You CANNOT interact with it! "
            "Use 'browser' tool if you need to click/read. "
            "Sites: youtube, google, maps, wikipedia, amazon, reddit, github."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Direct URL to open (e.g. 'https://youtube.com/watch?v=...')",
                },
                "site": {
                    "type": "string",
                    "enum": list(_SITE_TEMPLATES.keys()),
                    "description": "Site to search on (e.g. 'youtube', 'google', 'maps')",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for the site (used with 'site' parameter)",
                },
            },
        }

    async def execute(
        self,
        url: str = "",
        site: str = "",
        query: str = "",
    ) -> str:
        # Option 1: Direct URL
        if url:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            try:
                webbrowser.open(url)
                return f"Opened {url} in your browser."
            except Exception as e:
                return f"Failed to open URL: {e}"

        # Option 2: Site + query
        if site:
            site_key = site.lower().strip()
            template = _SITE_TEMPLATES.get(site_key)

            if not template:
                return f"Unknown site '{site}'. Supported: {', '.join(_SITE_TEMPLATES.keys())}"

            if not query:
                # Just open the site homepage
                homepages = {
                    "youtube": "https://www.youtube.com",
                    "google": "https://www.google.com",
                    "maps": "https://maps.google.com",
                    "wikipedia": "https://en.wikipedia.org",
                    "amazon": "https://www.amazon.com",
                    "reddit": "https://www.reddit.com",
                    "github": "https://github.com",
                    "twitter": "https://x.com",
                    "x": "https://x.com",
                    "spotify": "https://open.spotify.com",
                    "stackoverflow": "https://stackoverflow.com",
                }
                homepage = homepages.get(site_key, template.split("{q}")[0])
                try:
                    webbrowser.open(homepage)
                    return f"Opened {site_key.title()} in your browser."
                except Exception as e:
                    return f"Failed to open {site_key}: {e}"

            # Build search URL
            encoded_query = quote_plus(query)
            final_url = template.replace("{q}", encoded_query)

            try:
                webbrowser.open(final_url)
                site_name = site_key.title()
                if site_key == "youtube":
                    return f"Opened YouTube search for \"{query}\" in your browser."
                elif site_key in ("maps", "google_maps"):
                    return f"Opened Google Maps search for \"{query}\" in your browser."
                else:
                    return f"Opened {site_name} search for \"{query}\" in your browser."
            except Exception as e:
                return f"Failed to open {site_key}: {e}"

        return "Please provide either a 'url' to open or a 'site' with an optional 'query'."
