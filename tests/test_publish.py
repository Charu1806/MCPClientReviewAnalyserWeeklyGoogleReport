from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.brief import Draft, build_brief
from src.cluster import ThemeStats
from src.config import Config
from src.filter import FilterResult, Review
from src.publish.client import ToolInfo
from src.publish.docs import publish_doc
from src.publish.errors import PublishError
from src.publish.gmail import publish_draft
from src.quotes import Quote
from src.run import run_pulse


class FakeClient:
    def __init__(self, tools, handlers=None, call_log=None):
        self._tools = tools
        self._handlers = handlers or {}
        self.calls = call_log if call_log is not None else []
        self.closed = False

    def list_tools(self):
        return list(self._tools)

    def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        handler = self._handlers.get(name)
        if handler is None:
            raise PublishError(f"no handler for {name}")
        if isinstance(handler, Exception):
            raise handler
        if callable(handler):
            return handler(arguments)
        return handler

    def close(self):
        self.closed = True


def _docs_tools():
    return [
        ToolInfo(
            name="create_document",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        ),
        ToolInfo(
            name="update_document",
            input_schema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        ),
    ]


def _gmail_draft_tool():
    return ToolInfo(
        name="create_draft",
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    )


def test_publish_doc_create_and_parse_url():
    client = FakeClient(
        _docs_tools(),
        {
            "create_document": {
                "documentId": "doc-1",
                "url": "https://docs.google.com/document/d/doc-1",
            }
        },
    )
    ref = publish_doc(client, {}, "2026-09-28", "Title", "Body text")
    assert ref.doc_id == "doc-1"
    assert ref.url.startswith("https://")
    assert client.calls[0][0] == "create_document"
    assert client.calls[0][1]["title"] == "Title"
    assert client.calls[0][1]["content"] == "Body text"


def test_publish_doc_updates_when_state_has_id():
    client = FakeClient(
        _docs_tools(),
        {
            "update_document": {
                "id": "doc-1",
                "documentUrl": "https://docs.google.com/document/d/doc-1",
            }
        },
    )
    ref = publish_doc(
        client,
        {"2026-09-28": {"doc_id": "doc-1", "url": "https://old"}},
        "2026-09-28",
        "Title",
        "New body",
    )
    assert ref.doc_id == "doc-1"
    assert client.calls[0][0] == "update_document"
    assert client.calls[0][1]["documentId"] == "doc-1"


def test_publish_doc_id_without_url():
    client = FakeClient(_docs_tools(), {"create_document": {"documentId": "doc-2"}})
    ref = publish_doc(client, {}, "2026-09-28", "Title", "Body")
    assert ref.doc_id == "doc-2"
    assert ref.url == ""


def test_gmail_rejects_placeholder_and_requires_https():
    client = FakeClient([_gmail_draft_tool()])
    with pytest.raises(PublishError, match="doc_link"):
        publish_draft(client, "ops@example.com", "Subj", "see {doc_link}")
    with pytest.raises(PublishError, match="https://"):
        publish_draft(client, "ops@example.com", "Subj", "no link here")


def test_send_only_gmail_tools_never_called():
    calls = []
    client = FakeClient(
        [
            ToolInfo(
                name="send_email",
                input_schema={
                    "type": "object",
                    "properties": {"to": {}, "subject": {}, "body": {}},
                },
            )
        ],
        call_log=calls,
    )
    with pytest.raises(PublishError, match="Gmail tool would send"):
        publish_draft(
            client,
            "ops@example.com",
            "Subj",
            "Doc: https://docs.google.com/document/d/x",
        )
    assert calls == []


def test_workspace_server_tool_names_and_array_recipient():
    tools = [
        ToolInfo(
            name="docs_create",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                },
            },
        ),
        ToolInfo(
            name="docs_append_text",
            input_schema={
                "type": "object",
                "properties": {
                    "documentId": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        ),
        ToolInfo(
            name="gmail_send_email",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "array"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        ),
        ToolInfo(
            name="gmail_create_draft",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "array", "items": {"type": "string"}},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
            },
        ),
    ]
    calls = []
    client = FakeClient(
        tools,
        {
            "docs_create": {
                "ok": True,
                "documentId": "doc-w",
                "url": "https://docs.google.com/document/d/doc-w/edit",
            },
            "docs_append_text": {
                "ok": True,
                "documentId": "doc-w",
                "url": "https://docs.google.com/document/d/doc-w/edit",
            },
            "gmail_create_draft": {"ok": True, "mode": "draft"},
        },
        call_log=calls,
    )

    ref = publish_doc(client, {}, "2026-09-28", "Title", "Body")
    assert ref.doc_id == "doc-w"
    assert calls[0][0] == "docs_create"

    calls.clear()
    ref2 = publish_doc(
        client,
        {"2026-09-28": {"doc_id": "doc-w", "url": ref.url}},
        "2026-09-28",
        "Title",
        "More body",
    )
    assert ref2.doc_id == "doc-w"
    assert calls[0][0] == "docs_append_text"
    assert calls[0][1]["documentId"] == "doc-w"
    assert calls[0][1]["text"] == "More body"

    calls.clear()
    publish_draft(
        client,
        "ops@example.com",
        "Subj",
        "Doc: https://docs.google.com/document/d/doc-w/edit",
    )
    assert calls[0][0] == "gmail_create_draft"
    assert calls[0][1]["to"] == ["ops@example.com"]


def test_no_docs_create_tool():
    client = FakeClient(
        [
            ToolInfo(
                name="list_files",
                input_schema={"type": "object", "properties": {}},
            )
        ]
    )
    with pytest.raises(PublishError, match="Docs MCP server is not connected"):
        publish_doc(client, {}, "2026-09-28", "Title", "Body")
