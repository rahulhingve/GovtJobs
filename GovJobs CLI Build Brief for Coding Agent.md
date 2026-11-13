# GovJobs CLI: Build Brief for Coding Agent

Prepared November 2026. Hand this whole file to the coding agent. Work phase by phase and do not skip the acceptance checks.

## 1. Goal

Build a command-line tool that runs on the owner's own PC (India, home internet) and tracks **Indian government permanent jobs open to BTech/BE graduates**: central, state, UT, PSUs, defence (Army, Navy, Air Force, Coast Guard), police and aviation. It scrapes official recruitment pages, extracts structured data, stores it locally, and lists jobs sorted **expiring soon → active → upcoming**. A website comes later by reusing the same data, so keep the data layer clean.

**Scope is all of India, not a fixed list.** The sources named later in this brief are only a test set to prove the pipeline. The finished tool must cover every government body that recruits BTech/BE holders: central, state, UT, PSU, defence, police, maritime, aviation, utilities and local bodies. Section 14 says how coverage grows and how gaps are measured.

**Who counts as eligible.** A job qualifies when a BTech/BE holder can apply and the post is permanent. Each job is tagged `btech_required`, `btech_or_equivalent` or `any_graduate`, so the owner can filter.

## 2. Hard constraints

- Total cost is ₹0. No paid APIs, no API keys of any kind, no paid hosting. Reading and judging notices is done by the coding agent that operates the CLI.
- Runs locally via CLI. No server and no cloud database.
- **Never download or host notification PDFs.** Read them in memory or in a temp folder for extraction, store only the official link.
- Every job record must have an official `source_url`. No source URL means the record is discarded.
- Respect robots.txt where present, rate-limit to at most 1 request per 2 seconds per domain, and send an honest User-Agent.
- Wrong dates are the worst failure. Prefer `needs_review` over a guess.

## 3. Stack

- Python 3.11+, managed with `uv` or `venv`.
- `httpx` for fetching, `selectolax` or `beautifulsoup4` for HTML, `playwright` (Chromium) only for pages that need JavaScript.
- `pdfplumber` for PDF text, `pytesseract` only as a last resort for scanned PDFs.
- `typer` for the CLI, `rich` for tables, `pydantic` for schemas, `pyyaml` for the registry.
- SQLite (stdlib `sqlite3`) as the store, with a `jobs.json` export.
- No LLM SDK and no API key anywhere in the code. Extraction is done by the coding agent that is operating the CLI at the time (Section 9).
- `pytest` for tests.

## 4. Repo layout

```
govjobs/
  pyproject.toml
  README.md
  EXTRACTION.md           # instructions the operating agent reads before every extraction batch
  sources.yaml            # recruiter registry (grows to cover all of India)
  config.yaml             # expiring_days=7, extract_batch_size, delay settings
  govjobs/
    cli.py                # typer app
    models.py             # pydantic Job, Source, Branch enum
    registry.py           # load/validate sources.yaml
    fetch.py              # polite fetcher (httpx + playwright fallback), robots check, per-source SSL flag, cache
    scrapers/
      base.py             # Scraper interface
      generic_list.py     # configurable CSS-selector list page scraper
      pdf_notice.py       # PDF to text with smart page selection
      custom_<org>.py     # only when generic fails
    extract.py            # builds extraction tasks, rule-based hints, validates agent output, branch normalisation
    status.py             # status from dates, computed in IST
    store.py              # SQLite, stable ids, dedupe, export
    coverage.py           # category x state coverage grid
    discover.py           # tip-off feeds, add-url, add-source helpers
    render.py             # rich tables, HTML export
  data/                   # gitignored
    jobs.db  jobs.json  cache/
    inbox/                # extraction tasks waiting for the agent
    outbox/               # agent answers waiting for ingest
    done/  rejected/      # processed and failed-validation files
  tests/
    fixtures/             # saved real HTML/PDF text per source
    test_status.py test_extract.py test_scrapers.py test_ids.py
```

## 5. Data model

`Job` fields:

- `id`: stable key = hash of org + notice\_key + post\_key. `notice_key` is the notification number if present, otherwise the normalised notice title. `post_key` is the normalised post title (lowercase, punctuation stripped). Never include URLs or dates. If a new record has the same org and notice\_key and a post\_key at least 85% similar to an existing one, update that record instead of creating a new one, so corrigenda and typo fixes do not create duplicates. `content_hash` is separate and only decides whether to re-extract.
- `org`, `post_title`, `notification_no` (optional)
- `level`: `central | state | ut | psu | defence | police | other`
- `state` (for state/UT/police), `sector` (e.g. power, oil, railways, defence, maritime, aviation)
- `qualification_type`: `btech_required | btech_or_equivalent | any_graduate`
- `btech_eligible`: bool
- `branches`: list from a strict enum: `CSE, IT, ECE, EEE, INSTRU, ME, CE, CHE, MIN, MET, PETRO, PROD, AERO, MARINE, AUTO, BIO, ALL, OTHER`. `extract.py` and the agent must map every spelling in a notice ("Computer Science & Engineering", "Comp. Sc.", "CS/IT") to these codes. `branches_raw`: the original wording from the notice. `ALL` matches any branch filter, and `--branch` is case-insensitive.
- `gate_required`: bool or null
- `additional_requirements`: list of strings for hidden hurdles, e.g. `["GATE"]`, `["CPCT/Typing"]`, `["2 yrs experience"]`, `["Physical Test"]`, `["DGCA/AME licence"]`
- `employment_type`: `permanent | contract | apprentice | trainee | deputation | unknown`
- `vacancies`: int or null; `pay_level_or_scale`: string or null
- `start_date`, `end_date`: ISO dates or null
- `description`: 2 to 4 plain sentences written by the extractor, no copied paragraphs
- `source_url` (official page), `notice_url` (official PDF link, optional)
- `first_seen`, `last_seen`, `content_hash`
- `confidence`: 0 to 1; `needs_review`: bool; `review_reason`: string

## 6. Status logic (`status.py`)

Computed at read time from today's date in IST (Asia/Kolkata), never stored:

- `expiring`: end\_date within `expiring_days` (default 7) from today
- `active`: start\_date is null or past, and end\_date in the future beyond the expiring window
- `upcoming`: start\_date in the future, or the notice announces a future opening
- `closed`: end\_date has passed
- `unknown`: no usable dates. Show after `upcoming`, flagged "dates unverified".

Default sort order: expiring (soonest end\_date first), active (soonest end\_date first), upcoming (soonest start\_date first), unknown. Closed jobs appear only with `--include-closed`.

## 7. CLI commands

```
jobs update [--source NAME] [--category C] [--limit N]   # fetch pages, create extraction tasks
jobs extract [--limit N]     # print the next tasks for the agent, with instructions
jobs ingest                  # validate and store the agent's outbox files
jobs list [--level L] [--state S] [--branch B] [--sector X]
          [--gate-only | --no-gate] [--status expiring|active|upcoming]
          [--include-any-graduate] [--all-types] [--include-closed] [--search TEXT]
jobs show ID                 # full detail + official links
jobs review                  # list needs_review items, allow confirm/edit fields
jobs sources                 # registry health, plus inbox and outbox counts
jobs coverage                # category x state grid: enabled, healthy, missing
jobs add-url URL             # create an extraction task for one notice page or PDF the tool missed
jobs add-source URL          # propose a registry entry, save after the owner confirms
jobs export [--format json|csv|html]
jobs doctor                  # check env, network, playwright install, folders
```

By default `jobs list` shows only `employment_type = permanent` posts where `qualification_type` is `btech_required` or `btech_or_equivalent`. `--include-any-graduate` adds posts open to any graduate, and `--all-types` adds contract, apprentice, trainee and deputation posts.

## 8. Source registry (`sources.yaml`)

Each entry: `name`, `category` (one of the Section 14 categories), `level`, `state` (optional), `sector`, `list_url`, `type` (`html_list | pdf_index | js_page | custom`), selectors or hints, `verify_ssl` (default `true`) and `enabled`. Set `verify_ssl: false` only for a specific official .gov.in or .nic.in site that Phase 0 proves has a broken certificate chain, and log a warning every time it is used. The agent must **find and confirm the official recruitment or careers page URL for each source** by opening it, and record it. Do not guess URLs.

Test set of 14, chosen to cover every sector and source pattern. This is only the proving ground for the pipeline; full coverage of India is Section 14:

1. UPSC: engineering services and technical exams
2. SSC: Junior Engineer notifications
3. RRB: JE and technical posts (start with one zonal board)
4. DRDO: recruitment or CEPTAM page
5. ISRO: careers page
6. BARC or another DAE unit: recruitment page
7. One GATE-based power PSU, e.g. NTPC or Power Grid
8. One oil or gas PSU, e.g. IOCL or ONGC
9. Indian Navy, Army or Air Force technical entry notices (pick one)
10. Indian Coast Guard recruitment
11. One shipyard, e.g. Cochin Shipyard or Mazagon Dock
12. One aviation body, e.g. HAL or Airports Authority of India
13. One state PSC or selection board, e.g. MPESB or MPPSC
14. One state power utility

Optional seed: the Wikipedia list of PSUs in India gives company names and sites. Use it only to populate registry candidates (not as a job source) and attribute it in the README.

## 9. Extraction rules (`extract.py`)

- **No API key, no LLM SDK.** The coding agent that is operating the CLI (Antigravity or whichever agent is running at the time) does all reading and judgment work. The tool never calls a model itself.
- **Task queue.** For every new or changed `content_hash`, `jobs update` writes one task file to `data/inbox/<task_id>.json`: source name, official URLs, the selected text, and the currently stored record if one exists (so the agent can handle corrigenda). Unchanged content creates no task.
- **Hints from plain code first.** `extract.py` pulls out what code can do reliably: DD/MM/YYYY and DD.MM.YYYY dates, and keyword hits for B.Tech, B.E., GATE, vacancies. These go into the task as hints, so the agent confirms instead of starting from nothing.
- **PDF page selection.** `pdf_notice.py` always keeps pages 1 to 4 plus every page containing any of: B.Tech, B.E., Qualification, Eligibility, Vacancy, Vacancies, Last Date, Important Dates, Pay Level, capped at 12 pages. Notices may be bilingual; use the English text when present.
- **Agent step.** `jobs extract` prints the next batch of tasks (size from `extract_batch_size`, default 5) together with the rules in `EXTRACTION.md`. The agent reads each task and writes `data/outbox/<task_id>.json` matching the Job schema, using null for anything the notice does not state. One notice with many posts produces a list of posts in one file.
- **Ingest.** `jobs ingest` validates every file in `data/outbox/`, stores valid jobs, moves those files to `data/done/`, and moves invalid ones to `data/rejected/` with the error message. The agent fixes rejected files and runs ingest again.
- **EXTRACTION.md** is written in Phase 1 and holds the schema, the branch enum, the date rules, the `needs_review` rules and two worked examples. The agent re-reads it at the start of every batch.
- **Date rules.** Indian notices write dates as DD/MM/YYYY or DD.MM.YYYY: 05/06/2026 is 5 June 2026, never 6 May. Parse day first, never infer a missing date, and treat anything ambiguous as null. A corrigendum that extends a closing date updates the existing record.
- **Branches and hurdles.** Map branch names to the enum in Section 5 and keep the original wording in `branches_raw`. Put every hidden hurdle (GATE, typing or computer test, experience, physical test, licence) into `additional_requirements`.
- **Validation at ingest (pydantic).** Reject if `end_date < start_date`, if dates are more than 2 years out, if `source_url` is missing, or if a branch is outside the enum.
- **needs\_review.** The agent sets `needs_review = true` with a reason when: end\_date is missing, BTech eligibility is unclear, text came from OCR, or its confidence is below 0.7.
- `description` is written in the agent's own words, 2 to 4 short sentences, with no copied paragraphs.
- **Not unattended.** Fetching can run on a schedule, but extraction waits until an agent session processes the inbox. `jobs sources` shows how many tasks are waiting.

## 10. Fetching rules (`fetch.py`)

- Check robots.txt once per domain per run. If disallowed, skip and log.
- Per-domain delay, retries with backoff, 30 second timeout, honest User-Agent.
- Use the per-source `verify_ssl` flag for sites with broken certificate chains. Never turn certificate checks off globally.
- Cache raw responses in `data/cache/` keyed by URL and date so development does not hammer sites.
- Try plain HTTP first. Fall back to Playwright only if the page body is empty without JavaScript.
- Log every failure with the reason (timeout, block, SSL, parse error) so `jobs sources` can show source health.

## 11. Phases and acceptance checks

**Phase 0: Reality check (do this first, about 1 hour).** Fetch every test-set page (Section 8) from the owner's PC. Report which load, which block, which need JavaScript. Save one fixture per source. *Accept when:* a table of all test-set sources with load status, SSL and JavaScript notes exists, and the owner has seen it.

**Phase 1: Skeleton.** Project setup, models, registry loader, fetcher with cache and robots check, EXTRACTION.md, inbox/outbox task flow with ingest validation, SQLite store, `status.py` with tests, `jobs doctor`. *Accept when:* tests pass and `jobs doctor` is green.

**Phase 2: First 3 sources end to end.** Scrapers, the agent-run extraction loop (update, extract, ingest), store, `jobs list` and `jobs show`. Pick one HTML list, one PDF-based notice and one JavaScript page. *Accept when:* each source yields correct post, dates and official link, checked by hand against the live page for at least 5 records.

**Phase 3: Reach the 14-source test set.** Add the rest one at a time. Add a fixture test per source. *Accept when:* `jobs update` runs the whole test set without crashing, one broken source never stops the others, and `jobs sources` shows health.

**Phase 4: Review and quality.** `jobs review`, dedupe across reruns, change detection (updated notices update the record, not duplicate it), a batch-size limit for agent extraction. *Accept when:* running `jobs update` twice in a row creates zero new extraction tasks the second time.

**Phase 5: Output.** `jobs export` to JSON, CSV and a single static HTML page with the same sort order, filters and a "verify on official site" note on every card. Optionally a Windows Task Scheduler or cron example in the README for a daily `jobs update`. *Accept when:* the HTML page opens offline and matches `jobs list`.

**Phase 6: Coverage waves (ongoing, this is how the tool reaches all of India).** Add sources in waves of about 15, in this order: central bodies and PSUs, defence, shipyards, ports and aviation, then every state and UT (PSC, selection boards, power utilities, engineering departments, police), then local bodies. Each wave needs fixtures, tests and a clean `jobs sources` report. *Accept when:* `jobs coverage` shows the grid filling and no wave breaks an existing source.

**Phase 7: Keep it alive.** Flag any source that returns zero jobs on two runs in a row, or whose selectors match nothing, and list it in `jobs sources`. Review `needs_review` items weekly. *Accept when:* a deliberately broken selector shows up in `jobs sources` within one run.

**Later (not now):** host the exported page free on Cloudflare Pages, Telegram alerts, more sources (state PSCs, police, remaining PSUs).

## 12. Rules for the agent

- Work on one source at a time. Save a real fixture and write a test before moving on.
- Never invent a URL, a date or a vacancy count. Missing means null.
- Never add API keys or an LLM SDK. All reading and judging of notices is done by you, the agent, through the inbox and outbox files.
- Keep modules small and each CLI command working at the end of every phase.
- After each phase, print a short report: what works, what is broken, what you need from the owner.
- Ask the owner only when blocked (for example a site that needs a login or captcha). Otherwise make the simplest reasonable choice and note it in the README.

## 13. Known risks

- Site layouts change, so scrapers will break. Source health reporting and fixtures are how you notice.
- Extraction depends on an agent session. Scraping can be scheduled, but the inbox waits until the agent processes it, and content hashing keeps the inbox small.
- Scanned PDFs may extract badly. Send those to `needs_review` instead of guessing.
- Some sites use captchas or block automation. Mark them `enabled: false` with a note rather than working around protections.
- Always show users the official link and a reminder to verify details there before applying.

## 14. Coverage plan: all govt BTech jobs across India

The test set in Section 8 only proves the pipeline. The final scope is every government body that recruits BTech/BE holders, tracked by a coverage grid, not by a fixed list.

| Category | What to cover |
| --- | --- |
| Central exams and boards | UPSC, SSC, every RRB zone, DRDO, ISRO, BARC and other DAE units, CSIR and other central research labs |
| PSUs and CPSEs | Every company on the Wikipedia PSU list and the official government CPSE list, each through its own careers page |
| Banks and financial PSUs | Specialist and IT officer recruitment where BTech/BE holders are eligible |
| Defence and paramilitary | Army, Navy, Air Force technical entries, Coast Guard, central armed police engineering posts |
| Maritime | Shipyards, major ports, shipping bodies |
| Aviation | AAI, HAL, aviation regulators and airport companies |
| State PSCs and selection boards | All 28 states and 8 UTs |
| State power utilities | Generation, transmission and distribution companies in each state |
| State engineering departments | PWD, irrigation and water resources, public health engineering, rural development |
| State police technical posts | Each state's police recruitment board |
| Local and special bodies | Municipal corporations, development authorities, metro rail companies, highway and infrastructure authorities |

Rules for reaching full coverage:

- **Official first.** Store a job only when it resolves to the recruiter's own official site (.gov.in, .nic.in, .ac.in or the company's own domain). That link is `source_url`.
- **Seed the registry.** Use the Wikipedia PSU list and official lists the agent finds (CPSEs, state PSCs, boards, utilities). Anything without a working official page is added with `enabled: false` and a note, never silently skipped.
- **Tip-off feeds.** Employment News, the NCS portal and existing job aggregators may be used only to notice notices missing from the registry. Resolve each tip to its official page; if that fails, drop it. Never copy or republish aggregator text.
- **Manual escape hatch.** `jobs add-url URL` sends any single notice page or PDF through the same pipeline, so the owner can always add a missed job by hand.
- **Assisted onboarding.** `jobs add-source URL` fetches a page, proposes the source type and selectors, shows a sample parse, and writes to `sources.yaml` only after the owner confirms.
- **Measure it.** `jobs coverage` prints a grid of category by state/UT showing enabled, healthy and missing sources. The target is every cell filled wherever that body exists.
- **One record per job.** The same notice seen through several routes merges into one record by the stable `id`, preferring the official source.
- **Honest limits.** Report coverage instead of claiming it. Overseas and world-level jobs are out of scope.

The owner's goal is every government BTech job in India. The coverage grid measures how close the tool is, and Phase 6 does not end until the grid has no avoidable gaps.
