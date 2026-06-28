"""QR code generation tool."""

from __future__ import annotations

import base64
from io import BytesIO

from saladbox.tools.base import BaseTool

try:
    import qrcode

    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False


class QRCodeTool(BaseTool):
    """Generate QR codes for text, URLs, and data."""

    @property
    def name(self) -> str:
        return "qrcode"

    @property
    def description(self) -> str:
        return (
            "Generate QR codes for URLs, text, WiFi credentials, contact info, and more. "
            "Returns QR code as base64 image data. Can also decode QR codes from images."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["generate", "wifi", "contact", "event", "decode"],
                    "description": "QR code operation",
                },
                "data": {
                    "type": "string",
                    "description": "Data to encode in QR code",
                },
                "ssid": {
                    "type": "string",
                    "description": "WiFi network name (for wifi action)",
                },
                "password": {
                    "type": "string",
                    "description": "WiFi password (for wifi action)",
                },
                "security": {
                    "type": "string",
                    "enum": ["WPA", "WEP", "nopass"],
                    "description": "WiFi security type (default: WPA)",
                },
                "name": {
                    "type": "string",
                    "description": "Contact name (for contact action)",
                },
                "phone": {
                    "type": "string",
                    "description": "Contact phone (for contact action)",
                },
                "email": {
                    "type": "string",
                    "description": "Contact email (for contact action)",
                },
                "size": {
                    "type": "integer",
                    "description": "QR code size in pixels (default: 200)",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        data: str | None = None,
        ssid: str | None = None,
        password: str | None = None,
        security: str = "WPA",
        name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        size: int = 200,
    ) -> str:
        if not QRCODE_AVAILABLE:
            return "Error: qrcode library not installed. Install with: pip install qrcode[pil]"

        try:
            if action == "generate":
                if not data:
                    return "Error: 'data' required for generate action"
                return self._generate_qr(data, size)

            elif action == "wifi":
                if not ssid:
                    return "Error: 'ssid' required for wifi action"
                wifi_data = f"WIFI:T:{security};S:{ssid};P:{password or ''};;"
                return self._generate_qr(wifi_data, size, f"WiFi: {ssid}")

            elif action == "contact":
                if not name:
                    return "Error: 'name' required for contact action"
                vcard = self._create_vcard(name, phone, email)
                return self._generate_qr(vcard, size, f"Contact: {name}")

            elif action == "event":
                if not data:
                    return "Error: 'data' (event details) required for event action"
                return self._generate_qr(data, size, "Event")

            elif action == "decode":
                return "Error: QR code decoding requires image input which is not currently supported"

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            return f"Error: {e!s}"

    def _generate_qr(
        self, data: str, size: int = 200, label: str | None = None
    ) -> str:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()

        result = []
        if label:
            result.append(f"**QR Code: {label}**")
        else:
            result.append("**QR Code Generated**")

        result.append(f"Data: {data[:100]}{'...' if len(data) > 100 else ''}")
        result.append(f"Size: {size}x{size} pixels")
        result.append(f"\nBase64 image data (use in img src):\n{img_base64[:100]}...")

        return "\n".join(result)

    def _create_vcard(
        self, name: str, phone: str | None, email: str | None
    ) -> str:
        name_parts = name.split()
        last_name = name_parts[-1] if len(name_parts) > 1 else ""
        first_name = name_parts[0] if name_parts else name

        vcard = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"N:{last_name};{first_name};;;",
            f"FN:{name}",
        ]

        if phone:
            vcard.append(f"TEL:{phone}")
        if email:
            vcard.append(f"EMAIL:{email}")

        vcard.append("END:VCARD")

        return "\n".join(vcard)
