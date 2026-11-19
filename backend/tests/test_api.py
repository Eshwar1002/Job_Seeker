from pathlib import Path

from app.models import Job

FIXTURE = Path(__file__).parent / "fixtures" / "sample_resume.txt"


def _seed_job(db, **kw):
    defaults = dict(source="naukri", title="AI Engineer", company="Acme", location="Bengaluru",
                    dedupe_key=f"key-{kw.get('title', 'ai')}-{kw.get('company', 'acme')}",
                    match_score=70.0, skills=["python", "rag"], description="Python RAG role",
                    score_breakdown={"exp_fit": "fit"})
    defaults.update(kw)
    job = Job(**defaults)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _upload(client):
    return client.post("/api/profile/resume",
                       files={"file": ("sample_resume.txt", FIXTURE.read_bytes(), "text/plain")})


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "llm_providers" in r.json()


def test_profile_empty_then_upload(client, clean_db):
    assert client.get("/api/profile").json() is None
    assert client.put("/api/profile", json={"experience_years": 2}).status_code == 404

    r = _upload(client)
    assert r.status_code == 200
    p = r.json()
    assert p["experience_years"] == 1.2
    assert "langgraph" in p["skills"]
    assert p["target_roles"]

    r = client.put("/api/profile", json={"exp_stretch": 2.0, "preferred_locations": ["Pune"]})
    assert r.status_code == 200
    assert r.json()["exp_stretch"] == 2.0
    assert r.json()["preferred_locations"] == ["Pune"]


def test_upload_rejects_bad_type(client, clean_db):
    r = client.post("/api/profile/resume", files={"file": ("virus.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 400


def test_search_requires_profile(client, clean_db):
    r = client.post("/api/search", json={})
    assert r.status_code == 400


def test_jobs_list_and_filters(client, clean_db):
    _seed_job(clean_db, title="AI Engineer", company="Acme", source="naukri", match_score=80)
    _seed_job(clean_db, title="Data Analyst", company="Beta", source="indeed", match_score=40,
              dedupe_key="key-data-beta", score_breakdown={"exp_fit": "stretch"})

    jobs = client.get("/api/jobs").json()
    assert len(jobs) == 2
    assert jobs[0]["match_score"] >= jobs[1]["match_score"]

    assert len(client.get("/api/jobs", params={"q": "acme"}).json()) == 1
    assert len(client.get("/api/jobs", params={"source": "indeed"}).json()) == 1
    assert len(client.get("/api/jobs", params={"min_score": 50}).json()) == 1
    assert len(client.get("/api/jobs", params={"exp_fit": "stretch"}).json()) == 1
    assert len(client.get("/api/jobs", params={"status": "untracked"}).json()) == 2


def test_job_lifecycle_save_apply_rounds(client, clean_db):
    job = _seed_job(clean_db)

    r = client.post(f"/api/jobs/{job.id}/save")
    assert r.status_code == 200
    app = r.json()
    assert app["status"] == "saved"

    r = client.post(f"/api/jobs/{job.id}/track", json={"job_id": job.id, "status": "applied"})
    assert r.status_code == 200
    app = r.json()
    assert app["status"] == "applied"
    assert app["applied_at"]

    r = client.patch(f"/api/applications/{app['id']}",
                     json={"status": "in_process", "current_round": "Technical Round 1", "notes": "DSA round"})
    assert r.status_code == 200
    app = r.json()
    assert app["current_round"] == "Technical Round 1"
    assert app["notes"] == "DSA round"
    assert app["job"]["title"] == "AI Engineer"
    assert len(app["status_history"]) == 3

    r = client.patch(f"/api/applications/{app['id']}", json={"status": "rejected"})
    assert r.status_code == 200
    assert r.json()["current_round"] == ""

    assert client.patch(f"/api/applications/{app['id']}", json={"status": "bogus"}).status_code == 400

    apps = client.get("/api/applications", params={"status": "rejected"}).json()
    assert len(apps) == 1

    assert client.delete(f"/api/applications/{app['id']}").status_code == 200
    assert client.get("/api/applications").json() == []


def test_hide_and_404(client, clean_db):
    job = _seed_job(clean_db)
    assert client.post(f"/api/jobs/{job.id}/hide").status_code == 200
    assert client.get("/api/jobs").json() == []
    assert client.get("/api/jobs/999999").status_code == 404
    assert client.post("/api/jobs/999999/save").status_code == 404


def test_stats(client, clean_db):
    j1 = _seed_job(clean_db, title="J1", dedupe_key="k1")
    j2 = _seed_job(clean_db, title="J2", dedupe_key="k2")
    j3 = _seed_job(clean_db, title="J3", dedupe_key="k3")
    client.post(f"/api/jobs/{j1.id}/save")
    client.post(f"/api/jobs/{j2.id}/track", json={"job_id": j2.id, "status": "applied"})
    app3 = client.post(f"/api/jobs/{j3.id}/track", json={"job_id": j3.id, "status": "in_process"}).json()
    client.patch(f"/api/applications/{app3['id']}",
                 json={"status": "in_process", "current_round": "HR Round"})

    s = client.get("/api/stats").json()
    assert s["total_jobs"] == 3
    assert s["response_rate"] == 50.0
    assert sum(s["by_round"].values()) >= 1
    assert s["by_source"]["naukri"] == 3
    assert len(s["recent_activity"]) == 3


def test_enrich_fallback_insights(client, clean_db):
    _upload(client)
    job = _seed_job(clean_db, skills=["python", "rag", "kubernetes"],
                    score_breakdown={"matched_skills": ["python", "rag"], "missing_skills": ["kubernetes"]})
    r = client.post(f"/api/jobs/{job.id}/enrich")
    assert r.status_code == 200
    data = r.json()
    assert data["enriched"] is True
    assert data["insights"]["why_match"]