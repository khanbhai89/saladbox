"""JSON and YAML manipulation tool."""

from __future__ import annotations

import json
import re

from saladbox.tools.base import BaseTool

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class JsonYamlTool(BaseTool):
    """Parse, format, and manipulate JSON and YAML data."""

    @property
    def name(self) -> str:
        return "json_yaml"

    @property
    def description(self) -> str:
        return (
            "Parse, format, validate, and transform JSON and YAML data. "
            "Convert between formats, pretty-print, extract values by path, "
            "and validate structure."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "parse",
                        "format",
                        "validate",
                        "convert",
                        "extract",
                        "keys",
                    ],
                    "description": "Operation to perform on the data",
                },
                "data": {
                    "type": "string",
                    "description": "JSON or YAML data to process",
                },
                "path": {
                    "type": "string",
                    "description": "Dot-notation path to extract (e.g., 'users.0.name')",
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "yaml"],
                    "description": "Output format for convert action",
                },
                "indent": {
                    "type": "integer",
                    "description": "Indentation spaces for pretty-printing (default: 2)",
                },
            },
            "required": ["action", "data"],
        }

    async def execute(
        self,
        action: str,
        data: str,
        path: str | None = None,
        format: str = "json",
        indent: int = 2,
    ) -> str:
        if action == "parse":
            return self._parse(data)
        elif action == "format":
            return self._format(data, indent)
        elif action == "validate":
            return self._validate(data)
        elif action == "convert":
            return self._convert(data, format, indent)
        elif action == "extract":
            if not path:
                return "Error: 'path' required for extract action"
            return self._extract(data, path)
        elif action == "keys":
            return self._keys(data, path)
        else:
            return f"Unknown action: {action}"

    def _detect_format(self, data: str) -> str:
        data = data.strip()
        if data.startswith("{") or data.startswith("["):
            return "json"
        return "yaml"

    def _parse(self, data: str) -> str:
        data = data.strip()
        fmt = self._detect_format(data)

        try:
            if fmt == "json":
                parsed = json.loads(data)
            else:
                if not YAML_AVAILABLE:
                    return "Error: YAML support requires 'pyyaml' package"
                parsed = yaml.safe_load(data)

            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as e:
            return f"JSON parse error: {e!s}"
        except yaml.YAMLError as e:
            return f"YAML parse error: {e!s}"

    def _format(self, data: str, indent: int) -> str:
        data = data.strip()
        fmt = self._detect_format(data)

        try:
            if fmt == "json":
                parsed = json.loads(data)
                return json.dumps(parsed, indent=indent, ensure_ascii=False)
            else:
                if not YAML_AVAILABLE:
                    return "Error: YAML support requires 'pyyaml' package"
                parsed = yaml.safe_load(data)
                return yaml.dump(parsed, default_flow_style=False, indent=indent)
        except Exception as e:
            return f"Format error: {e!s}"

    def _validate(self, data: str) -> str:
        data = data.strip()
        fmt = self._detect_format(data)

        try:
            if fmt == "json":
                parsed = json.loads(data)
                return f"Valid JSON. Type: {type(parsed).__name__}, Size: {len(json.dumps(parsed))} chars"
            else:
                if not YAML_AVAILABLE:
                    return "Error: YAML support requires 'pyyaml' package"
                parsed = yaml.safe_load(data)
                return f"Valid YAML. Type: {type(parsed).__name__}"
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e!s}"
        except yaml.YAMLError as e:
            return f"Invalid YAML: {e!s}"

    def _convert(self, data: str, target_format: str, indent: int) -> str:
        data = data.strip()
        source_format = self._detect_format(data)

        try:
            if source_format == "json":
                parsed = json.loads(data)
            else:
                if not YAML_AVAILABLE:
                    return "Error: YAML support requires 'pyyaml' package"
                parsed = yaml.safe_load(data)

            if target_format == "json":
                return json.dumps(parsed, indent=indent, ensure_ascii=False)
            else:
                if not YAML_AVAILABLE:
                    return "Error: YAML support requires 'pyyaml' package"
                return yaml.dump(parsed, default_flow_style=False, indent=indent)
        except Exception as e:
            return f"Conversion error: {e!s}"

    def _extract(self, data: str, path: str) -> str:
        data = data.strip()
        fmt = self._detect_format(data)

        try:
            if fmt == "json":
                parsed = json.loads(data)
            else:
                if not YAML_AVAILABLE:
                    return "Error: YAML support requires 'pyyaml' package"
                parsed = yaml.safe_load(data)

            result = parsed
            path_parts = re.split(r"\.|\[|\]", path)
            path_parts = [p for p in path_parts if p]

            for part in path_parts:
                if part.isdigit():
                    part = int(part)
                    if isinstance(result, list) and 0 <= part < len(result):
                        result = result[part]
                    else:
                        return f"Error: Index {part} out of range"
                else:
                    if isinstance(result, dict) and part in result:
                        result = result[part]
                    else:
                        return f"Error: Key '{part}' not found"

            if isinstance(result, (dict, list)):
                return json.dumps(result, indent=2, ensure_ascii=False)
            return str(result)
        except Exception as e:
            return f"Extract error: {e!s}"

    def _keys(self, data: str, path: str | None) -> str:
        data = data.strip()
        fmt = self._detect_format(data)

        try:
            if fmt == "json":
                parsed = json.loads(data)
            else:
                if not YAML_AVAILABLE:
                    return "Error: YAML support requires 'pyyaml' package"
                parsed = yaml.safe_load(data)

            target = parsed
            if path:
                path_parts = re.split(r"\.|\[|\]", path)
                path_parts = [p for p in path_parts if p]
                for part in path_parts:
                    target = target[int(part)] if part.isdigit() else target[part]

            if isinstance(target, dict):
                keys = list(target.keys())
                return f"Keys ({len(keys)}): {', '.join(keys[:50])}"
            elif isinstance(target, list):
                return f"Array with {len(target)} items"
            else:
                return f"Scalar value: {type(target).__name__}"
        except Exception as e:
            return f"Keys error: {e!s}"
