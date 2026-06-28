"""Color conversion and manipulation tool."""

from __future__ import annotations

import re
from typing import Optional, Tuple

from saladbox.tools.base import BaseTool


class ColorTool(BaseTool):
    """Convert and manipulate colors between formats."""

    @property
    def name(self) -> str:
        return "color"

    @property
    def description(self) -> str:
        return (
            "Convert colors between HEX, RGB, HSL, HSV, and named colors. "
            "Generate color palettes, find complementary colors, and create gradients."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "convert",
                        "complement",
                        "triadic",
                        "analogous",
                        "palette",
                        "random",
                        "named",
                    ],
                    "description": "Color operation to perform",
                },
                "color": {
                    "type": "string",
                    "description": "Color value (hex like #FF5733, rgb like '255,87,51', or color name)",
                },
                "format": {
                    "type": "string",
                    "enum": ["hex", "rgb", "hsl", "hsv", "all"],
                    "description": "Output format for color values (default: all)",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of colors for palette generation (default: 5)",
                },
            },
            "required": ["action"],
        }

    COLOR_NAMES = {
        "red": (255, 0, 0),
        "green": (0, 128, 0),
        "blue": (0, 0, 255),
        "yellow": (255, 255, 0),
        "cyan": (0, 255, 255),
        "magenta": (255, 0, 255),
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "orange": (255, 165, 0),
        "pink": (255, 192, 203),
        "purple": (128, 0, 128),
        "brown": (165, 42, 42),
        "gray": (128, 128, 128),
        "grey": (128, 128, 128),
        "navy": (0, 0, 128),
        "teal": (0, 128, 128),
        "olive": (128, 128, 0),
        "maroon": (128, 0, 0),
        "aqua": (0, 255, 255),
        "lime": (0, 255, 0),
        "fuchsia": (255, 0, 255),
        "silver": (192, 192, 192),
        "gold": (255, 215, 0),
        "coral": (255, 127, 80),
        "salmon": (250, 128, 114),
        "violet": (238, 130, 238),
        "indigo": (75, 0, 130),
        "crimson": (220, 20, 60),
        "tomato": (255, 99, 71),
        "khaki": (240, 230, 140),
        "lavender": (230, 230, 250),
        "beige": (245, 245, 220),
        "ivory": (255, 255, 240),
    }

    async def execute(
        self,
        action: str,
        color: Optional[str] = None,
        format: str = "all",
        count: int = 5,
    ) -> str:
        try:
            if action == "convert":
                if not color:
                    return "Error: 'color' required for convert action"
                rgb = self._parse_color(color)
                if not rgb:
                    return f"Error: Could not parse color '{color}'"
                return self._format_color(rgb, format)

            elif action == "complement":
                if not color:
                    return "Error: 'color' required for complement action"
                rgb = self._parse_color(color)
                if not rgb:
                    return f"Error: Could not parse color '{color}'"
                comp = self._complementary(rgb)
                return f"Original: {self._format_color(rgb, 'all')}\n\nComplementary: {self._format_color(comp, 'all')}"

            elif action == "triadic":
                if not color:
                    return "Error: 'color' required for triadic action"
                rgb = self._parse_color(color)
                if not rgb:
                    return f"Error: Could not parse color '{color}'"
                triadic = self._triadic(rgb)
                result = ["**Triadic Colors**\n"]
                for i, c in enumerate(triadic):
                    result.append(f"{i + 1}. {self._format_color(c, 'hex')}")
                return "\n".join(result)

            elif action == "analogous":
                if not color:
                    return "Error: 'color' required for analogous action"
                rgb = self._parse_color(color)
                if not rgb:
                    return f"Error: Could not parse color '{color}'"
                analogous = self._analogous(rgb, count)
                result = ["**Analogous Colors**\n"]
                for i, c in enumerate(analogous):
                    result.append(f"{i + 1}. {self._format_color(c, 'hex')}")
                return "\n".join(result)

            elif action == "palette":
                rgb = self._parse_color(color) if color else None
                palette = self._generate_palette(count, rgb)
                result = ["**Color Palette**\n"]
                for i, c in enumerate(palette):
                    result.append(f"{i + 1}. {self._format_color(c, 'hex')}")
                return "\n".join(result)

            elif action == "random":
                palette = self._random_palette(count)
                result = ["**Random Colors**\n"]
                for i, c in enumerate(palette):
                    result.append(f"{i + 1}. {self._format_color(c, 'hex')}")
                return "\n".join(result)

            elif action == "named":
                return self._list_named_colors()

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            return f"Error: {str(e)}"

    def _parse_color(self, color: str) -> Optional[Tuple[int, int, int]]:
        color = color.strip().lower()

        if color.startswith("#"):
            hex_color = color[1:]
            if len(hex_color) == 3:
                hex_color = "".join([c * 2 for c in hex_color])
            if len(hex_color) == 6:
                return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

        if color in self.COLOR_NAMES:
            return self.COLOR_NAMES[color]

        rgb_match = re.match(r"rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", color)
        if rgb_match:
            return tuple(int(g) for g in rgb_match.groups())

        parts = color.replace(" ", "").split(",")
        if len(parts) == 3:
            try:
                return tuple(int(p) for p in parts)
            except ValueError:
                pass

        return None

    def _format_color(self, rgb: Tuple[int, int, int], fmt: str) -> str:
        r, g, b = rgb

        if fmt == "hex":
            return f"#{r:02x}{g:02x}{b:02x}".upper()

        hsl = self._rgb_to_hsl(rgb)
        hsv = self._rgb_to_hsv(rgb)

        if fmt == "rgb":
            return f"RGB({r}, {g}, {b})"
        elif fmt == "hsl":
            return f"HSL({hsl[0]:.0f}, {hsl[1]:.0f}%, {hsl[2]:.0f}%)"
        elif fmt == "hsv":
            return f"HSV({hsv[0]:.0f}, {hsv[1]:.0f}%, {hsv[2]:.0f}%)"
        else:
            return (
                f"HEX: #{r:02x}{g:02x}{b:02x}".upper()
                + "\n"
                + f"RGB: ({r}, {g}, {b})\n"
                + f"HSL: ({hsl[0]:.0f}, {hsl[1]:.0f}%, {hsl[2]:.0f}%)\n"
                + f"HSV: ({hsv[0]:.0f}, {hsv[1]:.0f}%, {hsv[2]:.0f}%)"
            )

    def _rgb_to_hsl(self, rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
        r, g, b = [x / 255.0 for x in rgb]
        max_c, min_c = max(r, g, b), min(r, g, b)
        l = (max_c + min_c) / 2

        if max_c == min_c:
            return (0, 0, l * 100)

        d = max_c - min_c
        s = d / (2 - max_c - min_c) if l > 0.5 else d / (max_c + min_c)

        if max_c == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif max_c == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4

        return (h * 60, s * 100, l * 100)

    def _rgb_to_hsv(self, rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
        r, g, b = [x / 255.0 for x in rgb]
        max_c, min_c = max(r, g, b), min(r, g, b)
        v = max_c

        if max_c == min_c:
            return (0, 0, v * 100)

        d = max_c - min_c
        s = d / max_c

        if max_c == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif max_c == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4

        return (h * 60, s * 100, v * 100)

    def _hsl_to_rgb(self, h: float, s: float, l: float) -> Tuple[int, int, int]:
        s, l = s / 100, l / 100
        c = (1 - abs(2 * l - 1)) * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = l - c / 2

        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))

    def _complementary(self, rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
        h, s, l = self._rgb_to_hsl(rgb)
        return self._hsl_to_rgb((h + 180) % 360, s, l)

    def _triadic(self, rgb: Tuple[int, int, int]) -> list:
        h, s, l = self._rgb_to_hsl(rgb)
        return [
            rgb,
            self._hsl_to_rgb((h + 120) % 360, s, l),
            self._hsl_to_rgb((h + 240) % 360, s, l),
        ]

    def _analogous(self, rgb: Tuple[int, int, int], count: int) -> list:
        h, s, l = self._rgb_to_hsl(rgb)
        colors = [rgb]
        step = 30
        for i in range(1, count):
            new_h = (h + i * step) % 360
            colors.append(self._hsl_to_rgb(new_h, s, l))
        return colors

    def _generate_palette(
        self, count: int, base_rgb: Optional[Tuple[int, int, int]]
    ) -> list:
        import random

        colors = []

        if base_rgb:
            colors.append(base_rgb)
            h, s, l = self._rgb_to_hsl(base_rgb)
            for i in range(1, count):
                new_h = (h + i * (360 / count)) % 360
                new_s = max(30, min(90, s + random.randint(-20, 20)))
                new_l = max(30, min(70, l + random.randint(-15, 15)))
                colors.append(self._hsl_to_rgb(new_h, new_s, new_l))
        else:
            for _ in range(count):
                h = random.randint(0, 359)
                s = random.randint(40, 80)
                l = random.randint(30, 70)
                colors.append(self._hsl_to_rgb(h, s, l))

        return colors

    def _random_palette(self, count: int) -> list:
        import random

        colors = []
        for _ in range(count):
            h = random.randint(0, 359)
            s = random.randint(50, 90)
            l = random.randint(35, 65)
            colors.append(self._hsl_to_rgb(h, s, l))
        return colors

    def _list_named_colors(self) -> str:
        result = ["**Named Colors**\n"]
        for name, rgb in sorted(self.COLOR_NAMES.items()):
            hex_val = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}".upper()
            result.append(f"- {name.title()}: {hex_val}")
        return "\n".join(result)
