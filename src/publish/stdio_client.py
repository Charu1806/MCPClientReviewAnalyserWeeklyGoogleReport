"""Stdio MCP client using the mcp package (Python 3.10+)."""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from src.publish.client import ToolInfo
from src.publish.errors import PublishError


class StdioMcpClient:
    """Spawn a local MCP server over stdio and call tools."""

    def __init__(self, command: str) -> None:
        parts = shlex.split(command)
        if not parts:
            raise PublishError("Docs MCP server is not connected")
        self._command = parts[0]
        self._args = parts[1:]

    def list_tools(self) -> list[ToolInfo]:
        return asyncio.run(self._list_tools())

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return asyncio.run(self._call_tool(name, arguments))

    def close(self) -> None:
        return None

    async def _list_tools(self) -> list[ToolInfo]:
        session, exit_stack = await self._connect()
        try:
            listed = await session.list_tools()
            out: list[ToolInfo] = []
            for tool in listed.tools:
                schema = getattr(tool, "inputSchema", None) or {}
                if not isinstance(schema, dict):
                    schema = {}
                out.append(ToolInfo(name=tool.name, input_schema=schema))
            return out
        finally:
            await exit_stack.aclose()

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        session, exit_stack = await self._connect()
        try:
            result = await session.call_tool(name, arguments)
            structured = getattr(result, "structuredContent", None)
            if structured is not None:
                return structured
            # Fall back to content list / model dump.
            if hasattr(result, "model_dump"):
                return result.model_dump()
            content = getattr(result, "content", None)
            if content is not None:
                return content
            return result
        finally:
            await exit_stack.aclose()

    async def _connect(self):
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise PublishError(
                "mcp package is required for stdio MCP (Python 3.10+)"
            ) from exc

        from contextlib import AsyncExitStack

        params = StdioServerParameters(command=self._command, args=self._args)
        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            return session, stack
        except Exception:
            await stack.aclose()
            raise


def open_stdio_client(command: str) -> StdioMcpClient:
    return StdioMcpClient(command)
