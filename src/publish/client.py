"""MCP tool client protocol. No Google REST."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolInfo:
    name: str
    input_schema: dict[str, Any]


class ToolClient(Protocol):
    def list_tools(self) -> list[ToolInfo]:
        """Return tools exposed by the connected MCP server."""

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool and return structured content, parsed JSON, or raw text."""

    def close(self) -> None:
        """Release the connection. Safe to call more than once."""
