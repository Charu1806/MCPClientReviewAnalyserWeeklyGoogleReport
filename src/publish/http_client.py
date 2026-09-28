"""HTTP Streamable MCP client for Charu1806/MCPserverGoogleWorkspace (Vercel).

That server is stateless and accepts a single JSON-RPC message per POST.
tools/list and tools/call work without a prior initialize on the same socket.
Auth: Authorization: Bearer {MCP_API_KEY} (also X-API-Key).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Mapping

from src.publish.client import ToolInfo
from src.publish.errors import PublishError

_PROTOCOL = "2024-11-05"
_TIMEOUT = 60.0


class HttpMcpClient:
    """Minimal streamable-HTTP MCP client. Sync. No Google REST."""

    def __init__(self, url: str, *, api_key: str = "") -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key.strip()
        self._request_id = 0
        self._closed = False

    def list_tools(self) -> list[ToolInfo]:
        self._ensure_open()
        result = self._rpc("tools/list", {})
        tools = result.get("tools") if isinstance(result, Mapping) else None
        if not isinstance(tools, list):
            raise PublishError("MCP tools/list returned no tools")
        out: list[ToolInfo] = []
        for item in tools:
            if not isinstance(item, Mapping):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            schema = item.get("inputSchema") or item.get("input_schema") or {}
            if not isinstance(schema, Mapping):
                schema = {}
            out.append(ToolInfo(name=name, input_schema=dict(schema)))
        return out

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self._ensure_open()
        result = self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments},
        )
        if isinstance(result, Mapping):
            if result.get("isError"):
                raise PublishError(_tool_error_text(result))
            structured = result.get("structuredContent")
            if structured is not None:
                return structured
            return result
        return result

    def close(self) -> None:
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise PublishError("MCP client is closed")

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _rpc(self, method: str, params: dict[str, Any]) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        message = self._post(payload)
        if "error" in message:
            err = message["error"]
            if isinstance(err, Mapping):
                raise PublishError(str(err.get("message") or err))
            raise PublishError(str(err))
        return message.get("result")

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": _PROTOCOL,
            "User-Agent": "groww-pulse/0.1",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
            headers["X-API-Key"] = self._api_key

        request = urllib.request.Request(self._url, data=raw, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                body = response.read()
                content_type = (response.headers.get("Content-Type") or "").lower()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PublishError(f"MCP HTTP {exc.code}: {detail[:300]}") from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise PublishError(f"MCP connection error: {exc}") from exc

        if not body.strip():
            raise PublishError("MCP returned an empty response")

        if "text/event-stream" in content_type:
            messages = _parse_sse_messages(body.decode("utf-8", errors="replace"))
            if not messages:
                raise PublishError("MCP SSE returned no data")
            return messages[-1]

        try:
            parsed = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise PublishError("MCP returned non-JSON") from exc
        if isinstance(parsed, list):
            dicts = [item for item in parsed if isinstance(item, dict)]
            if not dicts:
                raise PublishError("MCP returned an empty batch")
            return dicts[-1]
        if isinstance(parsed, dict):
            return parsed
        raise PublishError("MCP returned a non-object JSON-RPC message")


def open_http_client(url: str, *, api_key: str = "") -> HttpMcpClient:
    return HttpMcpClient(url, api_key=api_key)


def _parse_sse_messages(text: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal data_lines
        if not data_lines:
            return
        blob = "\n".join(data_lines)
        data_lines = []
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            return
        if isinstance(parsed, dict):
            messages.append(parsed)
        elif isinstance(parsed, list):
            messages.extend(item for item in parsed if isinstance(item, dict))

    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line.strip() == "":
            flush()
    flush()
    return messages


def _tool_error_text(result: Mapping[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return " ".join(parts)
    return "MCP tool returned isError"
