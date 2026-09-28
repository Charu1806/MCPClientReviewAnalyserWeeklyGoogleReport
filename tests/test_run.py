from datetime import date
from pathlib import Path

from src.brief import Draft
from src.config import Config
from src.publish.errors import PublishError
from src.run import run_pulse
from tests.test_publish import FakeClient, _docs_tools, _gmail_draft_tool


def _config(tmp_path: Path, **overrides) -> Config:
    data = {
        "groq_api_key": "test-key",
        "groq_model": "qwen/qwen3.8-27b",
        "recipient": "ops@example.com",
        "export_path": tmp_path / "reviews.csv",
        "window_weeks": 12,
        "run_date": date(2026, 9, 28),
        "docs_mcp_command": "https://example.test/mcp",
        "gmail_mcp_command": "https://example.test/mcp",
        "mcp_api_key": "",
    }
    data.update(overrides)
    return Config(**data)


def _write_export(path: Path) -> None:
    path.write_text(
        "store,rating,date,text,title,app_id\n"
        "play,1,2026-09-01,KYC failed,,com.nextbillion.groww\n"
        "play,2,2026-09-02,SIP payment failed,,com.nextbillion.groww\n"
        "app_store,1,2026-09-03,OTP login locked,,1404871703\n",
        encoding="utf-8",
    )


def _good_draft(brief) -> Draft:
    q1, q2, q3 = brief.quotes
    body = (
        "Top themes\n"
        "1. Onboarding and KYC — 1 reviews, average 1.0\n"
        "Users struggled with KYC.\n"
        "2. SIP and payments — 1 reviews, average 2.0\n"
        "Payments failed for some users.\n"
        "3. Login and access — 1 reviews, average 1.0\n"
        "Login OTP failed.\n"
        "\n"
        "Quotes\n"
        f'1. "{q1.text}" — Play, {q1.rating} stars, {q1.date}\n'
        f'2. "{q2.text}" — Play, {q2.rating} stars, {q2.date}\n'
        f'3. "{q3.text}" — App Store, {q3.rating} stars, {q3.date}\n'
        "\n"
        "Actions\n"
        "1. Onboarding and KYC: Clarify KYC retries in the app.\n"
        "2. SIP and payments: Improve payment failure messages.\n"
        "3. Login and access: Fix OTP delivery for login.\n"
    )
    return Draft(
        doc_body=body,
        email_subject=brief.title,
        email_body=body + "\nDoc: {doc_link}",
    )


def test_happy_path_writes_state_and_replaces_link(tmp_path: Path):
    export = tmp_path / "reviews.csv"
    _write_export(export)
    state_path = tmp_path / "state.json"
    runs_dir = tmp_path / "runs"
    gmail_calls = []

    docs = FakeClient(
        _docs_tools(),
        {
            "create_document": {
                "documentId": "doc-9",
                "url": "https://docs.google.com/document/d/doc-9",
            }
        },
    )
    gmail = FakeClient(
        [_gmail_draft_tool()],
        {
            "create_draft": {"ok": True},
        },
        call_log=gmail_calls,
    )

    code = run_pulse(
        _config(tmp_path, export_path=export),
        write_fn=lambda brief, *_: _good_draft(brief),
        open_docs=lambda: docs,
        open_gmail=lambda: gmail,
        state_path=state_path,
        runs_dir=runs_dir,
    )

    assert code == 0
    state = state_path.read_text(encoding="utf-8")
    assert "doc-9" in state
    assert gmail_calls
    body = gmail_calls[0][1]["body"]
    assert "https://docs.google.com/document/d/doc-9" in body
    assert "{doc_link}" not in body
    notes = (runs_dir / "2026-09-28.json").read_text(encoding="utf-8")
    assert '"draft_created": true' in notes


def test_docs_id_without_url_skips_gmail(tmp_path: Path):
    export = tmp_path / "reviews.csv"
    _write_export(export)
    gmail_opened = {"value": False}

    docs = FakeClient(_docs_tools(), {"create_document": {"documentId": "doc-x"}})

    def open_gmail():
        gmail_opened["value"] = True
        return FakeClient([_gmail_draft_tool()])

    code = run_pulse(
        _config(tmp_path, export_path=export),
        write_fn=lambda brief, *_: _good_draft(brief),
        open_docs=lambda: docs,
        open_gmail=open_gmail,
        state_path=tmp_path / "state.json",
        runs_dir=tmp_path / "runs",
    )
    assert code == 1
    assert gmail_opened["value"] is False
    assert "doc-x" in (tmp_path / "state.json").read_text(encoding="utf-8")


def test_gmail_failure_keeps_doc_state(tmp_path: Path):
    export = tmp_path / "reviews.csv"
    _write_export(export)
    state_path = tmp_path / "state.json"
    docs_calls = []

    docs = FakeClient(
        _docs_tools(),
        {
            "create_document": {
                "documentId": "doc-keep",
                "url": "https://docs.google.com/document/d/doc-keep",
            }
        },
        call_log=docs_calls,
    )
    gmail = FakeClient(
        [_gmail_draft_tool()],
        {"create_draft": PublishError("draft failed")},
    )

    code = run_pulse(
        _config(tmp_path, export_path=export),
        write_fn=lambda brief, *_: _good_draft(brief),
        open_docs=lambda: docs,
        open_gmail=lambda: gmail,
        state_path=state_path,
        runs_dir=tmp_path / "runs",
    )
    assert code == 1
    assert "doc-keep" in state_path.read_text(encoding="utf-8")
    # create called once; no second create on gmail failure
    assert [name for name, _ in docs_calls] == ["create_document"]
    notes = (tmp_path / "runs" / "2026-09-28.json").read_text(encoding="utf-8")
    assert '"draft_created": false' in notes


def test_missing_groq_key_skips_writer(tmp_path: Path):
    export = tmp_path / "reviews.csv"
    _write_export(export)
    called = {"write": False}

    def boom(brief, *_):
        called["write"] = True
        raise AssertionError("writer should not run")

    code = run_pulse(
        _config(tmp_path, export_path=export, groq_api_key=""),
        write_fn=boom,
        open_docs=lambda: (_ for _ in ()).throw(AssertionError("docs")),
        open_gmail=lambda: (_ for _ in ()).throw(AssertionError("gmail")),
        state_path=tmp_path / "state.json",
        runs_dir=tmp_path / "runs",
    )
    assert code == 1
    assert called["write"] is False
