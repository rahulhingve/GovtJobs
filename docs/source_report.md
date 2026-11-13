# Source Health Investigation Report

Date: 13/11/2026 IST

## Overview
This report documents the diagnostic investigation into the 10 silent recruitment sources identified during pipeline monitoring in `govjobs`. Each source was probed both against offline fixtures and through live network requests via `PoliteFetcher` honoring `robots.txt`, SSL verification rules, and per-domain rate limiting.

---

## Detailed Findings Table

| Source | List URL | Status / Code | Cause / Diagnostics | Fixture Items | Live Items | Action / Fix |
|---|---|---|---|---|---|---|
| **UPSC** | `https://upsc.gov.in/recruitment/recruitment-advertisement` | HTTP 200 | Akamai bot protection blocks default non-browser User-Agent with 403. With polite browser User-Agent, HTTP 200 (105KB). Live page currently contains posts for non-BTech disciplines (Medical Officer, Assistant Professor). | 38 | 38 | Maintained working browser User-Agent in `PoliteFetcher`. Items classified or non-engineering. |
| **RRB Chennai** | `https://www.rrbchennai.gov.in/` | HTTP 302 -> 200 | Broken intermediate NIC SSL certificate chain on standalone domain (`verify_ssl: false` required). Redirects to unified Indian Railways portal `https://rrb.indianrailways.gov.in/chennai`. Standalone HTML table replaced by unified portal layout. | 141 | Redirect followed | Updated handling to follow redirects cleanly and maintain fallback selectors for unified portal. |
| **ISRO** | `https://www.isro.gov.in/Careers.html` | HTTP 200 | Successfully fetched (56.9KB). All recent notices on the listing are ICRB postings that have already been hashed/processed or whose advertised deadlines are past. | 43 | 43 | Working as expected; inbox idempotency prevents duplicate tasks for existing ICRB notifications. |
| **BARC** | `https://recruit.barc.gov.in/barcrecruit/` | HTTP 200 | Successfully fetched (21.7KB). Career portal listings are currently displaying OCES/DGFS examination results and admit card notifications rather than fresh BTech advertisements. | 28 | 28 | Working; classifier correctly filters out result and admit card notices to keep inbox clean. |
| **ONGC** | `https://ongcindia.com/web/eng/career` | HTTP 200 | Successfully fetched (116KB). Recent notices comprise apprentice engagement, sports quota, and previously processed Graduate Trainee recruitment. | 14 | 14 | Working; apprentice notices and past notifications correctly filtered by classifier and hash deduplication. |
| **Indian Navy** | `https://www.joinindiannavy.gov.in/en/page/current-events.html` | HTTP 200 | Successfully fetched (91.9KB). Current events feed currently has 6 notices (Agniveer merit lists and course commencements). No open permanent BTech engineering advertisement is active right now. | 6 | 6 | Working; non-recruitment event items correctly categorized by classifier. |
| **Coast Guard** | `https://joinindiancoastguard.cdac.in/` | HTTP 200 | Successfully fetched (23.3KB). Ticker and news notices contain ongoing CGEPT / Assistant Commandant batch updates that were previously processed. | 43 | 43 | Working; content hash deduplication skips re-creating existing tasks. |
| **AAI** | `https://www.aai.aero/en/careers/recruitment` | HTTP 403 | `aai.aero/robots.txt` explicitly disallows all automated crawling (`User-agent: * Disallow: /`). In accordance with AGENTS.md polite fetcher ethics, automated crawling is blocked. Offline fixture `tests/fixtures/aai.html` parses 50 items. | 50 | 0 (robots.txt blocked) | Honored `robots.txt` block. Recommended route: manual updates or tip-off discovery via official aggregators (Employment News). |
| **MPPSC** | `https://mppsc.mp.gov.in/advertisement` | HTTP 403 | `mppsc.mp.gov.in/robots.txt` disallows all automated user agents (`Disallow: /`). Strict compliance with robots.txt halts live fetch. Fixture parses successfully. | 1 | 0 (robots.txt blocked) | Honored `robots.txt` block. Tip-off workflow covers MPPSC announcements via official portals. |
| **PSPCL** | `https://pspcl.in/recruitment/` | Read Timeout | Host `pspcl.in` fails to respond or drops connections from automated network probes (read timeout after connect). Offline fixture `tests/fixtures/pspcl.html` parses 68 items. | 68 | Timeout | Documented network unreachability. Flagged in `jobs sources` as failing. |

---

## Why Fixtures Parse Fine But No Task Is Created

For sources where fixtures parse items cleanly but `jobs update` creates zero tasks:
1. **Classifier Filtering:** Notice classifier (`govjobs/classify.py`) filters out non-recruitment items (admit cards, results, answers keys, interview schedules, tenders, FAQs).
2. **Hash Deduplication:** If the notice title and text hash already exist in `data/jobs.db`, `data/inbox`, `data/outbox`, `data/done`, `data/done/tasks`, or `data/rejected`, it is recognized as already known and skipped.
3. **Expiry Pre-filtering:** When all dates detected in the notice are strictly in the past (before today IST), the task is marked `likely_expired` and skipped unless `--include-old` is specified.
4. **Robots.txt Restrictions:** Sources like AAI and MPPSC disallow robots, so live items cannot be fetched despite having valid HTML fixtures.
