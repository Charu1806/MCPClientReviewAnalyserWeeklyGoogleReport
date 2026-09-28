# Implementation plan: Groww Weekly Review Pulse

**Follows:** [architecture.md](architecture.md) and [PRD.md](PRD.md). Row-level behavior is in [edgecases.md](edgecases.md).  
**How to use this file:** implement **one phase per session**. Paste that phase’s prompt. Do not start the next phase until its “Done when” checks pass.

## Standing rules (every phase)

- Python 3.11+. Module names and paths match [architecture.md](architecture.md). Do not rename them.
- Two commands. `python -m src.download` writes `data/exports/reviews.csv` from public store pages. `python -m src.run` reads that file and does not fetch store pages. Neither command logs into App Store Connect or Play Console.
- Theme assignment is keyword counting in `catalog.py`. Do not embed reviews and do not ask Groq to cluster them.
- Groq is the only writer. Endpoint: `https://api.groq.com/openai/v1/chat/completions`. Model: `qwen/qwen3.8-27b` unless `GROQ_MODEL` is set. No other chat provider, and no hand-written note when Groq fails.
- The model receives the brief only. It never receives the export, identity columns, unsafe review text, or `PULSE_RECIPIENT`.
- Docs and Gmail are MCP tools. Do not add `google-api-python-client`, `google-auth`, an OAuth client, or a REST call to Google.
- The Gmail path creates a draft. It never calls a tool whose name contains `send`.
- Quotes stay verbatim. The check compares them to the brief, character for character.
- Run notes and `data/state.json` store counts, the model name, the Doc id, and the Doc URL. They do not store review text or the recipient.
- `.env`, `data/exports/*`, `data/state.json`, and `data/runs/` stay gitignored.

## Phase order

| Phase | Builds | Depends on |
| --- | --- | --- |
| 1 | Skeleton, config, README | Nothing |
| 2 | Loader and filter | Phase 1 |
| 3 | Download into `data/exports/reviews.csv` | Phase 2 |
| 4 | Catalog, cluster, quotes | Phase 2 |
| 5 | Brief, header, checks | Phase 4 |
| 6 | Groq writer and retry | Phase 5 |
| 7 | MCP publish, state, run notes, CLI | Phase 6 |

---

## Phase 1 — Skeleton and config

**Goal:** a runnable package, dependencies, ignore rules, and config loading. No export parsing and no network calls.

**Create:**

- `requirements.txt` with `python-dotenv` and `pytest`. The MCP client library is added in Phase 7.
- `.gitignore` covering `.venv/`, `__pycache__/`, `.env`, `.pytest_cache/`, `data/exports/*`, `data/state.json`, `data/runs/`. Keep `data/exports/.gitkeep`.
- Empty packages: `src/__init__.py`, `src/publish/__init__.py`.
- `src/config.py`
- `.env.example`
- `README.md` with the project name and placeholder headings: Setup, Scope, Run, Themes, Known limits.
- `tests/test_config.py`

**.env.example keys:**

| Name | Example | Notes |
| --- | --- | --- |
| `GROQ_API_KEY` | empty | Required before Groq. |
| `GROQ_MODEL` | empty | Default `qwen/qwen3.8-27b`. |
| `PULSE_RECIPIENT` | empty | Operator address or alias. |
| `PULSE_EXPORT` | `data/exports/reviews.csv` | Overridden by `--export`. |
| `PULSE_WINDOW_WEEKS` | `12` | Allowed range is 8–12 when the export spans at least 8 weeks. |
| `DOCS_MCP_COMMAND` | empty | Stdio command for the Docs MCP server. Used in Phase 7. |
| `GMAIL_MCP_COMMAND` | empty | Stdio command for the Gmail MCP server. Used in Phase 7. |

**Config:**

- `Config` fields: `groq_api_key`, `groq_model`, `recipient`, `export_path`, `window_weeks`, `run_date`, `docs_mcp_command`, `gmail_mcp_command`.
- `load_config(env) -> Config` reads those variables. Default model `qwen/qwen3.8-27b`. Default window `12`. Default `run_date` is today’s date. Missing optional values become empty strings, not exceptions.
- `missing_runtime(config) -> list[str]` returns `"GROQ_API_KEY"` and `"PULSE_RECIPIENT"` when those are blank. It does not raise. Phase 7 calls it before the writer.

**Done when:**

- `pip install -r requirements.txt` is the only install step in the README.
- `tests/test_config.py` covers the defaults and `missing_runtime` for a blank key and a blank recipient.
- No `load.py`, catalog, Groq call, or MCP client yet.

**Prompt:**

```
Implement Phase 1 only from Docs/implementation.md. Follow Docs/architecture.md.
Create the skeleton, requirements, gitignore, config, .env.example, and README headings.
Do not parse reviews, do not call Groq, and do not start Phase 2.
```

---

## Phase 2 — Load and filter

**Goal:** turn a CSV or JSON export into kept reviews and drop counts. Pure functions. No themes and no network.

**Create:**

- `src/load.py`
- `src/filter.py`
- `tests/test_load.py`
- `tests/test_filter.py`
- `tests/fixtures/` with small CSV and JSON files used only by these tests

**Loader** (`load_export(path) -> list[dict]`):

- Missing path, unreadable path, or a directory raises `LoadError` and includes the path.
- Empty file returns `[]`.
- Suffix `.csv` or `.json` only. Anything else raises `LoadError`. Read UTF-8 with the BOM stripped (`utf-8-sig`).
- CSV: `csv.DictReader`. JSON list: use it. JSON object with exactly one value and that value is a list: use the list. Any other JSON raises `LoadError`.
- Header match is case-insensitive. Aliases: `review`, `content`, `body` → `text`; `stars`, `score` → `rating`; `platform` → `store`; `app_id`, `appId`, `package`, `bundle_id`, `product_id` → `app_id`.
- After aliasing, `store`, `rating`, and `date` must exist as columns, and at least one of `text` or `title` must exist. If not, raise `LoadError` and name the missing field.
- Drop these columns and do not return them: `author`, `userName`, `username`, `nickname`, `email`, `device`, `device_id`, `reviewer`, `user`.
- Each returned dict has `store`, `rating`, `date`, `text`, `title`, `app_id`. Missing `title` or `app_id` is `""`. If `text` is blank and `title` is not, copy `title` into `text`.

**Filter** (`filter_reviews(rows, *, window_weeks, run_date) -> FilterResult`):

`FilterResult` holds `kept`, `dropped`, `missing_stores`, `stores_empty_in_window`, `window_start`, `window_end`, `actual_start`, `actual_end`, and `stop_reason`.

`dropped` keys, all starting at 0: `empty`, `bad_date`, `bad_rating`, `bad_store`, `out_of_window`, `duplicate`, `wrong_app`.

`stop_reason` is `""` unless the run must stop. A stop leaves `kept` empty.

Window, when `window_weeks` is 8, 9, 10, 11, or 12:

- `window_end` is `run_date`.
- `window_start` is `run_date` minus `window_weeks * 7` days.
- Both ends are inclusive. Compare calendar dates. A datetime keeps its date part and drops the clock.

Example: `run_date` 2026-09-28 and 12 weeks → start 2026-07-06, end 2026-09-28.

If `window_weeks` is outside 8–12:

- Parse every row’s date first.
- If any parsed date exists and the span from the earliest to the latest is 8 weeks or more, set `stop_reason` to `window` and return. Do not clamp.
- If every parsed date falls inside a span shorter than 8 weeks, continue and say so later through `actual_start` and `actual_end`.

Per row, in this order, first match wins:

1. Ambiguous numeric date (`D/M/Y` or `M/D/Y`, slashes or dashes, 2- or 4-digit year) sets `stop_reason` to `ambiguous_date` and returns immediately.
2. Blank text after the title fallback increments `empty` and drops the row.
3. Blank, or unparseable, date increments `bad_date`. Accepted forms: `YYYY-MM-DD`, an ISO datetime using that date, and a date that contains an English month name (`28 September 2026`, `Sep 28, 2026`, `28 Sep 2026`).
4. Rating that is not an integer 1 through 5 increments `bad_rating`. `"5 stars"` and `"5.0"` are dropped.
5. Store alias: `ios`, `apple`, `app store`, `app_store` → `app_store`. `android`, `play`, `google play`, `play_store` → `play`. Anything else, including blank, increments `bad_store`.
6. Non-empty `app_id` other than `com.nextbillion.groww` or `1404871703` increments `wrong_app`.
7. Date outside the window increments `out_of_window`.
8. Duplicate of an already kept row increments `duplicate`. The key is store, calendar date, rating, and text after whitespace is collapsed to a single space. The first row in file order wins.

Whitespace is collapsed on the text that is stored. A kept review has `store` (`app_store` or `play`), `rating` (int), `date`, `text`, and `title`.

After the scan:

- `missing_stores` lists `app_store`, `play`, or both when no input row mapped to that store.
- `stores_empty_in_window` lists a store that did appear in the input and has zero kept rows.
- `actual_start` and `actual_end` are the min and max kept dates. They are `None` when nothing was kept.
- An empty file, a file whose rows are all the wrong app, and a window with zero kept rows are not stops.

**Done when:**

- `pytest tests/test_load.py tests/test_filter.py` passes.
- A fixture proves: BOM and aliases load, identity columns are absent from the result, an ambiguous date stops the run, the 2026-09-28 / 12-week bounds are 2026-07-06 through 2026-09-28, a duplicate is counted once, and a wrong app id is dropped.
- No catalog, Groq, or MCP code.

**Prompt:**

```
Implement Phase 2 only from Docs/implementation.md. Follow Docs/architecture.md §4 and Docs/edgecases.md §1–§3.
Add src/load.py, src/filter.py, and their tests.
Do not download reviews, do not assign themes, do not call Groq, and do not start Phase 3.
```

---

## Phase 3 — Download the export

**Goal:** write `data/exports/reviews.csv` for the Groww app from public pages, covering the same window the filter will use. No Groq and no MCP. Tests use fixtures and do not open a socket.

**Create:**

- `src/download.py`
- `tests/test_download.py`
- `tests/fixtures/apple_rss.json`, `tests/fixtures/apple_page.json`, `tests/fixtures/play_page.html`

**Command:** `python -m src.download`. Optional `--run-date YYYY-MM-DD`. Window weeks come from `PULSE_WINDOW_WEEKS`, default 12.

**Window, both stores:**

- `window_end` is the run date. `window_start` is the run date minus `window_weeks * 7` days. Both dates are inclusive.
- 12 weeks is 84 days. 8 weeks is 56 days. Example: run date 2026-09-28 and 12 weeks keeps 2026-07-06 through 2026-09-28.
- A value outside 8–12 exits 1 and does not write the CSV.
- A review older than `window_start` is counted as `older` and is not written.

**CSV columns, in this order:** `store`, `rating`, `date`, `title`, `text`, `app_id`.

- App Store rows use `store=app_store` and `app_id=1404871703`.
- Play rows use `store=play` and `app_id=com.nextbillion.groww`.
- `date` is `YYYY-MM-DD`.
- There is no reviewer-name column. Do not write `author`, `reviewerName`, or `dateAuthorText`.

**App Store, no login.** Two public GETs. Timeout 20 seconds. User-Agent is set. A timeout or HTTP 5xx retries that URL once.

1. Customer Reviews RSS, pages 1 through 10:

`https://itunes.apple.com/in/rss/customerreviews/page={page}/id=1404871703/sortBy=mostRecent/json`

- `feed.entry` may be missing, one object, or a list. An entry without `im:rating` is skipped.
- `rating` is `im:rating.label`. `title` is `title.label`. `text` is `content.label`. `date` is the calendar date before `T` in `updated.label`.
- Stop the page loop when `entry` is missing, the page has no rated reviews, or the newest rated review on the page is before `window_start`.

2. One GET of the public product page, because the Indian RSS for this app can return no entries:

`https://apps.apple.com/in/app/groww-stocks-mutual-fund-ipo/id1404871703`

- Parse the `serialized-server-data` JSON.
- Read `data[0].data.shelfMapping.allProductReviews.items[].review`.
- `text` is `contents`. `date` is the calendar date before `T` in `date`.
- This shelf is only the reviews on the first view of the page. Do not request further App Store review pages, and do not read a bearer token.

**Play Store, no login.** One GET and no other Play request:

`https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN&gl=IN`

- If the body contains review records with a rating, text, and a date, map those and drop any reviewer name.
- If it does not, keep zero Play rows and set the note `public page has no review list`.
- Do not call Play Console. Do not call a second Play URL. Do not paginate a private batch endpoint.

**Write rules:**

- Dedup on store, date, rating, and text after whitespace is collapsed. First row wins.
- Sort by store, date, rating, text.
- Try every source before writing. Write `data/exports/reviews.csv.tmp` and replace `reviews.csv` only after that.
- If every source URL fails, leave an existing CSV in place and exit 1.
- If the fetches succeed and no row is inside the window, write the header row only and exit 0.
- Write `data/exports/download_notes.json` with the window, rows kept by store, rows dropped as older, and any source error or empty-feed note. No review text and no reviewer name.

**Done when:**

- An RSS fixture with one in-window review and one older review writes only the in-window review, with no author field in the CSV.
- A product-page fixture that includes `reviewerName` writes the review text and does not write the name.
- A Play fixture with no review list produces zero Play rows and the note `public page has no review list`.
- `pytest tests/test_download.py` passes and does not open a socket.
- No catalog, Groq, or MCP code.

**Prompt:**

```
Implement Phase 3 only from Docs/implementation.md. Follow Docs/architecture.md §4 and Docs/edgecases.md §9.
Add src/download.py and tests/test_download.py. Tests use fixtures, not the network.
Do not assign themes, do not call Groq, and do not start Phase 4.
```

---

## Phase 4 — Catalog, cluster, and quotes

**Goal:** assign one theme, rank the top three, and select up to three verbatim quotes. Deterministic. No Groq.

**Create:**

- `src/catalog.py`
- `src/cluster.py`
- `src/quotes.py`
- `tests/test_cluster.py`
- `tests/test_quotes.py`

**Catalog order** is fixed. A hit is a case-insensitive match. Phrases match as substrings. Single words match on word boundaries, so `pay` is not a keyword and `sip` does not match inside another word.

| Order | Theme | Keywords |
| --- | --- | --- |
| 0 | Onboarding and KYC | `kyc`, `e-kyc`, `ekyc`, `onboarding`, `registration`, `sign up`, `signup`, `paperwork`, `demat`, `account opening` |
| 1 | SIP and payments | `sip`, `lump sum`, `lumpsum`, `upi`, `net banking`, `netbanking`, `mandate`, `payment`, `autopay`, `nach`, `purchase` |
| 2 | Login and access | `mpin`, `biometric`, `otp`, `password`, `login`, `log in`, `sign in`, `lockout`, `locked`, `fingerprint` |
| 3 | Portfolio and statements | `statement`, `capital gain`, `dashboard`, `holding`, `holdings`, `nav`, `portfolio`, `order`, `orders` |
| 4 | Redemption and service | `withdraw`, `withdrawal`, `redemption`, `redeem`, `bank detail`, `contact update`, `service request`, `sell`, `fast exit` |

Count distinct keywords, not repetitions. The theme with the most hits wins. A tie uses the earlier catalog order. Zero hits means unthemed. The rating is not an input to this function.

**Cluster:**

- `assign(review) -> str | None`
- `rank(themed_reviews) -> list[ThemeStats]`
- `ThemeStats`: `name`, `count`, `avg_rating`, `median_date`, `catalog_index`
- Average is the mean rounded half up to one decimal (`Decimal` with `ROUND_HALF_UP`).
- Median date is the upper median: sort the dates, and on an even count take the later of the two central dates.
- Sort key: higher count, then lower average, then more recent median date, then lower `catalog_index`.
- Highlight the first three themes whose count is at least 1. If fewer exist, highlight those. The rest with count at least 1 are `other_themes`.

**Quotes** (`select_quotes(themed_reviews, highlighted) -> list[Quote]`):

A review is unsafe when its title or text matches any of:

- an email address
- an `@handle` (`@` plus two or more letters, digits, or underscores)
- a PAN-shaped id, five letters, four digits, one letter
- a run of 10 or more digits

Unsafe reviews stay in the theme counts and are not candidates.

Skip a candidate whose letters and digits disappear after punctuation and emoji are removed.

Sort candidates within a theme by newer date, then lower rating, then text ascending.

1. Walk highlighted themes in rank order and take the first remaining safe candidate from each.
2. Fill to three from the remaining safe candidates in highlighted themes, using the same sort across those themes.
3. At most one quote per review.
4. Skip a candidate whose collapsed, lowercased text equals a quote already chosen.

Cut the text before saving it:

- Split sentences on `.`, `!`, or `?` followed by whitespace. If there is no split, the whole text is one sentence.
- If the first sentence has more than 40 words, keep its first 40 words and append `...`.
- Otherwise keep the first two sentences, joined by a single space.

`Quote` fields: `text` (the cut string), `store`, `rating`, `date`, `theme`.

**Done when:**

- The same fixture ranked twice yields the same theme order and the same quote strings.
- A two-keyword tie assigns the earlier catalog theme.
- A review that only contains a star rating is unthemed.
- A review with an email is counted in its theme and is not among the quotes.
- A 50-word first sentence becomes 40 words plus `...`, and those 40 words are a prefix of the source.
- `pytest tests/test_cluster.py tests/test_quotes.py` passes.
- No Groq call.

**Prompt:**

```
Implement Phase 4 only from Docs/implementation.md. Follow Docs/architecture.md §5 and Docs/edgecases.md §4–§5.
Add src/catalog.py, src/cluster.py, src/quotes.py, and their tests.
Do not call Groq, do not build the brief, and do not start Phase 5.
```

---

## Phase 5 — Brief, header, and checks

**Goal:** build the object Groq will see, render the header in code, and accept or reject a draft. Still no network.

**Create:**

- `src/brief.py`
- `src/checks.py`
- `tests/test_brief.py`
- `tests/test_checks.py`

**Brief fields:**

| Field | Content |
| --- | --- |
| `title` | `Groww — Weekly Review Pulse — week ending {window_end}` |
| `window_start`, `window_end`, `run_date` | From the filter |
| `actual_start`, `actual_end` | Min and max kept dates, or `None` |
| `kept`, `by_store` | Kept rows, keys `app_store` and `play` |
| `missing_stores`, `stores_empty_in_window` | From the filter |
| `unthemed` | Kept rows with no theme |
| `dropped` | The filter’s drop counts |
| `highlighted` | `name`, `count`, `avg_rating` for the highlighted themes, in rank order |
| `other_themes` | `name`, `count` only |
| `quotes` | The selected quotes, in selection order |
| `shortfalls` | The lines below that apply |
| `note_mode` | `empty_export`, `wrong_app`, `empty_window`, `unthemed`, or `normal` |

`note_mode`, first match:

1. Loader returned no rows → `empty_export`
2. At least one right-app row existed and `kept` is 0 → `empty_window`
3. `kept` is 0 and `wrong_app` is greater than 0 → `wrong_app`
4. `kept` is greater than 0 and every kept row is unthemed → `unthemed`
5. Otherwise → `normal`

Shortfall lines, included only when true, in this order:

- `No reviews in this export.`
- `No reviews for the Groww app in this export.`
- `No reviews in this window. {n} dropped as out of window.`
- `No catalog theme matched {n} reviews.`
- `App Store export is absent.`
- `Play export is absent.`
- `App Store had no reviews in the window.`
- `Play had no reviews in the window.`
- `Only {n} themes in this window.` when `n` is 1 or 2
- `No safe quote was available.` when `note_mode` is `normal` and the quote list is empty
- `{n} safe quotes; fewer than 3.` when `n` is 1 or 2

`prompt_payload(brief) -> dict` is the JSON sent to Groq. It includes the fields above and omits `PULSE_RECIPIENT`. It has no raw rows.

`render_header(brief) -> str` is the published header. It includes the title, the window, the run date, `Reviews kept: {kept} (App Store {n}, Play {n})`, the actual range when it differs from the window, the out-of-window count when it is non-zero, the duplicate count when it is non-zero, and each shortfall on its own line. This string is not part of the 250-word body.

**Draft** the checks accept:

- `doc_body`, `email_subject`, `email_body`

`check_draft(brief, draft) -> list[str]` returns failure names. An empty list passes. Strip one wrapping markdown fence from each field before checking, and only when the whole field is inside that fence.

Required body shape for `note_mode == "normal"`:

```
Top themes
1. {Theme} — {count} reviews, average {avg}
{one sentence}

Quotes
1. "{quote text}" — {App Store or Play}, {rating} stars, {YYYY-MM-DD}

Actions
1. {Theme}: {one sentence}
```

Number the items that exist. Omit the `Quotes` section when the brief has no quotes. Omit nothing else in `normal` mode.

| Failure name | Rule |
| --- | --- |
| `shape` | Any of the three strings is empty after the fence strip. For `normal`, the `Top themes` and `Actions` headings are missing. |
| `quotes` | A brief quote is missing from `doc_body`, or `doc_body` contains a quotation and the brief has no quotes. |
| `facts` | A highlighted name or its count is missing, an average does not match, or a catalog theme that is neither highlighted nor in `other_themes` appears. |
| `actions` | The `Actions` count is not the highlighted count, or an action line is for a theme that is not highlighted. Zero highlighted themes means the body has no `Actions` heading. |
| `length` | `len(doc_body.split())` is greater than 250. |
| `privacy` | `doc_body`, `email_subject`, or `email_body` matches the unsafe patterns from Phase 4. |
| `advice` | Case-insensitive word match on `buy`, `sell`, or `hold`, or a match on `invest in`, `best scheme`, `best fund`, or `you should`. |
| `subject` | `email_subject` stripped is not exactly `brief.title`. |
| `link` | `email_body` contains neither `{doc_link}` nor the full `doc_body`. |

For `empty_export`, `wrong_app`, `empty_window`, and `unthemed`: `doc_body` is one sentence, contains none of the five theme names, contains no `average`, and has no `Quotes` or `Actions` heading. The `facts` and `actions` rules reduce to that. `quotes` passes only when the body has no quoted review text.

**Done when:**

- A normal brief’s payload has no recipient and no review beyond the selected quotes.
- A draft that paraphrases a quote returns `quotes`.
- A draft over 250 words returns `length`.
- A draft that says `buy` returns `advice`.
- An empty-export brief rejects a body that names `SIP and payments`.
- `pytest tests/test_brief.py tests/test_checks.py` passes.
- No HTTP client yet.

**Prompt:**

```
Implement Phase 5 only from Docs/implementation.md. Follow Docs/architecture.md §3 and §7.
Add src/brief.py, src/checks.py, and their tests.
Do not call Groq, do not call MCP, and do not start Phase 6.
```

---

## Phase 6 — Groq writer

**Goal:** send the brief to Groq, parse the three strings, and run the Phase 5 checks with one repair call. No MCP.

**Create:**

- `src/writer.py`
- `tests/test_writer.py`
- A fake transport in the test. Do not call the network from tests.

**Call:**

- `POST https://api.groq.com/openai/v1/chat/completions`
- Header `Authorization: Bearer {GROQ_API_KEY}`
- Body: model, `temperature` 0.2, and two messages.
- Timeout 60 seconds.
- Use `urllib.request` from the standard library. Do not add a second LLM SDK.

System message rules:

- Write from the brief only. Do not invent counts, themes, quotes, or causes.
- `normal`: use the body shape from Phase 5. Copy each quote character for character, including `...`. One sentence per theme. One action per highlighted theme, naming that theme. Actions are product, support, or growth steps. They are not investment advice.
- Other modes: the whole `doc_body` is the first shortfall sentence, and nothing else.
- `email_subject` equals `title`.
- `email_body` contains `doc_body` and a final line `Doc: {doc_link}`.
- Return one JSON object with keys `doc_body`, `email_subject`, and `email_body`. No markdown fence.

User message: `prompt_payload(brief)` as JSON.

`write_once(brief, transport) -> Draft` posts, strips one fence, and `json.loads` the content. A missing key or invalid JSON becomes a draft that fails `shape`.

`write(brief, transport) -> Draft`:

1. Call `write_once`.
2. If `check_draft` is empty, return the draft.
3. Call `write_once` again. The user message adds `failed_checks` and the previous three strings.
4. If the second check is empty, return it.
5. Raise `WriterError` with the second failure names. Do not return a failed draft for publication.

Transport errors:

- Timeout, HTTP 429, 500, 502, 503, or 504: retry that HTTP call once, then raise `WriterError`.
- Any other HTTP status: raise `WriterError` with no content retry.
- The check repair and the HTTP retry are separate. A single `write()` performs at most two successful HTTP responses, and each of those may have had one transport retry.

Do not log the payload or the draft.

**Done when:**

- A fake 200 with valid JSON and a passing draft returns without a second content call.
- A first draft that fails `quotes`, then a second draft that passes, returns the second draft.
- Two failing drafts raise `WriterError` and the exception lists the failure names.
- A 429 followed by a 200 counts as one transport retry and still returns the draft.
- A 400 raises without a second attempt.
- `pytest tests/test_writer.py` passes and does not open a socket.

**Prompt:**

```
Implement Phase 6 only from Docs/implementation.md. Follow Docs/architecture.md §6 and §7.
Add src/writer.py and tests/test_writer.py with a fake transport.
Do not call MCP, do not add a Google client, and do not start Phase 7.
```

---

## Phase 7 — Publish, state, and the CLI

**Goal:** wire the pipeline. After a passing draft, write the Doc through MCP, fill `{doc_link}`, create one Gmail draft, and record run notes.

**Create:**

- `src/publish/client.py` — `ToolClient` with `list_tools()` and `call_tool(name, arguments)`.
- `src/publish/stdio_client.py` — stdio MCP client using the `mcp` package. Add `mcp` to `requirements.txt`.
- `src/publish/docs.py`
- `src/publish/gmail.py`
- `src/notes.py`
- `src/run.py`
- `tests/test_publish.py`
- `tests/test_run.py`

Tests inject a fake `ToolClient`. They do not start a real MCP server.

**Tool choice:**

- List tools. Match on the tool name, lowercased.
- Docs update: name contains `update` and either `document` or `doc`.
- Docs create: name contains `create` and either `document` or `doc`, and does not contain `draft`.
- Gmail draft: name contains `draft` and does not contain `send`.
- If the Docs server has no create tool, raise `PublishError` with `Docs MCP server is not connected`.
- If the Gmail server has no draft tool, raise `PublishError`. If its only mail tool contains `send`, the message is `Gmail tool would send`. Do not call that tool.

**Argument mapping** uses the tool’s input schema. Map the first property whose name matches:

| Value | Accepted property names |
| --- | --- |
| Title | `title`, `name` |
| Doc body | `text`, `content`, `body`, `markdown` |
| Doc id | `documentId`, `document_id`, `doc_id`, `id` |
| Recipient | `to`, `recipient` |
| Subject | `subject` |
| Email body | `body`, `message`, `text` |

If a required property is not in the schema, raise `PublishError` and name the tool and the missing value. Do not call the tool with an empty argument dict.

**Docs** (`publish_doc(client, state, week_key, title, full_text) -> DocRef`):

- `full_text` is `render_header(brief)`, a blank line, then `doc_body`.
- `week_key` is `window_end` as `YYYY-MM-DD`.
- If `state` has that key and an update tool exists, call update with the stored id and `full_text`.
- Otherwise call create once with the title and `full_text`.
- Read `structuredContent` when present. Otherwise read a JSON object in the tool text. Accept `documentId` or `id`, and `url` or `documentUrl`.
- A timeout or connection error with no id retries the call once. Then raise `PublishError`.
- An id without a URL returns `DocRef(doc_id, url="")` and does not retry.
- Do not call Gmail from this function.

**Gmail** (`publish_draft(client, recipient, subject, body) -> None`):

- Require `https://` in the body. If `{doc_link}` is still present, raise `PublishError` and do not call the tool.
- Call the draft tool once. Do not retry. A failure raises `PublishError` and leaves any existing Doc alone.

**State and notes:**

- `data/state.json` maps `week_key` to `{"doc_id", "url"}`. Write it only after an id comes back. A later failure does not delete the key. A missing URL is stored as `""`.
- `data/runs/{week_key}.json` holds window, kept, `by_store`, unthemed, dropped, highlighted theme names and counts, model, `doc_id`, `doc_url`, `draft_created`, and `stop_reason`. No quote text and no recipient.

**CLI** (`python -m src.run`):

1. Load config. `--export` overrides the path. `--run-date YYYY-MM-DD` overrides the date.
2. Load the export. On `LoadError`, write notes, print the error, exit 1.
3. Filter. On `stop_reason` of `ambiguous_date` or `window`, write notes, exit 1.
4. Cluster, select quotes, build the brief.
5. If `missing_runtime` is non-empty, write notes, exit 1. Do not call the writer or MCP.
6. Call `write`. On `WriterError`, write notes, exit 1. Do not call MCP.
7. Build the Docs client from `DOCS_MCP_COMMAND`. Blank command exits 1 before a create call.
8. `publish_doc`. Save state when an id exists.
9. If the URL is empty, write notes with `draft_created` false, exit 1.
10. Replace `{doc_link}` in `email_body`. Build the Gmail client. `publish_draft` uses `config.recipient`.
11. On Gmail `PublishError`, write notes with the Doc URL and `draft_created` false, exit 1. Do not create a second Doc.
12. On success, `draft_created` is true and the exit code is 0.

`src.run` reads `data/exports/reviews.csv`. It does not download. A missing file is a `LoadError`.

Update the README Setup, Run, and Known limits sections so they name `python -m src.download` before `python -m src.run`, the 12-week window for both stores, the five themes, and the MCP requirement.

**Done when:**

- A fake Docs create plus a fake Gmail draft exits 0, writes `state.json`, and the draft body contains the fake URL and not `{doc_link}`.
- A Docs result with an id and no URL exits 1 and never calls Gmail.
- A Gmail failure after a URL exits 1, keeps the Doc id in state, and does not call create a second time.
- A tool list that only contains `send_email` never calls it.
- A missing `GROQ_API_KEY` exits 1 before the fake writer is called.
- `pytest` passes.
- The repo has no Google API client.

**Prompt:**

```
Implement Phase 7 only from Docs/implementation.md. Follow Docs/architecture.md §8–§10 and Docs/edgecases.md §6–§8.
Add the MCP publisher, run notes, state, and python -m src.run.
Test publishers with a fake ToolClient. Do not send mail and do not add a Google REST client.
```
