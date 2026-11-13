import difflib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from govjobs.models import Job, normalize_key, generate_job_id
from govjobs.utils import IST

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    org TEXT NOT NULL,
    post_title TEXT NOT NULL,
    notification_no TEXT,
    level TEXT NOT NULL,
    state TEXT,
    sector TEXT NOT NULL,
    category TEXT,
    psu_name TEXT,
    psu_class TEXT,
    ministry TEXT,
    qualification_type TEXT NOT NULL,
    btech_eligible INTEGER NOT NULL,
    branches TEXT NOT NULL,
    branches_raw TEXT,
    gate_required INTEGER,
    additional_requirements TEXT NOT NULL,
    employment_type TEXT NOT NULL,
    vacancies INTEGER,
    pay_level_or_scale TEXT,
    start_date TEXT,
    end_date TEXT,
    description TEXT NOT NULL,
    source_url TEXT NOT NULL,
    notice_url TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    confidence REAL NOT NULL,
    needs_review INTEGER NOT NULL,
    review_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_org ON jobs(org);
CREATE INDEX IF NOT EXISTS idx_jobs_level ON jobs(level);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_sector ON jobs(sector);
CREATE INDEX IF NOT EXISTS idx_jobs_qualification ON jobs(qualification_type);
CREATE INDEX IF NOT EXISTS idx_jobs_employment ON jobs(employment_type);
CREATE INDEX IF NOT EXISTS idx_jobs_end_date ON jobs(end_date);

CREATE TABLE IF NOT EXISTS source_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    run_at TEXT NOT NULL,
    fetch_ok INTEGER NOT NULL,
    http_status INTEGER,
    used_playwright INTEGER NOT NULL,
    items_parsed INTEGER NOT NULL,
    items_classified_job INTEGER NOT NULL,
    tasks_created INTEGER NOT NULL,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_source_runs_source ON source_runs(source_name);
CREATE INDEX IF NOT EXISTS idx_source_runs_run_at ON source_runs(run_at);
"""

class JobStore:
    def __init__(self, db_path: str = "data/jobs.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript(CREATE_TABLE_SQL)
            # Add columns if missing (migration)
            for col in ["category", "psu_name", "psu_class", "ministry"]:
                try:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} TEXT")
                except sqlite3.OperationalError:
                    pass

            # Backfill PSU info for existing records if missing
            try:
                from govjobs.psu import find_psu_match
                cursor = conn.cursor()
                cursor.execute("SELECT id, org FROM jobs WHERE psu_name IS NULL OR psu_class IS NULL")
                rows = cursor.fetchall()
                for r in rows:
                    match = find_psu_match(r["org"])
                    if match:
                        conn.execute(
                            "UPDATE jobs SET psu_name = ?, psu_class = ?, ministry = ? WHERE id = ?",
                            (match["name"], match["ratna_class"], match.get("ministry"), r["id"]),
                        )
            except Exception:
                pass
            # Migrate any non-hash IDs to hash IDs
            cursor = conn.cursor()
            cursor.execute("SELECT id, org, notification_no, post_title FROM jobs")
            rows = cursor.fetchall()
            for r in rows:
                jid, org, notif, post = r["id"], r["org"], r["notification_no"], r["post_title"]
                if not re.match(r"^[0-9a-f]{16}$", jid):
                    new_id = generate_job_id(org, notif or "", post)
                    if new_id != jid:
                        conn.execute("UPDATE OR REPLACE jobs SET id = ? WHERE id = ?", (new_id, jid))
            conn.commit()

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        d = dict(row)
        d["btech_eligible"] = bool(d["btech_eligible"])
        d["needs_review"] = bool(d["needs_review"])
        d["gate_required"] = bool(d["gate_required"]) if d["gate_required"] is not None else None
        d["branches"] = json.loads(d["branches"]) if d["branches"] else []
        d["additional_requirements"] = json.loads(d["additional_requirements"]) if d["additional_requirements"] else []
        return Job(**d)

    def find_matching_existing_id(self, org: str, notice_title_or_no: str, post_title: str) -> Optional[str]:
        """
        Check if an existing job matches org and notice_key, and has post_key >= 85% similar.
        Returns the existing job's id if matched, or None.
        """
        org_norm = normalize_key(org)
        notice_norm = normalize_key(notice_title_or_no)
        new_post_norm = normalize_key(post_title)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, org, notification_no, post_title FROM jobs")
            for row in cursor.fetchall():
                row_org_norm = normalize_key(row["org"])
                if row_org_norm != org_norm:
                    continue
                row_notice_norm = normalize_key(row["notification_no"] or "")
                # If notice_norm is non-empty, require it to match or be closely matched
                if notice_norm and row_notice_norm:
                    if notice_norm != row_notice_norm:
                        continue
                existing_post_norm = normalize_key(row["post_title"])
                ratio = difflib.SequenceMatcher(None, new_post_norm, existing_post_norm).ratio()
                if ratio >= 0.85:
                    return row["id"]
        return None

    def upsert_job(self, job: Job) -> Tuple[str, bool]:
        """
        Insert or update a Job record.
        Handles deduplication using 85% similarity on post title.
        Returns (id, is_new).
        """
        matched_id = self.find_matching_existing_id(
            job.org,
            job.notification_no or "",
            job.post_title
        )

        job_id = matched_id if matched_id else job.id
        is_new = matched_id is None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if is_new:
                # Check if exact job_id exists
                cursor.execute("SELECT first_seen FROM jobs WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                if row:
                    first_seen = row[0]
                    is_new = False
                else:
                    first_seen = job.first_seen
            else:
                cursor.execute("SELECT first_seen FROM jobs WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                first_seen = row[0] if row else job.first_seen

            cursor.execute("""
            INSERT OR REPLACE INTO jobs (
                id, org, post_title, notification_no, level, state, sector,
                category, psu_name, psu_class, ministry,
                qualification_type, btech_eligible, branches, branches_raw,
                gate_required, additional_requirements, employment_type, vacancies,
                pay_level_or_scale, start_date, end_date, description,
                source_url, notice_url, first_seen, last_seen, content_hash,
                confidence, needs_review, review_reason
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?
            )
            """, (
                job_id,
                job.org,
                job.post_title,
                job.notification_no,
                job.level.value if hasattr(job.level, "value") else str(job.level),
                job.state,
                job.sector,
                job.category,
                job.psu_name,
                job.psu_class,
                job.ministry,
                job.qualification_type.value if hasattr(job.qualification_type, "value") else str(job.qualification_type),
                1 if job.btech_eligible else 0,
                json.dumps([b.value if hasattr(b, "value") else str(b) for b in job.branches]),
                job.branches_raw,
                None if job.gate_required is None else (1 if job.gate_required else 0),
                json.dumps(job.additional_requirements),
                job.employment_type.value if hasattr(job.employment_type, "value") else str(job.employment_type),
                job.vacancies,
                job.pay_level_or_scale,
                job.start_date,
                job.end_date,
                job.description,
                job.source_url,
                job.notice_url,
                first_seen,
                job.last_seen,
                job.content_hash,
                job.confidence,
                1 if job.needs_review else 0,
                job.review_reason
            ))
            conn.commit()
            return job_id, is_new

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_job(row)
        return None

    def get_all_jobs(self) -> List[Job]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs")
            return [self._row_to_job(row) for row in cursor.fetchall()]

    def export_json(self, export_path: str = "data/jobs.json", include_closed: bool = False, archive_path: str = "data/archive.json"):
        from govjobs.status import compute_job_status, JobStatus, job_sort_key
        from govjobs.utils import fmt_date, get_ist_today

        all_jobs = self.get_all_jobs()
        today = get_ist_today()

        path = Path(export_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        arch_path = Path(archive_path)
        arch_path.parent.mkdir(parents=True, exist_ok=True)

        active_jobs = []
        closed_jobs = []

        for job in all_jobs:
            st = compute_job_status(job, today=today)
            data = job.model_dump()
            data["start_date_display"] = fmt_date(job.start_date)
            data["end_date_display"] = fmt_date(job.end_date)
            data["status"] = st.value

            if st == JobStatus.CLOSED:
                closed_jobs.append(data)
                if include_closed:
                    active_jobs.append(data)
            else:
                active_jobs.append(data)

        # Sort active jobs by sort_key
        active_jobs.sort(key=lambda d: job_sort_key(Job(**{k: v for k, v in d.items() if k not in ["start_date_display", "end_date_display", "status"]}), today=today))

        path.write_text(json.dumps(active_jobs, indent=2, ensure_ascii=False), encoding="utf-8")
        arch_path.write_text(json.dumps(closed_jobs, indent=2, ensure_ascii=False), encoding="utf-8")

    def record_source_run(
        self,
        source_name: str,
        run_at: str,
        fetch_ok: bool,
        http_status: Optional[int],
        used_playwright: bool,
        items_parsed: int,
        items_classified_job: int,
        tasks_created: int,
        error: Optional[str] = None,
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO source_runs (
                    source_name, run_at, fetch_ok, http_status, used_playwright,
                    items_parsed, items_classified_job, tasks_created, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_name,
                    run_at,
                    1 if fetch_ok else 0,
                    http_status,
                    1 if used_playwright else 0,
                    items_parsed,
                    items_classified_job,
                    tasks_created,
                    error,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_latest_source_runs(self, source_name: Optional[str] = None, limit: int = 2) -> List[sqlite3.Row]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if source_name:
                cursor.execute(
                    "SELECT * FROM source_runs WHERE source_name = ? ORDER BY run_at DESC LIMIT ?",
                    (source_name, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM source_runs ORDER BY run_at DESC LIMIT ?",
                    (limit,),
                )
            return cursor.fetchall()

    def get_source_health(self, source_name: str) -> Dict[str, Any]:
        """
        Return health stats for a source:
        - last_run: Optional[sqlite3.Row]
        - prev_run: Optional[sqlite3.Row]
        - failed_twice: bool
        - zero_items_twice: bool
        - selectors_matched_nothing: bool
        - days_since_task: Optional[int]
        """
        runs = self.get_latest_source_runs(source_name=source_name, limit=2)
        last_run = runs[0] if len(runs) > 0 else None
        prev_run = runs[1] if len(runs) > 1 else None

        failed_twice = (
            last_run is not None
            and prev_run is not None
            and last_run["fetch_ok"] == 0
            and prev_run["fetch_ok"] == 0
        )
        zero_items_twice = (
            last_run is not None
            and prev_run is not None
            and last_run["fetch_ok"] == 1
            and prev_run["fetch_ok"] == 1
            and last_run["items_parsed"] == 0
            and prev_run["items_parsed"] == 0
        )
        selectors_matched_nothing = (
            last_run is not None
            and last_run["fetch_ok"] == 1
            and last_run["items_parsed"] == 0
        )

        days_since_task = None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT run_at FROM source_runs WHERE source_name = ? AND tasks_created > 0 ORDER BY run_at DESC LIMIT 1",
                (source_name,),
            )
            row = cursor.fetchone()
            if row:
                try:
                    dt = datetime.fromisoformat(row["run_at"].replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=IST)
                    days_since_task = (datetime.now(IST).date() - dt.date()).days
                except Exception:
                    pass

        return {
            "last_run": last_run,
            "prev_run": prev_run,
            "failed_twice": failed_twice,
            "zero_items_twice": zero_items_twice,
            "selectors_matched_nothing": selectors_matched_nothing,
            "days_since_task": days_since_task,
        }
