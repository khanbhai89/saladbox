"""Smart tool filtering to reduce tools sent to LLM.

Updated for modern LLM capabilities:
- Reasoning task type gets broader tool access (more iterations, less restriction)
- max_tools bumped to 14 to benefit from modern models' larger context
- Better scoring with word-boundary matching to reduce false positives
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


TOOL_KEYWORDS = {
    "shell": {
        "primary": ["shell", "command", "terminal", "execute", "run command", "bash"],
        "secondary": ["script", "cmd", "cli"],
        "weight": 1.0,
    },
    "reminder": {
        "primary": [
            "reminder",
            "remind me",
            "set reminder",
            "schedule reminder",
            "alert me",
            "notify me",
            "wake me",
            "don't forget",
            "remember to",
            "remind at",
            "remind tomorrow",
            "daily reminder",
            "weekly reminder",
            "recurring reminder",
        ],
        "secondary": ["alarm", "notification", "alert", "snooze", "remind"],
        "weight": 2.0,
    },
    "run_shell": {
        "primary": ["shell", "command", "terminal", "execute", "run command", "bash"],
        "secondary": ["script", "cmd", "cli"],
        "weight": 1.0,
    },
    "python_exec": {
        "primary": ["python", "python code", "execute python", "run python"],
        "secondary": ["py script", "python script"],
        "weight": 1.0,
    },
    "run_python": {
        "primary": ["python", "python code", "execute python", "run python"],
        "secondary": ["py script", "python script"],
        "weight": 1.0,
    },
    "browser": {
        "primary": [
            "browser",
            "website",
            "web page",
            "navigate to",
            "click on",
            "screenshot",
            "open youtube",
            "play video",
            "youtube",
            "watch video",
            "search on google",
            "google search",
            "search google",
            "search the web",
            "search for",
            "look up",
            "find online",
            "web search",
            "search online",
            "find on the web",
            "research",
            "find best",
            "compare",
            "what should i buy",
            "browse results",
            "visit",
            "fill form",
            "fill out",
            "fill in",
            "register",
            "sign up",
            "book ticket",
            "buy ticket",
            "checkout",
            "booking",
            "registration",
            "apply for",
            "submit form",
        ],
        "secondary": [
            "web",
            "url",
            "open page",
            "click",
            "goto",
            "type in",
            "browse",
            "internet",
            "google",
            "online",
            "shop",
            "store",
            "buy",
            "product",
            "price",
            "form",
            "ticket",
            "reserve",
            "signup",
            "login",
        ],
        "weight": 2.5,
    },
    "filesystem": {
        "primary": [
            "file",
            "directory",
            "folder",
            "read file",
            "write file",
            "list files",
            "search files",
        ],
        "secondary": ["path", "ls", "mkdir", "delete file"],
        "weight": 1.0,
    },
    "system_monitor": {
        "primary": [
            "system resources",
            "cpu usage",
            "memory usage",
            "disk usage",
            "system status",
            "check system",
            "system info",
        ],
        "secondary": [
            "cpu",
            "memory",
            "ram",
            "process",
            "running processes",
            "performance",
            "resources",
        ],
        "weight": 1.5,
    },
    "scheduler": {
        "primary": ["schedule", "cron", "recurring task", "scheduled task"],
        "secondary": ["timer task", "periodic"],
        "weight": 1.0,
    },
    "process_manager": {
        "primary": [
            "background process",
            "start process",
            "stop process",
            "long running",
        ],
        "secondary": ["daemon", "service"],
        "weight": 1.0,
    },
    "code_editor": {
        "primary": [
            "edit code",
            "code editor",
            "project",
            "find in code",
            "refactor",
            "open project",
        ],
        "secondary": ["source code", "codebase", "src"],
        "weight": 1.0,
    },
    "git": {
        "primary": [
            "git",
            "commit",
            "push",
            "pull",
            "branch",
            "merge",
            "clone repo",
            "pull request",
        ],
        "secondary": ["repository", "github", "version control"],
        "weight": 1.5,
    },
    "web_search": {
        "primary": [
            "search for",
            "find information about",
            "look up",
            "web search",
            "google",
            "search the web",
            "deep search",
            "find facts",
            "quick search",
        ],
        "secondary": ["find out", "search online", "info about", "learn about", "what is", "who is", "how to"],
        "weight": 1.5,
    },
    "calculator": {
        "primary": [
            "calculate",
            "compute",
            "what is 2+",
            "math",
            "sqrt",
            "square root",
            "power of",
            "multiply",
            "divide",
            "plus",
            "minus",
        ],
        "secondary": ["arithmetic", "equation"],
        "weight": 1.5,
    },
    "datetime_tool": {
        "primary": [
            "what time",
            "what date",
            "what day",
            "timezone",
            "current time",
            "current date",
            "convert time",
        ],
        "secondary": ["clock", "calendar", "today"],
        "weight": 1.5,
    },
    "clipboard": {
        "primary": [
            "clipboard",
            "copy to clipboard",
            "paste from clipboard",
            "read clipboard",
        ],
        "secondary": ["copy", "paste"],
        "weight": 1.0,
    },
    "notes": {
        "primary": [
            "note",
            "save note",
            "my notes",
            "remember this",
            "recall note",
            "stored notes",
        ],
        "secondary": ["remember", "save for later"],
        "weight": 1.0,
    },
    "weather": {
        "primary": [
            "weather in",
            "weather forecast",
            "temperature in",
            "what is the weather",
            "how is the weather",
        ],
        "secondary": ["rain", "sunny", "cloudy", "humidity", "forecast"],
        "weight": 1.5,
    },
    "http_client": {
        "primary": [
            "http request",
            "api call",
            "fetch url",
            "get request",
            "post request",
            "api endpoint",
        ],
        "secondary": ["rest api", "http"],
        "weight": 1.0,
    },
    "json_yaml": {
        "primary": ["json", "yaml", "parse json", "format json", "convert yaml"],
        "secondary": ["validate json", "json format"],
        "weight": 1.0,
    },
    "encoding": {
        "primary": ["base64", "encode", "decode", "hash", "md5", "sha256", "uuid"],
        "secondary": ["hex", "url encode"],
        "weight": 1.0,
    },
    "text": {
        "primary": [
            "convert to uppercase",
            "convert to lowercase",
            "sort lines",
            "count words",
            "text manipulation",
        ],
        "secondary": ["text", "string"],
        "weight": 1.0,
    },
    "password": {
        "primary": [
            "password",
            "generate password",
            "secure password",
            "random password",
            "passphrase",
            "create password",
        ],
        "secondary": ["secret key", "api key"],
        "weight": 1.5,
    },
    "finance": {
        "primary": [
            "bitcoin price",
            "bitcoin prices",
            "bitcoin",
            "crypto price",
            "crypto prices",
            "btc",
            "eth",
            "ethereum",
            "cryptocurrency",
            "cryptocurrencies",
            "exchange rate",
        ],
        "secondary": ["stock", "trading", "usd to", "currency"],
        "weight": 1.5,
    },
    "timer": {
        "primary": ["set timer", "timer for", "countdown", "stopwatch", "set alarm"],
        "secondary": ["countdown timer", "alarm"],
        "weight": 1.0,
    },
    "qrcode": {
        "primary": ["qr code", "qrcode", "generate qr", "scan qr"],
        "secondary": ["barcode"],
        "weight": 1.0,
    },
    "translate": {
        "primary": [
            "translate",
            "translation",
            "in spanish",
            "in french",
            "in german",
            "in japanese",
            "to english",
        ],
        "secondary": ["language", "spanish", "french", "german"],
        "weight": 1.5,
    },
    "color": {
        "primary": [
            "color",
            "hex color",
            "rgb color",
            "convert color",
            "color palette",
        ],
        "secondary": ["colour", "#"],
        "weight": 1.0,
    },
    "unit_converter": {
        "primary": [
            "convert",
            "celsius to fahrenheit",
            "km to miles",
            "kg to lbs",
            "unit conversion",
        ],
        "secondary": ["measurement", "meters", "feet"],
        "weight": 1.5,
    },
    "url": {
        "primary": ["parse url", "url components", "extract domain", "build url"],
        "secondary": ["link", "uri"],
        "weight": 1.0,
    },
    "location": {
        "primary": [
            "geocode",
            "coordinates",
            "latitude",
            "longitude",
            "location of",
            "where is",
        ],
        "secondary": ["map", "address", "gps"],
        "weight": 1.0,
    },
    "docker": {
        "primary": [
            "docker",
            "container",
            "docker container",
            "docker image",
            "docker ps",
        ],
        "secondary": ["docker-compose", "containerize"],
        "weight": 1.5,
    },
    "open_url": {
        "primary": [
            "open youtube",
            "play video",
            "play on youtube",
            "watch video",
            "watch on youtube",
            "open in browser",
            "open website",
            "open google maps",
            "open maps",
            "open spotify",
            "open reddit",
            "open github",
            "open twitter",
            "open amazon",
            "open wikipedia",
            "search youtube",
            "search on youtube",
            "youtube search",
            "go to",
            "launch",
            "open link",
            "open url",
            "open this",
            "show me on youtube",
            "find on youtube",
        ],
        "secondary": [
            "youtube",
            "play",
            "watch",
            "open",
            "visit",
            "launch",
            "stream",
            "video",
        ],
        "weight": 3.0,
    },
    "image_gen": {
        "primary": [
            "generate image",
            "create image",
            "make image",
            "draw",
            "make a picture",
            "image of",
            "generate a picture",
            "create a picture",
            "generate art",
            "create art",
            "make art",
            "create an image",
            "generate an image",
            "create a picture of",
            "draw a picture",
        ],
        "secondary": [
            "illustration",
            "artwork",
            "photo of",
            "painting",
            "picture",
            "image",
            "render",
            "visualize",
        ],
        "weight": 2.5,
    },
    "screen_capture": {
        "primary": [
            "take screenshot",
            "screenshot",
            "capture screen",
            "screen capture",
            "take a screenshot",
            "screenshot of",
            "capture my screen",
            "show my screen",
            "grab screen",
            "print screen",
            "snap screen",
            "show what is on screen",
            "show homescreen",
            "take screenshot of homescreen",
        ],
        "secondary": [
            "screenshot",
            "screen",
            "capture",
            "snap",
            "homescreen",
        ],
        "weight": 2.5,
    },
}

RECOGNITION_PATTERNS = {
    "system_monitor": [
        r"\bcheck\s+(my\s+)?system\b",
        r"\bsystem\s+(resources|status|info)\b",
        r"\b(cpu|memory|disk)\s+(usage|status)\b",
        r"\bwhat.*using.*memory\b",
        r"\bhow\s+much\s+(cpu|memory|ram)\b",
    ],
    "weather": [
        r"\bweather\s+(in|for|at)\s+\w+",
        r"\bwhat.*weather\b",
        r"\btemperature\s+(in|for)\s+\w+",
        r"\bforecast\s+(for|in)\s+\w+",
    ],
    "finance": [
        r"\b(bitcoin|btc)\s+price\b",
        r"\b(ethereum|eth)\s+price\b",
        r"\bcrypto\s+price\b",
        r"\bwhat.*bitcoin\b",
        r"\bexchange\s+rate\b",
        r"\b(what\s+is\s+)?(btc|bitcoin|eth|ethereum)\s+(at|price|value|worth)\b",
        r"\b(btc|bitcoin|eth|ethereum)\s+price\b",
    ],
    "calculator": [
        r"\bcalculate\s+",
        r"\bcompute\s+",
        r"\bwhat\s+is\s+\d+",
        r"\d+\s*[\+\-\*\/]\s*\d+",
        r"\bsqrt\s*\(",
    ],
    "password": [
        r"\bgenerate\s+(a\s+)?password\b",
        r"\bcreate\s+(a\s+)?password\b",
        r"\brandom\s+password\b",
        r"\bsecure\s+password\b",
    ],
    "datetime_tool": [
        r"\bwhat\s+time\s+is\s+it\b",
        r"\bwhat\s+(is\s+the\s+)?date\b",
        r"\bwhat\s+day\s+is\s+it\b",
        r"\bcurrent\s+time\b",
        r"\btime\s+in\s+\w+",
    ],
    "translate": [
        r"\btranslate\s+.*\s+to\s+\w+",
        r"\b(in|to)\s+(spanish|french|german|japanese|chinese|italian)\b",
    ],
    "git": [
        r"\bgit\s+(commit|push|pull|branch|merge|status)\b",
        r"\bcreate\s+(a\s+)?(commit|branch)\b",
        r"\bpull\s+request\b",
    ],
    "docker": [
        r"\bdocker\s+(ps|images|run|stop|start|logs)\b",
        r"\bcontainer\s+(status|list|stop|start)\b",
    ],
    "reminder": [
        r"\bremind\s+me\b",
        r"\bset\s+(a\s+)?reminder\b",
        r"\breminder\s+(at|for|in|tomorrow)\b",
        r"\bnotify\s+me\b",
        r"\balert\s+me\b",
        r"\bdaily\s+reminder\b",
        r"\bweekly\s+reminder\b",
        r"\bdon'?t\s+forget\b",
    ],
    "browser": [
        r"\bfill\s+(out|in)\s+(the\s+)?form\b",
        r"\bfill\s+form\b",
        r"\b(book|buy|purchase)\s+(a\s+)?(ticket|flight|hotel)\b",
        r"\b(register|sign\s*up)\s+(for|on|at)\b",
        r"\bcheckout\b",
        r"\bapply\s+(for|to)\b",
        r"\bsubmit\s+(the\s+)?form\b",
        r"\bgoogle\s+search\b",
        r"\bsearch\s+google\b",
        r"\bopen\s+(website|page|url)\b",
    ],
    "web_search": [
        r"\bsearch\s+(for|the\s+web)\b",
        r"\bwhat\s+is\s+(?!\d+\b)\w+",
        r"\bwho\s+is\s+\w+",
        r"\bhow\s+to\s+\w+",
        r"\bfind\s+information\b",
        r"\blook\s+up\b",
    ],
    "open_url": [
        r"\b(play|watch)\s+.{0,30}\b(youtube|video)\b",
        r"\b(open|launch|go\s+to)\s+(youtube|google|maps|spotify|reddit|github|twitter|amazon|wikipedia|stackoverflow)\b",
        r"\bsearch\s+(on\s+)?youtube\b",
        r"\byoutube\s+search\b",
        r"\bopen\s+(this\s+)?(link|url|website|page)\b",
        r"\bplay\s+(a\s+|some\s+)?(video|music|song)\b",
        r"\bwatch\s+(a\s+|some\s+)?(video|movie|clip)\b",
        r"\bshow\s+me\s+on\s+youtube\b",
        r"\bfind\s+on\s+youtube\b",
        r"\bopen\s+in\s+(the\s+)?browser\b",
        r"\bstream\s+(on\s+)?(youtube|spotify)\b",
    ],
    "image_gen": [
        r"\b(generate|create|make|draw)\s+(an?\s+)?(image|picture|photo|illustration|artwork)\b",
        r"\b(image|picture|photo)\s+of\b",
        r"\bgenerate\s+art\b",
        r"\bcreate\s+(an?\s+)?(illustration|artwork|render)\b",
        r"\bmake\s+(an?\s+)?(image|picture|photo)\b",
    ],
    "screen_capture": [
        r"\b(take|capture|grab|snap)\s+(a\s+)?screenshot\b",
        r"\bscreenshot\s+(of|my)\b",
        r"\bcapture\s+(my\s+)?screen\b",
        r"\bscreen\s*capture\b",
        r"\bshow\s+(my\s+|what.+)?screen\b",
        r"\bprint\s+screen\b",
        r"\bhomescreen\b",
    ],
}


class ToolFilter:
    """Smart tool filtering based on query analysis.

    Uses keyword scoring + regex patterns to pick the most relevant tools
    from the full registered set, capping at max_tools to keep prompts tight.
    For 'reasoning' tasks the cap is relaxed to allow broader exploration.
    """

    def __init__(self, max_tools: int = 14):
        self.max_tools = max_tools

    def score_relevance(self, query: str, tool_name: str) -> float:
        """Score how relevant a tool is for a query."""
        query_lower = query.lower()
        score = 0.0

        if tool_name not in TOOL_KEYWORDS:
            return 0.0

        def _match_keyword(q: str, kw: str) -> bool:
            # If the keyword has no alphanumeric characters, check substring match (e.g. "#")
            if not any(c.isalnum() or c == '_' for c in kw):
                return kw in q

            # Construct a regex that respects word boundaries for alphanumeric bounds
            pattern = r""
            if kw[0].isalnum() or kw[0] == '_':
                pattern += r"\b"
            pattern += re.escape(kw)
            if kw[-1].isalnum() or kw[-1] == '_':
                pattern += r"\b"
            return bool(re.search(pattern, q))

        tool_info = TOOL_KEYWORDS[tool_name]
        weight = tool_info.get("weight", 1.0)

        for keyword in tool_info.get("primary", []):
            if _match_keyword(query_lower, keyword):
                score += 3.0 * weight

        for keyword in tool_info.get("secondary", []):
            if _match_keyword(query_lower, keyword):
                score += 1.0 * weight

        if tool_name in RECOGNITION_PATTERNS:
            for pattern in RECOGNITION_PATTERNS[tool_name]:
                if re.search(pattern, query_lower):
                    score += 5.0 * weight
                    break

        return score

    def get_relevant_tools(
        self,
        query: str,
        all_tools: list[dict],
        min_tools: int = 6,
        task_type: str = "default",
    ) -> list[dict]:
        """Get most relevant tools for a query.

        For 'reasoning' task type the cap is raised by 4 to let the model
        explore a wider set of tools during complex multi-step analysis.
        """
        effective_max = self.max_tools
        if task_type == "reasoning":
            effective_max = min(self.max_tools + 4, len(all_tools))

        if len(all_tools) <= effective_max:
            return all_tools

        tool_scores: list[tuple[str, float]] = []

        for tool in all_tools:
            name = tool.get("function", {}).get("name", "")
            score = self.score_relevance(query, name)
            tool_scores.append((name, score, tool))

        tool_scores.sort(key=lambda x: x[1], reverse=True)

        selected_tools = []
        selected_names = set()

        for name, score, tool in tool_scores:
            if score > 0:
                selected_tools.append(tool)
                selected_names.add(name)
            if len(selected_tools) >= effective_max:
                break

        if len(selected_tools) < min_tools:
            for name, score, tool in tool_scores:
                if name not in selected_names:
                    selected_tools.append(tool)
                    selected_names.add(name)
                if len(selected_tools) >= min_tools:
                    break

        essential_tools = {"run_shell", "filesystem", "web_search", "open_url"}
        for tool in all_tools:
            name = tool.get("function", {}).get("name", "")
            if name in essential_tools and name not in selected_names:
                selected_tools.append(tool)
                selected_names.add(name)

        logger.info(
            f"Tool filtering: {len(all_tools)} -> {len(selected_tools)} tools "
            f"(task_type={task_type}, cap={effective_max}). "
            f"Top: {list(selected_names)[:5]}"
        )

        return selected_tools

    def get_best_tool(
        self, query: str, all_tools: list[dict]
    ) -> tuple[str, dict] | None:
        """Get single best tool for a query (for fallback)."""
        best_name = None
        best_score = 0.0

        for tool in all_tools:
            name = tool.get("function", {}).get("name", "")
            score = self.score_relevance(query, name)
            if score > best_score:
                best_score = score
                best_name = name

        if best_name and best_score > 0:
            best_args = self._get_default_args(best_name, query)
            logger.info(f"[TOOL_FILTER] Best tool: {best_name}, args: {best_args}")
            return best_name, best_args

        return None

    def _get_default_args(self, tool_name: str, query: str = "") -> dict[str, Any]:
        # Smart extraction for reminder — parse message and time from query
        if tool_name == "reminder" and query:
            return self._extract_reminder_args(query)

        # Smart extraction for image_gen — use the query as the prompt
        if tool_name == "image_gen" and query:
            return {"prompt": query}

        # Smart extraction for browser — extract search query from request
        if tool_name == "browser" and query:
            return self._extract_browser_args(query)

        defaults = {
            "system_monitor": {"action": "all"},
            "web_search": {"query": ""},
            "weather": {"location": "", "forecast": "current"},
            "calculator": {"expression": ""},
            "datetime_tool": {"action": "now"},
            "filesystem": {"action": "list", "path": "."},
            "run_shell": {"command": ""},
            "finance": {"action": "crypto", "symbol": "bitcoin"},
            "password": {"action": "password"},
            "translate": {"action": "detect"},
            "notes": {"action": "list"},
            "timer": {"action": "list"},
            "clipboard": {"action": "read"},
            "docker": {"action": "ps"},
            "git": {"action": "status"},
            "open_url": {"site": "youtube", "query": ""},
            "screen_capture": {"action": "capture"},
            "image_gen": {"prompt": ""},
            "reminder": {"action": "add", "message": "", "remind_at": ""},
            "browser": {"action": "google_search", "value": ""},
        }
        return defaults.get(tool_name, {})

    @staticmethod
    def _extract_reminder_args(query: str) -> dict[str, Any]:
        """Parse a reminder query into action/message/remind_at args.

        Handles patterns like:
        - "remind me in 5 minutes to check emails"
        - "remind me at 8pm to call mom"
        - "set a reminder for tomorrow at 9am meeting with John"
        """
        q = query.lower().strip()

        # Extract time expression
        remind_at = ""
        time_patterns = [
            # "in X minutes/hours"
            (r"\bin\s+(\d+\s+(?:minutes?|mins?|hours?|hrs?|seconds?|secs?))", None),
            # "at 8pm", "at 3:30 PM"
            (r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", None),
            # "tomorrow", "tomorrow at X"
            (r"\b(tomorrow(?:\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?)", None),
            # "in X minutes" — just the time part
            (r"\b(in\s+\d+\s+\w+)", None),
        ]

        for pattern, _ in time_patterns:
            match = re.search(pattern, q)
            if match:
                remind_at = match.group(1).strip()
                break

        if not remind_at:
            remind_at = "5 minutes"

        # Extract message — strip out the time and reminder keywords
        message = q
        # Remove common prefixes
        for prefix in [
            r"remind\s+me\s+",
            r"set\s+(a\s+)?reminder\s+(for\s+|to\s+)?",
            r"don'?t\s+forget\s+to\s+",
            r"notify\s+me\s+to\s+",
            r"alert\s+me\s+to\s+",
        ]:
            message = re.sub(prefix, "", message, count=1).strip()

        # Remove time expressions from message
        for pattern, _ in time_patterns:
            message = re.sub(pattern, "", message).strip()

        # Clean up connectors
        message = re.sub(r"^\s*(to|that|about)\s+", "", message).strip()
        message = re.sub(r"\s+", " ", message).strip()

        if not message:
            message = query  # Fall back to full query

        return {
            "action": "add",
            "message": message,
            "remind_at": remind_at,
        }

    def _extract_browser_args(self, query: str) -> dict[str, Any]:
        """Extract browser action and search query from user request.

        Handles patterns like:
        - "open browser and signup for esim" -> action="google_search", value="esim signup"
        - "search for flights to paris" -> action="google_search", value="flights to paris"
        - "go to google.com" -> action="navigate", value="google.com"
        """
        q = query.lower().strip()

        # Check for URL patterns like "go to X" or "visit X"
        url_match = re.search(
            r"\b(?:go\s+to|visit|open|navigate\s+to)\s+(https?://)?(\S+)", q
        )
        if url_match:
            url = url_match.group(2)
            # Add https:// if no protocol specified
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            return {"action": "navigate", "value": url}

        # Default: treat as google search, extract what user wants
        search_query = q
        # Remove common browser-opening prefixes
        for prefix in [
            r"^open\s+(the\s+)?browser\s+(and\s+)?",
            r"^start\s+browser\s+(and\s+)?",
            r"^launch\s+browser\s+(and\s+)?",
            r"^go\s+to\s+browser\s+(and\s+)?",
            r"^browse\s+(the\s+)?web\s+(and\s+)?",
            r"^search\s+(the\s+)?web\s+(for\s+)?",
            r"^search\s+for\s+",
            r"^find\s+",
            r"^look\s+up\s+",
        ]:
            search_query = re.sub(prefix, "", search_query).strip()

        # Clean up
        search_query = re.sub(r"\s+", " ", search_query).strip()

        if not search_query:
            search_query = query  # Fall back to full query

        return {"action": "google_search", "value": search_query}
