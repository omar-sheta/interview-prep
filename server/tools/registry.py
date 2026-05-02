"""Internal tool registry seams for future agent and MCP adapters.

This module intentionally stays lightweight: current application tools are
plain Python functions, and future MCP tools can be exposed through the same
registry contract without making MCP a core runtime dependency.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


ToolCallable = Callable[..., Any] | Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class ToolDefinition:
    """Describes an internal tool available to agent orchestration code."""

    name: str
    description: str
    handler: ToolCallable
    domain: str = "general"


class ToolRegistry:
    """Simple in-process registry for agent tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> ToolDefinition:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list(self, *, domain: str | None = None) -> list[ToolDefinition]:
        tools = self._tools.values()
        if domain is not None:
            tools = [tool for tool in tools if tool.domain == domain]
        return list(tools)


tool_registry = ToolRegistry()


__all__ = ["ToolCallable", "ToolDefinition", "ToolRegistry", "tool_registry"]
