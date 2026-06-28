#!/usr/bin/env python3
"""Comprehensive tests for tool calling functionality - no external dependencies."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from saladbox.core.tool_filter import TOOL_KEYWORDS, ToolFilter
from saladbox.core.tool_registry import ToolRegistry
from saladbox.tools import TOOL_MAP, get_enabled_tools


class SimpleAssertionTracker:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def test(self, name: str, condition: bool, message: str = ""):
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.errors.append((name, message))
            print(f"  ✗ {name}: {message}")

    def verify(self):
        total = self.passed + self.failed
        print(f"\n{'=' * 60}")
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("\nFailed tests:")
            for name, msg in self.errors:
                print(f"  - {name}: {msg}")
        assert self.failed == 0, f"{self.failed} assertions failed: {self.errors}"



def test_tool_filter_scoring():
    """Test tool scoring functionality."""
    print("\n[Test Tool Filter Scoring]")
    runner = SimpleAssertionTracker()
    tool_filter = ToolFilter(max_tools=12)

    test_cases = [
        ("Check my system resources", "system_monitor"),
        ("What is the CPU usage?", "system_monitor"),
        ("How much memory is used?", "system_monitor"),
        ("What is the weather in Tokyo?", "weather"),
        ("Weather forecast for London", "weather"),
        ("What is Bitcoin price?", "finance"),
        ("What is BTC at?", "finance"),
        ("Ethereum price", "finance"),
        ("Generate a secure password", "password"),
        ("Create a random password", "password"),
        ("What time is it?", "datetime_tool"),
        ("What date is today?", "datetime_tool"),
        ("Calculate 123 * 456", "calculator"),
        ("Compute 10 + 20", "calculator"),
        ("Translate hello to Spanish", "translate"),
        ("How do you say goodbye in French?", "translate"),
        ("Git status", "git"),
        ("Create a commit", "git"),
        ("Docker ps", "docker"),
        ("List docker containers", "docker"),
        ("Search for Python tutorials", "web_search"),
        ("Find information about AI", "web_search"),
    ]

    for query, expected_tool in test_cases:
        score = tool_filter.score_relevance(query, expected_tool)
        runner.test(
            f"'{query[:30]}...' -> {expected_tool}", score > 0, f"Score was {score}"
        )

    runner.verify()


def test_tool_filter_best_selection():
    """Test that the correct tool gets the highest score."""
    print("\n[Test Tool Filter Best Selection]")
    runner = SimpleAssertionTracker()
    tool_filter = ToolFilter(max_tools=12)

    config = {name: True for name in TOOL_MAP}
    tools = get_enabled_tools(config)
    registry = ToolRegistry()
    registry.register_tools(tools)
    all_schemas = registry.get_schemas()

    test_cases = [
        ("Check my system resources", "system_monitor"),
        ("What is the weather in Tokyo?", "weather"),
        ("What is Bitcoin price?", "finance"),
        ("Generate a secure password", "password"),
        ("What time is it?", "datetime_tool"),
    ]

    for query, expected_tool in test_cases:
        scores = {}
        for schema in all_schemas:
            name = schema.get("function", {}).get("name", "")
            scores[name] = tool_filter.score_relevance(query, name)

        best = max(scores.keys(), key=lambda k: scores[k])
        runner.test(
            f"Best for '{query[:30]}...'",
            best == expected_tool,
            f"Expected {expected_tool}, got {best} (scores: {scores.get(expected_tool, 0)} vs {scores.get(best, 0)})",
        )

    runner.verify()


def test_tool_filtering():
    """Test tool filtering reduces tool count."""
    print("\n[Test Tool Filtering]")
    runner = SimpleAssertionTracker()
    tool_filter = ToolFilter(max_tools=12)

    config = {name: True for name in TOOL_MAP}
    tools = get_enabled_tools(config)
    registry = ToolRegistry()
    registry.register_tools(tools)
    all_schemas = registry.get_schemas()

    runner.test(
        "Total tools registered", len(all_schemas) == 34, f"Got {len(all_schemas)}"
    )

    query = "Check my system resources"
    filtered = tool_filter.get_relevant_tools(query, all_schemas)

    runner.test(
        "Filtered tools <= max_tools",
        len(filtered) <= tool_filter.max_tools,
        f"Got {len(filtered)}",
    )
    runner.test(
        "Filtered tools >= min_tools", len(filtered) >= 6, f"Got {len(filtered)}"
    )

    tool_names = [t.get("function", {}).get("name") for t in filtered]
    runner.test(
        "system_monitor in filtered tools",
        "system_monitor" in tool_names,
        f"Tools: {tool_names[:5]}...",
    )

    runner.verify()


async def test_tool_execution():
    """Test actual tool execution."""
    print("\n[Test Tool Execution]")
    runner = SimpleAssertionTracker()

    config = {name: True for name in TOOL_MAP}
    tools = get_enabled_tools(config)
    registry = ToolRegistry()
    registry.register_tools(tools)

    # Test system_monitor
    result = await registry.execute("system_monitor", {"action": "cpu"})
    runner.test(
        "system_monitor cpu",
        not result.is_error and "CPU" in result.content,
        result.content[:50] if result.is_error else "OK",
    )

    result = await registry.execute("system_monitor", {"action": "memory"})
    runner.test(
        "system_monitor memory",
        not result.is_error and ("Memory" in result.content or "GB" in result.content),
        result.content[:50] if result.is_error else "OK",
    )

    # Test calculator
    result = await registry.execute("calculator", {"expression": "2 + 2"})
    runner.test(
        "calculator 2+2",
        not result.is_error and "4" in result.content,
        result.content[:50] if result.is_error else "OK",
    )

    result = await registry.execute("calculator", {"expression": "sqrt(16)"})
    runner.test(
        "calculator sqrt",
        not result.is_error and "4" in result.content,
        result.content[:50] if result.is_error else "OK",
    )

    # Test datetime_tool
    result = await registry.execute("datetime_tool", {"action": "now"})
    runner.test(
        "datetime_tool now",
        not result.is_error,
        result.content[:50] if result.is_error else "OK",
    )

    # Test password
    result = await registry.execute("password", {"action": "password", "length": 16})
    runner.test(
        "password generate",
        not result.is_error and "Generated" in result.content,
        result.content[:50] if result.is_error else "OK",
    )

    # Test encoding
    result = await registry.execute(
        "encoding", {"action": "base64_encode", "data": "Hello"}
    )
    runner.test(
        "encoding base64",
        not result.is_error and "SGVsbG8" in result.content,
        result.content[:50] if result.is_error else "OK",
    )

    # Test json_yaml
    result = await registry.execute(
        "json_yaml", {"action": "parse", "data": '{"key": "value"}'}
    )
    runner.test(
        "json_yaml parse",
        not result.is_error and "key" in result.content,
        result.content[:50] if result.is_error else "OK",
    )

    # Test text
    result = await registry.execute("text", {"action": "upper", "text": "hello world"})
    runner.test(
        "text uppercase",
        not result.is_error and "HELLO WORLD" in result.content,
        result.content[:50] if result.is_error else "OK",
    )

    # Test unit_converter
    result = await registry.execute(
        "unit_converter",
        {
            "action": "convert",
            "category": "length",
            "value": 1,
            "from_unit": "km",
            "to_unit": "m",
        },
    )
    runner.test(
        "unit_converter km->m",
        not result.is_error and "1000" in result.content,
        result.content[:50] if result.is_error else "OK",
    )

    # Test color
    result = await registry.execute("color", {"action": "convert", "color": "#FF0000"})
    runner.test(
        "color convert",
        not result.is_error and "255" in result.content,
        result.content[:50] if result.is_error else "OK",
    )

    runner.verify()


async def test_all_tools_execution():
    """Test that all tools can be instantiated and have correct schema."""
    print("\n[Test All Tools Schema]")
    runner = SimpleAssertionTracker()

    config = {name: True for name in TOOL_MAP}
    tools = get_enabled_tools(config)
    registry = ToolRegistry()
    registry.register_tools(tools)

    runner.test(
        "All tools registered",
        len(registry.tool_names) == len(TOOL_MAP),
        f"Expected {len(TOOL_MAP)}, got {len(registry.tool_names)}",
    )

    schemas = registry.get_schemas()
    for schema in schemas:
        name = schema.get("function", {}).get("name", "")
        has_type = schema.get("type") == "function"
        has_name = "name" in schema.get("function", {})
        has_desc = "description" in schema.get("function", {})
        has_params = "parameters" in schema.get("function", {})

        runner.test(
            f"Schema for {name}",
            has_type and has_name and has_desc and has_params,
            f"type={has_type}, name={has_name}, desc={has_desc}, params={has_params}",
        )

    runner.verify()


async def test_end_to_end_queries():
    """Test end-to-end query processing with filtered tools."""
    print("\n[Test End-to-End Query Processing]")
    runner = SimpleAssertionTracker()
    tool_filter = ToolFilter(max_tools=12)

    config = {name: True for name in TOOL_MAP}
    tools = get_enabled_tools(config)
    registry = ToolRegistry()
    registry.register_tools(tools)
    all_schemas = registry.get_schemas()

    queries = [
        ("Check my system resources", "system_monitor", {"action": "all"}),
        ("What time is it?", "datetime_tool", {"action": "now"}),
        ("Calculate 10 + 10", "calculator", {"expression": "10 + 10"}),
        ("Generate a password", "password", {"action": "password"}),
    ]

    for query, expected_tool, args in queries:
        filtered = tool_filter.get_relevant_tools(query, all_schemas)
        tool_names = [t.get("function", {}).get("name") for t in filtered]

        runner.test(
            f"Filter includes {expected_tool} for '{query[:20]}...'",
            expected_tool in tool_names,
            f"Filtered: {tool_names[:5]}...",
        )

        result = await registry.execute(expected_tool, args)
        runner.test(
            f"Execute {expected_tool}",
            not result.is_error,
            result.content[:50] if result.is_error else "OK",
        )

    runner.verify()


def test_all_tools_have_keywords():
    """Verify all tools have keyword definitions."""
    print("\n[Test All Tools Have Keywords]")
    runner = SimpleAssertionTracker()

    missing = []
    for tool_name in TOOL_MAP:
        if tool_name not in TOOL_KEYWORDS:
            missing.append(tool_name)

    runner.test("All tools have keywords", len(missing) == 0, f"Missing: {missing}")

    runner.verify()


async def main():
    print("=" * 60)
    print("TOOL CALLING COMPREHENSIVE TESTS")
    print("=" * 60)

    try:
        test_tool_filter_scoring()
        test_tool_filter_best_selection()
        test_tool_filtering()
        await test_tool_execution()
        await test_all_tools_execution()
        await test_end_to_end_queries()
        test_all_tools_have_keywords()
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        return 0
    except AssertionError as e:
        print("\n" + "=" * 60)
        print("✗ SOME TESTS FAILED")
        print(e)
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
