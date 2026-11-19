"""Hirist (hirist.tech) adapter — best effort.

Hirist renders job lists client-side via an XHR API guarded by a guest Bearer
token (hirist_seeker_enc cookie set by JS). This adapter tries the SEO listing
page's embedded state and JSON-LD; when Hirist serves an empty shell (bot
protection), it fails gracefully and the run notes report it.
"""
import json
import logging
import re

import requests

from .base import NormalizedJob, parse_experience

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _parse_preloaded(html: str) -> list[dict]:
    m = re.search(r"window\.__PRELOADED_STATE__\s*=\s*", html)
    if not m:
        return []
    try:
        obj, _ = json.JSONDecoder().raw_decode(html[m.end():])
        return obj.get("feed", {}).get("jobFeed") or []
    except (ValueError, AttributeError):
        return []


def _parse_jsonld(html: str) -> list[dict]:
    out = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            d = json.loads(block)
        except ValueError:
            continue
        items = d if isinstance(d, list) else [d]
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "JobPosting":
                out.append(it)
            elif isinstance(it, dict) and it.get("@type") == "ItemList":
                out.extend(x for x in it.get("itemListElement", []) if isinstance(x, dict) and x.get("title"))
    return out


def search(queries: list[str], locations: list[str] | None = None, results: int = 30) -> list[NormalizedJob]:
    jobs, seen = [], set()
    loc = (locations or ["bangalore"])[0]
    for q in queries[:2]:
        url = f"https://www.hirist.tech/{_slugify(q)}-jobs-in-{_slugify(loc)}"
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
            r.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"Hirist request failed: {e}") from e
        raw = _parse_preloaded(r.text)
        for j in raw:
            jid = str(j.get("jobId") or j.get("id") or "")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            exp_text = j.get("experience") or f"{j.get('minExp', '')}-{j.get('maxExp', '')} Yrs"
            exp_min, exp_max = parse_experience(str(exp_text))
            jobs.append(NormalizedJob(
                source="hirist", source_id=jid,
                title=j.get("title") or j.get("jobTitle") or "",
                company=j.get("companyName") or (j.get("company") or {}).get("name", ""),
                location=j.get("location") or ", ".join(j.get("locations") or []),
                exp_min=exp_min, exp_max=exp_max, experience_text=str(exp_text),
                description=j.get("jobDescription") or j.get("description") or "",
                skills=[s.strip() for s in (j.get("skills") or j.get("tagsAndSkills") or "").split(",") if s.strip()]
                       if isinstance(j.get("skills") or j.get("tagsAndSkills"), str) else (j.get("skills") or []),
                url=j.get("jobUrl") or f"https://www.hirist.tech/j/{jid}",
                posted_text=j.get("postedDate") or "",
            ))
        for j in _parse_jsonld(r.text):
            title = j.get("title", "")
            if not title or title in seen:
                continue
            seen.add(title)
            jobs.append(NormalizedJob(
                source="hirist", title=title,
                company=(j.get("hiringOrganization") or {}).get("name", ""),
                location=str((j.get("jobLocation") or {}).get("address", {}).get("addressLocality", "")),
                description=j.get("description", ""), url=j.get("url", url),
                posted_text=(j.get("datePosted") or "")[:10],
            ))
    if not jobs:
        raise RuntimeError("Hirist serves jobs via authenticated XHR (bot protection) — no public data in page")
    return jobs[:results]