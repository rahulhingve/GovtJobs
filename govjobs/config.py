import os
from pathlib import Path
from typing import Dict, List, Any
import yaml

DEFAULT_CONFIG: Dict[str, Any] = {
    "expiring_days": 7,
    "extract_batch_size": 5,
    "max_items_per_source": 15,
    "request_delay_seconds": 2.0,
    "request_timeout_seconds": 30.0,
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 GovJobs/0.1",
    "data_dir": "data",
    "classifier": {
        "menu_items": [
            "select location", "archived items", "current job openings", "name of the post",
            "faqs", "status", "home", "contact", "read more", "click here", "download", "details"
        ],
        "negative_keywords": [
            "admit card", "hall ticket", "call letter", "interview letter", "result",
            "answer key", "cut-off", "cutoff", "city of examination", "document verification",
            "scorecard", "candidate response", "application count", "applications received",
            "draft mode", "roll number", "roll no", "helpdesk", "faq", "tender", "quotation",
            "objection management", "debarred", "portal unavailable", "unclaimed amount"
        ],
        "positive_keywords": [
            "advertisement", "advt", "recruitment", "vacancy", "vacancies", "notification",
            "engagement", "trainee", "gate", "walk-in", "executive", "engineer", "officer",
            "scientist", "apprentice"
        ],
        "update_keywords": [
            "corrigendum", "extension", "revised dates", "revised date", "addendum",
            "amendment", "cancellation", "tentative schedule"
        ]
    }
}

class Config:
    _instance = None

    def __init__(self, config_file: str = "config.yaml"):
        self.config_data = dict(DEFAULT_CONFIG)
        p = Path(config_file)
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    user_cfg = yaml.safe_load(f)
                    if isinstance(user_cfg, dict):
                        self._deep_merge(self.config_data, user_cfg)
            except Exception:
                pass

    def _deep_merge(self, base: dict, override: dict):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v

    def get(self, key: str, default: Any = None) -> Any:
        return self.config_data.get(key, default)

    @property
    def expiring_days(self) -> int:
        return int(self.config_data.get("expiring_days", 7))

    @property
    def extract_batch_size(self) -> int:
        return int(self.config_data.get("extract_batch_size", 5))

    @property
    def max_items_per_source(self) -> int:
        return int(self.config_data.get("max_items_per_source", 15))

    @property
    def request_delay_seconds(self) -> float:
        return float(self.config_data.get("request_delay_seconds", 2.0))

    @property
    def request_timeout_seconds(self) -> float:
        return float(self.config_data.get("request_timeout_seconds", 30.0))

    @property
    def user_agent(self) -> str:
        return str(self.config_data.get("user_agent", DEFAULT_CONFIG["user_agent"]))

    @property
    def data_dir(self) -> Path:
        return Path(self.config_data.get("data_dir", "data"))

    @property
    def classifier_config(self) -> dict:
        return self.config_data.get("classifier", DEFAULT_CONFIG["classifier"])

_config_obj: Config = None

def get_config(config_file: str = "config.yaml") -> Config:
    global _config_obj
    if _config_obj is None:
        _config_obj = Config(config_file)
    return _config_obj
