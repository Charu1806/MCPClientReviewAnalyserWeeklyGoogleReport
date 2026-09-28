"""Gmail draft publish via MCP. Never send."""

from __future__ import annotations

from src.publish.client import ToolClient
from src.publish.errors import PublishError, find_gmail_draft, map_arguments


def publish_draft(client: ToolClient, recipient: str, subject: str, body: str) -> None:
    """Create one Gmail draft. No retry. Leaves any Doc alone on failure."""
    if "{doc_link}" in body:
        raise PublishError("email body still contains {doc_link}")
    if "https://" not in body:
        raise PublishError("email body requires an https:// document link")

    tools = client.list_tools()
    tool = find_gmail_draft(tools)
    args = map_arguments(
        tool,
        required={
            "recipient": recipient,
            "subject": subject,
            "email_body": body,
        },
    )
    try:
        client.call_tool(tool.name, args)
    except PublishError:
        raise
    except Exception as exc:
        raise PublishError(str(exc)) from exc
