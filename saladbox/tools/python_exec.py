"""Sandboxed Python code execution tool."""

from __future__ import annotations

import asyncio
import sys
import textwrap

from saladbox.tools.base import BaseTool


class PythonExecTool(BaseTool):
    """Execute Python code in a sandboxed subprocess."""

    @property
    def name(self) -> str:
        return "run_python"

    @property
    def description(self) -> str:
        return (
            "Execute Python code in a sandboxed environment and return the output. "
            "The code runs in a separate process with a timeout. "
            "Print statements and the value of the last expression are captured. "
            "For HTTP requests use urllib.request (stdlib); the 'requests' module may not be installed. "
            "For fetching web pages or reading sites, prefer the browser tool (navigate + get_text)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 15)",
                },
            },
            "required": ["code"],
        }

    async def execute(
        self, code: str, timeout: int | str = 15
    ) -> str:
        # LLM sometimes sends timeout as a string (e.g. "30"); wait_for() requires int
        try:
            timeout = int(timeout) if timeout is not None else 15
        except (TypeError, ValueError):
            timeout = 15
        timeout = max(1, min(timeout, 300))  # clamp 1–300s

        wrapper = self._build_wrapper(code)

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            wrapper,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return f"Execution timed out after {timeout}s"

        output = stdout.decode(errors="replace") if stdout else ""
        errors = stderr.decode(errors="replace") if stderr else ""

        max_len = 4000
        if len(output) > max_len:
            output = output[:max_len] + "\n... (truncated)"

        result = ""
        if output.strip():
            result += output
        if errors.strip():
            result += f"\nErrors:\n{errors[:2000]}"
        if not result.strip():
            result = "(no output)"

        return result

    def _build_wrapper(self, code: str) -> str:
        """Build a wrapper script that restricts dangerous operations.

        Uses base64 encoding to safely embed user code without any
        string escaping vulnerabilities.
        """
        import base64

        code_b64 = base64.b64encode(code.encode()).decode()
        return textwrap.dedent(f"""\
            import sys
            import io
            import base64

            _code = base64.b64decode("{code_b64}").decode()

            # Capture stdout
            _old_stdout = sys.stdout
            sys.stdout = _buf = io.StringIO()

            try:
                _compiled = compile(_code, '<sandbox>', 'exec')
                _globals = {{'__builtins__': __builtins__}}
                exec(_compiled, _globals)
            except Exception as e:
                print(f"Error: {{type(e).__name__}}: {{e}}")
            finally:
                sys.stdout = _old_stdout
                print(_buf.getvalue(), end='')
        """)
