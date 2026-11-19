"""Company career-page adapter via public ATS APIs (Greenhouse / Lever / Ashby).

Idea borrowed from career-ops (github.com/career-ops-hq/career-ops): scan company
boards directly through their public JSON APIs — no scraping, no ban risk.
Slugs below were validated live; edit COMPANY_BOARDS to add companies.
"""
import html
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from .base import NormalizedJob, parse_experience, strip_html

logger = logging.getLogger(__name__)

COMPANY_BOARDS = [
    ("greenhouse", "anthropic", "Anthropic"),
    ("greenhouse", "airbnb", "Airbnb"),
    ("greenhouse", "stripe", "Stripe"),
    ("greenhouse", "databricks", "Databricks"),
    ("greenhouse", "gitlab", "GitLab"),
    ("greenhouse", "agoda", "Agoda"),
    ("greenhouse", "groww", "Groww"),
    ("lever", "cred", "CRED"),
    ("lever", "meesho", "Meesho"),
    ("ashby", "openai", "OpenAI"),
    ("ashby", "sarvam", "Sarvam AI"),
    ("ashby", "cursor", "Cursor"),
    ("ashby", "elevenlabs", "ElevenLabs"),
]

INDIA_TOKENS = ["india", "bengaluru", "bangalore", "hyderabad", "pune", "chennai", "mumbai",
                "delhi", "gurgaon", "gurugram", "noida", "kolkata", "ahmedabad", "remote"]
ROLE_WORDS = ["engineer", "scientist", "developer", "researcher", "analyst", "architect"]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def _get_json(url: str):
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=25)
    if r.status_code != 200:
        return None
    try:
        return r.json()
    except ValueError:
        return None


def _fetch_board(provider: str, slug: str, company: str) -> list[dict]:
    if provider == "greenhouse":
        data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        if not data:
            return []
        out = []
        for j in data.get("jobs", []):
            desc = strip_html(html.unescape(j.get("content") or ""))
            out.append({"title": j.get("title", ""), "company": company,
                        "location": (j.get("location") or {}).get("name", ""),
                        "url": j.get("absolute_url", ""), "description": desc,
                        "source_id": str(j.get("id", "")), "posted_text": (j.get("updated_at") or "")[:10],
                        "is_remote": "remote" in ((j.get("location") or {}).get("name", "")).lower()})
        return out
    if provider == "lever":
        data = _get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        if not isinstance(data, list):
            return []
        out = []
        for j in data:
            cats = j.get("categories") or {}
            created = j.get("createdAt")
            posted = ""
            if created:
                try:
                    posted = datetime.fromtimestamp(created / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                except Exception:
                    pass
            out.append({"title": j.get("text", ""), "company": company,
                        "location": cats.get("location", ""), "url": j.get("hostedUrl", ""),
                        "description": j.get("descriptionPlain") or strip_html(j.get("description") or ""),
                        "source_id": j.get("id", ""), "posted_text": posted,
                        "is_remote": (j.get("workplaceType") or "").lower() == "remote"})
        return out
    if provider == "ashby":
        data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
        if not data:
            return []
        out = []
        for j in data.get("jobs", []):
            if not j.get("isListed", True):
                continue
            out.append({"title": j.get("title", ""), "company": company,
                        "location": j.get("location", ""), "url": j.get("jobUrl", ""),
                        "description": j.get("descriptionPlain") or strip_html(j.get("descriptionHtml") or ""),
                        "source_id": j.get("id", ""), "posted_text": (j.get("publishedAt") or "")[:10],
                        "is_remote": bool(j.get("isRemote", False))})
        return out
    return []


def _title_matches(title: str, queries: list[str]) -> bool:
    t = title.lower()
    for q in queries:
        q = q.lower().strip()
        if q in t:
            return True
        domain = [w for w in re.split(r"\s+", q) if w not in ROLE_WORDS and len(w) > 1]
        if domain and any(w in t for w in domain) and any(r in t for r in ROLE_WORDS):
            return True
    return False


def _location_matches(location: str, is_remote: bool, locations: list[str], remote_ok: bool) -> bool:
    loc = location.lower()
    if remote_ok and (is_remote or "remote" in loc or "worldwide" in loc or "anywhere" in loc):
        return True
    targets = [l.lower() for l in locations] if locations else INDIA_TOKENS
    return any(t in loc for t in targets if t != "remote")


def search(queries: list[str], locations: list[str] | None = None, remote_ok: bool = True,
           results: int = 40, boards: list[tuple] | None = None) -> list[NormalizedJob]:
    boards = boards or COMPANY_BOARDS
    raw: list[dict] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_board, p, s, c): (p, s) for p, s, c in boards}
        for fut in as_completed(futures):
            try:
                raw.extend(fut.result())
            except Exception as e:
                logger.warning("ATS board %s failed: %s", futures[fut], e)

    jobs = []
    seen = set()
    for j in raw:
        if not _title_matches(j["title"], queries):
            continue
        if not _location_matches(j["location"], j["is_remote"], locations or [], remote_ok):
            continue
        key = (j["title"].lower(), j["company"].lower())
        if key in seen:
            continue
        seen.add(key)
        exp_min, exp_max = parse_experience(j["description"][:4000])
        jobs.append(NormalizedJob(
            source="company_site", source_id=j["source_id"], title=j["title"], company=j["company"],
            location=j["location"], is_remote=j["is_remote"], description=j["description"],
            url=j["url"], posted_text=j["posted_text"], exp_min=exp_min, exp_max=exp_max,
            experience_text=f"{exp_min}-{exp_max} Yrs" if exp_min is not None else "",
        ))
    return jobs[:results]