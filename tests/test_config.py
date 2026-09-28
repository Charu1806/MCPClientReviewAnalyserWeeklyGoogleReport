from datetime import date

from src.config import load_config, missing_runtime


def test_defaults_when_env_is_empty():
    config = load_config({})

    assert config.groq_api_key == ""
    assert config.groq_model == "qwen/qwen3.8-27b"
    assert config.recipient == ""
    assert config.export_path.as_posix() == "data/exports/reviews.csv"
    assert config.window_weeks == 12
    assert config.run_date == date.today()
    assert config.docs_mcp_command == ""
    assert config.gmail_mcp_command == ""
    assert config.mcp_api_key == ""


def test_blank_key_and_blank_recipient_are_missing():
    config = load_config({"GROQ_API_KEY": "  ", "PULSE_RECIPIENT": ""})

    assert missing_runtime(config) == ["GROQ_API_KEY", "PULSE_RECIPIENT"]


def test_blank_key_only():
    config = load_config({"GROQ_API_KEY": "", "PULSE_RECIPIENT": "me@example.com"})

    assert missing_runtime(config) == ["GROQ_API_KEY"]


def test_blank_recipient_only():
    config = load_config({"GROQ_API_KEY": "test-key", "PULSE_RECIPIENT": "   "})

    assert missing_runtime(config) == ["PULSE_RECIPIENT"]


def test_runtime_complete_when_key_and_recipient_are_set():
    config = load_config(
        {
            "GROQ_API_KEY": "test-key",
            "GROQ_MODEL": "custom-model",
            "PULSE_RECIPIENT": "me@example.com",
            "PULSE_EXPORT": "data/exports/other.csv",
            "PULSE_WINDOW_WEEKS": "8",
            "DOCS_MCP_COMMAND": "docs-mcp",
            "GMAIL_MCP_COMMAND": "gmail-mcp",
            "MCP_API_KEY": "mcp-secret",
        }
    )

    assert missing_runtime(config) == []
    assert config.groq_model == "custom-model"
    assert config.export_path.as_posix() == "data/exports/other.csv"
    assert config.window_weeks == 8
    assert config.docs_mcp_command == "docs-mcp"
    assert config.gmail_mcp_command == "gmail-mcp"
    assert config.mcp_api_key == "mcp-secret"


def test_mcp_url_fills_docs_and_gmail_when_commands_blank():
    config = load_config(
        {"MCP_URL": "https://mc-pserver-google-workspace.vercel.app/mcp"}
    )
    assert config.docs_mcp_command == "https://mc-pserver-google-workspace.vercel.app/mcp"
    assert config.gmail_mcp_command == "https://mc-pserver-google-workspace.vercel.app/mcp"
