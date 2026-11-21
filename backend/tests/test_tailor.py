from pathlib import Path

from app.agents import resume_tailor as rt
from app.models import Job

FIXTURE = Path(__file__).parent / "fixtures" / "sample_resume.txt"


def _seed_job(db, score=90.0, **kw):
    defaults = dict(source="naukri", title="AI Engineer", company="Acme", location="Bengaluru",
                    dedupe_key=f"tailor-{score}-{kw.get('title', 'ai')}", match_score=score,
                    skills=["python", "kubernetes"], description="Python and Kubernetes role.")
    defaults.update(kw)
    job = Job(**defaults)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _upload(client):
    return client.post("/api/profile/resume",
                       files={"file": ("sample_resume.txt", FIXTURE.read_bytes(), "text/plain")})


def test_extract_jd_keywords():
    kws = rt.extract_jd_keywords({"title": "ML Engineer", "skills": ["Python"],
                                  "description": "Must know Docker and Kubernetes."})
    assert {"python", "docker", "kubernetes"} <= set(kws)


def test_classify_gaps_add_vs_learn():
    profile = {"skills": [], "raw_text": "Built LLMs and RAG pipelines."}
    job = {"skills": ["llm", "rag", "kubernetes"], "description": "", "title": ""}
    gaps = rt.classify_gaps(profile, job)
    assert "rag" in gaps["present"]
    add_kw = [g["keyword"] for g in gaps["add"]]
    learn_kw = [g["keyword"] for g in gaps["learn"]]
    assert "llm" in add_kw          # evidenced as plural "LLMs" -> safe to rephrase
    assert "kubernetes" in learn_kw  # true gap -> learn, never auto-add
    assert gaps["add"][0]["evidence"]


def test_learn_gap_always_has_resource():
    profile = {"skills": [], "raw_text": "Python developer."}
    job = {"skills": ["kubernetes", "flask"], "description": "", "title": ""}
    gaps = rt.classify_gaps(profile, job)
    by_kw = {g["keyword"]: g["resource"] for g in gaps["learn"]}
    assert by_kw["kubernetes"] == rt.LEARN_RESOURCES["kubernetes"]  # curated official doc
    assert by_kw["flask"].startswith("https://www.google.com/search?q=")  # fallback for uncurated
    assert all(g["resource"] for g in gaps["learn"])  # every learn gap is actionable


def test_ats_score_improves_with_keywords():
    job = {"title": "Platform Engineer", "skills": ["python", "kubernetes"],
           "description": "Python and Kubernetes role."}
    before = rt.ats_score("Python developer.", job)
    after = rt.ats_score("Python developer. Kubernetes operator.", job)
    assert before["components"]["keyword_match"] == 0.5
    assert after["components"]["keyword_match"] == 1.0
    assert after["score"] > before["score"]
    assert "kubernetes" in before["missing_keywords"]
    assert "kubernetes" not in after["missing_keywords"]


def test_ats_parse_warnings():
    res = rt.ats_score("short text", {"title": "x", "skills": [], "description": ""})
    assert res["parse_warnings"]


def test_build_draft_heuristic_no_fabrication():
    profile = {"raw_text": "Python dev with RAG.", "skills": ["python", "rag"]}
    job = {"title": "AI Engineer", "skills": ["python", "rag"], "description": ""}
    gaps = rt.classify_gaps(profile, job)
    draft = rt.build_draft(profile, job, gaps)
    assert draft["method"] == "heuristic"
    assert "Python dev with RAG." in draft["content"]


def test_tailor_gate_and_flow(client, clean_db):
    _upload(client)
    low = _seed_job(clean_db, score=50.0, title="Low")
    high = _seed_job(clean_db, score=90.0, title="High")

    assert client.get(f"/api/jobs/{low.id}/tailor").status_code == 403
    assert client.get(f"/api/jobs/{high.id}/tailor").status_code == 200

    analysis = client.get(f"/api/jobs/{high.id}/tailor").json()
    assert analysis["match_score"] == 90.0
    master = analysis["master_content"]

    edited = master + "\nTARGETED SKILLS: Kubernetes"
    score = client.post(f"/api/jobs/{high.id}/tailor/score", json={"content": edited}).json()
    assert score["score"] >= analysis["base_ats"]["score"]

    saved = client.post(f"/api/jobs/{high.id}/tailor", json={"content": edited}).json()
    assert saved["ats_score"] == score["score"]
    assert "kubernetes" in saved["keywords_added"]

    assert client.get(f"/api/jobs/{high.id}/tailor/export?format=txt").status_code == 200
    assert client.get(f"/api/jobs/{high.id}/tailor/export?format=docx").status_code == 200
    assert client.get(f"/api/jobs/{high.id}/tailor/export?format=pdf").status_code == 422

    listed = client.get("/api/tailored").json()
    assert len(listed) == 1 and listed[0]["job_id"] == high.id

    draft = client.post(f"/api/jobs/{high.id}/tailor/draft").json()
    assert draft["content"]