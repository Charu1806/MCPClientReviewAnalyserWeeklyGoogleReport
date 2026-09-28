# Groww Weekly Review Pulse

MCP **client** for the weekly Groww review note. It does not talk to Google APIs directly.

Google Docs + Gmail draft tools come from the companion MCP **server**:

- Repo: https://github.com/Charu1806/MCPserverGoogleWorkspace
- Remote MCP: `https://mc-pserver-google-workspace.vercel.app/mcp`
- Tools used: `docs_create` / `docs_append_text`, `gmail_create_draft` (never `gmail_send_email`)

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`:

| Variable | Role |
| --- | --- |
| `GROQ_API_KEY` | Required before the writer |
| `PULSE_RECIPIENT` | Operator address for the Gmail draft |
| `MCP_URL` | Workspace MCP HTTP endpoint (default Vercel URL above) |
| `MCP_API_KEY` | Same secret as the server’s `MCP_API_KEY` (`Authorization: Bearer …`) |

Server-side Google OAuth (`GOOGLE_CLIENT_ID`, refresh token, etc.) lives only in the [MCP server](https://github.com/Charu1806/MCPserverGoogleWorkspace) / Vercel env — not in this client.

## Scope

Groww Stocks, Mutual Fund, IPO only.

| Store | Id |
| --- | --- |
| Google Play | `com.nextbillion.groww` |
| App Store | `1404871703` |

## Themes

Five fixed themes in `src/catalog.py`: Onboarding and KYC, SIP and payments, Login and access, App performance, Customer support.

## Run

```bash
python -m src.download
python -m src.run --run-date 2026-09-28
```

1. `download` writes `data/exports/reviews.csv` (public App Store + Play, 12-week window).
2. `run` loads that file, builds the brief in code, asks Groq for the note/email, then publishes through MCP:
   - Google Doc via `docs_create` (re-run appends with `docs_append_text`)
   - Gmail **draft** via `gmail_create_draft` with `{doc_link}` replaced

Optional stage JSON (no publish):

```bash
python -m src.analyze --run-date 2026-09-28
```

## Known limits

- Window is 8–12 weeks (default 12) for both stores.
- No App Store Connect / Play Console login. Public listing feeds only.
- No Google REST client in this repo — Docs and Gmail go through MCP only.
- Quotes and counts are code-owned; Groq only writes wording.
- A Docs id without a URL stops before Gmail. A Gmail failure keeps the Doc.
