"""Normalized job schema shared by all platform adapters."""
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class NormalizedJob:
    source: str
    title: str
    company: str = ""
    location: str = ""
    is_remote: bool = False
    salary: str = ""
    exp_min: float | None = None
    exp_max: float | None = None
    experience_text: str = ""
    description: str = ""
    skills: list[str] = field(default_factory=list)
    url: str = ""
    source_id: str = ""
    posted_text: str = ""
    posted_at: datetime | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def dedupe_key(self) -> str:
        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", s.lower())
        return f"{norm(self.title)[:80]}|{norm(self.company)[:60]}|{norm(self.location)[:40]}"


_EXP_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.I)
_EXP_PLUS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)", re.I)
_EXP_SINGLE_RE = re.compile(r"(?:minimum|at least|min\.?)\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", re.I)
_FRESHER_RE = re.compile(r"\b(fresher|freshers|entry[- ]level|0\s*(?:-|–|to)\s*1\s*(?:years?|yrs?))\b", re.I)


def parse_experience(text: str) -> tuple[float | None, float | None]:
    """Extract (min, max) years of experience from a requirement string."""
    if not text:
        return None, None
    m = _EXP_RANGE_RE.search(text)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = _EXP_PLUS_RE.search(text)
    if m:
        return float(m.group(1)), None
    m = _EXP_SINGLE_RE.search(text)
    if m:
        return float(m.group(1)), None
    if _FRESHER_RE.search(text):
        return 0.0, 1.0
    return None, None


def strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()