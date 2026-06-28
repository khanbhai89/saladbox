"""Location and maps tool."""

from __future__ import annotations

import aiohttp

from saladbox.tools.base import BaseTool


class LocationTool(BaseTool):
    """Get location information, geocoding, and maps links."""

    @property
    def name(self) -> str:
        return "location"

    @property
    def description(self) -> str:
        return (
            "Get information about locations: geocoding (address to coordinates), "
            "reverse geocoding (coordinates to address), timezone info, and generate "
            "map links. Uses free Nominatim API (OpenStreetMap)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["geocode", "reverse", "search", "map_link", "distance"],
                    "description": "Location operation",
                },
                "address": {
                    "type": "string",
                    "description": "Address to geocode",
                },
                "lat": {
                    "type": "number",
                    "description": "Latitude coordinate",
                },
                "lon": {
                    "type": "number",
                    "description": "Longitude coordinate",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for locations",
                },
                "dest_lat": {
                    "type": "number",
                    "description": "Destination latitude for distance calculation",
                },
                "dest_lon": {
                    "type": "number",
                    "description": "Destination longitude for distance calculation",
                },
                "provider": {
                    "type": "string",
                    "enum": ["google", "apple", "osm"],
                    "description": "Map provider for links (default: google)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        address: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        query: str | None = None,
        dest_lat: float | None = None,
        dest_lon: float | None = None,
        provider: str = "google",
    ) -> str:
        if action == "geocode":
            if not address:
                return "Error: 'address' required for geocode action"
            return await self._geocode(address)

        elif action == "reverse":
            if lat is None or lon is None:
                return "Error: 'lat' and 'lon' required for reverse geocoding"
            return await self._reverse_geocode(lat, lon)

        elif action == "search":
            if not query:
                return "Error: 'query' required for search action"
            return await self._search_locations(query)

        elif action == "map_link":
            return self._generate_map_link(lat, lon, address, provider)

        elif action == "distance":
            if lat is None or lon is None or dest_lat is None or dest_lon is None:
                return "Error: both origin (lat, lon) and destination (dest_lat, dest_lon) required"
            return self._calculate_distance(lat, lon, dest_lat, dest_lon)

        else:
            return f"Unknown action: {action}"

    async def _geocode(self, address: str) -> str:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": address,
            "format": "json",
            "limit": 3,
            "addressdetails": 1,
        }

        try:
            async with aiohttp.ClientSession() as session, session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "Saladbox/1.0"},
            ) as resp:
                if resp.status != 200:
                    return f"Error: API returned status {resp.status}"
                data = await resp.json()

            if not data:
                return f"No results found for: {address}"

            result = [f"**Geocoding Results for '{address}'**\n"]

            for i, item in enumerate(data, 1):
                result.append(f"\n{i}. **{item.get('display_name', 'Unknown')}**")
                result.append(
                    f"   Coordinates: {item.get('lat', 'N/A')}, {item.get('lon', 'N/A')}"
                )
                result.append(f"   Type: {item.get('type', 'N/A')}")

                addr = item.get("address", {})
                if addr.get("city"):
                    result.append(f"   City: {addr['city']}")
                if addr.get("country"):
                    result.append(f"   Country: {addr['country']}")

            return "\n".join(result)

        except aiohttp.ClientError as e:
            return f"Network error: {e!s}"
        except Exception as e:
            return f"Error: {e!s}"

    async def _reverse_geocode(self, lat: float, lon: float) -> str:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "addressdetails": 1,
        }

        try:
            async with aiohttp.ClientSession() as session, session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "Saladbox/1.0"},
            ) as resp:
                if resp.status != 200:
                    return f"Error: API returned status {resp.status}"
                data = await resp.json()

            if "error" in data:
                return f"Error: {data['error']}"

            result = ["**Reverse Geocoding Result**\n"]
            result.append(f"Coordinates: {lat}, {lon}")
            result.append(f"\n**Address:** {data.get('display_name', 'Unknown')}")

            addr = data.get("address", {})
            if addr:
                result.append("\n**Details:**")
                for key in [
                    "house_number",
                    "road",
                    "suburb",
                    "city",
                    "state",
                    "postcode",
                    "country",
                ]:
                    if addr.get(key):
                        result.append(f"  {key.title()}: {addr[key]}")

            return "\n".join(result)

        except aiohttp.ClientError as e:
            return f"Network error: {e!s}"
        except Exception as e:
            return f"Error: {e!s}"

    async def _search_locations(self, query: str) -> str:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 5,
        }

        try:
            async with aiohttp.ClientSession() as session, session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "Saladbox/1.0"},
            ) as resp:
                if resp.status != 200:
                    return f"Error: API returned status {resp.status}"
                data = await resp.json()

            if not data:
                return f"No locations found for: {query}"

            result = [f"**Location Search: '{query}'**\n"]

            for i, item in enumerate(data, 1):
                name = item.get("display_name", "Unknown")[:80]
                result.append(f"{i}. {name}")
                result.append(f"   📍 {item.get('lat')}, {item.get('lon')}")

            return "\n".join(result)

        except Exception as e:
            return f"Error: {e!s}"

    def _generate_map_link(
        self,
        lat: float | None,
        lon: float | None,
        address: str | None,
        provider: str,
    ) -> str:
        if lat is not None and lon is not None:
            if provider == "google":
                url = f"https://www.google.com/maps?q={lat},{lon}"
            elif provider == "apple":
                url = f"https://maps.apple.com/?q={lat},{lon}"
            else:
                url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}&zoom=15"

            return f"**Map Link ({provider.title()})**\nCoordinates: {lat}, {lon}\nURL: {url}"

        elif address:
            encoded = address.replace(" ", "+")
            if provider == "google":
                url = f"https://www.google.com/maps/search/{encoded}"
            elif provider == "apple":
                url = f"https://maps.apple.com/?q={encoded}"
            else:
                url = f"https://www.openstreetmap.org/search?query={encoded}"

            return f"**Map Link ({provider.title()})**\nAddress: {address}\nURL: {url}"

        else:
            return "Error: Either coordinates (lat, lon) or address required"

    def _calculate_distance(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> str:
        import math

        R = 6371

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance_km = R * c
        distance_mi = distance_km * 0.621371

        bearing = self._calculate_bearing(lat1, lon1, lat2, lon2)

        return (
            f"**Distance Calculation**\n"
            f"From: {lat1}, {lon1}\n"
            f"To: {lat2}, {lon2}\n"
            f"Distance: {distance_km:.2f} km ({distance_mi:.2f} miles)\n"
            f"Bearing: {bearing:.1f}°"
        )

    def _calculate_bearing(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        import math

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lon = math.radians(lon2 - lon1)

        x = math.sin(delta_lon) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(
            lat2_rad
        ) * math.cos(delta_lon)

        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360) % 360
