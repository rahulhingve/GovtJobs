import csv
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from govjobs.config import get_config

IST = timezone(timedelta(hours=5, minutes=30))

class ClassificationResult:
    def __init__(self, decision: str, reason: str, kind: str = "new"):
        self.decision = decision  # "task", "skip"
        self.reason = reason
        self.kind = kind          # "new", "update"

    @property
    def should_create_task(self) -> bool:
        return self.decision == "task"

def classify_notice(
    source_name: str,
    title: str,
    raw_text: Optional[str] = None,
    log_file: str = "data/logs/classify.csv"
) -> ClassificationResult:
    """
    Classify whether a scraped notice row should create an inbox task.
    Decisions:
    - task (kind: 'new')
    - task (kind: 'update')
    - skip
    Logs decision to data/logs/classify.csv.
    """
    cfg = get_config().classifier_config
    menu_items = cfg.get("menu_items", [])
    negatives = cfg.get("negative_keywords", [])
    positives = cfg.get("positive_keywords", [])
    updates = cfg.get("update_keywords", [])

    clean_title = (title or "").strip()
    title_lower = clean_title.lower()
    full_text_lower = f"{title_lower} {(raw_text or '').lower()}"

    # 1. Very short or starts with '#'
    if len(clean_title) < 8 or clean_title.startswith("#"):
        res = ClassificationResult("skip", "Title too short (<8 chars) or starts with '#'")
        _log_decision(log_file, source_name, clean_title, res.decision, res.reason)
        return res

    # 2. Obvious menu items
    for item in menu_items:
        if title_lower == item or title_lower.startswith(f"{item} "):
            res = ClassificationResult("skip", f"Menu/navigation item matching '{item}'")
            _log_decision(log_file, source_name, clean_title, res.decision, res.reason)
            return res

    # 3. Corrigendum / Updates (must check before negatives, e.g. 'revised dates')
    for kw in updates:
        if kw in full_text_lower:
            res = ClassificationResult("task", f"Notice update/corrigendum matching '{kw}'", kind="update")
            _log_decision(log_file, source_name, clean_title, res.decision, res.reason)
            return res

    # 4. Negative keywords (admit cards, results, FAQs, call letters, etc.)
    for kw in negatives:
        if kw in full_text_lower:
            res = ClassificationResult("skip", f"Non-recruitment notice matching '{kw}'")
            _log_decision(log_file, source_name, clean_title, res.decision, res.reason)
            return res

    # 5. Positive keywords (recruitment, vacancy, engineer, etc.)
    for kw in positives:
        if kw in full_text_lower:
            res = ClassificationResult("task", f"Recruitment advertisement matching '{kw}'", kind="new")
            _log_decision(log_file, source_name, clean_title, res.decision, res.reason)
            return res

    # 6. Default fallback: if it contains an active PDF link or mentions posts/dates
    if any(k in full_text_lower for k in [".pdf", "post", "date"]):
        res = ClassificationResult("task", "Notice contains PDF or post/date references", kind="new")
    else:
        res = ClassificationResult("skip", "No positive recruitment signals found")

    _log_decision(log_file, source_name, clean_title, res.decision, res.reason)
    return res

def _log_decision(log_file: str, source: str, title: str, decision: str, reason: str):
    try:
        p = Path(log_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        is_new = not p.exists()
        with open(p, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["timestamp", "source", "title", "decision", "reason"])
            writer.writerow([
                datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                source,
                title[:100],
                decision,
                reason
            ])
    except Exception:
        pass
