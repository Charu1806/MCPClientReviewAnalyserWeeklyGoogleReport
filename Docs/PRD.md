# PRD: Groww Weekly Review Pulse

**Product:** Weekly pulse that turns public App Store and Play Store reviews of the Groww app into a one-page note, a Google Doc, and a Gmail draft.  
**App:** Groww Stocks, Mutual Fund, IPO. Public reviews only.  
**Audience:** Product, growth, support, and leadership. Class demo.  
**Status:** Draft for build.  
**Last updated:** 28 September 2026.

## 1. Problem

Store reviews for Groww already say what is working and what is stuck: onboarding and KYC, SIP and payments, login, portfolio and statements, redemptions and trading. The raw list is too long to scan in a weekly meeting. People need a one-page pulse: the themes that dominate, the words users actually used, and three next steps grounded in those themes.

## 2. Goal

Ship an agent workflow that:

- Reads a public export of recent App Store and Play Store reviews for this app.
- Clusters those reviews into at most five themes and selects the quotes and counts for the note.
- Uses **Groq** to write the one-page note and the email from that brief.
- Publishes the note with a **Google Docs MCP** server only after that draft passes the checks below.
- Creates a **Gmail draft** (not a sent message) to the operator or an alias, with the note or a clear link to the Doc.

Success is a run a classmate can repeat: public reviews in, one scannable Doc out, one Gmail draft that points at it. Docs and Gmail are reached through MCP tools. The build does not ship its own Google OAuth client or REST client as the integration path.

## 3. Who it is for

| User | Need |
| --- | --- |
| Product / Growth | See which fixes and improvements the last 8–12 weeks of reviews actually support |
| Support | Align replies with the wording users use in the stores |
| Leadership | A one-page health check without reading the raw review list |
| Class reviewer | A visible path from public reviews to a Groq-written note, then a Doc and a Gmail draft via MCP |

## 4. Scope

### 4.1 App

One app, both stores:

| Store | Listing | Public id |
| --- | --- | --- |
| Google Play | Groww Stocks, Mutual Fund, IPO | `com.nextbillion.groww` |
| Apple App Store | Groww Stocks, Mutual Fund, IPO | `1404871703` |

Reviews of other brokers or apps are out.

### 4.2 In scope

- Download public App Store and Play reviews into `data/exports/reviews.csv`, then import that file.
- The download window is the last **12 weeks (84 days)** by default, ending on the run date, for both stores. `PULSE_WINDOW_WEEKS` may set 8–12 weeks (56–84 days).
- Fields used when the export provides them: rating, title, text, date, store. Ignore reviewer name and any other identity field.
- Cluster into **at most 5 themes**.
- Select the top 3 themes, the counts, and 3 verbatim quotes in code.
- Call Groq to write the weekly note and the email from that brief.
- Create or update one Google Doc with the Groq-written note.
- Create one Gmail draft to the operator or a configured alias from the Groq-written email.

### 4.3 Out of scope

- Logging into App Store Connect or Google Play Console.
- Scraping behind a store login, or automation that violates store terms.
- Replying to reviewers, or posting anything to the stores.
- Sending the email. The artifact is a draft.
- A custom Google OAuth app and handwritten Docs or Gmail REST calls as the way the product talks to Google.
- Investment advice, return comparisons, or recommendations of schemes.
- Storing or printing PII: usernames, emails, phone numbers, device IDs, folio numbers, PAN, or other reviewer identifiers.
- Reviews older than the chosen 8–12 week window, except a one-line count of how many were dropped as out of window.

## 5. End-to-end flow

```
Public App Store and Play pages
    → Download reviews inside the last 12 weeks (84 days)
    → data/exports/reviews.csv
    → Keep rating, title, text, date, store
    → Drop or redact PII
    → Cluster into ≤ 5 themes
    → Rank themes; keep the top 3 for the note
    → Pick 3 verbatim quotes (code, not the model)
    → Groq writes the Doc body and the email from that brief
    → Check word count, quotes, PII, and advice rules
    → Google Docs MCP: create or update the one-page pulse
    → Fill the Doc link into the email
    → Gmail MCP: create a draft to self / alias
```

Groq runs before either Google call. Docs and Gmail receive the checked text. They do not write the pulse themselves.

One run produces one Doc and one draft for one week window. Re-running the same window updates the same Doc when the Docs tool supports update; otherwise it creates a new Doc and the draft links to that new Doc. It does not send mail.

## 6. Review input

`python -m src.download` writes `data/exports/reviews.csv` before the pulse run. `python -m src.run` reads that file and does not fetch again. Neither command logs into a store.

The download window is the same for the App Store and Play. It ends on the run date and starts 12 weeks (84 days) earlier. Both ends are inclusive. For a run date of 28 September 2026 the file keeps 6 July 2026 through 28 September 2026. `PULSE_WINDOW_WEEKS` may be 8, 9, 10, 11, or 12. Eight weeks is 56 days. Reviews older than the start date are not written.

Columns, and nothing else: `store`, `rating`, `date`, `title`, `text`, `app_id`. Dates are `YYYY-MM-DD`. Reviewer names are not stored.

| Store | Public source | What is saved |
| --- | --- | --- |
| App Store `1404871703` | Apple’s public iTunes `userReviewsRow` feed for India (paginated, most recent), plus Customer Reviews RSS and the public see-all reviews page as backups | Rows with `store=app_store` inside the window. Reviewer names are dropped. |
| Play `com.nextbillion.groww` | Play’s public `batchexecute` reviews RPC (`UsvDTd`, paginated, newest first) for India, plus the public details page as a backup | Rows with `store=play` inside the window. Reviewer names are dropped. |

Play Console and App Store Connect are out. No publisher login. Download stops paging once review dates fall before the window start. If one store fails, the other is still saved. Rows are not invented.

After the file exists, the pulse run:

1. Reads `data/exports/reviews.csv`.
2. Uses both stores when both are present. A missing store is named in the note.
3. Keeps rows inside the same window. If the file’s own dates span less than 8 weeks, the note states the actual range and the count.
4. Drops empty text and duplicate rows (same store, date, rating, and text).
5. Requires `store`, `rating`, `date`, and `text`. `title` is included when present.

## 7. Themes

At most five themes. Use this catalog, and only a theme that has at least one review in the window:

| Theme | What belongs here |
| --- | --- |
| Onboarding and KYC | Registration, eKYC, demat or account opening, paperwork, first-time setup |
| SIP and payments | SIP start or stop, lump sum, UPI, net banking, mandate, payment failure, stock or MF purchase |
| Login and access | MPIN, biometric, OTP, password, lockout |
| Portfolio and statements | Dashboard, holdings, orders, NAV, statements, capital-gains documents |
| Redemption and service | Withdrawal, redemption, sell or exit, bank-detail change, contact update, other service requests |

Assignment rules:

1. Each review gets one primary theme, chosen from the text and title. Rating alone never assigns a theme.
2. A review that fits none of the five is counted as unthemed. Unthemed is not a sixth theme and does not appear in the top 3. The header may say how many reviews were unthemed.
3. If fewer than three catalog themes occur, the note highlights only the themes that occur and says the shortfall. It does not pad with empty themes.
4. Rank by review count in the window. Break ties by lower average star rating, then by the more recent median review date.
5. The written pulse highlights the **top 3** after that ranking. The Doc may include a single compact line listing the other themes and their counts. That line is not a second essay.

## 8. The weekly note

The note is one page and scannable. The body — top themes, quotes, and actions — is **250 words or fewer**. A short header sits outside that count.

### 8.1 Header

- Title: `Groww — Weekly Review Pulse — week ending <YYYY-MM-DD>`
- Window start and end, review count kept, count by store, and the run date.
- One line if a store or a quote was omitted, and why.

### 8.2 Top themes

For each of the top 3:

- Theme name.
- How many reviews, and the average star rating to one decimal.
- One sentence on what those reviews are about, using only patterns present in the reviews. No invented causes, no invented percentages beyond the counts above.

### 8.3 Quotes

Exactly three quotes when three safe quotes exist. Otherwise fewer, with the shortfall stated.

1. Verbatim snippets from review title or text. No paraphrases, no merged reviews, no words the reviewer did not write.
2. Prefer one quote from each top theme. If a top theme has no safe quote, take the next safest quote from the remaining reviews in the top 3.
3. A quote is one or two sentences, or a shorter snippet if the review is long. Ellipsis may mark a cut. The words that remain are unchanged.
4. Each quote shows store, star rating, and review date. No reviewer name.
5. Strip or skip any snippet that contains a username, email, phone number, device id, folio, PAN, or similar identifier. If redaction would change the wording, skip that review and pick another. Do not rewrite the sentence to hide the identifier.

### 8.4 Action ideas

Exactly three. Each action:

- Names the theme it comes from (one of the top 3).
- Is a concrete next step a product, growth, or support owner can take (fix, clarify in the app, or change a support reply).
- Is justified by the reviews in that theme. It does not claim a metric the export does not contain.
- Is not investment advice and does not tell users which scheme to buy.

If fewer than three themes exist, write one action per theme that exists and state that the set is short. Do not invent a third theme to fill the list.

## 9. Groq writes the Doc and the email

Groq is the only writer for the note and the email. Same provider as Milestone 1: chat completions on Groq, model `qwen/qwen3.8-27b` unless `GROQ_MODEL` is set. No other chat provider.

The model does not see reviewer names or other identity fields. It receives a brief built in code:

- Header facts: title, window, run date, review counts, counts by store, unthemed count, and any store that is missing.
- Top 3 themes with review count and average star rating.
- The three verbatim quotes, each already tagged with store, rating, and date.
- The theme catalog names, so actions stay inside the top 3.

Groq returns two texts:

1. **Doc body** matching section 8: theme sentences, the three quotes copied unchanged, and three action ideas. Body ≤ 250 words, header not included in that count.
2. **Email**: subject equal to the Doc title, and a short body that contains the note, a pointer line, or both. The pointer uses the literal placeholder `{doc_link}` until the Doc exists.

Checks run on the Groq output before any MCP call:

1. Each selected quote appears in the Doc body character for character. Quotes are not paraphrased.
2. Counts and theme names match the brief. The model does not add a fourth highlighted theme or a new number.
3. Doc body is 250 words or fewer, excluding the header.
4. No email address, phone number, or other reviewer identifier in either text. The operator’s own recipient address is not part of the Groq prompt.
5. No buy, sell, or scheme recommendation.

If a check fails, call Groq once more with the failed check named. If the second draft still fails, stop. Do not publish a failed draft, and do not replace it with hand-written prose.

`GROQ_API_KEY` is required. If it is missing, or Groq errors after one retry, stop before Docs and Gmail.

## 10. Google Docs and Gmail via MCP

Docs and Gmail are MCP-first.

1. A Google Docs MCP tool creates or updates the pulse document. The Doc body is the checked Groq text from section 9.
2. Replace `{doc_link}` in the Groq email with the Doc URL. A Gmail MCP tool then creates a draft. Recipient: the operator’s own address or an alias set in configuration. Subject and body stay the Groq text aside from that link.
3. The draft is left in Drafts. The workflow does not call a send tool.
4. Credentials, tokens, and consent stay inside the MCP server’s own auth. This repo does not implement a Google OAuth consent screen or a REST client for Docs or Gmail.
5. If an MCP call fails, stop and report the error. Do not fall back to a handwritten Google API integration to finish the run.

The operator connects the Docs and Gmail MCP servers in the environment before the run. The PRD does not require a particular vendor package, only that the tools used are MCP tools for those two products.

## 11. Privacy

- The brief sent to Groq, the Doc, the draft, logs, and any saved summary contain no reviewer PII.
- Do not write the export’s author, nickname, or profile fields into any artifact.
- Quotes are anonymous: store, rating, and date only.
- Configuration may store the operator’s own email or alias, because that is the draft recipient, not a reviewer.
- Do not persist raw exports inside the Doc or the email. The export stays a local input.

## 12. Non-functional requirements

- **One page:** A stakeholder can read the Doc in a few minutes. Body ≤ 250 words.
- **Traceable:** Every quote can be found in the input export by store, date, rating, and exact snippet.
- **No invention:** Missing stores, missing themes, or missing quotes are stated. They are not filled in.
- **Stable brief:** The same export and the same window produce the same theme ranking, counts, and three quote strings. Groq wording can differ between runs. Quotes and counts cannot.
- **Groq before Google:** Docs and Gmail are called only after the Groq draft passes section 9.
- **MCP-only Google path:** Docs and Gmail calls go through MCP tools.
- **Facts, not advice:** The note describes review themes. It does not recommend funds.

## 13. Deliverables

| Item | Description |
| --- | --- |
| Weekly pulse Doc | Groq-written Google Doc with header, top 3 themes, 3 quotes, 3 actions. Body ≤ 250 words. |
| Gmail draft | Groq-written draft to the operator or alias containing the note or a clear link to the Doc. Not sent. |
| Review export | `data/exports/reviews.csv`, downloaded from the public App Store and Play pages for the last 12 weeks (or the configured 8–12). No reviewer names. |
| Run notes | Window, counts by store, theme counts, the Groq model used, and which MCP tools created the Doc and the draft. |
| This PRD | Product scope the build follows. |

## 14. Acceptance criteria

- `python -m src.download` writes `data/exports/reviews.csv` for `1404871703` and `com.nextbillion.groww`. The default window is 12 weeks (84 days) ending on the run date, for both stores.
- The CSV has no reviewer-name column. Play rows are present only when the public Play page included them.
- The pulse input is that file, dated inside the same 8–12 week window (or a shorter span when the public pages contain less, and the note says so).
- Clustering uses at most the five themes in section 7. The Doc highlights three, or fewer if fewer occur.
- The three quotes are verbatim, anonymous, and present in the export. No quote contains an email, phone number, or other identifier.
- The three actions each name a top theme and follow from reviews in that theme.
- The Doc body and the email body were produced by Groq (`qwen/qwen3.8-27b` unless `GROQ_MODEL` is set) from the code-built brief.
- A failed Groq check does not create a Doc or a draft.
- The Doc body is 250 words or fewer, excluding the header.
- The Doc was created or updated by a Google Docs MCP tool, using the checked Groq text.
- A Gmail MCP tool created one draft to the operator or alias. The mailbox Sent folder has no new message from this run.
- The repo contains no Google OAuth client and no Docs or Gmail REST client used to publish the pulse.
- A second run on the same export does not change the theme ranking, the counts, or the three quote strings.

## 15. Known limits

- Apple’s Customer Reviews RSS can return no entries. The downloader then uses iTunes `userReviewsRow` and the public see-all page.
- Play reviews come from the public `batchexecute` feed. A store missing from the file is named in the header.
- Theme labels are a fixed catalog. A new topic in the reviews shows up as unthemed until this PRD adds a theme and drops another so the cap stays at five.
- Average rating is the average of stars on the clustered reviews, not a store-wide score.
- Theme sentences and action wording come from Groq, so two runs can phrase the same brief differently. Quotes and counts stay fixed.
- The pulse is a reading of reviews. It is not a bug tracker, a support macro, or investment advice.
- MCP auth is environment-specific. A run without the Docs or Gmail server connected fails rather than switching to a direct Google API client.
