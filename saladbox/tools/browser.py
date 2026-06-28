"""Browser automation tool using Playwright — fast, smart, privacy-first."""

from __future__ import annotations

import logging
import time

from saladbox.tools.base import BaseTool

logger = logging.getLogger(__name__)

# ---------- Cookie / consent selectors (privacy-first: always reject) ----------
_REJECT_SELECTORS = [
    # Explicit reject / decline / necessary-only buttons
    'button[id*="reject"]',
    'button[id*="decline"]',
    'button[id*="deny"]',
    'button[class*="reject"]',
    'button[class*="decline"]',
    'button[class*="deny"]',
    'a[id*="reject"]',
    'a[class*="reject"]',
    'button[aria-label*="Reject"]',
    'button[aria-label*="reject"]',
    'button[aria-label*="Decline"]',
    'button[aria-label*="decline"]',
    'button[aria-label*="Deny"]',
    'button[data-testid*="reject"]',
    'button[data-testid*="decline"]',
    # "Only necessary" / "Manage" patterns
    'button[id*="necessary"]',
    'button[class*="necessary"]',
    'button[class*="manage"]',
    # OneTrust (very common CMP)
    "#onetrust-reject-all-handler",
    ".onetrust-close-btn-handler",
    "#onetrust-pc-btn-handler",
    # Cookiebot
    "#CybotCookiebotDialogBodyButtonDecline",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinDeclineAll",
    # Quantcast / TCF
    "button.qc-cmp2-summary-buttons button:first-child",
    ".qc-cmp-button:first-child",
    # Google / YouTube consent
    'form[action*="consent"] button:first-of-type',
    'button[jsname="tWT92d"]',
    # TrustArc
    ".truste_overlay .truste-button2",
    # Klaro
    ".klaro .cn-decline",
    # Generic GDPR banners
    '[class*="cookie-banner"] button:first-of-type',
    '[id*="cookie-banner"] button:first-of-type',
    '[class*="gdpr"] button:first-of-type',
]

_REJECT_TEXTS = [
    "Reject all",
    "Reject All",
    "Reject",
    "Decline",
    "Decline all",
    "Decline All",
    "Deny",
    "Deny all",
    "Only necessary",
    "Only essential",
    "Necessary only",
    "Refuse",
    "Refuse all",
    "No thanks",
    "No, thanks",
    "Save and close",
    "Manage preferences",
]

_ACCEPT_TEXTS = [
    "Accept all",
    "Accept All",
    "I agree",
    "Agree",
    "OK",
    "Got it",
    "Allow all",
    "Allow All",
    "Continue",
    "Understood",
    "Accept cookies",
    "Accept Cookies",
]

_CLOSE_SELECTORS = [
    'button[aria-label="Close"]',
    'button[aria-label="close"]',
    'button[aria-label="Dismiss"]',
    'button[aria-label="dismiss"]',
    'button[class*="close-modal"]',
    'button[class*="modal-close"]',
    'button[class*="dialog-close"]',
    'div[role="dialog"] button[aria-label="Close"]',
    '[class*="overlay"] button[class*="close"]',
    ".modal .close",
    ".popup-close",
    '[class*="cookie"] button[class*="close"]',
    '[id*="cookie"] button[class*="close"]',
]

# JS to nuke cookie banners that survive button clicks
_NUKE_OVERLAYS_JS = """
() => {
    let removed = [];
    const sels = [
        '[class*="consent"]', '[class*="cookie"]', '[id*="consent"]',
        '[id*="cookie"]', '[class*="gdpr"]', '[id*="gdpr"]',
        '[class*="privacy"]', '[id*="privacy-banner"]',
        '[class*="cc-banner"]', '[id*="cc-banner"]',
        '[class*="CookieConsent"]', '#CybotCookiebotDialog',
        '#onetrust-banner-sdk', '.qc-cmp2-container',
        '[class*="truste"]',
    ];
    for (const sel of sels) {
        document.querySelectorAll(sel).forEach(el => {
            const s = window.getComputedStyle(el);
            if (s.position === 'fixed' || s.position === 'sticky' || s.position === 'absolute') {
                el.remove();
                removed.push(sel);
            }
        });
    }
    // Remove backdrop overlays
    document.querySelectorAll('[class*="overlay"], [class*="backdrop"], [class*="modal-bg"]').forEach(el => {
        const s = window.getComputedStyle(el);
        if (s.position === 'fixed' && (parseFloat(s.opacity) < 1 || s.backgroundColor.includes('0,'))) {
            el.remove();
            removed.push('overlay/backdrop');
        }
    });
    // Restore scroll
    document.body.style.overflow = '';
    document.documentElement.style.overflow = '';
    document.body.classList.remove('modal-open', 'no-scroll', 'overflow-hidden');
    return removed;
}
"""

# JS to get quick page state summary
_PAGE_STATE_JS = """
() => {
    const interactive = document.querySelectorAll(
        'a[href], button, input, select, textarea, [role="button"], [onclick], [tabindex]'
    );
    const links = document.querySelectorAll('a[href]');
    const inputs = document.querySelectorAll('input, textarea, select');
    const buttons = document.querySelectorAll('button, [role="button"]');
    return {
        title: document.title,
        url: location.href,
        links: links.length,
        buttons: buttons.length,
        inputs: inputs.length,
        interactive: interactive.length,
        scrollHeight: document.body.scrollHeight,
        viewportHeight: window.innerHeight,
        hasMore: document.body.scrollHeight > window.innerHeight + 200,
    };
}
"""


class BrowserTool(BaseTool):
    """Fast, smart browser automation with cookie rejection, form filling, and page intelligence."""

    max_output_chars = 2500

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._pages: dict[str, object] = {}  # tab_id -> page

    @property
    def name(self) -> str:
        return "browser"

    @property
    def description(self) -> str:
        return (
            "Control a web browser for web automation, searching, and form filling. "
            "Cookies/consent popups are auto-rejected.\n"
            "WORKFLOW: For signup/registration tasks: 1) google_search 2) navigate to result 3) extract_form 4) fill_form with JSON.\n"
            "IMPORTANT: After getting search results, IMMEDIATELY navigate to the best result and continue the workflow. Do not ask for clarification - proceed with common choices.\n"
            "Actions:\n"
            "- google_search: Search Google and return results (RECOMMENDED)\n"
            "- browse_results: Visit search results, extract details, recommend best\n"
            "- navigate: Go to a URL\n"
            "- extract_form: Detect all form fields on the page (for filling forms)\n"
            "- fill_form: Fill multiple form fields at once (pass JSON in value)\n"
            "- click: Click element\n"
            "- type/fill: Enter text into a field\n"
            "- select: Select dropdown option\n"
            "- get_text: Get page text\n"
            "- get_state: Get interactive elements\n"
            "- scroll: Scroll page\n"
            "FORM FILLING: Use extract_form to see fields, then fill_form with "
            'value=\'{"field_name": "value", ...}\' to fill them. '
            "Works for ticket booking, registration, checkout, etc."
        )

    @property
    def compact_description(self) -> str:
        return (
            "Web browser: google_search, navigate, extract_form, fill_form, "
            "click, type, select, get_state, scroll. "
            "For forms: extract_form then fill_form with JSON."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "navigate",
                        "google_search",
                        "browse_results",
                        "search",
                        "extract_form",
                        "fill_form",
                        "click",
                        "type",
                        "fill",
                        "press_key",
                        "screenshot",
                        "get_text",
                        "get_html",
                        "wait",
                        "scroll",
                        "evaluate_js",
                        "select",
                        "get_links",
                        "get_state",
                        "new_tab",
                        "switch_tab",
                        "close",
                    ],
                    "description": "Browser action. Use extract_form + fill_form for form filling.",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector or text content for the target element",
                },
                "value": {
                    "type": "string",
                    "description": (
                        "URL for navigate, query for search, text for type/fill, "
                        'JSON for fill_form (e.g. \'{"name": "John", "email": "j@x.com"}\'), '
                        "key for press_key, direction for scroll"
                    ),
                },
                "url": {
                    "type": "string",
                    "description": "URL for navigate (alias for value)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in ms (default: 15000)",
                },
            },
            "required": ["action"],
        }

    # ── Browser lifecycle ──────────────────────────────────────────

    async def _ensure_browser(self):
        """Lazily start Playwright browser with stealth + privacy settings."""
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--disable-popup-blocking",
                ],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                permissions=[],
                geolocation=None,
                color_scheme="light",
            )
            # Stealth scripts
            await self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                window.chrome = { runtime: {} };
                // Spoof permissions
                const origQuery = window.navigator.permissions?.query;
                if (origQuery) {
                    window.navigator.permissions.query = (params) =>
                        params.name === 'notifications'
                            ? Promise.resolve({ state: Notification.permission })
                            : origQuery(params);
                }
            """)

            # Handle new tabs/popups opened by link clicks
            self._context.on("page", self._on_new_page)

            self._page = await self._context.new_page()
            self._page.set_default_timeout(15000)
            logger.info("Browser launched (stealth + privacy mode)")

    async def _on_new_page(self, page):
        """Handle new tabs/popups opened by link clicks."""
        tab_id = f"tab_{len(self._pages) + 1}"
        self._pages[tab_id] = page
        self._page = page  # auto-switch to new tab
        page.set_default_timeout(15000)
        logger.info(f"New tab opened: {tab_id}")
        # Auto-dismiss cookies on the new page after it loads
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await self._dismiss_cookies()
        except Exception:
            pass

    # ── Main execute ───────────────────────────────────────────────

    async def execute(
        self,
        action: str,
        selector: str = "",
        value: str = "",
        url: str = "",
        timeout: int | str = 30000,
    ) -> str:
        if action == "navigate" and not value and url:
            value = url
        try:
            timeout = int(timeout) if timeout is not None else 15000
        except (TypeError, ValueError):
            timeout = 15000
        timeout = max(3000, min(timeout, 120000))

        if action == "close":
            return await self._close()

        await self._ensure_browser()

        interactive_actions = {
            "extract_form", "fill_form", "click", "type", "fill",
            "press_key", "get_text", "get_html", "select", "get_state",
            "evaluate_js", "wait", "get_links"
        }
        if action in interactive_actions and self._page and self._page.url == "about:blank":
            return (
                f"Error: The browser is currently on a blank page ('about:blank'). "
                f"You must use 'navigate', 'google_search', or 'search' to open a website "
                f"before you can use the '{action}' action! (Note: the 'open_url' tool opens "
                f"the user's system default browser which you CANNOT control. To control a browser, "
                f"you must use the 'browser' tool to navigate first)."
            )

        try:
            match action:
                case "navigate":
                    return await self._navigate(value, timeout)
                case "google_search":
                    return await self._google_search(value, timeout)
                case "browse_results":
                    return await self._browse_results(value, timeout)
                case "search":
                    return await self._search(value, timeout)
                case "extract_form":
                    return await self._extract_form(selector)
                case "fill_form":
                    return await self._fill_form(value, selector, timeout)
                case "click":
                    return await self._click(selector, timeout)
                case "type":
                    return await self._type(selector, value, timeout)
                case "fill":
                    return await self._fill(selector, value, timeout)
                case "press_key":
                    return await self._press_key(value, selector)
                case "screenshot":
                    return await self._screenshot()
                case "get_text":
                    return await self._get_text(selector, timeout)
                case "get_html":
                    return await self._get_html(selector, timeout)
                case "wait":
                    return await self._wait(selector, timeout)
                case "scroll":
                    return await self._scroll(value)
                case "evaluate_js":
                    return await self._evaluate_js(value)
                case "select":
                    return await self._select(selector, value, timeout)
                case "get_links":
                    return await self._get_links()
                case "get_state":
                    return await self._get_state()
                case "new_tab":
                    return await self._new_tab(value)
                case "switch_tab":
                    return await self._switch_tab(value)
                case _:
                    return f"Unknown action: {action}"
        except Exception as e:
            return f"Browser error ({action}): {e}"

    # ── Cookie / popup dismissal ───────────────────────────────────

    async def _dismiss_cookies(self) -> list[str]:
        """Aggressively reject all cookies and consent dialogs."""
        dismissed: list[str] = []

        # Strategy 1: Click explicit reject/decline buttons (CSS selectors)
        for sel in _REJECT_SELECTORS:
            try:
                btn = await self._page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=1500)
                    dismissed.append(f"reject:{sel}")
                    await self._page.wait_for_timeout(300)
                    break
            except Exception:
                continue

        # Strategy 2: Click reject buttons by text
        if not dismissed:
            for text in _REJECT_TEXTS:
                try:
                    btn = self._page.get_by_role("button", name=text, exact=False)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click(timeout=1500)
                        dismissed.append(f"reject-text:'{text}'")
                        await self._page.wait_for_timeout(300)
                        break
                except Exception:
                    continue

        # Strategy 3: Also try link-type reject buttons
        if not dismissed:
            for text in _REJECT_TEXTS[:6]:
                try:
                    link = self._page.get_by_role("link", name=text, exact=False)
                    if await link.count() > 0 and await link.first.is_visible():
                        await link.first.click(timeout=1500)
                        dismissed.append(f"reject-link:'{text}'")
                        await self._page.wait_for_timeout(300)
                        break
                except Exception:
                    continue

        # Strategy 4: If no reject found, accept (some sites require it)
        if not dismissed:
            for text in _ACCEPT_TEXTS:
                try:
                    btn = self._page.get_by_role("button", name=text, exact=False)
                    if await btn.count() > 0 and await btn.first.is_visible():
                        await btn.first.click(timeout=1500)
                        dismissed.append(f"accept:'{text}'")
                        await self._page.wait_for_timeout(300)
                        break
                except Exception:
                    continue

        # Strategy 5: Close modal/overlay buttons
        for sel in _CLOSE_SELECTORS:
            try:
                btn = await self._page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=1500)
                    dismissed.append(f"close:{sel}")
                    await self._page.wait_for_timeout(300)
            except Exception:
                continue

        # Strategy 6: Nuclear option — remove overlays via JS
        try:
            removed = await self._page.evaluate(_NUKE_OVERLAYS_JS)
            if removed:
                dismissed.append(f"nuked:{len(removed)} overlays")
        except Exception:
            pass

        if dismissed:
            logger.info(f"Cookie/popup dismissed: {dismissed}")
        return dismissed

    # ── Page state helper ──────────────────────────────────────────

    async def _get_page_state_summary(self) -> str:
        """Return a compact page state for embedding in responses."""
        try:
            state = await self._page.evaluate(_PAGE_STATE_JS)
            parts = [state["title"][:60], state["url"]]
            parts.append(
                f"({state['links']} links, {state['buttons']} buttons, "
                f"{state['inputs']} inputs)"
            )
            if state.get("hasMore"):
                parts.append("Page has more content below")
            return " | ".join(parts)
        except Exception:
            try:
                title = await self._page.title()
                url = self._page.url
                return f"{title} | {url}"
            except Exception:
                return ""

    # ── Actions ────────────────────────────────────────────────────

    async def _navigate(self, url: str, timeout: int) -> str:
        if not url:
            return "URL is required for navigate action"
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        try:
            response = await self._page.goto(
                url, timeout=timeout, wait_until="networkidle"
            )
        except Exception:
            try:
                response = await self._page.goto(
                    url, timeout=timeout, wait_until="domcontentloaded"
                )
            except Exception as e:
                return f"Failed to navigate to {url}: {e!s}"
        status = response.status if response else "unknown"

        # Auto-dismiss cookies immediately
        dismissed = await self._dismiss_cookies()

        # Get page state
        state = await self._get_page_state_summary()
        result = f"Navigated to {url} (status: {status})\n{state}"
        if dismissed:
            result += f"\nAuto-dismissed cookies: {', '.join(dismissed)}"

        # YouTube special handling
        if "youtube.com/results" in url or "youtube.com/search" in url:
            await self._page.wait_for_timeout(1500)
            videos = await self._page.evaluate("""
                () => {
                    const vids = [];
                    document.querySelectorAll('a[href*="/watch?v="], a#video-title').forEach(link => {
                        const href = link.href;
                        const title = link.getAttribute('title') || link.innerText?.trim() || '';
                        if (href?.includes('/watch?v=')) {
                            const vid = href.match(/[?&]v=([^&]+)/)?.[1];
                            if (vid && !vids.find(v => v.id === vid)) {
                                vids.push({ id: vid, title: title.substring(0, 80),
                                    url: 'https://www.youtube.com/watch?v=' + vid });
                            }
                        }
                    });
                    return vids.slice(0, 10);
                }
            """)
            if videos:
                result += f"\n\n**Found {len(videos)} videos:**"
                for i, v in enumerate(videos, 1):
                    result += f"\n{i}. {v['title']}\n   {v['url']}"
                return result

        # Extract readable text
        try:
            text = await self._page.inner_text("body")
            if len(text) > 2500:
                text = text[:2500] + "\n... (truncated - use get_text for more)"
            result += f"\n\n{text}"
        except Exception:
            result += "\n(could not extract page text)"

        return result

    async def _google_search(self, query: str, timeout: int) -> str:
        """Open Google and perform a search, returning results."""
        if not query:
            return "Search query is required"

        import urllib.parse

        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://www.google.com/search?q={encoded}"

        try:
            await self._page.goto(search_url, timeout=timeout, wait_until="networkidle")
        except Exception:
            await self._page.goto(
                search_url, timeout=timeout, wait_until="domcontentloaded"
            )

        # Dismiss cookie popups
        await self._dismiss_cookies()
        await self._page.wait_for_timeout(2000)

        # Check if Google is blocking us
        page_text = await self._page.inner_text("body")
        if "unusual traffic" in page_text.lower() or "not a robot" in page_text.lower():
            # Fallback to DuckDuckGo
            return await self._search(query, timeout)

        # Extract search results
        results = await self._page.evaluate("""
            () => {
                const items = [];
                const seen = new Set();
                // Google search results
                const divs = document.querySelectorAll('#search .g, #rso .g');
                for (const div of [...divs].slice(0, 15)) {
                    const link = div.querySelector('a[href^="http"]');
                    const title = div.querySelector('h3');
                    const snippet = div.querySelector('[data-sncf], .VwiC3b, span[data-sncf]');
                    if (link && title) {
                        const url = link.href;
                        if (seen.has(url)) continue;
                        seen.add(url);
                        items.push({
                            title: title.innerText.trim(),
                            url: url,
                            snippet: snippet ? snippet.innerText.trim().substring(0, 200) : ''
                        });
                    }
                }
                // Fallback
                if (items.length === 0) {
                    document.querySelectorAll('#search a[href^="http"], #rso a[href^="http"]').forEach(a => {
                        const h3 = a.querySelector('h3');
                        const url = a.href;
                        if (h3 && !seen.has(url)) {
                            seen.add(url);
                            items.push({ title: h3.innerText.trim(), url: url, snippet: '' });
                        }
                    });
                }
                return items.slice(0, 8);
            }
        """)

        if not results:
            # Fallback to DuckDuckGo
            return await self._search(query, timeout)

        lines = [f"## Google Search: {query}\n"]
        for i, r in enumerate(results, 1):
            title = r["title"].strip()
            url = r["url"]
            display_url = url.split("?")[0][:60]
            lines.append(f"### {i}. [{title}]({url})")
            lines.append(f"**URL:** {display_url}")
            if r["snippet"]:
                lines.append(f"*{r['snippet']}*")
            lines.append("")

        lines.append("\n---\n*Google is open. Click a result or scroll for more.*")
        return "\n".join(lines)

    async def _search(self, query: str, timeout: int) -> str:
        if not query:
            return "Search query is required"

        import urllib.parse

        encoded = urllib.parse.quote_plus(query)
        search_url = f"https://duckduckgo.com/?q={encoded}&ia=web"

        try:
            await self._page.goto(search_url, timeout=timeout, wait_until="networkidle")
        except Exception:
            await self._page.goto(
                search_url, timeout=timeout, wait_until="domcontentloaded"
            )

        # Dismiss cookie popups
        await self._dismiss_cookies()
        await self._page.wait_for_timeout(1500)

        results = await self._page.evaluate("""
            () => {
                const items = [];
                const seen = new Set();
                // DuckDuckGo results
                const divs = document.querySelectorAll(
                    '[data-testid="result"], article[data-testid], li[data-layout]'
                );
                for (const div of [...divs].slice(0, 15)) {
                    const link = div.querySelector('a[href^="http"]');
                    const title = div.querySelector('h2, h3, [data-testid="result-title-a"]');
                    const snippet = div.querySelector('[data-testid="result-snippet"], span[data-testid]');
                    if (link && title) {
                        const url = link.href;
                        // Skip ads and duplicates
                        if (url.includes('y.js?') || url.includes('ad_domain') || seen.has(url)) continue;
                        seen.add(url);
                        items.push({
                            title: title.innerText.trim(),
                            url: url,
                            snippet: snippet ? snippet.innerText.trim().substring(0, 200) : ''
                        });
                    }
                }
                // Fallback
                if (items.length === 0) {
                    document.querySelectorAll('a[href^="http"]').forEach(a => {
                        const t = a.innerText.trim() || a.querySelector('span')?.innerText?.trim();
                        const url = a.href;
                        if (t && !t.includes('DuckDuckGo') && !url.includes('duckduckgo.com') && !seen.has(url)) {
                            seen.add(url);
                            items.push({ title: t.substring(0, 100), url: url, snippet: '' });
                        }
                    });
                }
                return items.slice(0, 8);
            }
        """)

        if not results:
            text = await self._page.inner_text("body")
            return f"No results extracted. Page text:\n{text[:2000]}"

        lines = [f"## Search Results: {query}\n"]
        for i, r in enumerate(results, 1):
            title = r["title"].strip()
            url = r["url"]
            # Skip ad URLs
            if "y.js?" in url or "ad_domain" in url or "click_metadata" in url:
                continue
            # Clean up URL for display
            display_url = url.split("?")[0][:60]
            lines.append(f"### {i}. [{title}]({url})")
            lines.append(f"**URL:** {display_url}")
            if r["snippet"]:
                lines.append(f"*{r['snippet']}*")
            lines.append("")

        if len(lines) <= 2:
            lines.append("No clean results found. Try a different search term.")

        lines.append("\n---\n*Browser is open. Click a result or scroll for more.*")
        return "\n".join(lines)

    async def _browse_results(self, query: str, timeout: int) -> str:
        """Visit top search results, extract details, and recommend best options."""
        if not query:
            return "Query is required to browse results"

        # First do a search
        search_result = await self._google_search(query, timeout)

        # Extract URLs from search results
        import re

        url_pattern = r"https?://[^\s\)]+"
        urls = re.findall(url_pattern, search_result)

        # Filter out ad URLs and duplicates
        seen = set()
        clean_urls = []
        for url in urls:
            if "y.js?" in url or "ad_domain" in url or "click_metadata" in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            clean_urls.append(url)
            if len(clean_urls) >= 4:
                break

        if not clean_urls:
            return search_result + "\n\nNo clean result URLs found to browse."

        # Visit each URL and extract info
        results = []
        for i, url in enumerate(clean_urls):
            try:
                try:
                    await self._page.goto(
                        url, timeout=timeout, wait_until="networkidle"
                    )
                except Exception:
                    await self._page.goto(
                        url, timeout=timeout, wait_until="domcontentloaded"
                    )
                await self._dismiss_cookies()
                await self._page.wait_for_timeout(1500)

                # Extract page content
                page_info = await self._page.evaluate("""
                    () => {
                        const title = document.title || '';
                        const meta_desc = document.querySelector('meta[name="description"]')?.content || '';

                        // Try to find products/items
                        const products = [];

                        // E-commerce patterns
                        document.querySelectorAll('[data-product], .product, .item, article, .card, [class*="product"], [class*="item"]').forEach(el => {
                            const name = el.querySelector('h1, h2, h3, h4, .title, .name, [class*="title"], [class*="name"]');
                            const price = el.querySelector('[class*="price"], .price');
                            const rating = el.querySelector('[class*="rating"], [class*="star"], .rating');
                            const link = el.querySelector('a[href]');

                            if (name) {
                                products.push({
                                    name: name.innerText.trim().substring(0, 100),
                                    price: price ? price.innerText.trim() : '',
                                    rating: rating ? rating.innerText.trim().substring(0, 20) : '',
                                    link: link ? link.href : ''
                                });
                            }
                        });

                        // Get main text content
                        const main = document.querySelector('main, article, .content, #content, .main');
                        const text = main ? main.innerText.substring(0, 500) : document.body.innerText.substring(0, 500);

                        return {
                            title,
                            meta_desc: meta_desc.substring(0, 200),
                            products: products.slice(0, 5),
                            text: text.replace(/\\s+/g, ' ').trim()
                        };
                    }
                """)

                results.append(
                    {
                        "url": url,
                        "title": page_info.get("title", ""),
                        "description": page_info.get("meta_desc", ""),
                        "products": page_info.get("products", []),
                        "snippet": page_info.get("text", "")[:300],
                    }
                )

            except Exception as e:
                results.append({"url": url, "error": str(e)[:100]})

        # Format results with recommendations
        lines = [f"## Research Results: {query}\n"]
        lines.append(f"Visited {len(results)} pages. Here's what I found:\n")

        all_products = []
        for i, r in enumerate(results, 1):
            if "error" in r:
                lines.append(f"### {i}. [Error visiting page]({r['url']})")
                lines.append(f"*{r['error']}*\n")
                continue

            lines.append(f"### {i}. [{r['title']}]({r['url']})")
            if r["description"]:
                lines.append(f"*{r['description']}*")

            # Add products found
            if r["products"]:
                lines.append("\n**Items found:**")
                for p in r["products"]:
                    lines.append(f"- **{p['name']}**")
                    if p["price"]:
                        lines.append(f"  Price: {p['price']}")
                    if p["rating"]:
                        lines.append(f"  Rating: {p['rating']}")
                    all_products.append({**p, "source": r["title"], "url": r["url"]})
            else:
                # Add text snippet
                lines.append(f"\n{r['snippet'][:200]}...")

            lines.append("")

        # Add recommendations
        if all_products:
            lines.append("---\n## 🎯 Top Recommendations\n")
            lines.append("Based on the research, here are the best options:\n")

            # Sort by rating if available
            rated = [p for p in all_products if p.get("rating")]
            if rated:
                lines.append("**Highest Rated:**")
                for p in rated[:3]:
                    lines.append(f"- **{p['name']}** from {p['source']}")
                    if p["price"]:
                        lines.append(f"  💰 {p['price']}")
                    if p["rating"]:
                        lines.append(f"  ⭐ {p['rating']}")
            else:
                lines.append("**Best Options Found:**")
                for p in all_products[:5]:
                    lines.append(
                        f"- **{p['name']}** - {p.get('price', 'Price not listed')}"
                    )
                    lines.append(f"  📦 [{p['source']}]({p['url']})")

        return "\n".join(lines)

    async def _click(self, selector: str, timeout: int) -> str:
        if not selector:
            return "Selector is required for click action"
        try:
            # Try CSS selector first
            await self._page.click(selector, timeout=timeout)
        except Exception:
            # Fallback: try as text content
            try:
                el = self._page.get_by_text(selector, exact=False)
                if await el.count() > 0:
                    await el.first.click(timeout=timeout)
                else:
                    return (
                        f"Element not found: '{selector}'. "
                        "Use get_state to see available elements, or scroll to load more."
                    )
            except Exception as e:
                return f"Click failed: {e}"

        await self._dismiss_cookies()
        state = await self._get_page_state_summary()
        return f"Clicked: {selector}\n{state}"

    async def _type(self, selector: str, value: str, timeout: int) -> str:
        if not selector or not value:
            return "Selector and value are required for type action"
        await self._page.type(selector, value, timeout=timeout)
        return f"Typed '{value}' into {selector}. Use press_key 'Enter' to submit."

    async def _press_key(self, key: str, selector: str = "") -> str:
        if not key:
            return "Key name required (Enter, Tab, Escape, ArrowDown, Backspace, Space)"
        key_map = {
            "enter": "Enter",
            "tab": "Tab",
            "escape": "Escape",
            "esc": "Escape",
            "backspace": "Backspace",
            "delete": "Delete",
            "space": "Space",
            "arrowdown": "ArrowDown",
            "arrowup": "ArrowUp",
            "arrowleft": "ArrowLeft",
            "arrowright": "ArrowRight",
            "home": "Home",
            "end": "End",
            "pageup": "PageUp",
            "pagedown": "PageDown",
        }
        normalized = key_map.get(key.lower().strip(), key)
        if selector:
            await self._page.press(selector, normalized)
        else:
            await self._page.keyboard.press(normalized)
        await self._page.wait_for_timeout(800)
        state = await self._get_page_state_summary()
        return (
            f"Pressed '{normalized}'"
            + (f" on {selector}" if selector else "")
            + f"\n{state}"
        )

    async def _fill(self, selector: str, value: str, timeout: int) -> str:
        if not selector:
            return "Selector is required for fill action"
        await self._page.fill(selector, value, timeout=timeout)
        return f"Filled {selector} with '{value}'"

    async def _screenshot(self) -> str:
        path = f"/tmp/saladbox_screenshot_{int(time.time())}.png"
        await self._page.screenshot(path=path, full_page=False)
        return f"Screenshot saved to {path}"

    async def _get_text(self, selector: str, timeout: int) -> str:
        await self._dismiss_cookies()
        if selector:
            try:
                element = await self._page.wait_for_selector(
                    selector, timeout=10000, state="attached"
                )
                text = await element.inner_text()
            except Exception:
                text = await self._page.evaluate(
                    """
                    () => {
                        const el = document.querySelector(arguments[0]);
                        return el ? el.innerText : document.body.innerText;
                    }
                """,
                    selector,
                )
        else:
            text = await self._page.inner_text("body")
        if len(text) > 4000:
            text = text[:4000] + "\n... (truncated)"
        return text

    async def _get_html(self, selector: str, timeout: int) -> str:
        if selector:
            element = await self._page.wait_for_selector(selector, timeout=timeout)
            html = await element.inner_html()
        else:
            html = await self._page.content()
        if len(html) > 4000:
            html = html[:4000] + "\n... (truncated)"
        return html

    async def _wait(self, selector: str, timeout: int) -> str:
        if not selector:
            return "Selector is required for wait action"
        await self._page.wait_for_selector(selector, timeout=timeout)
        return f"Element found: {selector}"

    async def _scroll(self, direction: str) -> str:
        direction = (direction or "down").lower()
        scroll_map = {
            "down": "window.scrollBy(0, 600)",
            "up": "window.scrollBy(0, -600)",
            "top": "window.scrollTo(0, 0)",
            "bottom": "window.scrollTo(0, document.body.scrollHeight)",
        }
        js = scroll_map.get(direction)
        if not js:
            return f"Unknown direction: {direction}. Use: up, down, top, bottom"
        await self._page.evaluate(js)
        await self._page.wait_for_timeout(500)
        state = await self._get_page_state_summary()
        return f"Scrolled {direction}\n{state}"

    async def _evaluate_js(self, code: str) -> str:
        if not code:
            return "JavaScript code is required"
        result = await self._page.evaluate(code)
        text = str(result)
        if len(text) > 4000:
            text = text[:4000] + "\n... (truncated)"
        return text

    async def _select(self, selector: str, value: str, timeout: int) -> str:
        if not selector or not value:
            return "Selector and value are required"
        await self._page.select_option(selector, value, timeout=timeout)
        return f"Selected '{value}' in {selector}"

    async def _get_links(self) -> str:
        links = await self._page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.innerText.trim().substring(0, 80),
                href: a.href
            })).filter(l => l.text && l.href).slice(0, 50)
        """)
        if not links:
            return "No links found"
        lines = [f"Found {len(links)} links:"]
        for link in links:
            lines.append(f"  [{link['text']}] -> {link['href']}")
        return "\n".join(lines)

    async def _get_state(self) -> str:
        """Return detailed page state: interactive elements with indices."""
        state = await self._page.evaluate("""
            () => {
                const elements = [];
                const interactive = document.querySelectorAll(
                    'a[href], button, input, select, textarea, [role="button"], [onclick]'
                );
                let idx = 0;
                for (const el of interactive) {
                    if (idx >= 50) break;
                    const rect = el.getBoundingClientRect();
                    if (rect.width === 0 || rect.height === 0) continue;
                    const visible = rect.top < window.innerHeight && rect.bottom > 0;
                    if (!visible) continue;

                    const tag = el.tagName.toLowerCase();
                    const type = el.type || '';
                    const text = (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().substring(0, 60);
                    const href = el.href || '';

                    let selector = '';
                    if (el.id) selector = '#' + el.id;
                    else if (el.name) selector = tag + '[name="' + el.name + '"]';
                    else if (el.className && typeof el.className === 'string')
                        selector = tag + '.' + el.className.split(' ')[0];
                    else selector = tag;

                    elements.push({ idx, tag, type, text, href: href.substring(0, 100), selector });
                    idx++;
                }
                return {
                    title: document.title,
                    url: location.href,
                    elements,
                    scrollPos: Math.round(window.scrollY),
                    scrollMax: document.body.scrollHeight - window.innerHeight,
                };
            }
        """)

        lines = [
            f"Page: {state['title']}",
            f"URL: {state['url']}",
            f"Scroll: {state['scrollPos']}/{state['scrollMax']}px",
            f"\nInteractive elements ({len(state['elements'])} visible):",
        ]
        for el in state["elements"]:
            desc = f"  [{el['idx']}] <{el['tag']}"
            if el["type"]:
                desc += f" type={el['type']}"
            desc += f"> {el['text']}"
            if el["href"]:
                desc += f" -> {el['href']}"
            desc += f"  (selector: {el['selector']})"
            lines.append(desc)

        return "\n".join(lines)

    # ── Form extraction & filling ────────────────────────────────

    async def _extract_form(self, selector: str = "") -> str:
        """Extract all form fields from the page for intelligent form filling.

        Returns a structured list of fields with their types, names, labels,
        current values, and available options (for selects/radios).
        """
        await self._dismiss_cookies()

        form_data = await self._page.evaluate(
            """
            (formSelector) => {
                const forms = formSelector
                    ? [document.querySelector(formSelector)]
                    : Array.from(document.querySelectorAll('form'));

                if (forms.length === 0) {
                    // No <form> tags - look for input groups
                    const inputs = document.querySelectorAll('input, select, textarea');
                    if (inputs.length === 0) return { forms: [], error: 'No forms found' };
                    forms.push(document.body);
                }

                const result = { forms: [] };

                for (const form of forms) {
                    if (!form) continue;
                    const formInfo = {
                        action: form.action || '',
                        method: form.method || 'GET',
                        fields: []
                    };

                    const elements = form.querySelectorAll(
                        'input, select, textarea, [contenteditable="true"]'
                    );

                    for (const el of elements) {
                        const type = el.type || el.tagName.toLowerCase();
                        // Skip hidden and submit-type fields
                        if (type === 'hidden' || type === 'submit' || type === 'button' || type === 'image') continue;

                        // Find label
                        let label = '';
                        if (el.id) {
                            const labelEl = document.querySelector(`label[for="${el.id}"]`);
                            if (labelEl) label = labelEl.innerText.trim();
                        }
                        if (!label) {
                            const parent = el.closest('label, .form-group, .field, [class*="form"]');
                            if (parent) {
                                const labelEl = parent.querySelector('label, .label, legend');
                                if (labelEl) label = labelEl.innerText.trim();
                            }
                        }
                        if (!label) {
                            label = el.placeholder || el.getAttribute('aria-label') || el.name || '';
                        }

                        const field = {
                            type: type,
                            name: el.name || el.id || '',
                            id: el.id || '',
                            label: label.substring(0, 60),
                            value: el.value || '',
                            required: el.required || false,
                            selector: el.id ? '#' + el.id
                                     : el.name ? `[name="${el.name}"]`
                                     : null,
                        };

                        // Select options
                        if (type === 'select-one' || type === 'select-multiple') {
                            field.options = Array.from(el.options)
                                .filter(o => o.value)
                                .slice(0, 20)
                                .map(o => ({ value: o.value, text: o.text.trim().substring(0, 40) }));
                        }

                        // Radio/checkbox groups
                        if (type === 'radio' || type === 'checkbox') {
                            if (el.name) {
                                const group = document.querySelectorAll(`input[name="${el.name}"]`);
                                field.options = Array.from(group).map(r => ({
                                    value: r.value,
                                    text: r.nextSibling?.textContent?.trim()?.substring(0, 40) || r.value,
                                    checked: r.checked
                                }));
                            }
                        }

                        if (field.selector) {
                            formInfo.fields.push(field);
                        }
                    }

                    // Also find submit buttons
                    const submitBtns = form.querySelectorAll(
                        'button[type="submit"], input[type="submit"], button:not([type])'
                    );
                    formInfo.submit_buttons = Array.from(submitBtns).map(b => ({
                        text: (b.innerText || b.value || 'Submit').trim().substring(0, 30),
                        selector: b.id ? '#' + b.id
                                 : b.name ? `button[name="${b.name}"]`
                                 : b.type === 'submit' ? 'button[type="submit"]'
                                 : null
                    })).filter(b => b.selector);

                    if (formInfo.fields.length > 0) {
                        result.forms.push(formInfo);
                    }
                }
                return result;
            }
        """,
            selector or "",
        )

        if not form_data or not form_data.get("forms"):
            return "No forms found on this page. Try scrolling or navigating to the right page."

        lines = []
        for i, form in enumerate(form_data["forms"]):
            if len(form_data["forms"]) > 1:
                lines.append(f"## Form {i + 1}")
            if form.get("action"):
                lines.append(f"Action: {form['action'][:60]}")

            lines.append(f"\n**Fields ({len(form['fields'])}):**")
            for f in form["fields"]:
                req = " *" if f.get("required") else ""
                label = f["label"] or f["name"] or "unnamed"
                line = (
                    f"- **{label}**{req} (type={f['type']}, selector=`{f['selector']}`)"
                )
                if f.get("value"):
                    line += f" [current: {f['value'][:30]}]"
                lines.append(line)

                if f.get("options"):
                    opts = ", ".join(
                        o.get("text", o.get("value", "")) for o in f["options"][:8]
                    )
                    lines.append(f"  Options: {opts}")

            if form.get("submit_buttons"):
                btns = ", ".join(f"`{b['text']}`" for b in form["submit_buttons"])
                lines.append(f"\nSubmit: {btns}")

        lines.append(
            '\n---\nUse fill_form with value=\'{"selector": "value", ...}\' to fill fields.'
        )

        result = "\n".join(lines)
        return self.format_output(result)

    async def _fill_form(
        self, value: str, selector: str = "", timeout: int = 15000
    ) -> str:
        """Fill multiple form fields at once from a JSON mapping.

        value should be JSON: {"selector_or_name": "value_to_fill", ...}
        selector can optionally scope to a specific form.
        """
        import json as json_mod

        if not value:
            return (
                "Error: value is required. Pass a JSON object mapping field selectors to values.\n"
                'Example: \'{"#name": "John", "[name=\\"email\\"]": "john@example.com"}\'\n'
                "Use extract_form first to see available fields."
            )

        try:
            field_data = json_mod.loads(value)
        except json_mod.JSONDecodeError:
            return (
                "Error: value must be valid JSON.\n"
                'Example: \'{"#name": "John", "[name=\\"email\\"]": "john@example.com"}\''
            )

        if not isinstance(field_data, dict):
            return "Error: value must be a JSON object {selector: value, ...}"

        await self._dismiss_cookies()

        filled = []
        errors = []

        for field_sel, field_val in field_data.items():
            try:
                # Try the selector directly first
                actual_selector = field_sel

                # If it looks like a name (no CSS characters), convert to selector
                if not any(c in field_sel for c in "#.[]="):
                    actual_selector = f'[name="{field_sel}"], #{field_sel}'

                # Scope to form if selector provided
                if selector:
                    actual_selector = f"{selector} {actual_selector}"

                # Determine element type
                el = await self._page.query_selector(actual_selector)
                if not el:
                    # Try by placeholder or label text
                    el = await self._page.query_selector(
                        f'input[placeholder*="{field_sel}" i], '
                        f'textarea[placeholder*="{field_sel}" i]'
                    )
                    if not el:
                        errors.append(f"{field_sel}: not found")
                        continue

                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                input_type = await el.evaluate("el => el.type || ''")

                if tag == "select":
                    await el.select_option(str(field_val), timeout=timeout)
                    filled.append(f"{field_sel} -> selected '{field_val}'")
                elif input_type in ("checkbox", "radio"):
                    is_checked = await el.is_checked()
                    should_check = str(field_val).lower() in (
                        "true",
                        "1",
                        "yes",
                        "on",
                        field_val,
                    )
                    if should_check and not is_checked:
                        await el.check(timeout=timeout)
                        filled.append(f"{field_sel} -> checked")
                    elif not should_check and is_checked:
                        await el.uncheck(timeout=timeout)
                        filled.append(f"{field_sel} -> unchecked")
                    else:
                        filled.append(
                            f"{field_sel} -> already {'checked' if is_checked else 'unchecked'}"
                        )
                elif input_type == "file":
                    errors.append(f"{field_sel}: file inputs not supported")
                else:
                    await el.fill(str(field_val), timeout=timeout)
                    filled.append(f"{field_sel} -> '{str(field_val)[:30]}'")

            except Exception as e:
                errors.append(f"{field_sel}: {str(e)[:50]}")

        result_parts = []
        if filled:
            result_parts.append(f"Filled {len(filled)} fields:")
            for f in filled:
                result_parts.append(f"  {f}")
        if errors:
            result_parts.append(f"\nErrors ({len(errors)}):")
            for e in errors:
                result_parts.append(f"  {e}")

        if not filled and not errors:
            result_parts.append("No fields to fill.")

        result_parts.append(
            "\nNext: click the submit button, or use extract_form to verify filled values."
        )

        return "\n".join(result_parts)

    async def _new_tab(self, url: str = "") -> str:
        """Open a new browser tab, optionally navigating to a URL."""
        page = await self._context.new_page()
        page.set_default_timeout(15000)
        tab_id = f"tab_{len(self._pages) + 1}"
        self._pages[tab_id] = page
        self._page = page

        if url:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            await page.goto(url, wait_until="domcontentloaded")
            await self._dismiss_cookies()
            state = await self._get_page_state_summary()
            return f"Opened new tab {tab_id} at {url}\n{state}"
        return f"Opened new empty tab: {tab_id}"

    async def _switch_tab(self, tab_id: str) -> str:
        """Switch to a different tab."""
        if tab_id in self._pages:
            self._page = self._pages[tab_id]
            state = await self._get_page_state_summary()
            return f"Switched to {tab_id}\n{state}"

        # Try by index
        pages = self._context.pages
        try:
            idx = int(tab_id)
            if 0 <= idx < len(pages):
                self._page = pages[idx]
                return f"Switched to tab index {idx}: {self._page.url}"
        except ValueError:
            pass

        tabs = list(self._pages.keys())
        return f"Tab not found: {tab_id}. Available: {tabs}"

    async def _close(self) -> str:
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
            self._page = None
            self._pages.clear()
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        return "Browser closed"
