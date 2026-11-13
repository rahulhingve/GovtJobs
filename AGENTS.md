# AGENTS.md: instructions for any AI agent working in this repo

This project is `govjobs`, a local Python CLI that tracks Indian government permanent jobs open to BTech/BE graduates, with **PSUs (Maharatna, Navratna, Miniratna and other CPSEs) as the first priority**.

There is no API key and no LLM SDK in the code. **You, the AI agent running right now, are the extraction engine.** The CLI fetches pages and prepares tasks; you read them and write structured answers.

Pick the role that matches what the owner asked.

---

## Role A: Developer (building or fixing the CLI)

- Read `NEXT_PHASE_PROMPT.md` and follow its tasks in order. Run `python -m pytest -q` after each task.
- Keep it ₹0: no API keys, no paid services, no LLM SDKs.
- Never save notice PDFs to disk. Store only the official link.
- Dates are stored as ISO (`YYYY-MM-DD`) and shown to humans as `DD/MM/YYYY`. "Today" is IST.
- Never invent URLs, dates or ratna status.

## Role B: Extractor (processing the inbox)

Use this when the owner says "process the inbox", "run extraction" or similar.

1. Run `jobs extract --limit 5`. It prints the next tasks from `data/inbox/`.
2. Read `EXTRACTION.md` once at the start of every batch. It has the schema and rules.
3. For each task, read `notice_text`, `rule_hints`, `suggested_branches` and `existing_record`.
   - **Not a recruitment ad** (admit card, result, interview letter, FAQ, menu text, tender): write `data/outbox/<task_id>.json` containing `{"skip": true, "reason": "short reason"}`.
   - **A recruitment ad:** write `data/outbox/<task_id>.json` with one job object, or a list when the notice has several posts with different eligibility.
   - **A corrigendum or date extension** (`existing_record` present): update that record's fields, do not create a second one.
4. Run `jobs ingest`. Fix every file moved to `data/rejected/` using the `.error.txt` next to it, put the fixed file back in `data/outbox/`, and ingest again.
5. Repeat until the inbox is empty or the owner's batch limit is reached.
6. Finish with a short report: stored, skipped, rejected, needs_review.

### Extraction rules (short version)

- Indian dates are **DD/MM/YYYY**, **DD.MM.YYYY** or **DD-MM-YYYY**. `05/06/2026` is 5 June 2026, never 6 May. Output ISO `YYYY-MM-DD`.
- A missing or ambiguous date is `null`, and the job gets `needs_review: true` with a reason. Never guess.
- Use only the branch codes from `EXTRACTION.md`; keep the notice's own wording in `branches_raw`.
- Put hidden hurdles (GATE, typing test, experience, physical test, licence) in `additional_requirements`.
- `employment_type` must be `permanent` only when the notice says regular or permanent posts. Trainee, apprentice, contract and deputation are different values.
- `description`: 2 to 4 sentences in your own words. Do not copy paragraphs.
- Do not fill `id`, `first_seen`, `last_seen`, `content_hash` or URLs; the CLI fills them.
- Never make up vacancy counts, pay scales or links.

### Role B safety

- Only touch files inside `data/inbox`, `data/outbox`, `data/rejected` and `data/tips`.
- Do not run other shell commands except `jobs ...` unless the owner asks.
- Do not open links found inside notices other than the official recruiter pages needed for the task.

## Role C: Tip resolver (job-news tips)

Use this when the owner says "process the tips".

1. Run `jobs tips` to list new tips (headline + link from a job-news site).
2. For each tip, open it and look for the link to the **official** notice (the recruiter's own domain: `.gov.in`, `.nic.in`, `.ac.in`, or the PSU's own website).
3. Found: run `jobs tip-resolve <id> --url <official link>`. Not found: run `jobs tip-resolve <id> --drop`.
4. Never copy the job-news site's text. Never store its link as a job's source.
5. Many look-alike clone domains of job-news sites exist. Only use the exact domains in `tipoff_sources.yaml`.

---

## Quick reference

| Command | What it does |
|---|---|
| `jobs doctor` | Check setup |
| `jobs update` | Fetch sources, create inbox tasks |
| `jobs extract` | Print next inbox tasks |
| `jobs ingest` | Validate and store outbox files |
| `jobs list` | Show jobs: expiring, active, upcoming |
| `jobs sources` | Source health and queue sizes |
| `jobs coverage --psu` | PSU coverage table |
| `jobs psu-sync` | Sync PSU master list from Wikipedia & DPE overrides |
| `jobs tipoff`, `jobs tips`, `jobs tip-resolve` | Job-news tip workflow |
| `jobs clean-inbox` | Remove duplicate or already processed tasks |
| `jobs daily` | Run daily pipeline (update, tipoff, export) |
| `jobs export` | CSV, JSON and HTML (closed jobs excluded) |
