"""Unit conversion tool."""

from __future__ import annotations

from typing import Optional

from saladbox.tools.base import BaseTool


class UnitConverterTool(BaseTool):
    """Convert between different units of measurement."""

    LENGTH_UNITS = {
        "mm": 0.001,
        "cm": 0.01,
        "m": 1,
        "km": 1000,
        "in": 0.0254,
        "ft": 0.3048,
        "yd": 0.9144,
        "mi": 1609.344,
        "nmi": 1852,
    }

    WEIGHT_UNITS = {
        "mg": 0.000001,
        "g": 0.001,
        "kg": 1,
        "t": 1000,
        "oz": 0.0283495,
        "lb": 0.453592,
        "st": 6.35029,
    }

    VOLUME_UNITS = {
        "ml": 0.001,
        "l": 1,
        "m3": 1000,
        "tsp": 0.00492892,
        "tbsp": 0.0147868,
        "floz": 0.0295735,
        "cup": 0.236588,
        "pt": 0.473176,
        "qt": 0.946353,
        "gal": 3.78541,
    }

    TEMPERATURE_OFFSETS = {"c": 0, "f": -32, "k": -273.15}
    TEMPERATURE_SCALES = {"c": 1, "f": 5 / 9, "k": 1}

    AREA_UNITS = {
        "mm2": 0.000001,
        "cm2": 0.0001,
        "m2": 1,
        "km2": 1000000,
        "ha": 10000,
        "ac": 4046.86,
        "sqft": 0.092903,
        "sqmi": 2589988,
    }

    SPEED_UNITS = {
        "mps": 1,
        "kph": 0.277778,
        "mph": 0.44704,
        "knot": 0.514444,
        "fps": 0.3048,
    }

    DATA_UNITS = {
        "b": 1,
        "kb": 1000,
        "mb": 1000000,
        "gb": 1000000000,
        "tb": 1000000000000,
        "pb": 1000000000000000,
        "kib": 1024,
        "mib": 1048576,
        "gib": 1073741824,
        "tib": 1099511627776,
        "pib": 1125899906842624,
    }

    TIME_UNITS = {
        "ns": 1e-9,
        "us": 1e-6,
        "ms": 0.001,
        "s": 1,
        "min": 60,
        "h": 3600,
        "d": 86400,
        "wk": 604800,
        "mo": 2592000,
        "yr": 31536000,
    }

    PRESSURE_UNITS = {
        "pa": 1,
        "kpa": 1000,
        "bar": 100000,
        "psi": 6894.76,
        "atm": 101325,
        "mmhg": 133.322,
    }

    @property
    def name(self) -> str:
        return "unit_converter"

    @property
    def description(self) -> str:
        return (
            "Convert between units of length, weight, volume, temperature, area, speed, "
            "data storage, time, and pressure. Supports metric and imperial units."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["convert", "list"],
                    "description": "Conversion operation",
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "length",
                        "weight",
                        "volume",
                        "temperature",
                        "area",
                        "speed",
                        "data",
                        "time",
                        "pressure",
                    ],
                    "description": "Unit category",
                },
                "value": {
                    "type": "number",
                    "description": "Value to convert",
                },
                "from_unit": {
                    "type": "string",
                    "description": "Source unit (e.g., 'km', 'lb', 'c')",
                },
                "to_unit": {
                    "type": "string",
                    "description": "Target unit (e.g., 'mi', 'kg', 'f')",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        category: Optional[str] = None,
        value: Optional[float] = None,
        from_unit: Optional[str] = None,
        to_unit: Optional[str] = None,
    ) -> str:
        if action == "list":
            if category:
                return self._list_units(category)
            return self._list_all_categories()

        elif action == "convert":
            if value is None or not from_unit or not to_unit:
                return "Error: 'value', 'from_unit', and 'to_unit' required for convert action"

            from_unit = from_unit.lower()
            to_unit = to_unit.lower()

            detected_category = category or self._detect_category(from_unit, to_unit)
            if not detected_category:
                return f"Error: Could not determine unit category for {from_unit} -> {to_unit}"

            return self._convert(value, from_unit, to_unit, detected_category)

        else:
            return f"Unknown action: {action}"

    def _detect_category(self, from_unit: str, to_unit: str) -> Optional[str]:
        categories = [
            ("length", self.LENGTH_UNITS),
            ("weight", self.WEIGHT_UNITS),
            ("volume", self.VOLUME_UNITS),
            ("area", self.AREA_UNITS),
            ("speed", self.SPEED_UNITS),
            ("data", self.DATA_UNITS),
            ("time", self.TIME_UNITS),
            ("pressure", self.PRESSURE_UNITS),
        ]

        for name, units in categories:
            if from_unit in units and to_unit in units:
                return name

        if (
            from_unit in self.TEMPERATURE_OFFSETS
            and to_unit in self.TEMPERATURE_OFFSETS
        ):
            return "temperature"

        return None

    def _convert(
        self, value: float, from_unit: str, to_unit: str, category: str
    ) -> str:
        if category == "temperature":
            result = self._convert_temperature(value, from_unit, to_unit)
        else:
            units_map = {
                "length": self.LENGTH_UNITS,
                "weight": self.WEIGHT_UNITS,
                "volume": self.VOLUME_UNITS,
                "area": self.AREA_UNITS,
                "speed": self.SPEED_UNITS,
                "data": self.DATA_UNITS,
                "time": self.TIME_UNITS,
                "pressure": self.PRESSURE_UNITS,
            }

            units = units_map.get(category)
            if not units:
                return f"Error: Unknown category '{category}'"

            if from_unit not in units:
                return f"Error: Unknown unit '{from_unit}' for {category}"
            if to_unit not in units:
                return f"Error: Unknown unit '{to_unit}' for {category}"

            base_value = value * units[from_unit]
            result = base_value / units[to_unit]

        if abs(result) < 0.01 or abs(result) >= 10000:
            formatted = f"{result:.6g}"
        else:
            formatted = f"{result:.4f}"

        return f"{value} {from_unit} = {formatted} {to_unit}"

    def _convert_temperature(self, value: float, from_unit: str, to_unit: str) -> float:
        celsius = (
            value + self.TEMPERATURE_OFFSETS[from_unit]
        ) * self.TEMPERATURE_SCALES[from_unit]

        if to_unit == "c":
            return celsius
        elif to_unit == "f":
            return celsius * 9 / 5 + 32
        else:
            return celsius + 273.15

    def _list_units(self, category: str) -> str:
        units_map = {
            "length": ("Length", self.LENGTH_UNITS),
            "weight": ("Weight/Mass", self.WEIGHT_UNITS),
            "volume": ("Volume", self.VOLUME_UNITS),
            "temperature": (
                "Temperature",
                dict((k, 1) for k in self.TEMPERATURE_OFFSETS),
            ),
            "area": ("Area", self.AREA_UNITS),
            "speed": ("Speed", self.SPEED_UNITS),
            "data": ("Data Storage", self.DATA_UNITS),
            "time": ("Time", self.TIME_UNITS),
            "pressure": ("Pressure", self.PRESSURE_UNITS),
        }

        if category not in units_map:
            return f"Unknown category: {category}"

        name, units = units_map[category]
        result = [f"**{name} Units**\n"]

        for unit in sorted(units.keys()):
            result.append(f"- `{unit}`")

        return "\n".join(result)

    def _list_all_categories(self) -> str:
        return (
            "**Unit Categories**\n\n"
            "- `length`: mm, cm, m, km, in, ft, yd, mi, nmi\n"
            "- `weight`: mg, g, kg, t, oz, lb, st\n"
            "- `volume`: ml, l, m3, tsp, tbsp, floz, cup, pt, qt, gal\n"
            "- `temperature`: c, f, k (Celsius, Fahrenheit, Kelvin)\n"
            "- `area`: mm2, cm2, m2, km2, ha, ac, sqft, sqmi\n"
            "- `speed`: mps, kph, mph, knot, fps\n"
            "- `data`: b, kb, mb, gb, tb, pb, kib, mib, gib, tib, pib\n"
            "- `time`: ns, us, ms, s, min, h, d, wk, mo, yr\n"
            "- `pressure`: pa, kpa, bar, psi, atm, mmhg"
        )
