# GovJobs Phase 2: Fix, Focus on PSUs, Improve UI (prompt for the coding agent)

You are continuing an existing Python CLI project called `govjobs`. Read `AGENTS.md`, `README.md`, `EXTRACTION.md` and `GovJobs CLI Build Brief for Coding Agent.md` before you change anything.

Work through the tasks below **in order**. After every task: run `python -m pytest -q`, fix failures, then give a short report (what changed, what you tested, what is still open). Do not start the next task until tests pass. Do not rewrite the project; make targeted changes.

Review date: 13/11/2026 (IST). The owner is in India and the main focus is **government PSUs: Maharatna, Navratna, Miniratna and other CPSEs**, then everything else in the brief.

---

## 0. Ground rules

- Cost stays ₹0. No API keys, no LLM SDKs, no paid services. All reading and judging of notices is done by the AI agent operating the CLI, through `data/inbox` and `data/outbox`.
- Never download or save notice PDFs permanently. Read them in memory and store only the official link.
- Store dates as ISO (`YYYY-MM-DD`) in the database and `jobs.json`. **Show every date to a human as `DD/MM/YYYY`**: CLI tables, `jobs show`, CSV, HTML.
- "Today" is always computed in IST (`Asia/Kolkata`). No UTC "today" anywhere.
- Python 3.11+ (the owner runs a newer Python, so avoid anything version-fragile). Must work on Windows, macOS and Linux. UTF-8 for all files.
- Never invent a URL, date, vacancy count or ratna status. Missing means null.
- Respect robots.txt, rate limits and honest User-Agent for every request, including PDF downloads.
- Keep existing tests passing. Add tests for everything you change.

---

## 1. Review findings (verified on the uploaded code)

| # | Problem | Evidence | Fix in task |
|---|---|---|---|
| 1 | Expired jobs are listed in exports | `jobs.json` holds DRDO (closed 14/06/2026) and SSC JE (closed 18/04/2026); `export_csv` and `export_html` are called with `get_all_jobs()`, so closed jobs are exported | 1 |
| 2 | Dates shown as `2026-11-18` | `cli.py` list/show, `render.py` CSV and HTML print ISO strings | 1 |
| 3 | HTML snapshot goes stale and is unsorted | Status is baked in at export time; cards are in database order, not expiring-first | 1, 6 |
| 4 | Inbox is full of non-job noise | 46 tasks, only about 5 are real recruitment ads. Others: admit cards, interview letters, results, FAQs, cut-offs, table headers (`# Status`, `Name of the post`), menu items (`Select Location`, `Archived Items`, `Current Job Openings`) | 2 |
| 4b | Tasks are created for old notices | PowerGrid notices from 2021 to 2025 became tasks | 2 |
| 5 | Processed tasks stay in the inbox | `d4ca152a47d9aa5a`, `ea3f4e16b826e60e`, `fef5e2784b3954de` exist in both `data/inbox` and `data/done`, so `jobs extract` shows them again | 2 |
| 6 | Agent-supplied IDs break the stable-ID rule | Stored ids are `ssc_je_exam_2026`, `powergrid_et_ee_2026`. `generate_job_id()` exists but is never enforced | 2 |
| 7 | `EXTRACTION.md` examples contain invented data | Fake PDF links (`Advt_ET_2026.pdf`, `AE_2026_Notice.pdf`) and invented MPPSC details that an agent may copy | 2 |
| 8 | `config.yaml` is ignored | `PoliteFetcher()` and `expiring_days` use hardcoded defaults; `jobs extract` hardcodes 5 | 2 |
| 9 | PDFs are re-downloaded and hammer sites | `update` downloads up to 15 PDFs per source on every run, with no delay, robots check or cache; `check_robots` always uses `verify=False` | 2 |
| 10 | No source health | Only 4 of 14 sources (POWERGRID, SSC, Cochin Shipyard, DRDO) produced tasks; UPSC, ISRO, BARC, ONGC, AAI, Navy, Coast Guard, MPPSC, PSPCL and RRB gave nothing and nothing says why. `jobs sources` only lists the registry | 3 |
| 11 | HTML is not escaped | `render.py` writes job fields straight into HTML; `href` is not checked | 6 |
| 12 | Coverage logic is wrong | `coverage.py` counts jobs with `j.sector in cat.lower()`, which mostly matches nothing | 4 |
| 13 | Date check uses UTC | `models.py` uses `datetime.now(timezone.utc)` for the 2-year check | 1 |
| 14 | Repo hygiene | `__pycache__`, `.pytest_cache`, `egg-info` and about 900 KB of cache are in the project; no `.gitignore` | 7 |

---

## 2. Task 1: Expired jobs and DD/MM/YYYY (P0)

1. Add `fmt_date(iso: str | None) -> str` (returns `DD/MM/YYYY`, or `-` when empty) in a new `govjobs/utils.py`, plus `days_left(job, today)`.
2. Use it in: `jobs list`, `jobs show`, `jobs review`, CSV export, HTML export. Add a "Days left" column to `jobs list`. Keep ISO in `jobs.json`, and add `end_date_display` and `start_date_display` fields there.
3. `jobs export`: exclude `closed` jobs by default for CSV, HTML and JSON. Add `--include-closed`. Always write closed jobs to `data/archive.json` so nothing is lost.
4. `jobs list` already hides closed by default; keep that and add a one-line footer: `N closed jobs hidden (use --include-closed)`.
5. Replace UTC "today" in `models.py` validators with IST.
6. `Job` validator should also accept day-first `DD/MM/YYYY`, `DD.MM.YYYY`, `DD-MM-YYYY` input from agents and convert to ISO. Month-first must never be assumed. Anything else is rejected with a clear message.

**Acceptance:** exports contain no job with `end_date` before today; a unit test with a fake "today" proves it; `jobs list` shows `18/11/2026`, never `2026-11-18`.

---

## 3. Task 2: Pipeline hygiene (P0)

**2a. Notice classifier (before creating a task).** New `govjobs/classify.py`:
- Skip table header rows, rows whose title is shorter than 8 characters or starts with `#`, and obvious menu items (`Select Location`, `Archived Items`, `Current Job Openings`, `Name of the post`, `FAQs`, `Status`, `Home`, `Contact`).
- Negative titles (skip): admit card, hall ticket, call letter, interview letter, result, answer key, cut-off/cutoff, city of examination, document verification, scorecard, candidate response, application count/received, roll number, helpdesk, FAQ, tender, quotation.
- Positive titles (create task): advertisement, advt, recruitment, vacancy/vacancies, notification, engagement, trainee, GATE, walk-in, executive, engineer, officer, scientist, apprentice.
- Corrigendum, extension, revised dates, addendum: **do** create a task but set `kind: "update"` and attach the matching existing record when found (use the existing 85% matcher).
- Everything is logged to `data/logs/classify.csv` (source, title, decision, reason) so the owner can tune rules.
- Make word lists configurable in `config.yaml`.

**2b. Expiry pre-filter.** If the notice text contains dates and **all** of them are before today (IST), mark the task `likely_expired: true` and do not create it unless `jobs update --include-old` is used. Count how many were skipped and print it.

**2c. Inbox lifecycle.**
- `jobs ingest` must remove (move) `data/inbox/<task_id>.json` into `data/done/tasks/` after a task is processed or skipped.
- `jobs extract` must ignore tasks that already have a file in `outbox`, `done` or `rejected`.
- `jobs update` must treat hashes in `outbox`, `done`, `rejected` and `done/tasks` as known.
- `jobs extract` prints tasks ordered: updates first, then likely-active, then the rest. Print the instructions pointer (`Read EXTRACTION.md`) once at the top and show one compact task at a time.
- Skip protocol: if the outbox file is `{"skip": true, "reason": "..."}`, ingest closes the task without storing a job.
- Add `jobs clean-inbox` to remove stale tasks that are already processed (run it once now to clear the 3 duplicates).

**2d. Agent schema and stable IDs.**
- Create an `AgentJob` model (what the agent must provide): `org, post_title, notification_no, qualification_type, btech_eligible, branches, branches_raw, gate_required, additional_requirements, employment_type, vacancies, pay_level_or_scale, start_date, end_date, description, confidence, needs_review, review_reason`. Everything else is filled by `ingest` from the task file.
- Task files must now include `notice_title` (the list-item title) and `category`.
- `ingest` always overwrites `id` with `generate_job_id(org, notification_no or notice_title, post_title)`, and sets `first_seen`, `last_seen`, `content_hash`, `source_url`, `notice_url`, `level`, `sector`, `state`, `category` from the task. Never trust agent-supplied values for these.
- Run a one-off migration that rewrites the 5 existing jobs to hash ids without creating duplicates.

**2e. EXTRACTION.md.** Remove the two fabricated worked examples (fake PDFs, invented MPPSC notice). Replace them with two examples clearly labelled `ILLUSTRATIVE ONLY, DO NOT COPY` that use `https://example.invalid/...` links. Document the skip protocol, `DD/MM/YYYY` input and that `id`, `first_seen`, `last_seen`, `content_hash`, URLs are not the agent's job.

**2f. Config.** Add `govjobs/config.py` that loads `config.yaml` once. Wire in: `expiring_days`, `extract_batch_size` (default for `jobs extract`), delay, timeout, User-Agent, `data_dir`, date format, classifier word lists. Remove hardcoded copies.

**2g. Polite PDFs.**
- All PDF downloads go through the same robots check, per-domain delay and retry logic as pages.
- Cache extracted PDF text by URL hash under `data/cache/pdf/` (text only, never the PDF).
- `check_robots` must honour the source's `verify_ssl` flag instead of always using `verify=False`.
- Default limit of 15 items per source becomes `max_items_per_source` in config; process newest first when dates are available.

**Acceptance:** run `jobs update` twice; the second run creates zero tasks. A fixture-based test shows the classifier drops admit cards, results and header rows from `ssc.html`, `drdo_rac.html`, `powergrid.html` and `cochin_shipyard.html`, and keeps the real advertisements. Inbox no longer contains tasks that are in done.

---

## 4. Task 3: Source health (P1)

1. Add a `source_runs` table: `source_name, run_at, fetch_ok, http_status, used_playwright, items_parsed, items_classified_job, tasks_created, error`.
2. `jobs update` writes one row per source per run.
3. `jobs sources` shows, per source: last run time (DD/MM/YYYY HH:MM IST), last result (OK / FAILED / ZERO ITEMS), items parsed, last error, days since a task was last created. Flag in red: failed twice in a row, or zero items twice in a row, or selectors matched nothing.
4. Investigate the 10 silent sources (UPSC, ISRO, BARC, ONGC, AAI, Indian Navy, Coast Guard, MPPSC, PSPCL, RRB Chennai). For each, run it, record the real cause (blocked, timeout, SSL, JS needed, wrong URL, selector mismatch, no recent notices), fix what is fixable, and write the findings to `docs/source_report.md` as a table. Do not guess URLs; open each page and confirm.
5. Where a fixture parses fine but no task was created, explain why (for example everything classified as non-job, or all hashes known).

**Acceptance:** `jobs sources` prints a health line for every source; `docs/source_report.md` exists with a cause for each of the 10 sources.

---

## 5. Task 4: PSU-first registry (P1, the main focus)

Goal: every Maharatna, Navratna, Miniratna (Category I and II) and other CPSE has a verified careers source, and the owner can see at a glance which PSUs are covered.

**4a. PSU master list.** New `jobs psu-sync` command that:
- Fetches `https://en.wikipedia.org/wiki/List_of_public_sector_undertakings_in_India` (through the polite fetcher), parses the main table (`PSU | Inc. | Ministry | Headquarters | Sector | Group | Ratna status`) and writes `psu_registry.yaml`.
- Fields per PSU: `name`, `aliases` (short names like NTPC, BHEL), `ratna_class` (`maharatna | navratna | miniratna_1 | miniratna_2 | none`), `schedule` (A/B/C/D if known), `ministry`, `sector`, `hq`, `website`, `careers_url`, `uses_gate` (`true | false | null`), `operating_status` (`active | under_construction | dormant`), `verified` (bool), `ratna_source_url`, `verified_on`.
- Normalise the page's inconsistent ratna labels, for example: `Miniratna Category - I`, `Miniratna Category - l` (lowercase L), `Miniratna Category-I`, `Mini Ratna Company Category -1`, `Miniratna Category II`, `Navratna Category - I`, `Navratna Category`. Use a regex, and put anything unrecognised in a `needs_review` list printed at the end.
- Mark rows with Group `Enterprises Under Construction` or `Dormant company` accordingly.
- Do **not** import companies from the page's lower tables (disinvested, privatised, liquidated, under liquidation).
- Manual corrections live in `psu_overrides.yaml` and always win over scraped values.

**4b. Ratna status must be verified.** The Wikipedia page is stale in places. As fetched on 13/11/2026 its main table lists as Maharatna: BHEL, BPCL, Coal India, GAIL, HAL, IOCL, NTPC, ONGC, Oil India, Power Grid, SAIL; and as Navratna: BEL, CONCOR (Category I), Engineers India, MIDHANI, NHPC, NALCO, NBCC, NLC India, NMDC, Numaligarh Refinery, PFC, Shipping Corporation of India, RINL. Its own disinvestment table lists HPCL and REC as acquired by ONGC and PFC, yet both still recruit under their own names. So:
- Treat Wikipedia as a **seed only**. Verify the current ratna list against the Department of Public Enterprises (DPE) official site, record `ratna_source_url` and `verified_on`, and fix `psu_overrides.yaml`.
- Add important PSUs the page misses or hides (check at least HPCL and REC) with `verified: true` only after you open an official page.
- Never mark a ratna status as verified from memory.

**4c. Careers sources for PSUs.** Work in waves: Maharatna, then Navratna, then Miniratna I, Miniratna II, then Schedule A, B, C, D CPSEs. For each PSU:
- Open the company website, find the official careers/recruitment page, record `careers_url`, and create a `sources.yaml` entry (category `PSUs and CPSEs`, `level: psu`, `priority: 1` for ratna companies). Confirm it loads and parses before enabling it.
- If a PSU recruits only through GATE or an external portal, note it in `uses_gate` or `notes` and still link the official page.
- If no working official page is found, keep `careers_url: null` and `enabled: false` with a note. Never skip silently.
- Add a fixture and a parser test per new source type (not per company when the same parser works).

**4d. Job fields and filters.**
- Add to `Job`: `category`, `psu_name`, `psu_class`, `ministry`. Add an automatic migration (`ALTER TABLE ... ADD COLUMN`, wrapped in try/except) so the existing `jobs.db` keeps working.
- `ingest` fills `psu_class` and `ministry` by matching the job's org to `psu_registry.yaml` aliases.
- `jobs list --psu-class maharatna|navratna|miniratna|any` and `--psu NAME`.

**4e. PSU coverage view.** `jobs coverage --psu` prints one row per PSU: name, ratna class, careers URL found (yes/no), source enabled and healthy, jobs found, last job end date (DD/MM/YYYY). Sorted Maharatna first. End with totals, for example `Maharatna 10 of 11 covered`. Fix the old coverage logic (finding 12) by counting jobs by the new `category` field.

**Acceptance:** `psu_registry.yaml` exists with normalised classes and a printed review list; `jobs coverage --psu` runs; at least all Maharatna and Navratna companies have either a working enabled source or a documented reason why not.

---

## 6. Task 5: Tip-off discovery from job-news sites (P2)

Use job-news sites **only to notice notices we missed**. They are never a source of stored data.

Sites to start with (exact domains; many look-alike clone domains exist, so pin these and never follow similar-looking ones):
`sarkariresult.com`, `testbook.com` (government jobs section), `indgovtjobs.in`, `freejobalert.com`, `employmentnews.gov.in` (official), `ncs.gov.in` (official). The owner also mentioned a site called "kaam"; ask the owner for its exact URL before adding it.

Implementation:
- `tipoff_sources.yaml` (provided) lists each site with its listing URL, `kind` (`aggregator` or `official_feed`), `enabled`, `verified_domain`.
- New `jobs tipoff` command: fetch each listing page politely, parse headline and link, keep only items that look like engineering or PSU recruitment (engineering keywords, or names/aliases from `psu_registry.yaml`), drop anything already known, and write `data/tips/<tip_id>.json` with: title, tip site, tip URL, matched PSU (if any), `status: new`.
- **Do not store or copy the aggregator's own text.** Only the headline and the link.
- Resolution step (done by the AI agent): open the tip, find the link to the **official** notice (recruiter's own domain: `.gov.in`, `.nic.in`, `.ac.in`, or the PSU's own site), then run `jobs add-url <official link>`. If no official link can be found, mark the tip `dropped`. Add `jobs tips` to list the queue and `jobs tip-resolve <id> --url <official> | --drop`.
- A job is only ever stored when its `source_url` is on an official recruiter domain. Add a validator that rejects aggregator domains from the `tipoff_sources.yaml` blocklist.
- `jobs coverage --psu` gets an extra section: "Tips that matched a PSU with no registered source". This is how the registry grows.
- Purge tips older than 30 days. Respect each site's robots.txt and terms; if a site disallows fetching, disable it and say so.

**Acceptance:** `jobs tipoff` runs against fixtures in tests (save one fixture page per site type), produces tips, and a test shows an aggregator URL is rejected as a `source_url`.

---

## 7. Task 6: HTML UI redesign (P2)

Rebuild `data/jobs.html` as a single offline file (no external requests, no CDN fonts). Current output is a plain card list with stale status and an incomplete branch dropdown.

Requirements:
- Embed all jobs as JSON in a `<script type="application/json">` and render in the browser. **Compute status in JavaScript from the dates and today's IST date**, so an old snapshot never shows an expired job as active. Closed jobs are hidden by default behind a toggle.
- Header: title, totals (`Expiring N | Active N | Upcoming N`), "Last updated DD/MM/YYYY HH:MM IST".
- Status tabs with counts: **Expiring soon**, **Active**, **Upcoming**, **Unverified dates**, **All**. Default order: expiring (soonest first), then active, then upcoming.
- Filters (sticky bar, mobile friendly): search box; PSU class chips (Maharatna, Navratna, Miniratna, Other PSU, Non-PSU); level; state; sector; **all** branch codes from the enum (multi-select); GATE only / no GATE; employment type; sort (closing soon, newest, most vacancies).
- Card layout: organisation + PSU badge, post title, a coloured "N days left" chip (red at 3 days or fewer, orange at 7 or fewer), vacancies, branches, GATE tag, additional requirements, pay scale, `Start DD/MM/YYYY` and `Last date DD/MM/YYYY`, two buttons: "Official page" and "Official notice (PDF)" when present, and the "verify on the official portal" note.
- `needs_review` jobs show a "Dates unverified" badge and never sit in Active.
- Accessible: semantic HTML, keyboard focus, contrast that passes WCAG AA, `prefers-color-scheme` light and dark themes, print stylesheet.
- Security: HTML-escape every field in Python and in JavaScript (use `textContent`); only allow `http` and `https` links, with `rel="noopener noreferrer"`.
- Performance: handle 1,000+ jobs smoothly (render in chunks of 50 with a "Show more" button).
- Also add `jobs export --format html --include-closed` for an archive view.

**Acceptance:** open the file in a browser with a fixture of 30 mixed jobs; expiring jobs appear first; filters and counts work; no console errors; no network requests; a test checks that `<script>` in a job description does not execute (is escaped).

---

## 8. Task 7: Agent files, docs, tests, hygiene (P3)

1. `AGENTS.md` (provided) is the single instruction file for any AI agent. Create `CLAUDE.md` and `GEMINI.md` containing one line: `Read AGENTS.md in this folder and follow it.` Keep all three in sync if AGENTS.md changes.
2. Keep `README.md` (provided) accurate: update the command list whenever you add or rename a command.
3. Add `.gitignore`: `.venv/`, `venv/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`, `data/` (but keep `data/.gitkeep`), `.env`.
4. Delete committed junk (`__pycache__`, `.pytest_cache`, `egg-info`, old cache JSON) from the working tree.
5. Add tests: ingest (valid, rejected, skip, id override), exports exclude closed, `fmt_date`, classifier fixtures, inbox lifecycle, PSU label normaliser, tip-off blocklist, HTML escaping.
6. `jobs doctor` also checks that Playwright browsers are installed (print `playwright install chromium` if not), that `config.yaml` is valid, and that `psu_registry.yaml` loads.
7. Add `jobs daily`: runs `update`, `tipoff`, `export`, then prints inbox size and how many tips need an agent.

---

## 9. Final checklist before you say "done"

- [ ] `python -m pytest -q` passes.
- [ ] `jobs export` produces CSV, JSON, HTML with **no closed jobs** and dates as `DD/MM/YYYY` (JSON keeps ISO plus display fields).
- [ ] Second `jobs update` creates zero tasks; inbox has no already-processed tasks.
- [ ] Every stored job has a hash id and an official `source_url`.
- [ ] `jobs sources` shows health for every source; `docs/source_report.md` exists.
- [ ] `psu_registry.yaml` exists; `jobs coverage --psu` works; ratna statuses carry `verified_on`.
- [ ] `jobs tipoff` and `jobs tips` work; aggregator links can never become a job's `source_url`.
- [ ] HTML UI meets Task 6.
- [ ] README and AGENTS.md match the real commands.

Finish with a final report: what you changed per task, what you could not verify, and any decision you want the owner to make.
