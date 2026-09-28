# Edge cases: Groww Weekly Review Pulse

**Follows:** [PRD.md](PRD.md).  
**Last updated:** 28 September 2026.

Each case has one outcome. **Publish** means Groq still writes the note and the email, the checks pass, and MCP creates the Doc and the draft. **Stop** means no Doc and no draft, unless a case below says the Doc already exists.

The window is inclusive. Default end date is the run date. Default start date is 12 weeks before that end date. A review on either boundary is kept.

## 1. Export file

| Case | Handling |
| --- | --- |
| Path missing, unreadable, or not a file | Stop. Report the path. |
| File is empty, or CSV/JSON has a header and no rows | Publish a short note: header plus “No reviews in this export.” No themes, quotes, or actions. |
| Not CSV or JSON | Stop. Do not guess a delimiter. |
| JSON is one object with a single list value | Read that list. |
| JSON is anything else | Stop. |
| UTF-8 BOM | Strip the BOM and continue. |
| Required field missing after alias mapping | Stop. Name the missing field. Aliases: `review`, `content`, `body` → `text`; `stars`, `score` → `rating`; `platform` → `store`. |
| `text` empty but `title` present | Use the title as the text and continue. |
| `text` and `title` both empty or whitespace | Drop the row. Count it as dropped empty. |
| Extra identity columns (`author`, `userName`, `nickname`, `email`, device id) | Drop the columns before clustering, the Groq brief, logs, the Doc, and the draft. The review can still be counted. |
| App id column present and not `com.nextbillion.groww` or `1404871703` | Drop the row. If none remain, publish “No reviews for the Groww app in this export.” |
| No app id column | Keep the rows. The file is a single-app export supplied for this app. |

## 2. Dates, ratings, store

| Case | Handling |
| --- | --- |
| ISO-8601 date, or a date with an English month name | Parse it. Compare calendar dates, not clock times. |
| Numeric date that could be day/month or month/day | Stop. Ask for ISO dates. Do not guess. |
| Date missing or unparseable on some rows | Drop those rows. Count them as dropped bad-date. Continue with the rest. |
| Every date unparseable | Stop. The window cannot be applied. |
| Date in the future, or before the window start | Drop the row. The header includes how many rows were out of window. |
| Every row is out of window | Publish. Header shows the window, zero kept, and the out-of-window count. No themes, quotes, or actions. |
| Configured window shorter than 8 weeks or longer than 12, while the export covers at least 8 weeks | Stop. Do not clamp silently. |
| Export’s own earliest kept date is inside an 8-week span | Continue. Header states the actual start, end, and count. This is the only path shorter than 8 weeks. |
| Rating missing, not an integer, or outside 1–5 | Drop the row. Count it as dropped bad-rating. |
| Store missing | Drop the row. |
| Store is `ios`, `apple`, or `app store` | Treat as App Store. |
| Store is `android`, `play`, or `google play` | Treat as Play. |
| Store is anything else | Drop the row. |
| One store has no rows in the file | Continue. Header names the missing store. Do not invent its reviews. |
| Both stores are in the file, and one has zero rows inside the window | Continue. Header says that store had no reviews in the window. |

## 3. Duplicates and PII

| Case | Handling |
| --- | --- |
| Same store, calendar date, rating, and text after whitespace is collapsed | Keep the first row. Drop the rest. Header may include the duplicate count. Never quote the same row twice. |
| Same words on both stores | Keep both. They are different reviews. Do not select both as quotes. |
| Email, phone number, `@handle`, PAN-shaped id (`AAAAA9999A`), or a run of 10 or more digits in title or text | Count the review toward its theme. Do not use it as a quote. Do not put that text in the Groq brief. |
| A digit run that is only the star rating or the review date | Not PII. |
| Redaction would require changing the reviewer’s words | Skip the quote. Do not rewrite the sentence. |
| Operator email or alias | Used only as the Gmail recipient. Never placed in the Groq prompt, the Doc body, or a quote. |

## 4. Themes and ranking

| Case | Handling |
| --- | --- |
| Review matches more than one theme | Assign the theme with more keyword hits in title plus text. If the hits tie, use the earlier theme in the catalog in PRD section 7. |
| Review matches no theme | Count as unthemed. Unthemed is not a theme and cannot be in the top 3. |
| Every kept review is unthemed | Publish. Header gives the unthemed count. No highlighted themes, quotes, or actions. |
| One or two themes have reviews | Highlight only those. One action per theme. The note says the set is short. Do not add an empty theme. |
| Four or five themes have reviews | Highlight the top 3. One count line for the others. No extra paragraphs. |
| Tie on review count | Lower average star rating wins. Average is shown to one decimal. |
| Tie on count and average rating | More recent median review date wins. |
| Tie on count, average, and median date | Earlier theme in the catalog wins. The ranking does not depend on row order. |
| Rating is the only signal in the text | Leave the review unthemed. Stars never assign a theme. |

## 5. Quotes

Selection happens in code, before Groq. Prefer one quote from each highlighted theme. If a theme has no safe quote, fill from the other highlighted themes. At most one quote per review.

| Case | Handling |
| --- | --- |
| Three or more safe quotes | Select three. |
| One or two safe quotes | Select those. The note states the shortfall. |
| Themes exist and no safe quote exists | Publish themes and actions. State that no safe quote was available. The brief’s quote list is empty. |
| Review longer than two sentences | Cut on a sentence boundary. If the first sentence is longer than 40 words, keep its first 40 words and add `...`. The words before `...` are a prefix of the source. |
| Quote would be emoji or punctuation only | Skip it and take the next safe quote. |
| Review is not in English | Do not translate. Theme it only when catalog keywords match. A selected quote stays in the original words. |
| Groq paraphrases, translates, or “fixes” a quote | The quote check fails. Retry once. Second failure stops. |

The string stored in the brief, including any `...` the selector added, is the string that must appear in the Doc. The check compares the Doc with the brief, not with a fresh cut of the review.

## 6. Groq

| Case | Handling |
| --- | --- |
| `GROQ_API_KEY` missing or blank | Stop before Docs and Gmail. |
| Timeout, HTTP 429, or HTTP 5xx | Retry the call once. Then stop before Docs and Gmail. |
| Any other HTTP error, or a second failure | Stop before Docs and Gmail. |
| Response empty, or not a Doc body plus an email subject and body | Treat as a failed check. |
| Doc quotes are not character-for-character the brief’s quotes | Failed check. No extra quotation of review text is allowed when the brief has zero quotes. |
| Highlighted themes or counts differ from the brief | Failed check. |
| More actions than highlighted themes, or an action for a theme that was not highlighted | Failed check. Zero themes means zero actions. |
| Doc body over 250 words, excluding the header | Failed check. |
| Email, phone, `@handle`, PAN-shaped id, or a 10-digit run in the Doc or the email | Failed check. |
| Buy, sell, hold, or a scheme recommendation | Failed check. |
| Email subject is not the Doc title | Failed check. |
| Email has neither the note nor the literal `{doc_link}` | Failed check. |
| One wrapping code fence around an otherwise valid response | Strip the fence, then run the checks. |
| A check fails | Call Groq once more and name the failed checks. |
| The second draft still fails | Stop. Do not publish. Do not substitute hand-written prose. |

Provider stays Groq. Model stays `qwen/qwen3.8-27b` unless `GROQ_MODEL` is set. Do not fall through to another chat provider.

## 7. Docs and Gmail

Validate `GROQ_API_KEY` and the recipient before any MCP call. MCP is still only called after the Groq checks pass.

| Case | Handling |
| --- | --- |
| Docs MCP server is not connected | Stop. Do not call Gmail. Do not call the Google REST API. |
| Docs tool returns a transport error and no document id | Retry that call once. Then stop. |
| Docs tool returns a document id and no URL | Stop before Gmail. Report the id. Do not invent a URL. Do not leave `{doc_link}` in a draft. |
| An update tool exists and this week’s Doc id is already known | Update that Doc. Do not create a second Doc in the same run. |
| Update is not supported | Create one new Doc and point the draft at it. |
| Docs call succeeded and Gmail then fails | Keep the Doc. Do not delete it. Run notes include the Doc URL and say the draft was not created. Do not retry by creating another Doc. |
| Gmail MCP server is not connected | Stop as in the row above if the Doc already exists. Otherwise stop with no Doc. |
| Recipient is missing | Stop before Groq. |
| Recipient was taken from a review | Stop. The only recipient is the configured operator address or alias. |
| The only Gmail tool sends mail | Stop. Do not send. |
| `{doc_link}` is still in the body when the draft is created | Do not create the draft. |
| Gmail create is retried after an unclear result | Do not retry if a draft may already exist. Report the uncertainty. |
| Re-run of the same window | Update the same Doc when its id is known. A new draft is allowed. Nothing is sent. Old drafts are left as they are. |

## 8. What a short note must contain

When the brief has no themes, Groq still writes the Doc and the email, and the same checks apply with the empty lists.

The Doc is the header plus one sentence:

- no rows, or no rows for this app
- no rows inside the window
- rows kept, and none of them matched a catalog theme

It does not contain a theme name, a quote, an action, or a star average.

## 9. Download

The download window matches section 2. Default span is 84 days. Both stores use that span. Rows older than the start date are not written to `data/exports/reviews.csv`.

| Case | Handling |
| --- | --- |
| `PULSE_WINDOW_WEEKS` outside 8–12 | Stop. Do not write the CSV. |
| App Store RSS page is empty, or has no `im:rating` | Stop paging. Keep reviews already accepted from earlier pages and from the product page. |
| Indian RSS returns no reviews | Continue. Read the public product-page review shelf. |
| Product-page shelf is missing | Keep the RSS rows. Note that the shelf was missing. |
| A review on the product page has `reviewerName` | Write rating, title, text, and date. Do not write the name. |
| Play details page has no review text with a rating and a date | Write zero Play rows. Note `public page has no review list`. Do not call another Play URL. |
| Timeout or HTTP 5xx on one URL | Retry that URL once. Then record the error and continue with the other sources. |
| Every source URL fails | Leave any existing CSV in place. Exit with an error. |
| Fetches succeed and every review is older than the window | Write the CSV header only. The pulse run then publishes the empty-window note. |
| The same review appears in the RSS and on the product page | Keep the first. The key is store, date, rating, and collapsed text. |
