from datetime import datetime

from pydantic import BaseModel, Field


class ProfileOut(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    current_role: str
    experience_years: float
    skills: list[str]
    work_history: list[dict]
    education: list[dict]
    projects: list[dict]
    certifications: list[str]
    target_roles: list[str]
    preferred_locations: list[str]
    remote_ok: bool
    exp_stretch: float
    resume_filename: str
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    name: str | None = None
    current_role: str | None = None
    experience_years: float | None = None
    skills: list[str] | None = None
    target_roles: list[str] | None = None
    preferred_locations: list[str] | None = None
    remote_ok: bool | None = None
    exp_stretch: float | None = Field(default=None, ge=0, le=5)


class SearchRequest(BaseModel):
    keywords: list[str] | None = None
    locations: list[str] | None = None
    platforms: list[str] = Field(default_factory=lambda: ["naukri", "indeed", "linkedin", "glassdoor", "company_site", "wellfound", "hirist"])
    hours_old: int = Field(default=168, ge=1, le=720)
    results_per_site: int = Field(default=30, ge=5, le=100)
    experience: float | None = None
    remote_only: bool = False


class SearchRunOut(BaseModel):
    id: int
    params: dict
    status: str
    progress: str
    stats: dict
    error: str
    started_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: int
    source: str
    title: str
    company: str
    location: str
    is_remote: bool
    salary: str
    exp_min: float | None
    exp_max: float | None
    experience_text: str
    description: str
    skills: list[str]
    url: str
    posted_text: str
    posted_at: datetime | None
    fetched_at: datetime
    match_score: float
    score_breakdown: dict
    insights: dict
    enriched: bool
    application: "ApplicationOut | None" = None

    model_config = {"from_attributes": True}


class ApplicationCreate(BaseModel):
    job_id: int
    status: str = "saved"


class ApplicationUpdate(BaseModel):
    status: str | None = None
    current_round: str | None = None
    notes: str | None = None


class ApplicationOut(BaseModel):
    id: int
    job_id: int
    status: str
    current_round: str
    notes: str
    status_history: list[dict]
    applied_at: datetime | None
    created_at: datetime
    updated_at: datetime
    job: dict | None = None

    model_config = {"from_attributes": True}


class StatsOut(BaseModel):
    total_jobs: int
    saved: int
    applied: int
    in_process: int
    offer: int
    rejected: int
    ghosted: int
    response_rate: float
    avg_match_score: float
    by_source: dict[str, int]
    by_round: dict[str, int]
    recent_activity: list[dict]


JobOut.model_rebuild()
ApplicationOut.model_rebuild()


class TailorSave(BaseModel):
    content: str


class TailoredResumeOut(BaseModel):
    id: int
    job_id: int
    content: str
    base_ats_score: float
    ats_score: float
    keywords_added: list[str]
    gaps: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}