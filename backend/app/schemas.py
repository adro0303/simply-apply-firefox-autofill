"""Pydantic contracts shared by the API, the LLM layer, and the renderers.

The resume shape is a subset of the JSON Resume standard (https://jsonresume.org) rather
than a bespoke schema. That buys interop with existing themes/tooling and means a
contributor already knows the field names.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- jobs


class JobRecord(BaseModel):
    """Normalized posting. Every connector returns these, whatever the upstream shape."""

    id: str
    source: str
    title: str
    company: str
    location: str = ""
    remote: bool = False
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    posted_at: datetime | None = None
    apply_url: str
    description: str = ""


class SearchQuery(BaseModel):
    query: str = ""
    location: str = ""
    remote_only: bool = False
    limit: int = 50

    def cache_key(self) -> str:
        return f"{self.query.strip().lower()}|{self.location.strip().lower()}|{self.remote_only}"


class SearchResponse(BaseModel):
    jobs: list[JobRecord]
    sources_ok: list[str]
    sources_failed: dict[str, str] = Field(default_factory=dict)
    from_cache: bool = False


class AdhocJobIn(BaseModel):
    """A job page the extension scraped itself — not from a connector SimplyApply runs."""

    company: str = Field(max_length=200)
    title: str = Field(max_length=200)
    description: str = Field(max_length=50_000)
    apply_url: str = Field(max_length=200)
    location: str = ""
    remote: bool = False


# ------------------------------------------------------------------------ resume


class Location(BaseModel):
    city: str = ""
    region: str = ""
    countryCode: str = ""


class Profile(BaseModel):
    network: str = ""
    username: str = ""
    url: str = ""


class Basics(BaseModel):
    name: str = ""
    label: str = ""
    email: str = ""
    phone: str = ""
    url: str = ""
    summary: str = ""
    location: Location = Field(default_factory=Location)
    profiles: list[Profile] = Field(default_factory=list)


class Work(BaseModel):
    name: str = ""  # employer — JSON Resume calls this `name`
    position: str = ""
    url: str = ""
    startDate: str = ""
    endDate: str = ""
    location: str = ""
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str = ""
    area: str = ""
    studyType: str = ""
    startDate: str = ""
    endDate: str = ""
    score: str = ""
    courses: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    name: str = ""
    level: str = ""
    keywords: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str = ""
    description: str = ""
    url: str = ""
    startDate: str = ""
    endDate: str = ""
    highlights: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class StructuredResume(BaseModel):
    basics: Basics = Field(default_factory=Basics)
    work: list[Work] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)


class ResumeOut(BaseModel):
    id: int
    name: str
    is_base: bool
    created_at: datetime
    tailored_for_job_id: str | None = None
    data: StructuredResume


# ----------------------------------------------------------------------- tailoring


class GuardrailViolation(BaseModel):
    kind: str  # employer | title | date | metric | skill | contact
    value: str
    where: str
    detail: str


class TailorResult(BaseModel):
    resume: StructuredResume
    changed: bool
    fell_back: bool = False
    violations: list[GuardrailViolation] = Field(default_factory=list)
    warning: str | None = None
    notes: list[str] = Field(default_factory=list)


class CoverLetterResult(BaseModel):
    body: str
    changed: bool
    fell_back: bool = False
    violations: list[GuardrailViolation] = Field(default_factory=list)
    warning: str | None = None


class ApplyResponse(BaseModel):
    application_id: int
    resume_id: int
    job: JobRecord
    docx_url: str | None = None
    pdf_url: str | None = None
    pdf_error: str | None = None
    tailoring: TailorResult


# ------------------------------------------------------------------------ settings


class SettingsOut(BaseModel):
    llm_provider: str
    model: str
    has_key: bool
    ollama_host: str
    openai_base_url: str
    enabled_sources: list[str]
    available_sources: list[str]
    cache_ttl_minutes: int


class SettingsIn(BaseModel):
    llm_provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    ollama_host: str | None = None
    openai_base_url: str | None = None
    enabled_sources: list[str] | None = None
    greenhouse_companies: list[str] | None = None


class ApplicationOut(BaseModel):
    id: int
    job_id: str
    resume_id: int
    applied_at: datetime
    status: str
    notes: str
    title: str = ""
    company: str = ""
    apply_url: str = ""
    docx_url: str | None = None
    pdf_url: str | None = None


class ApplicationDetail(BaseModel):
    """Everything the extension needs for a page it recognizes: what was sent, and how."""

    application: ApplicationOut
    resume: StructuredResume
    cover_letter: str | None = None
    cover_letter_fell_back: bool = False
