"""Translation tool using free APIs."""

from __future__ import annotations

import aiohttp
from typing import Optional

from saladbox.tools.base import BaseTool


class TranslateTool(BaseTool):
    """Translate text between languages."""

    LANGUAGE_NAMES = {
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "ru": "Russian",
        "ja": "Japanese",
        "ko": "Korean",
        "zh": "Chinese",
        "ar": "Arabic",
        "hi": "Hindi",
        "tr": "Turkish",
        "pl": "Polish",
        "nl": "Dutch",
        "sv": "Swedish",
        "da": "Danish",
        "fi": "Finnish",
        "no": "Norwegian",
        "el": "Greek",
        "he": "Hebrew",
        "th": "Thai",
        "vi": "Vietnamese",
        "id": "Indonesian",
        "ms": "Malay",
        "cs": "Czech",
        "ro": "Romanian",
        "hu": "Hungarian",
        "uk": "Ukrainian",
        "bn": "Bengali",
        "ta": "Tamil",
        "te": "Telugu",
        "ml": "Malayalam",
        "fa": "Persian",
        "ur": "Urdu",
        "sw": "Swahili",
    }

    @property
    def name(self) -> str:
        return "translate"

    @property
    def description(self) -> str:
        return (
            "Translate text between different languages. Supports auto-detection of source "
            "language. Uses free translation APIs. Common language codes: en (English), "
            "es (Spanish), fr (French), de (German), zh (Chinese), ja (Japanese)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["translate", "detect", "languages"],
                    "description": "Translation operation",
                },
                "text": {
                    "type": "string",
                    "description": "Text to translate or detect language",
                },
                "source_lang": {
                    "type": "string",
                    "description": "Source language code (default: auto-detect)",
                },
                "target_lang": {
                    "type": "string",
                    "description": "Target language code (required for translate)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        text: Optional[str] = None,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None,
    ) -> str:
        if action == "translate":
            if not text or not target_lang:
                return "Error: 'text' and 'target_lang' required for translate action"
            return await self._translate(text, source_lang, target_lang)

        elif action == "detect":
            if not text:
                return "Error: 'text' required for detect action"
            return await self._detect_language(text)

        elif action == "languages":
            return self._list_languages()

        else:
            return f"Unknown action: {action}"

    async def _translate(self, text: str, source: Optional[str], target: str) -> str:
        source = source or "auto"

        url = "https://api.mymemory.translated.net/get"
        params = {
            "q": text[:500],
            "langpair": f"{source}|{target}",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        return f"Translation failed with status {resp.status}"
                    data = await resp.json()

            if data.get("responseStatus") != 200:
                return (
                    f"Translation error: {data.get('responseDetails', 'Unknown error')}"
                )

            translated = data.get("responseData", {}).get("translatedText", "")
            detected_lang = data.get("responseData", {}).get("detectedLanguage", {})

            result = [f"**Translation**"]

            if detected_lang and source == "auto":
                src_lang = detected_lang.get("language", source)
                result.append(
                    f"Detected: {self.LANGUAGE_NAMES.get(src_lang, src_lang)}"
                )

            result.append(
                f"From: {self.LANGUAGE_NAMES.get(source, source) if source != 'auto' else 'Auto-detected'}"
            )
            result.append(f"To: {self.LANGUAGE_NAMES.get(target, target)}")
            result.append(f"\n**Original:**\n{text}")
            result.append(f"\n**Translation:**\n{translated}")

            return "\n".join(result)

        except aiohttp.ClientError as e:
            return f"Translation error: {str(e)}"
        except Exception as e:
            return f"Error: {str(e)}"

    async def _detect_language(self, text: str) -> str:
        url = "https://api.mymemory.translated.net/get"
        params = {
            "q": text[:200],
            "langpair": "auto|en",
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status != 200:
                        return f"Detection failed with status {resp.status}"
                    data = await resp.json()

            detected = data.get("responseData", {}).get("detectedLanguage", {})

            if not detected:
                return "Could not detect language"

            lang_code = detected.get("language", "unknown")
            confidence = detected.get("confidence", 0)

            lang_name = self.LANGUAGE_NAMES.get(lang_code, lang_code)

            return (
                f"**Language Detection**\n"
                f"Language: {lang_name} ({lang_code})\n"
                f"Confidence: {confidence:.1%}"
                if confidence
                else f"Language: {lang_name} ({lang_code})"
            )

        except Exception as e:
            return f"Detection error: {str(e)}"

    def _list_languages(self) -> str:
        result = ["**Supported Languages**\n"]

        for code, name in sorted(self.LANGUAGE_NAMES.items(), key=lambda x: x[1]):
            result.append(f"- {name}: `{code}`")

        return "\n".join(result)
