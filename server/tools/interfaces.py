"""Shared types for internal agent tools."""

from typing import Any, Protocol


class AgentTool(Protocol):
    """Protocol implemented by callable tools used by agent workflows."""

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Run the tool with implementation-specific arguments."""

