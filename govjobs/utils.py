import re
from datetime import datetime, date, timedelta, timezone
from typing import Optional

# Indian Standard Time (UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_today() -> date:
    """Return today's date in Indian Standard Time (Asia/Kolkata)."""
    return datetime.now(IST).date()

def parse_to_iso_date(val: Optional[str]) -> Optional[str]:
    """
    Parse date input and return ISO YYYY-MM-DD.
    Accepts:
    - ISO: YYYY-MM-DD
    - Indian Day-First: DD/MM/YYYY, DD.MM.YYYY, DD-MM-YYYY
    Rejects month-first or invalid dates.
    """
    if not val or not str(val).strip():
        return None
    
    s = str(val).strip()

    # Check ISO format YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            dt = datetime.strptime(s, "%Y-%m-%d").date()
            return dt.strftime("%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Invalid calendar date '{s}': {e}")

    # Check Indian day-first: DD/MM/YYYY, DD.MM.YYYY, DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[/\.-](\d{1,2})[/\.-](\d{4})$", s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dt = date(year, month, day)
            return dt.strftime("%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"Invalid calendar date '{s}' (expected day-first DD/MM/YYYY): {e}")

    raise ValueError(f"Date '{s}' must be in DD/MM/YYYY or YYYY-MM-DD format (day-first). Month-first is never assumed.")

def fmt_date(iso: Optional[str]) -> str:
    """
    Format an ISO date string (YYYY-MM-DD) as DD/MM/YYYY.
    Returns '-' if empty or None.
    """
    if not iso or not str(iso).strip():
        return "-"
    s = str(iso).strip()
    try:
        # If it's already DD/MM/YYYY
        if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
            return s
        dt = datetime.strptime(s, "%Y-%m-%d").date()
        return dt.strftime("%d/%m/%Y")
    except ValueError:
        return s

def fmt_datetime_ist(iso_or_dt: Optional[str]) -> str:
    """Format an ISO datetime string as DD/MM/YYYY HH:MM IST."""
    if not iso_or_dt or not str(iso_or_dt).strip():
        return "-"
    s = str(iso_or_dt).strip()
    try:
        # Handle trailing Z or timezone offsets
        clean_s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        else:
            dt = dt.astimezone(IST)
        return dt.strftime("%d/%m/%Y %H:%M IST")
    except Exception:
        return s[:16]

def days_left(job_or_end_date, today: Optional[date] = None) -> Optional[int]:
    """
    Calculate days left until end_date relative to today (in IST).
    Accepts either a Job object (with .end_date) or an ISO date string.
    """
    if today is None:
        today = get_ist_today()

    end_date_str = getattr(job_or_end_date, "end_date", job_or_end_date)
    if not end_date_str or not str(end_date_str).strip():
        return None

    try:
        d_end = datetime.strptime(str(end_date_str).strip(), "%Y-%m-%d").date()
        return (d_end - today).days
    except ValueError:
        return None
