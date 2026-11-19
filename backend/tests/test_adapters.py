import base64

from app.sources import ats_source, naukri, wellfound


def test_wellfound_parse_data():
    data = {
        "StartupResult:1": {"name": "Acme AI",
                            "highlightedJobListings": [{"__ref": "JobListingSearchResult:99"}]},
        "JobListingSearchResult:99": {
            "id": 99, "title": "ML Engineer", "slug": "ml-engineer",
            "locationNames": ["Bengaluru"], "remote": True,
            "yearsExperienceMin": 1, "yearsExperienceMax": 3,
            "compensation": "₹10–20L", "liveStartAt": 1700000000,
            "description": "Python role",
        },
    }
    jobs = wellfound._parse_data(data)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.company == "Acme AI"
    assert j.source == "wellfound"
    assert (j.exp_min, j.exp_max) == (1.0, 3.0)
    assert j.is_remote is True
    assert j.url == "https://wellfound.com/jobs/99-ml-engineer"
    assert j.posted_text


def test_wellfound_parse_empty():
    assert wellfound._parse_data({}) == []


def test_naukri_parse_job():
    raw = {
        "jobId": "123", "title": "AI <b>Engineer</b>", "companyName": "Acme",
        "experienceText": "1-3 Yrs",
        "placeholders": [{"type": "location", "label": "Bengaluru"},
                         {"type": "salary", "label": "Not disclosed"}],
        "tagsAndSkills": "Python, RAG, LangChain",
        "jdURL": "/job-listings-ai-engineer-acme-123",
        "jobDescription": "<p>Build RAG pipelines</p>",
    }
    j = naukri._parse_job(raw)
    assert j.title == "AI Engineer"
    assert (j.exp_min, j.exp_max) == (1.0, 3.0)
    assert j.location == "Bengaluru"
    assert j.skills == ["Python", "RAG", "LangChain"]
    assert j.url.startswith("https://www.naukri.com/")
    assert j.description == "Build RAG pipelines"


def test_naukri_nkparam_shape():
    param = naukri.generate_nkparam()
    decoded = base64.b64decode(param)
    assert len(decoded) == 64  # RSA-512 PKCS1_v1_5 ciphertext


def test_ats_title_matches():
    assert ats_source._title_matches("AI Engineer", ["AI Engineer"])
    assert ats_source._title_matches("Senior Machine Learning Engineer", ["Machine Learning Engineer"])
    assert not ats_source._title_matches("Sales Manager", ["AI Engineer"])


def test_ats_location_matches():
    assert ats_source._location_matches("Bengaluru, India", False, ["Bengaluru"], True)
    assert ats_source._location_matches("Remote", True, [], True)
    assert not ats_source._location_matches("New York, US", False, ["Bengaluru"], False)