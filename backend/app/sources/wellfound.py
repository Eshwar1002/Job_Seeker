"""Wellfound (AngelList Talent) adapter via server-rendered role pages.

Validated live: wellfound.com/role/l/{role}/{location} and /role/r/{role} (remote)
embed a full Apollo state JSON in __NEXT_DATA__ with JobListingSearchResult
objects (title, locations, compensation, yearsExperienceMin/Max, description).
"""
import json
import logging
import re
from datetime import datetime, timezone

import requests

from .base import NormalizedJob, strip_html

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

ROLE_SLUGS = {
    "ai engineer": "ai-engineer",
    "machine learning engineer": "machine-learning-engineer",
    "ml engineer": "machine-learning-engineer",
    "data scientist": "data-scientist",
    "genai engineer": "ai-engineer",
    "python developer": "python-developer",
    "software engineer": "software-engineer",
    "nlp engineer": "nlp-engineer",
    "data engineer": "data-engineer",
}


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _fetch_page(url: str) -> dict:
    r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html"}, timeout=25)
    if r.status_code == 403:
        raise RuntimeError("Wellfound blocked the request (Cloudflare)")
    r.raise_for_status()
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(1))
        return d.get("props", {}).get("pageProps", {}).get("apolloState", {}).get("data", {})
    except (ValueError, AttributeError):
        return {}


def _parse_data(data: dict) -> list[NormalizedJob]:
    company_by_job: dict[str, str] = {}
    for key, val in data.items():
        if key.startswith("StartupResult:") and isinstance(val, dict):
            for ref in val.get("highlightedJobListings") or []:
                if isinstance(ref, dict) and ref.get("__ref"):
                    company_by_job[ref["__ref"]] = val.get("name", "")
    jobs = []
    for key, j in data.items():
        if not key.startswith("JobListingSearchResult:") or not isinstance(j, dict):
            continue
        jid = str(j.get("id") or key.split(":")[-1])
        locations = j.get("locationNames") or []
        posted = None
        if j.get("liveStartAt"):
            try:
                posted = datetime.fromtimestamp(int(j["liveStartAt"]), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                pass
        exp_min = j.get("yearsExperienceMin")
        exp_max = j.get("yearsExperienceMax")
        jobs.append(NormalizedJob(
            source="wellfound",
            source_id=jid,
            title=j.get("title", ""),
            company=company_by_job.get(key, ""),
            location=", ".join(locations) if isinstance(locations, list) else str(locations),
            is_remote=bool(j.get("remote")),
            salary=(j.get("compensation") or "").replace("", "-"),
            exp_min=float(exp_min) if exp_min is not None else None,
            exp_max=float(exp_max) if exp_max is not None else None,
            experience_text=f"{exp_min}-{exp_max} Yrs" if exp_min is not None else "",
            description=(j.get("description") or "")[:6000],
            url=f"https://wellfound.com/jobs/{jid}-{j.get('slug', '')}",
            posted_text=posted.strftime("%Y-%m-%d") if posted else "",
            posted_at=posted,
        ))
    return jobs


def search(queries: list[str], locations: list[str] | None = None,
           remote_ok: bool = True, results: int = 40) -> list[NormalizedJob]:
    urls = []
    locs = locations or ["india"]
    for q in queries[:2]:
        slug = ROLE_SLUGS.get(q.lower().strip()) or _slugify(q)
        for loc in locs[:2]:
            loc_slug = _slugify(loc)
            if loc_slug in ("remote", "work-from-home"):
                urls.append(f"https://wellfound.com/role/r/{slug}")
            else:
                urls.append(f"https://wellfound.com/role/l/{slug}/{loc_slug}")
        if remote_ok:
            urls.append(f"https://wellfound.com/role/r/{slug}")
    jobs, seen = [], set()
    errors = []
    for url in dict.fromkeys(urls):
        try:
            for j in _parse_data(_fetch_page(url)):
                if j.source_id not in seen and j.title:
                    seen.add(j.source_id)
                    jobs.append(j)
        except Exception as e:
            errors.append(str(e))
            logger.warning("Wellfound fetch failed %s: %s", url, e)
    if not jobs and errors:
        raise RuntimeError(f"Wellfound unavailable: {errors[0]}")
    return jobs[:results]