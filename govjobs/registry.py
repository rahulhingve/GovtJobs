import logging
from pathlib import Path
from typing import List, Optional
import yaml
from govjobs.models import Source

logger = logging.getLogger("govjobs.registry")

VALID_CATEGORIES = [
    "Central exams and boards",
    "PSUs and CPSEs",
    "Banks and financial PSUs",
    "Defence and paramilitary",
    "Maritime",
    "Aviation",
    "State PSCs and selection boards",
    "State power utilities",
    "State engineering departments",
    "State police technical posts",
    "Local and special bodies",
]

def load_sources(file_path: str = "sources.yaml") -> List[Source]:
    path = Path(file_path)
    if not path.exists():
        logger.warning(f"Sources registry file {file_path} not found.")
        return []

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected a list of sources in {file_path}")

    sources: List[Source] = []
    for item in data:
        src = Source(**item)
        if src.category not in VALID_CATEGORIES:
            logger.warning(f"Source '{src.name}' has category '{src.category}' not in Section 14 valid categories list.")
        if not src.verify_ssl:
            logger.warning(f"[SSL WARNING] Source '{src.name}' ({src.list_url}) has verify_ssl=False due to broken official certificate chain.")
        sources.append(src)

    return sources

def get_source_by_name(name: str, file_path: str = "sources.yaml") -> Optional[Source]:
    sources = load_sources(file_path)
    for s in sources:
        if s.name.lower() == name.lower():
            return s
    return None
