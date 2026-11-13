import hashlib
import re
from datetime import datetime, timedelta
from govjobs.utils import get_ist_today, parse_to_iso_date
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator, model_validator

# Strict Branch Enum
class Branch(str, Enum):
    CSE = "CSE"
    IT = "IT"
    ECE = "ECE"
    EEE = "EEE"
    INSTRU = "INSTRU"
    ME = "ME"
    CE = "CE"
    CHE = "CHE"
    MIN = "MIN"
    MET = "MET"
    PETRO = "PETRO"
    PROD = "PROD"
    AERO = "AERO"
    MARINE = "MARINE"
    AUTO = "AUTO"
    BIO = "BIO"
    ALL = "ALL"
    OTHER = "OTHER"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val_upper = value.strip().upper()
            for member in cls:
                if member.value == val_upper:
                    return member
        return None

class Level(str, Enum):
    CENTRAL = "central"
    STATE = "state"
    UT = "ut"
    PSU = "psu"
    DEFENCE = "defence"
    POLICE = "police"
    OTHER = "other"

class QualificationType(str, Enum):
    BTECH_REQUIRED = "btech_required"
    BTECH_OR_EQUIVALENT = "btech_or_equivalent"
    ANY_GRADUATE = "any_graduate"

class EmploymentType(str, Enum):
    PERMANENT = "permanent"
    CONTRACT = "contract"
    APPRENTICE = "apprentice"
    TRAINEE = "trainee"
    DEPUTATION = "deputation"
    UNKNOWN = "unknown"

def normalize_key(text: str) -> str:
    """Lowercase and strip punctuation for key hashing."""
    if not text:
        return ""
    # remove punctuation and condense whitespace
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(cleaned.split())

def generate_job_id(org: str, notice_title_or_no: str, post_title: str) -> str:
    """Generate stable job ID as sha256 hash of org + notice_key + post_key."""
    org_key = normalize_key(org)
    notice_key = normalize_key(notice_title_or_no)
    post_key = normalize_key(post_title)
    seed = f"{org_key}|{notice_key}|{post_key}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:16]

class Job(BaseModel):
    id: str = Field(description="Stable key: hash of org + notice_key + post_key")
    org: str
    post_title: str
    notification_no: Optional[str] = None
    level: Level = Level.OTHER
    state: Optional[str] = None
    sector: str
    category: Optional[str] = None
    psu_name: Optional[str] = None
    psu_class: Optional[str] = None
    ministry: Optional[str] = None
    qualification_type: QualificationType = QualificationType.BTECH_REQUIRED
    btech_eligible: bool = True
    branches: List[Branch] = Field(default_factory=list)
    branches_raw: Optional[str] = None
    gate_required: Optional[bool] = None
    additional_requirements: List[str] = Field(default_factory=list)
    employment_type: EmploymentType = EmploymentType.PERMANENT
    vacancies: Optional[int] = None
    pay_level_or_scale: Optional[str] = None
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None    # YYYY-MM-DD
    description: str
    source_url: str
    notice_url: Optional[str] = None
    first_seen: str
    last_seen: str
    content_hash: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    needs_review: bool = False
    review_reason: Optional[str] = None

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, v: str) -> str:
        if not v or not v.strip().startswith(("http://", "https://")):
            raise ValueError("source_url must be a valid http/https URL")
        from govjobs.tipoff import is_aggregator_domain
        if is_aggregator_domain(v):
            raise ValueError(f"source_url cannot be an aggregator URL ('{v}'). Stored jobs must link to official recruiter domains.")
        return v.strip()

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return parse_to_iso_date(str(v))

    @model_validator(mode="after")
    def validate_dates_and_consistency(self) -> "Job":
        # Check end_date >= start_date
        if self.start_date and self.end_date:
            d_start = datetime.strptime(self.start_date, "%Y-%m-%d").date()
            d_end = datetime.strptime(self.end_date, "%Y-%m-%d").date()
            if d_end < d_start:
                raise ValueError(f"end_date ({self.end_date}) cannot be earlier than start_date ({self.start_date})")

        # Check dates not more than 2 years out from today in IST
        today_ist = get_ist_today()
        two_years_ahead = today_ist + timedelta(days=730)
        for date_str, name in [(self.start_date, "start_date"), (self.end_date, "end_date")]:
            if date_str:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                if d > two_years_ahead:
                    raise ValueError(f"{name} ({date_str}) is more than 2 years in the future from IST today ({today_ist})")

        # Needs review if confidence < 0.7 or end_date missing
        if self.confidence < 0.7 and not self.needs_review:
            self.needs_review = True
            if not self.review_reason:
                self.review_reason = f"Low confidence ({self.confidence:.2f})"
        if not self.end_date and not self.needs_review:
            self.needs_review = True
            if not self.review_reason:
                self.review_reason = "Missing end_date"

        return self

class AgentJob(BaseModel):
    org: str
    post_title: str
    notification_no: Optional[str] = None
    qualification_type: QualificationType = QualificationType.BTECH_REQUIRED
    btech_eligible: bool = True
    branches: List[Branch] = Field(default_factory=list)
    branches_raw: Optional[str] = None
    gate_required: Optional[bool] = None
    additional_requirements: List[str] = Field(default_factory=list)
    employment_type: EmploymentType = EmploymentType.PERMANENT
    vacancies: Optional[int] = None
    pay_level_or_scale: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    needs_review: bool = False
    review_reason: Optional[str] = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        return parse_to_iso_date(str(v))

class SourceType(str, Enum):
    HTML_LIST = "html_list"
    PDF_INDEX = "pdf_index"
    JS_PAGE = "js_page"
    CUSTOM = "custom"

class Source(BaseModel):
    name: str
    category: str
    level: Level
    state: Optional[str] = None
    sector: str
    list_url: str
    type: SourceType = SourceType.HTML_LIST
    selectors: Optional[dict] = None
    verify_ssl: bool = True
    enabled: bool = True
