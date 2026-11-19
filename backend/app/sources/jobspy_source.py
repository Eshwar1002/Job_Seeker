"""LinkedIn / Indeed / Glassdoor adapter backed by the JobSpy repo (github.com/cullenwatson/JobSpy)."""
import logging
import math
from datetime import datetime

from .base import NormalizedJob, parse_experience, strip_html

logger = logging.getLogger(__name__)

SUPPORTED = {"linkedin", "indeed", "glassdoor"}


def _clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def _salary(row: dict) -> str:
    lo, hi = row.get("min_amount"), row.get("max_amount")
    currency = _clean(row.get("currency"))
    interval = _clean(row.get("interval"))
    try:
        lo_f = float(lo) if lo is not None and not (isinstance(lo, float) and math.isnan(lo)) else None
        hi_f = float(hi) if hi is not None and not (isinstance(hi, float) and math.isnan(hi)) else None
    except (TypeError, ValueError):
        return ""
    if lo_f is None and hi_f is None:
        return ""
    unit = f"{currency} " if currency else ""
    per = f"/{interval}" if interval else ""
    if lo_f is not None and hi_f is not None and lo_f != hi_f:
        return f"{unit}{lo_f:,.0f} - {hi_f:,.0f}{per}"
    return f"{unit}{(hi_f or lo_f):,.0f}{per}"


def search(sites: list[str], keyword: str, location: str = "India",
           results: int = 30, hours_old: int = 168, country: str = "India") -> list[NormalizedJob]:
    from jobspy import scrape_jobs

    sites = [s for s in sites if s in SUPPORTED]
    if not sites:
        return []
    try:
        df = scrape_jobs(
            site_name=sites,
            search_term=keyword,
            location=location,
            results_wanted=results,
            hours_old=hours_old,
            country_indeed=country,
            linkedin_fetch_description=True,
            verbose=0,
        )
    except Exception as e:
        raise RuntimeError(f"JobSpy failed: {e}") from e
    if df is None or df.empty:
        return []

    jobs = []
    for _, row in df.iterrows():
        row = row.to_dict()
        description = strip_html(_clean(row.get("description")))
        exp_text = _clean(row.get("experience_range")) or _clean(row.get("job_level"))
        exp_min, exp_max = parse_experience(exp_text)
        if exp_min is None:
            exp_min, exp_max = parse_experience(description[:3000])
        posted = row.get("date_posted")
        posted_at = None
        if posted is not None and not (isinstance(posted, float) and math.isnan(posted)):
            try:
                posted_at = datetime.combine(posted, datetime.min.time()) if hasattr(posted, "year") else None
            except Exception:
                posted_at = None
        raw_skills = row.get("skills")
        skills = [s.strip() for s in _clean(raw_skills).split(",") if s.strip()] if raw_skills is not None else []
        jobs.append(NormalizedJob(
            source=_clean(row.get("site")) or "jobspy",
            source_id=_clean(row.get("id")),
            title=_clean(row.get("title")),
            company=_clean(row.get("company")),
            location=_clean(row.get("location")),
            is_remote=bool(row.get("is_remote")) if row.get("is_remote") is not None else False,
            salary=_salary(row),
            exp_min=exp_min,
            exp_max=exp_max,
            experience_text=exp_text,
            description=description,
            skills=skills,
            url=_clean(row.get("job_url_direct")) or _clean(row.get("job_url")),
            posted_text=posted_at.strftime("%Y-%m-%d") if posted_at else "",
            posted_at=posted_at,
        ))
    return [j for j in jobs if j.title]