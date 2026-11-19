"""Naukri.com adapter via the public jobapi v3 search endpoint.

Approach from github.com/Traverser25/NopeRi: the search API requires an `nkparam`
header — an RSA-encrypted timestamp signed with Naukri's public frontend key.
No login is needed for search. Verified live: HTTP 200 with the full header set.
"""
import base64
import logging
import re
import time

import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from .base import NormalizedJob, parse_experience, strip_html

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.naukri.com/jobapi/v3/search"
PUBLIC_KEY = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBALrlQ+djR0RjJwBF1xuisHmdFv334MIm\n"
    "K6LgzJhmLhN7B5yuEyaKoasgXQk3+OQglsOaBxEJ0j5PcTL3nbOvt80CAwEAAQ==\n"
    "-----END PUBLIC KEY-----"
)
_cipher = PKCS1_v1_5.new(RSA.import_key(PUBLIC_KEY))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def generate_nkparam(page_type: str = "srp") -> str:
    plaintext = f"v0|{int(time.time() * 1000)}|121_{page_type}"
    return base64.b64encode(_cipher.encrypt(plaintext.encode("utf-8"))).decode("utf-8")


def _seo_key(keyword: str, location: str, page: int) -> str:
    kw = re.sub(r"\s+", "-", keyword.strip().lower()).replace("+", "-").strip("-")
    if location.strip():
        loc = re.sub(r"\s+", "-", location.strip().lower())
        return f"{kw}-jobs-in-{loc}-{page}"
    return f"{kw}-jobs-{page}"


def _headers() -> dict:
    return {
        "appid": "109",
        "systemid": "Naukri",
        "clientid": "d3skt0p",
        "gid": "LOCATION,INDUSTRY,EDUCATION,FAREA_ROLE",
        "nkparam": generate_nkparam("srp"),
        "accept": "application/json",
        "accept-language": "en-US,en;q=0.9",
        "User-Agent": UA,
        "referer": "https://www.naukri.com/",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    }


def _parse_job(raw: dict) -> NormalizedJob:
    placeholders = {p.get("type"): p.get("label", "") for p in raw.get("placeholders", [])}
    exp_text = raw.get("experienceText") or placeholders.get("experience", "")
    exp_min, exp_max = parse_experience(exp_text)
    location = placeholders.get("location", "")
    jd_url = raw.get("jdURL", "")
    if jd_url.startswith("/"):
        jd_url = "https://www.naukri.com" + jd_url
    skills = [s.strip() for s in (raw.get("tagsAndSkills") or "").split(",") if s.strip()]
    return NormalizedJob(
        source="naukri",
        source_id=str(raw.get("jobId") or raw.get("id") or ""),
        title=strip_html(raw.get("title") or raw.get("jobTitle") or ""),
        company=raw.get("companyName") or "",
        location=location,
        is_remote="remote" in location.lower() or "work from home" in location.lower(),
        salary=placeholders.get("salary", "") or raw.get("salaryDetail", "") or "",
        exp_min=exp_min,
        exp_max=exp_max,
        experience_text=exp_text,
        description=strip_html(raw.get("jobDescription") or ""),
        skills=skills,
        url=jd_url,
        posted_text=raw.get("footerPlaceholderLabel") or "",
    )


def search(keyword: str, location: str = "", experience: float = 1.0,
           job_age_days: int = 7, results: int = 30, pages: int = 1) -> list[NormalizedJob]:
    jobs: list[NormalizedJob] = []
    per_page = min(results, 20)
    for page in range(1, pages + 1):
        params = {
            "noOfResults": per_page,
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": keyword,
            "k": keyword,
            "pageNo": page,
            "experience": int(experience),
            "jobAge": job_age_days,
            "seoKey": _seo_key(keyword, location, page),
            "src": "jobsearchDesk",
            "nignbevent_src": "jobsearchDeskGNB",
            "latLong": "",
        }
        if location:
            params["location"] = location
        try:
            r = requests.get(SEARCH_URL, params=params, headers=_headers(), timeout=30)
        except requests.RequestException as e:
            raise RuntimeError(f"Naukri request failed: {e}") from e
        if r.status_code in (403, 406):
            raise RuntimeError(f"Naukri blocked (HTTP {r.status_code}) — nkparam may need refresh")
        if r.status_code == 400:
            logger.warning("Naukri 400 for keyword=%r: %s", keyword, r.text[:200])
            break
        r.raise_for_status()
        data = r.json()
        raw_jobs = data.get("jobDetails") or []
        if not raw_jobs:
            break
        jobs.extend(_parse_job(j) for j in raw_jobs)
        if len(jobs) >= results:
            break
        time.sleep(1.0)
    return jobs[:results]