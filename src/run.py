"""CLI: load export → brief → Groq → Docs MCP → Gmail draft → notes."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from typing import Callable

from src.brief import Brief, Draft, build_brief, render_header
from src.cluster import highlight, rank, theme_reviews
from src.config import Config, load_config, missing_runtime
from src.filter import filter_reviews
from src.load import LoadError, load_export
from src.notes import (
    DEFAULT_RUNS_DIR,
    DEFAULT_STATE_PATH,
    load_state,
    save_state_entry,
    write_run_notes,
)
from src.publish.client import ToolClient
from src.publish.docs import publish_doc
from src.publish.errors import PublishError
from src.publish.factory import open_tool_client
from src.publish.gmail import publish_draft
from src.quotes import select_quotes
from src.writer import UrllibTransport, WriterError, write


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Groww weekly review pulse.")
    parser.add_argument("--export", help="Path to reviews.csv or .json")
    parser.add_argument("--run-date", help="YYYY-MM-DD. Defaults to today.")
    args = parser.parse_args(argv)
    _load_dotenv()
    config = load_config(os.environ)
    export_path = Path(args.export) if args.export else config.export_path
    if args.run_date:
        try:
            run_date = date.fromisoformat(args.run_date)
        except ValueError:
            print("invalid --run-date; use YYYY-MM-DD")
            return 1
    else:
        run_date = config.run_date

    # Rebuild config with CLI run_date override without mutating frozen fields.
    config = Config(
        groq_api_key=config.groq_api_key,
        groq_model=config.groq_model,
        recipient=config.recipient,
        export_path=export_path,
        window_weeks=config.window_weeks,
        run_date=run_date,
        docs_mcp_command=config.docs_mcp_command,
        gmail_mcp_command=config.gmail_mcp_command,
        mcp_api_key=config.mcp_api_key,
    )
    return run_pulse(config)


def run_pulse(
    config: Config,
    *,
    write_fn: Callable[[Brief, object], Draft] | None = None,
    open_docs: Callable[[], ToolClient] | None = None,
    open_gmail: Callable[[], ToolClient] | None = None,
    state_path: Path = DEFAULT_STATE_PATH,
    runs_dir: Path = DEFAULT_RUNS_DIR,
) -> int:
    """Pipeline body. Tests inject write_fn and MCP client factories."""
    week_key = config.run_date.isoformat()
    notes: dict = {
        "window_start": None,
        "window_end": None,
        "kept": None,
        "by_store": None,
        "unthemed": None,
        "dropped": None,
        "highlighted": None,
        "model": config.groq_model,
        "doc_id": None,
        "doc_url": None,
        "draft_created": False,
        "stop_reason": "",
    }

    def flush(code: int, *, reason: str = "") -> int:
        if reason:
            notes["stop_reason"] = reason
        # Prefer window_end from filter when known.
        key = notes.get("window_end") or week_key
        if isinstance(key, date):
            key = key.isoformat()
        write_run_notes(str(key), notes, runs_dir=runs_dir)
        return code

    try:
        rows = load_export(config.export_path)
    except LoadError as exc:
        print(exc)
        return flush(1, reason=str(exc))

    filtered = filter_reviews(
        rows, window_weeks=config.window_weeks, run_date=config.run_date
    )
    notes["window_start"] = filtered.window_start.isoformat()
    notes["window_end"] = filtered.window_end.isoformat()
    notes["kept"] = len(filtered.kept)
    notes["dropped"] = dict(filtered.dropped)
    notes["by_store"] = {
        "app_store": sum(1 for r in filtered.kept if r.store == "app_store"),
        "play": sum(1 for r in filtered.kept if r.store == "play"),
    }
    week_key = filtered.window_end.isoformat()

    if filtered.stop_reason in {"ambiguous_date", "window"}:
        print(f"filter stopped: {filtered.stop_reason}")
        return flush(1, reason=filtered.stop_reason)

    themed = theme_reviews(filtered.kept)
    stats = rank(themed)
    top, other = highlight(stats)
    quotes = select_quotes(themed, top)
    unthemed = sum(1 for _, theme in themed if theme is None)
    notes["unthemed"] = unthemed
    notes["highlighted"] = [{"name": item.name, "count": item.count} for item in top]

    brief = build_brief(
        filtered=filtered,
        run_date=config.run_date,
        highlighted=top,
        other_themes=other,
        quotes=quotes,
        unthemed=unthemed,
        loaded_count=len(rows),
    )

    missing = missing_runtime(config)
    if missing:
        msg = "missing " + ", ".join(missing)
        print(msg)
        return flush(1, reason=msg)

    writer = write_fn
    if writer is None:

        def writer(brief, _transport=None):
            return write(
                brief,
                UrllibTransport(api_key=config.groq_api_key, model=config.groq_model),
            )

    try:
        try:
            draft = writer(brief, None)
        except TypeError:
            draft = writer(brief)
    except WriterError as exc:
        print(exc)
        reason = f"writer: {exc}"
        if exc.failures:
            reason = f"writer: {', '.join(exc.failures)}"
        return flush(1, reason=reason)

    if not config.docs_mcp_command.strip():
        print("Docs MCP server is not connected")
        return flush(1, reason="Docs MCP server is not connected")

    docs_client = None
    gmail_client = None
    try:
        docs_client = (open_docs or (lambda: open_tool_client(
            config.docs_mcp_command, api_key=config.mcp_api_key
        )))()
        full_text = render_header(brief) + "\n\n" + draft.doc_body
        state = load_state(state_path)
        try:
            doc_ref = publish_doc(
                docs_client,
                state,
                week_key,
                brief.title,
                full_text,
            )
        except PublishError as exc:
            print(exc)
            return flush(1, reason=str(exc))

        notes["doc_id"] = doc_ref.doc_id
        notes["doc_url"] = doc_ref.url
        save_state_entry(
            week_key,
            doc_id=doc_ref.doc_id,
            url=doc_ref.url,
            path=state_path,
        )

        if not doc_ref.url.strip():
            print("Docs returned an id without a URL")
            return flush(1, reason="Docs returned an id without a URL")

        email_body = _fill_doc_link(draft.email_body, doc_ref.url)
        gmail_client = (open_gmail or (lambda: open_tool_client(
            config.gmail_mcp_command, api_key=config.mcp_api_key
        )))()
        try:
            publish_draft(
                gmail_client,
                config.recipient,
                draft.email_subject,
                email_body,
            )
        except PublishError as exc:
            print(exc)
            notes["draft_created"] = False
            return flush(1, reason=str(exc))

        notes["draft_created"] = True
        print(f"doc={doc_ref.url}")
        print("draft_created=true")
        return flush(0)
    finally:
        if docs_client is not None:
            docs_client.close()
        if gmail_client is not None:
            gmail_client.close()


def _fill_doc_link(email_body: str, url: str) -> str:
    """Replace {doc_link}; if Groq omitted it, append the Doc URL."""
    body = email_body.replace("{doc_link}", url)
    if "https://" not in body:
        body = body.rstrip() + f"\nDoc: {url}\n"
    return body


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


if __name__ == "__main__":
    sys.exit(main())
