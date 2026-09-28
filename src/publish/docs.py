"""Google Docs publish via MCP tools only."""

from __future__ import annotations

from typing import Any, Mapping

from src.publish.client import ToolClient
from src.publish.errors import (
    DocRef,
    PublishError,
    find_docs_create,
    find_docs_update,
    map_arguments,
    parse_doc_ref,
)

_TRANSPORT_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "connect",
    "temporarily unavailable",
    "reset by peer",
    "broken pipe",
)


def publish_doc(
    client: ToolClient,
    state: Mapping[str, Any],
    week_key: str,
    title: str,
    full_text: str,
) -> DocRef:
    """Create or update this week's Doc. Does not call Gmail."""
    tools = client.list_tools()
    existing = state.get(week_key) if isinstance(state.get(week_key), Mapping) else None
    doc_id = ""
    if isinstance(existing, Mapping):
        raw_id = existing.get("doc_id")
        if isinstance(raw_id, str):
            doc_id = raw_id.strip()

    update_tool = find_docs_update(tools) if doc_id else None
    if doc_id and update_tool is not None:
        args = map_arguments(
            update_tool,
            required={"doc_id": doc_id, "doc_body": full_text},
        )
        return _call_for_ref(client, update_tool.name, args)

    create_tool = find_docs_create(tools)
    args = map_arguments(
        create_tool,
        required={"title": title, "doc_body": full_text},
    )
    return _call_for_ref(client, create_tool.name, args)


def _call_for_ref(client: ToolClient, name: str, args: dict[str, Any]) -> DocRef:
    try:
        result = client.call_tool(name, args)
    except Exception as exc:
        if isinstance(exc, PublishError) and not _is_transport(exc):
            raise
        if not _is_transport(exc):
            raise PublishError(str(exc)) from exc
        try:
            result = client.call_tool(name, args)
        except Exception as retry_exc:
            raise PublishError(str(retry_exc)) from retry_exc
    return parse_doc_ref(result)


def _is_transport(exc: BaseException) -> bool:
    text = str(exc).casefold()
    return any(marker in text for marker in _TRANSPORT_MARKERS) or isinstance(
        exc, (TimeoutError, ConnectionError, OSError)
    )
