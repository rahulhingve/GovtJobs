from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel

class NoticeItem(BaseModel):
    title: str
    url: str
    pdf_url: Optional[str] = None
    notification_no: Optional[str] = None
    raw_date: Optional[str] = None
    raw_text: Optional[str] = None
    department: Optional[str] = None
    vacancies: Optional[int] = None

class BaseScraper(ABC):
    @abstractmethod
    def parse_list(self, html_content: str, base_url: str) -> List[NoticeItem]:
        """Parse list page HTML and extract notice items."""
        pass
