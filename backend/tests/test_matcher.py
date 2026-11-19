from app.agents.matcher import experience_fit, job_skills, rank_jobs, skill_score
from app.sources.base import NormalizedJob, parse_experience, strip_html


def test_parse_experience_range():
    assert parse_experience("2-4 years of experience") == (2.0, 4.0)
    assert parse_experience("0 – 2 yrs") == (0.0, 2.0)


def test_parse_experience_plus_and_min():
    assert parse_experience("5+ years") == (5.0, None)
    assert parse_experience("minimum 3 years") == (3.0, None)


def test_parse_experience_fresher():
    assert parse_experience("Freshers welcome") == (0.0, 1.0)
    assert parse_experience("entry-level role") == (0.0, 1.0)


def test_parse_experience_none():
    assert parse_experience("competitive salary") == (None, None)
    assert parse_experience("") == (None, None)


def test_strip_html():
    assert strip_html("<p>Hello <b>world</b></p>\n") == "Hello world"


def test_dedupe_key_normalizes():
    a = NormalizedJob(source="naukri", title="AI Engineer!", company="Acme Corp", location="Bengaluru")
    b = NormalizedJob(source="indeed", title="ai engineer", company="ACME CORP", location="bengaluru")
    assert a.dedupe_key == b.dedupe_key


def test_experience_fit_buckets():
    assert experience_fit(1.2, 1.8, {"exp_min": 0, "exp_max": 2}) == (1.0, "fit")
    assert experience_fit(1.2, 1.8, {"exp_min": 2, "exp_max": 3}) == (0.65, "stretch")
    assert experience_fit(1.2, 1.8, {"exp_min": 4, "exp_max": 7}) == (0.1, "out_of_range")
    assert experience_fit(1.2, 1.8, {}) == (0.6, "unknown")


def test_experience_fit_senior_penalty():
    score, label = experience_fit(1.2, 1.8, {"title": "Lead Machine Learning Engineer"})
    assert (score, label) == (0.35, "senior_unknown")
    score, label = experience_fit(6.0, 1.8, {"title": "Senior AI Engineer"})
    assert (score, label) == (0.6, "unknown")


def test_skill_score_coverage():
    job = {"skills": ["python", "pytorch", "rag", "langchain"]}
    score, matched, missing = skill_score(["Python", "RAG"], job)
    assert score == 0.5
    assert matched == ["python", "rag"]
    assert missing == ["langchain", "pytorch"]


def test_skill_score_alias_canonicalization():
    score, matched, _ = skill_score(["large language model"], {"skills": ["LLM"]})
    assert score == 1.0
    assert matched == ["llm"]


def test_job_skills_detects_from_description():
    job = {"title": "ML Engineer", "skills": [], "description": "Must know Python, Docker and Kubernetes."}
    skills = job_skills(job)
    assert {"python", "docker", "kubernetes"} <= skills


def test_rank_jobs_filters_out_of_range():
    profile = {"skills": ["python"], "experience_years": 1.2, "exp_stretch": 1.8}
    jobs = [
        {"title": "Junior AI Engineer", "skills": ["python"], "exp_min": 0, "exp_max": 2},
        {"title": "Staff Engineer", "skills": ["python"], "exp_min": 8, "exp_max": 12},
    ]
    ranked = rank_jobs(jobs, profile)
    assert len(ranked) == 1
    assert ranked[0]["title"] == "Junior AI Engineer"
    assert 0 <= ranked[0]["match_score"] <= 100
    assert ranked[0]["score_breakdown"]["exp_fit"] == "fit"

    kept = rank_jobs(jobs, profile, include_out_of_range=True)
    assert len(kept) == 2
    assert kept[0]["match_score"] >= kept[1]["match_score"]


def test_rank_jobs_empty():
    assert rank_jobs([], {"skills": []}) == []