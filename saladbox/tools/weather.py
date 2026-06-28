"""Weather tool using wttr.in (no API key required)."""

from __future__ import annotations

import aiohttp

from saladbox.tools.base import BaseTool


class WeatherTool(BaseTool):
    """Get weather information using wttr.in API."""

    @property
    def name(self) -> str:
        return "weather"

    @property
    def description(self) -> str:
        return (
            "Get current weather and forecasts for any location. Provides temperature, "
            "conditions, humidity, wind, and multi-day forecasts. No API key required."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name, zip code, or coordinates (e.g., 'London', '90210', '51.5,-0.1')",
                },
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial", "auto"],
                    "description": "Temperature units: metric (C), imperial (F), or auto",
                },
                "forecast": {
                    "type": "string",
                    "enum": ["current", "today", "3day", "full"],
                    "description": "Forecast period: current, today, 3day, or full",
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "json"],
                    "description": "Output format: text (human-readable) or json (structured)",
                },
            },
            "required": ["location"],
        }

    async def execute(
        self,
        location: str,
        units: str = "metric",
        forecast: str = "current",
        format: str = "text",
    ) -> str:
        if not location.strip():
            return "Error: Location is required"

        location = location.strip().replace(" ", "+")

        if format == "json":
            return await self._get_json(location, units, forecast)
        else:
            return await self._get_text(location, units, forecast)

    async def _get_text(self, location: str, units: str, forecast: str) -> str:
        unit_code = "m" if units == "metric" else "u" if units == "imperial" else ""

        if forecast == "current":
            url = f"https://wttr.in/{location}?format=3&{unit_code}"
        elif forecast == "today":
            url = f"https://wttr.in/{location}?0&{unit_code}"
        elif forecast == "3day":
            url = f"https://wttr.in/{location}?3&{unit_code}"
        else:
            url = f"https://wttr.in/{location}?{unit_code}"

        try:
            async with aiohttp.ClientSession() as session, session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "curl"},
            ) as resp:
                if resp.status != 200:
                    return f"Error: Weather service returned status {resp.status}"
                text = await resp.text()

            return text.strip()

        except aiohttp.ClientError as e:
            return f"Error fetching weather: {e!s}"
        except Exception as e:
            return f"Unexpected error: {e!s}"

    async def _get_json(self, location: str, units: str, forecast: str) -> str:
        url = f"https://wttr.in/{location}?format=j1"

        try:
            async with aiohttp.ClientSession() as session, session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"User-Agent": "curl"},
            ) as resp:
                if resp.status != 200:
                    return f"Error: Weather service returned status {resp.status}"
                data = await resp.json()

            current = data.get("current_condition", [{}])[0]
            location_data = data.get("nearest_area", [{}])[0]

            result = {
                "location": {
                    "name": location_data.get("areaName", [{}])[0].get(
                        "value", "Unknown"
                    ),
                    "region": location_data.get("region", [{}])[0].get("value", ""),
                    "country": location_data.get("country", [{}])[0].get("value", ""),
                },
                "current": {
                    "temp_c": current.get("temp_C"),
                    "temp_f": current.get("temp_F"),
                    "feels_like_c": current.get("FeelsLikeC"),
                    "feels_like_f": current.get("FeelsLikeF"),
                    "description": current.get("weatherDesc", [{}])[0].get("value", ""),
                    "humidity": current.get("humidity"),
                    "wind_speed_kmh": current.get("windspeedKmph"),
                    "wind_dir": current.get("winddir16Point"),
                    "visibility": current.get("visibility"),
                    "pressure": current.get("pressure"),
                    "cloud_cover": current.get("cloudcover"),
                },
            }

            if forecast in ["today", "3day", "full"]:
                weather = data.get("weather", [])
                days = (
                    3
                    if forecast == "3day"
                    else len(weather)
                    if forecast == "full"
                    else 1
                )
                result["forecast"] = []
                for day in weather[:days]:
                    result["forecast"].append(
                        {
                            "date": day.get("date"),
                            "max_temp_c": day.get("maxtempC"),
                            "min_temp_c": day.get("mintempC"),
                            "avg_temp_c": day.get("avgtempC"),
                            "max_temp_f": day.get("maxtempF"),
                            "min_temp_f": day.get("mintempF"),
                            "totalprecip_mm": day.get("totalprecip_mm"),
                            "sunrise": day.get("astronomy", [{}])[0].get("sunrise"),
                            "sunset": day.get("astronomy", [{}])[0].get("sunset"),
                        }
                    )

            import json

            return json.dumps(result, indent=2)

        except aiohttp.ClientError as e:
            return f"Error fetching weather: {e!s}"
        except Exception as e:
            return f"Unexpected error: {e!s}"
