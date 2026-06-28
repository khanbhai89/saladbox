"""Comprehensive tests for tool calling functionality."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from saladbox.core.tool_filter import ToolFilter, TOOL_KEYWORDS, RECOGNITION_PATTERNS
from saladbox.core.tool_registry import ToolRegistry
from saladbox.core.types import Message, Role, ToolCall, ToolResult
from saladbox.tools import get_enabled_tools, TOOL_MAP


class TestToolFilter:
    """Tests for the ToolFilter class."""

    @pytest.fixture
    def tool_filter(self):
        return ToolFilter(max_tools=12)

    @pytest.fixture
    def all_tools(self):
        config = {name: True for name in TOOL_MAP}
        tools = get_enabled_tools(config)
        registry = ToolRegistry()
        registry.register_tools(tools)
        return registry.get_schemas()

    # Test scoring for each tool type
    @pytest.mark.parametrize(
        "query,expected_tool",
        [
            ("Check my system resources", "system_monitor"),
            ("What is the CPU usage?", "system_monitor"),
            ("How much memory is being used?", "system_monitor"),
            ("Show running processes", "system_monitor"),
            ("What is the weather in Tokyo?", "weather"),
            ("Weather forecast for New York", "weather"),
            ("Temperature in London", "weather"),
            ("What is Bitcoin price?", "finance"),
            ("What is BTC at?", "finance"),
            ("Ethereum price", "finance"),
            ("Crypto prices", "finance"),
            ("Generate a secure password", "password"),
            ("Create a random password", "password"),
            ("Make me a passphrase", "password"),
            ("What time is it?", "datetime_tool"),
            ("What date is today?", "datetime_tool"),
            ("What day is it?", "datetime_tool"),
            ("Time in London", "datetime_tool"),
            ("Calculate 123 * 456", "calculator"),
            ("What is 100 + 200?", "calculator"),
            ("Compute the square root of 16", "calculator"),
            ("Translate hello to Spanish", "translate"),
            ("How do you say goodbye in French?", "translate"),
            ("Translate this to Japanese", "translate"),
            ("Git status", "git"),
            ("Create a commit", "git"),
            ("Push to remote", "git"),
            ("Docker ps", "docker"),
            ("List docker containers", "docker"),
            ("Stop container", "docker"),
            ("Search for Python tutorials", "web_search"),
            ("Find information about AI", "web_search"),
            ("Look up latest news", "web_search"),
        ],
    )
    def test_tool_scoring(self, tool_filter, all_tools, query, expected_tool):
        """Test that the correct tool gets the highest score."""
        scores = {}
        for tool in all_tools:
            name = tool.get("function", {}).get("name", "")
            scores[name] = tool_filter.score_relevance(query, name)

        best_tool = max(scores.keys(), key=lambda k: scores[k])
        assert best_tool == expected_tool, (
            f"Expected {expected_tool}, got {best_tool}. Scores: {scores}"
        )

    def test_get_relevant_tools_reduces_count(self, tool_filter, all_tools):
        """Test that get_relevant_tools reduces the number of tools."""
        query = "Check my system resources"
        filtered = tool_filter.get_relevant_tools(query, all_tools)

        assert len(filtered) <= tool_filter.max_tools
        assert len(filtered) >= 6  # min_tools
        assert len(filtered) < len(all_tools)  # Should be reduced

    def test_get_relevant_tools_includes_correct_tool(self, tool_filter, all_tools):
        """Test that filtered tools include the relevant tool."""
        query = "What is Bitcoin price?"
        filtered = tool_filter.get_relevant_tools(query, all_tools)

        tool_names = [t.get("function", {}).get("name") for t in filtered]
        assert "finance" in tool_names

    def test_get_best_tool(self, tool_filter, all_tools):
        """Test getting single best tool."""
        result = tool_filter.get_best_tool("Check my system resources", all_tools)
        assert result is not None
        tool_name, args = result
        assert tool_name == "system_monitor"
        assert args.get("action") == "all"

    def test_get_best_tool_no_match(self, tool_filter, all_tools):
        """Test get_best_tool with no matching keywords."""
        result = tool_filter.get_best_tool("Hello how are you?", all_tools)
        # Should return None or low-score tool
        # This is a casual greeting with no tool intent

    def test_essential_tools_always_included(self, tool_filter, all_tools):
        """Test that essential tools are always included."""
        query = "random xyz query with no keywords"
        filtered = tool_filter.get_relevant_tools(query, all_tools)

        tool_names = [t.get("function", {}).get("name") for t in filtered]
        # Essential tools should be present
        assert (
            "run_shell" in tool_names
            or "filesystem" in tool_names
            or "web_search" in tool_names
        )

    def test_pattern_matching(self, tool_filter):
        """Test regex pattern matching for tool recognition."""
        test_cases = [
            ("Check my system", "system_monitor"),
            ("What is the weather like today?", "weather"),
            ("Bitcoin price right now", "finance"),
            ("Calculate 5 + 5", "calculator"),
            ("Generate a password for me", "password"),
        ]

        for query, expected_tool in test_cases:
            score = tool_filter.score_relevance(query, expected_tool)
            assert score > 0, f"Pattern should match for '{query}' -> {expected_tool}"

    def test_all_tools_have_keywords(self):
        """Test that all registered tools have keyword definitions."""
        missing = []
        for tool_name in TOOL_MAP.keys():
            if tool_name not in TOOL_KEYWORDS:
                missing.append(tool_name)

        assert not missing, f"Tools missing keyword definitions: {missing}"

    def test_weight_system(self, tool_filter):
        """Test that tool weights affect scoring."""
        # Both queries mention "price" but finance should score higher due to weight
        finance_score = tool_filter.score_relevance("Bitcoin price", "finance")
        calculator_score = tool_filter.score_relevance("Bitcoin price", "calculator")

        assert finance_score > calculator_score


class TestToolRegistry:
    """Tests for the ToolRegistry class."""

    @pytest.fixture
    def registry(self):
        config = {name: True for name in TOOL_MAP}
        tools = get_enabled_tools(config)
        registry = ToolRegistry()
        registry.register_tools(tools)
        return registry

    def test_all_tools_registered(self, registry):
        """Test that all tools are registered."""
        assert len(registry.tool_names) == len(TOOL_MAP)

    def test_get_schemas(self, registry):
        """Test that schemas are generated correctly."""
        schemas = registry.get_schemas()
        assert len(schemas) == len(TOOL_MAP)

        for schema in schemas:
            assert "type" in schema
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"]
            assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_execute_tool(self, registry):
        """Test executing a tool."""
        result = await registry.execute("system_monitor", {"action": "cpu"})
        assert result.name == "system_monitor"
        assert result.content
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, registry):
        """Test executing an unknown tool."""
        result = await registry.execute("unknown_tool", {})
        assert result.is_error
        assert "Unknown tool" in result.content


class TestToolExecution:
    """Tests for actual tool execution."""

    @pytest.mark.asyncio
    async def test_system_monitor_cpu(self):
        """Test system_monitor CPU action."""
        from saladbox.tools.system_monitor import SystemMonitorTool

        tool = SystemMonitorTool()
        result = await tool.execute(action="cpu")

        assert "CPU" in result or "Usage" in result

    @pytest.mark.asyncio
    async def test_system_monitor_memory(self):
        """Test system_monitor memory action."""
        from saladbox.tools.system_monitor import SystemMonitorTool

        tool = SystemMonitorTool()
        result = await tool.execute(action="memory")

        assert "Memory" in result or "GB" in result

    @pytest.mark.asyncio
    async def test_calculator(self):
        """Test calculator tool."""
        from saladbox.tools.calculator import CalculatorTool

        tool = CalculatorTool()
        result = await tool.execute(expression="2 + 2")

        assert "4" in result

    @pytest.mark.asyncio
    async def test_calculator_complex(self):
        """Test calculator with complex expression."""
        from saladbox.tools.calculator import CalculatorTool

        tool = CalculatorTool()
        result = await tool.execute(expression="sqrt(16) * 2")

        assert "8" in result

    @pytest.mark.asyncio
    async def test_datetime_now(self):
        """Test datetime_tool now action."""
        from saladbox.tools.datetime_tool import DateTimeTool

        tool = DateTimeTool()
        result = await tool.execute(action="now")

        # Should contain a date/time
        assert "UTC" in result or "Local" in result or "-" in result

    @pytest.mark.asyncio
    async def test_password_generate(self):
        """Test password generation."""
        from saladbox.tools.password import PasswordTool

        tool = PasswordTool()
        result = await tool.execute(action="password", length=16)

        assert "Generated" in result

    @pytest.mark.asyncio
    async def test_encoding_base64(self):
        """Test base64 encoding."""
        from saladbox.tools.encoding import EncodingTool

        tool = EncodingTool()
        result = await tool.execute(action="base64_encode", data="Hello")

        assert "SGVsbG8" in result  # Base64 of "Hello"

    @pytest.mark.asyncio
    async def test_json_yaml_parse(self):
        """Test JSON parsing."""
        from saladbox.tools.json_yaml import JsonYamlTool

        tool = JsonYamlTool()
        result = await tool.execute(action="parse", data='{"key": "value"}')

        assert "key" in result

    @pytest.mark.asyncio
    async def test_text_uppercase(self):
        """Test text uppercase."""
        from saladbox.tools.text import TextTool

        tool = TextTool()
        result = await tool.execute(action="upper", text="hello world")

        assert result == "HELLO WORLD"

    @pytest.mark.asyncio
    async def test_unit_converter(self):
        """Test unit conversion."""
        from saladbox.tools.unit_converter import UnitConverterTool

        tool = UnitConverterTool()
        result = await tool.execute(
            action="convert", category="length", value=1, from_unit="km", to_unit="m"
        )

        assert "1000" in result

    @pytest.mark.asyncio
    async def test_color_conversion(self):
        """Test color conversion."""
        from saladbox.tools.color import ColorTool

        tool = ColorTool()
        result = await tool.execute(action="convert", color="#FF0000")

        assert "255" in result  # Red component


class TestEndToEnd:
    """End-to-end tests for tool calling."""

    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM client."""
        mock = MagicMock()
        mock.chat = AsyncMock()
        return mock

    @pytest.fixture
    def registry(self):
        config = {name: True for name in TOOL_MAP}
        tools = get_enabled_tools(config)
        registry = ToolRegistry()
        registry.register_tools(tools)
        return registry

    @pytest.mark.asyncio
    async def test_full_flow_system_monitor(self, registry):
        """Test full flow for system monitor query."""
        # Simulate tool call
        result = await registry.execute("system_monitor", {"action": "all"})

        assert not result.is_error
        assert "CPU" in result.content or "Memory" in result.content

    @pytest.mark.asyncio
    async def test_full_flow_calculator(self, registry):
        """Test full flow for calculator query."""
        result = await registry.execute("calculator", {"expression": "10 * 10"})

        assert not result.is_error
        assert "100" in result.content


class TestToolFilterIntegration:
    """Integration tests for tool filtering with various queries."""

    @pytest.fixture
    def tool_filter(self):
        return ToolFilter(max_tools=12)

    @pytest.fixture
    def all_tools(self):
        config = {name: True for name in TOOL_MAP}
        tools = get_enabled_tools(config)
        registry = ToolRegistry()
        registry.register_tools(tools)
        return registry.get_schemas()

    @pytest.mark.parametrize(
        "query,required_tools",
        [
            ("Check my system resources", ["system_monitor"]),
            ("What is the weather in Tokyo?", ["weather"]),
            ("What is Bitcoin price?", ["finance"]),
            ("Generate a secure password", ["password"]),
            ("Calculate 100 * 50", ["calculator"]),
            ("What time is it?", ["datetime_tool"]),
            ("Translate hello to Spanish", ["translate"]),
            ("Git status", ["git"]),
            ("List docker containers", ["docker"]),
        ],
    )
    def test_filtered_tools_include_required(
        self, tool_filter, all_tools, query, required_tools
    ):
        """Test that filtered tools always include the required tool."""
        filtered = tool_filter.get_relevant_tools(query, all_tools)
        tool_names = [t.get("function", {}).get("name") for t in filtered]

        for required in required_tools:
            assert required in tool_names, (
                f"Required tool '{required}' not in filtered tools for query: {query}"
            )


def run_tests():
    """Run all tests."""
    import os
    import subprocess

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    print(result.stderr)
    return result.returncode


if __name__ == "__main__":
    exit(run_tests())
