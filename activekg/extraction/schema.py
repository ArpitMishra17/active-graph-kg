"""Pydantic schemas for resume extraction output."""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Configurable caps
MAX_PRIMARY_SKILLS = max(0, int(os.getenv("EXTRACTION_MAX_PRIMARY_SKILLS", "12")))
MAX_RECENT_TITLES = max(0, int(os.getenv("EXTRACTION_MAX_RECENT_TITLES", "3")))
MAX_CERTIFICATIONS = max(0, int(os.getenv("EXTRACTION_MAX_CERTIFICATIONS", "10")))
MAX_INDUSTRIES = max(0, int(os.getenv("EXTRACTION_MAX_INDUSTRIES", "5")))
MAX_PRIMARY_TITLES = max(0, int(os.getenv("EXTRACTION_MAX_PRIMARY_TITLES", "3")))
MAX_SKILLS_RAW = max(0, int(os.getenv("EXTRACTION_MAX_SKILLS_RAW", "15")))
MAX_SKILLS_NORMALIZED = max(0, int(os.getenv("EXTRACTION_MAX_SKILLS_NORMALIZED", "15")))
MAX_DOMAINS = max(0, int(os.getenv("EXTRACTION_MAX_DOMAINS", "5")))
MAX_FUNCTIONS = max(0, int(os.getenv("EXTRACTION_MAX_FUNCTIONS", "5")))
MAX_YEARS_BY_SKILL = max(0, int(os.getenv("EXTRACTION_MAX_YEARS_BY_SKILL", "10")))

_SENIORITY_ALLOWED = {
    "intern",
    "junior",
    "mid",
    "senior",
    "staff",
    "lead",
    "manager",
    "director",
    "vp",
    "cxo",
}


class LocationInfo(BaseModel):
    """Optional location-related attributes."""

    city: str | None = None
    country: str | None = None
    remote_preference: str | None = None
    work_authorization: str | None = None
    open_to_relocate: bool | None = None


class ExtractionResult(BaseModel):
    """Structured extraction output from resume parsing."""

    # Phase 2A fields (must-have)
    current_title: str | None = Field(default=None, description="Most recent or current job title")
    primary_titles: list[str] = Field(
        default_factory=list,
        description="1-3 canonical titles (normalized)",
        min_length=0,
        max_length=MAX_PRIMARY_TITLES or 1,
    )
    seniority: str | None = Field(
        default=None,
        description="Seniority level (intern/junior/mid/senior/staff/lead/manager/director/vp/cxo)",
    )
    skills_raw: list[str] = Field(
        default_factory=list,
        description="Top skills as raw phrases",
        min_length=0,
        max_length=MAX_SKILLS_RAW or 1,
    )
    skills_normalized: list[str] = Field(
        default_factory=list,
        description="Normalized skills (lowercased canonical tokens)",
        min_length=0,
        max_length=MAX_SKILLS_NORMALIZED or 1,
    )
    total_years_experience: int | float | str | None = Field(
        default=None,
        description="Total years of experience (number or bucket like '5-7')",
    )
    years_by_skill: dict[str, int | float] | None = Field(
        default=None,
        description="Years of experience by skill (skill -> years)",
    )
    domains: list[str] = Field(
        default_factory=list,
        description="Industry or domain tags (e.g., FinTech, Healthcare)",
        min_length=0,
        max_length=MAX_DOMAINS or 1,
    )
    functions: list[str] = Field(
        default_factory=list,
        description="Functional tags (backend, data, ML, product, etc.)",
        min_length=0,
        max_length=MAX_FUNCTIONS or 1,
    )
    location: LocationInfo | None = Field(
        default=None, description="Location + work authorization preferences"
    )

    # Optional fields
    certifications: list[str] | None = Field(
        default=None,
        description="Professional certifications (AWS, PMP, etc.)",
    )
    industries: list[str] | None = Field(
        default=None,
        description="Industries worked in (e.g., 'Finance', 'Healthcare', 'Tech')",
    )

    # Legacy fields (kept for backward compatibility)
    primary_skills: list[str] = Field(
        default_factory=list,
        description="Legacy: top skills list",
        min_length=0,
        max_length=MAX_PRIMARY_SKILLS or 1,
    )
    recent_job_titles: list[str] = Field(
        default_factory=list,
        description="Legacy: most recent job titles",
        min_length=0,
        max_length=MAX_RECENT_TITLES or 1,
    )
    years_experience_total: int | str | None = Field(
        default=None,
        description="Legacy: total years of experience",
    )

    # Extraction metadata
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence score (0-1)",
    )

    @field_validator("primary_skills", mode="before")
    @classmethod
    def clean_skills(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        # Dedupe and limit to configured cap
        seen: set[str] = set()
        result: list[str] = []
        for skill in v:
            normalized = skill.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(skill.strip())
        return result[:MAX_PRIMARY_SKILLS]

    @field_validator("skills_raw", mode="before")
    @classmethod
    def clean_skills_raw(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        seen: set[str] = set()
        result: list[str] = []
        for skill in v:
            normalized = skill.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(skill.strip())
        return result[:MAX_SKILLS_RAW]

    @field_validator("skills_normalized", mode="before")
    @classmethod
    def clean_skills_normalized(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        seen: set[str] = set()
        result: list[str] = []
        for skill in v:
            normalized = str(skill).strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result[:MAX_SKILLS_NORMALIZED]

    @field_validator("recent_job_titles", mode="before")
    @classmethod
    def clean_titles(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        # Dedupe and limit to configured cap
        seen: set[str] = set()
        result: list[str] = []
        for title in v:
            normalized = title.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(title.strip())
        return result[:MAX_RECENT_TITLES]

    @field_validator("primary_titles", mode="before")
    @classmethod
    def clean_primary_titles(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        seen: set[str] = set()
        result: list[str] = []
        for title in v:
            normalized = title.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(title.strip())
        return result[:MAX_PRIMARY_TITLES]

    @field_validator("seniority", mode="before")
    @classmethod
    def clean_seniority(cls, v: str | None) -> str | None:
        if not v:
            return None
        normalized = str(v).strip().lower()
        if normalized in _SENIORITY_ALLOWED:
            return normalized
        return None

    @field_validator("certifications", mode="before")
    @classmethod
    def clean_certifications(cls, v: list[str] | None) -> list[str] | None:
        if not v:
            return None
        # Dedupe and limit to configured cap
        seen: set[str] = set()
        result: list[str] = []
        for cert in v:
            normalized = cert.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(cert.strip())
        return result[:MAX_CERTIFICATIONS] if result else None

    @field_validator("domains", mode="before")
    @classmethod
    def clean_domains(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        seen: set[str] = set()
        result: list[str] = []
        for domain in v:
            normalized = domain.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(domain.strip())
        return result[:MAX_DOMAINS]

    @field_validator("functions", mode="before")
    @classmethod
    def clean_functions(cls, v: list[str] | None) -> list[str]:
        if not v:
            return []
        seen: set[str] = set()
        result: list[str] = []
        for fn in v:
            normalized = fn.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(fn.strip())
        return result[:MAX_FUNCTIONS]

    @field_validator("years_by_skill", mode="before")
    @classmethod
    def clean_years_by_skill(
        cls, v: dict[str, int | float] | None
    ) -> dict[str, int | float] | None:
        if not v:
            return None
        out: dict[str, int | float] = {}
        for k, val in v.items():
            key = str(k).strip().lower()
            if not key:
                continue
            try:
                num = float(val)
            except Exception:
                continue
            if num < 0:
                continue
            out[key] = int(num) if num.is_integer() else num
            if MAX_YEARS_BY_SKILL and len(out) >= MAX_YEARS_BY_SKILL:
                break
        return out or None

    @field_validator("industries", mode="before")
    @classmethod
    def clean_industries(cls, v: list[str] | None) -> list[str] | None:
        if not v:
            return None
        # Dedupe and limit to configured cap
        seen: set[str] = set()
        result: list[str] = []
        for industry in v:
            normalized = industry.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(industry.strip())
        return result[:MAX_INDUSTRIES] if result else None

    def has_required_fields(self) -> bool:
        """Check if extraction has minimum required fields."""
        return (
            len(self.skills_raw) >= 1
            or len(self.skills_normalized) >= 1
            or len(self.primary_titles) >= 1
            or bool(self.current_title)
            or len(self.primary_skills) >= 1
            or len(self.recent_job_titles) >= 1
        )

    def to_props(self) -> dict:
        """Convert to node props dict for storage."""
        props: dict = {}

        # Primary Phase 2A fields
        if self.current_title:
            props["current_title"] = self.current_title
        if self.primary_titles:
            props["primary_titles"] = self.primary_titles
        if self.seniority:
            props["seniority"] = self.seniority
        if self.skills_raw:
            props["skills_raw"] = self.skills_raw
        if self.skills_normalized:
            props["skills_normalized"] = self.skills_normalized
        if self.total_years_experience is not None:
            props["total_years_experience"] = self.total_years_experience
        if self.years_by_skill:
            props["years_by_skill"] = self.years_by_skill
        if self.domains:
            props["domains"] = self.domains
        if self.functions:
            props["functions"] = self.functions
        if self.location:
            loc = self.location.model_dump(exclude_none=True)
            if loc:
                props["location"] = loc
        if self.certifications:
            props["certifications"] = self.certifications
        if self.industries:
            props["industries"] = self.industries
        elif self.domains:
            props["industries"] = self.domains

        # Backfill legacy fields if missing
        primary_skills = self.primary_skills or self.skills_raw
        if primary_skills:
            props["primary_skills"] = primary_skills[:MAX_PRIMARY_SKILLS]
        recent_titles = self.recent_job_titles or self.primary_titles
        if not recent_titles and self.current_title:
            recent_titles = [self.current_title]
        if recent_titles:
            props["recent_job_titles"] = recent_titles[:MAX_RECENT_TITLES]
        if self.years_experience_total is not None:
            props["years_experience_total"] = self.years_experience_total
        elif self.total_years_experience is not None:
            props["years_experience_total"] = self.total_years_experience
        if self.industries and not props.get("industries"):
            props["industries"] = self.industries

        # Auto-fill skills_normalized if missing and raw exists
        if not props.get("skills_normalized") and props.get("skills_raw"):
            normalized = []
            for s in props["skills_raw"]:
                key = str(s).strip().lower()
                if key and key not in normalized:
                    normalized.append(key)
            props["skills_normalized"] = normalized[:MAX_SKILLS_NORMALIZED]

        return props


class ExtractionStatus(BaseModel):
    """Extraction status metadata stored in node props."""

    status: Literal["queued", "processing", "ready", "failed", "skipped"] = "queued"
    error: str | None = None
    confidence: float | None = None
    extracted_at: str | None = None
    extraction_version: str | None = None
    model_used: str | None = None

    def to_props(self) -> dict:
        """Convert to node props dict for storage."""
        return {
            "extraction_status": self.status,
            "extraction_error": self.error,
            "extraction_confidence": self.confidence,
            "extracted_at": self.extracted_at,
            "extraction_version": self.extraction_version,
            "extraction_model": self.model_used,
        }
