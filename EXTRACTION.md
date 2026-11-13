# EXTRACTION INSTRUCTIONS FOR OPERATING AGENT

Read these instructions carefully before processing any batch of tasks in `data/inbox/`.

## 1. Goal & Identity
You are extracting structured job records from Indian government recruitment notices.
You will read each task file in `data/inbox/<task_id>.json` and output `data/outbox/<task_id>.json`.

- **Skip Protocol:** If a notice is NOT a recruitment advertisement (for example an admit card, interview call letter, answer key, results list, table header row, menu item, FAQ, or tender), output:
  ```json
  {
    "skip": true,
    "reason": "Short explanation, e.g. Admit card notice, not a recruitment ad"
  }
  ```
- **Recruitment Ad:** Write `data/outbox/<task_id>.json` containing one job object, or a JSON array of job objects when a notice contains multiple distinct posts with different eligibility criteria.
- **Fields you DO NOT fill:** `id`, `first_seen`, `last_seen`, `content_hash`, `source_url`, `notice_url`, `level`, `sector`, `category`. The ingest engine automatically fills these from the task file and computes a secure stable hash ID.

## 2. Hard Date Rules (Indian Format)
- Indian notices write dates as **DD/MM/YYYY**, **DD.MM.YYYY**, or **DD-MM-YYYY**.
- Example: `05/06/2026` is **5 June 2026**, NEVER May 6.
- In outbox files, you can output dates in either `DD/MM/YYYY` or ISO `YYYY-MM-DD`. The validator will automatically convert day-first dates to ISO.
- Parse day first.
- If a date is ambiguous, missing, or unspecified, use `null`. NEVER invent or guess a date.
- `end_date` cannot be earlier than `start_date`.

## 3. Strict Branch Enum
Map every branch or degree name mentioned in the notice to one or more of these strict codes:
- `CSE` (Computer Science & Engineering, CS, Comp Sc)
- `IT` (Information Technology)
- `ECE` (Electronics & Communication Engineering, E&C)
- `EEE` (Electrical & Electronics Engineering, Electrical Engineering)
- `INSTRU` (Instrumentation & Control, Electronics & Instrumentation)
- `ME` (Mechanical Engineering)
- `CE` (Civil Engineering)
- `CHE` (Chemical Engineering)
- `MIN` (Mining Engineering)
- `MET` (Metallurgical Engineering, Materials)
- `PETRO` (Petroleum Engineering, Petrochemical)
- `PROD` (Production Engineering, Industrial Engineering)
- `AERO` (Aeronautical, Aerospace)
- `MARINE` (Marine Engineering, Naval Architecture)
- `AUTO` (Automobile Engineering)
- `BIO` (Biotechnology, Biomedical)
- `ALL` (Any engineering branch eligible)
- `OTHER` (Specific niche engineering discipline not listed above)

Always store the notice's own wording verbatim in `branches_raw`.

## 4. Eligibility & Hurdle Fields
- `qualification_type`:
  - `btech_required`: Specifically requires BE/BTech.
  - `btech_or_equivalent`: Requires BE/BTech or equivalent (e.g. AMIE, MCA).
  - `any_graduate`: Open to any graduate degree.
- `btech_eligible`: boolean (`true` if a BTech/BE graduate can apply, `false` otherwise).
- `employment_type`: `permanent | contract | apprentice | trainee | deputation | unknown`. Use `permanent` only when the notice explicitly says regular or permanent posts.
- `gate_required`: `true` if GATE score is mandatory, `false` if not required, `null` if unspecified.
- `additional_requirements`: List of strings for hidden hurdles, e.g.: `["GATE 2026 Score"]`, `["2 years experience"]`, `["Physical Test"]`.

## 5. Description
Write 2 to 4 plain sentences in your own words summarizing the role, discipline, and key conditions.
**DO NOT copy paragraphs** verbatim from the notice.

## 6. needs_review Rules
Set `needs_review = true` and provide a clear `review_reason` string if:
1. `end_date` is missing or ambiguous.
2. BTech eligibility is borderline or unclear.
3. Text came from degraded OCR.
4. Your confidence is below 0.7.

---

## 7. Worked Examples (ILLUSTRATIVE ONLY, DO NOT COPY)

### Example A: Single Recruitment Post (ILLUSTRATIVE ONLY)
```json
{
  "org": "National Power Corporation (Example)",
  "post_title": "Executive Trainee (Electrical)",
  "notification_no": "NPC/01/2026",
  "qualification_type": "btech_required",
  "btech_eligible": true,
  "branches": ["EEE"],
  "branches_raw": "Full time B.E./B.Tech in Electrical / Electrical & Electronics",
  "gate_required": true,
  "additional_requirements": ["Valid GATE 2026 Score in EE", "Minimum 60% marks in BTech"],
  "employment_type": "permanent",
  "vacancies": 45,
  "pay_level_or_scale": "E2 (Rs. 50,000 - 1,60,000)",
  "start_date": "15/01/2026",
  "end_date": "18/02/2026",
  "description": "National Power Corporation is recruiting Executive Trainees in Electrical engineering through GATE 2026. Applicants must possess a full-time BTech in Electrical with at least 60% aggregate. Selection involves GATE performance followed by interview.",
  "confidence": 0.95,
  "needs_review": false,
  "review_reason": null
}
```

### Example B: Non-Recruitment Notice (Skip Protocol)
```json
{
  "skip": true,
  "reason": "Document verification schedule for previously examined candidates; not a new job opening."
}
```
