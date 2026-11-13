from datetime import datetime, date, timedelta
from enum import Enum
from typing import Optional, Tuple, Any
from govjobs.models import Job
from govjobs.utils import IST, get_ist_today

class JobStatus(str, Enum):
    EXPIRING = "expiring"
    ACTIVE = "active"
    UPCOMING = "upcoming"
    CLOSED = "closed"
    UNKNOWN = "unknown"

def compute_job_status(job: Job, today: Optional[date] = None, expiring_days: int = 7) -> JobStatus:
    """
    Compute job status dynamically in IST:
    - expiring: end_date within expiring_days (inclusive) from today
    - active: start_date is None or <= today, and end_date > today + expiring_days
    - upcoming: start_date > today
    - closed: end_date < today
    - unknown: no usable dates or unverified
    """
    if today is None:
        today = get_ist_today()

    d_start: Optional[date] = None
    d_end: Optional[date] = None

    if job.start_date:
        try:
            d_start = datetime.strptime(job.start_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    if job.end_date:
        try:
            d_end = datetime.strptime(job.end_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    # 1. Upcoming if start_date is in the future
    if d_start and d_start > today:
        return JobStatus.UPCOMING

    # 2. If end_date is missing, it cannot be active or expiring definitively
    if not d_end:
        return JobStatus.UNKNOWN

    # 3. Closed if end_date has passed
    if d_end < today:
        return JobStatus.CLOSED

    # 4. Expiring if end_date is within expiring_days from today
    expiring_cutoff = today + timedelta(days=expiring_days)
    if d_end <= expiring_cutoff:
        return JobStatus.EXPIRING

    # 5. Active if start_date is null or past, and end_date beyond expiring window
    return JobStatus.ACTIVE

def job_sort_key(job: Job, today: Optional[date] = None, expiring_days: int = 7) -> Tuple[int, Any, str]:
    """
    Default sort order:
    1. expiring (soonest end_date first)
    2. active (soonest end_date first)
    3. upcoming (soonest start_date first)
    4. unknown
    5. closed (most recent end_date first)
    """
    status = compute_job_status(job, today=today, expiring_days=expiring_days)
    far_future = "9999-12-31"
    far_past = "0000-01-01"

    if status == JobStatus.EXPIRING:
        return (1, job.end_date or far_future, job.id)
    elif status == JobStatus.ACTIVE:
        return (2, job.end_date or far_future, job.id)
    elif status == JobStatus.UPCOMING:
        return (3, job.start_date or far_future, job.id)
    elif status == JobStatus.UNKNOWN:
        return (4, far_future, job.id)
    else:  # CLOSED
        # To show most recently closed first, we reverse order or put far_past
        return (5, job.end_date or far_past, job.id)
