"""Open an MCP ToolClient from a command string or HTTP URL.

This pulse app is the MCP client. The Google Workspace server is:
https://github.com/Charu1806/MCPserverGoogleWorkspace
"""

from __future__ import annotations

from src.publish.client import ToolClient
from src.publish.errors import PublishError
from src.publish.http_client import open_http_client
from src.publish.stdio_client import open_stdio_client


def open_tool_client(command: str, *, api_key: str = "") -> ToolClient:
    """Use HTTP when command is an http(s) URL; otherwise stdio."""
    value = command.strip()
    if not value:
        raise PublishError("Docs MCP server is not connected")
    if value.startswith("http://") or value.startswith("https://"):
        return open_http_client(value, api_key=api_key)
    return open_stdio_client(value)
