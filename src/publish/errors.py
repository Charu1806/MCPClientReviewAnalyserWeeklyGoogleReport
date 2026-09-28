"""Shared publish helpers: errors, schema mapping, tool selection, result parse.

Aligned with Charu1806/MCPserverGoogleWorkspace tools:
docs_create, docs_append_text, gmail_create_draft (never gmail_send_email).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.publish.client import ToolInfo

_TITLE_KEYS = ("title", "name")
_DOC_BODY_KEYS = ("text", "content", "body", "markdown")
_DOC_ID_KEYS = ("documentId", "document_id", "doc_id", "id")
_RECIPIENT_KEYS = ("to", "recipient")
_SUBJECT_KEYS = ("subject",)
_EMAIL_BODY_KEYS = ("body", "message", "text")

_VALUE_KEYS = {
    "title": _TITLE_KEYS,
    "doc_body": _DOC_BODY_KEYS,
    "doc_id": _DOC_ID_KEYS,
    "recipient": _RECIPIENT_KEYS,
    "subject": _SUBJECT_KEYS,
    "email_body": _EMAIL_BODY_KEYS,
}


class PublishError(Exception):
    """Docs or Gmail publish failed. The message is safe to print."""


@dataclass(frozen=True)
class DocRef:
    doc_id: str
    url: str


def map_arguments(
    tool: ToolInfo,
    *,
    required: Mapping[str, Any],
) -> dict[str, Any]:
    """Map logical values onto the first matching schema property name."""
    props = _schema_properties(tool.input_schema)
    if not props and required:
        raise PublishError(f"{tool.name}: schema has no properties for {', '.join(required)}")

    mapped: dict[str, Any] = {}
    for logical, value in required.items():
        keys = _VALUE_KEYS[logical]
        found = None
        for key in keys:
            if key in props:
                found = key
                break
        if found is None:
            raise PublishError(f"{tool.name}: missing argument for {logical}")
        mapped[found] = _coerce_value(props.get(found), value)
    if not mapped:
        raise PublishError(f"{tool.name}: refusing empty argument dict")
    return mapped


def find_docs_create(tools: Sequence[ToolInfo]) -> ToolInfo:
    by_name = {tool.name: tool for tool in tools}
    if "docs_create" in by_name:
        return by_name["docs_create"]
    for tool in tools:
        name = tool.name.lower()
        if (
            "create" in name
            and ("document" in name or "doc" in name)
            and "draft" not in name
            and "append" not in name
            and "email" not in name
        ):
            return tool
    raise PublishError("Docs MCP server is not connected")


def find_docs_update(tools: Sequence[ToolInfo]) -> ToolInfo | None:
    """Prefer a true update tool; else docs_append_text from the Workspace server."""
    by_name = {tool.name: tool for tool in tools}
    if "docs_append_text" in by_name:
        return by_name["docs_append_text"]
    for tool in tools:
        name = tool.name.lower()
        if "update" in name and ("document" in name or "doc" in name):
            return tool
    for tool in tools:
        name = tool.name.lower()
        if "append" in name and ("document" in name or "doc" in name):
            return tool
    return None


def find_gmail_draft(tools: Sequence[ToolInfo]) -> ToolInfo:
    by_name = {tool.name: tool for tool in tools}
    if "gmail_create_draft" in by_name:
        return by_name["gmail_create_draft"]
    for tool in tools:
        name = tool.name.lower()
        if "draft" in name and "send" not in name:
            return tool

    mail_tools = [
        tool
        for tool in tools
        if any(token in tool.name.lower() for token in ("mail", "email", "gmail"))
    ]
    if mail_tools and all("send" in tool.name.lower() for tool in mail_tools):
        raise PublishError("Gmail tool would send")
    raise PublishError("Gmail MCP server is not connected")


def parse_doc_ref(result: Any) -> DocRef:
    data = _as_mapping(result)
    doc_id = _first_str(data, ("documentId", "document_id", "doc_id", "id"))
    url = _first_str(data, ("url", "documentUrl", "document_url")) or ""
    if not doc_id:
        raise PublishError("Docs tool returned no document id")
    return DocRef(doc_id=doc_id, url=url)


def _coerce_value(prop_schema: Any, value: Any) -> Any:
    """gmail_create_draft expects to: string[]. Coerce a single address."""
    if not isinstance(prop_schema, Mapping):
        return value
    if prop_schema.get("type") == "array" and not isinstance(value, list):
        return [value]
    return value


def _schema_properties(schema: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(schema, Mapping):
        return {}
    props = schema.get("properties")
    if isinstance(props, Mapping):
        return dict(props)
    # Some servers expose a flat zod-like map of field → schema.
    reserved = {"type", "required", "additionalProperties", "$schema", "definitions", "$defs"}
    flat = {
        key: value
        for key, value in schema.items()
        if key not in reserved and isinstance(value, Mapping)
    }
    return flat


def _as_mapping(result: Any) -> dict[str, Any]:
    if isinstance(result, Mapping):
        structured = result.get("structuredContent")
        if isinstance(structured, Mapping):
            return dict(structured)
        if "documentId" in result or "id" in result or "url" in result:
            return dict(result)
        content = result.get("content")
        if isinstance(content, list):
            return _from_content_list(content)
        return dict(result)

    if isinstance(result, str):
        text = result.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PublishError("Docs tool returned non-JSON text") from exc
        return _as_mapping(parsed)

    if isinstance(result, list):
        return _from_content_list(result)

    raise PublishError("Docs tool returned an unexpected result")


def _from_content_list(content: list[Any]) -> dict[str, Any]:
    for item in content:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            text = item["text"].strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping):
                return dict(parsed)
        if "documentId" in item or "id" in item:
            return dict(item)
    raise PublishError("Docs tool returned no document id")


def _first_str(data: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and key in {"id", "documentId", "doc_id", "document_id"}:
            return str(value)
    return None
