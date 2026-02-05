"""Extraction prompts for resume parsing.

Prompt version is tied to EXTRACTION_VERSION env var.
When prompt changes significantly, bump the version to trigger re-extraction.
"""

from __future__ import annotations

import os

# Prompt version - bump this when prompt logic changes significantly
# Format: YYYY-MM-DD.N where N is revision number
EXTRACTION_PROMPT_VERSION = os.getenv("EXTRACTION_VERSION", "2026-02-05.1")

RESUME_EXTRACTION_SYSTEM = """You are a resume parser that extracts structured information from resume text.

OUTPUT FORMAT:
Return ONLY valid JSON matching this schema:
{
  "current_title": "string",
  "primary_titles": ["string", ...],
  "seniority": "intern|junior|mid|senior|staff|lead|manager|director|vp|cxo",
  "skills_raw": ["string", ...],
  "skills_normalized": ["string", ...],
  "total_years_experience": <number or "X-Y" or null>,
  "years_by_skill": { "skill": number, ... },
  "domains": ["string", ...],
  "functions": ["string", ...],
  "location": {
    "city": "string",
    "country": "string",
    "remote_preference": "onsite|hybrid|remote|any",
    "work_authorization": "string",
    "open_to_relocate": true|false
  },
  "certifications": ["string", ...],
  "confidence": 0.XX
}

EXTRACTION RULES:
1. current_title: Most recent or current job title (not company)
2. primary_titles: 1-3 canonical titles inferred from role history
3. seniority: Normalize to one of the allowed values; leave null if uncertain
4. skills_raw: Concrete, searchable skills (languages, frameworks, tools, methodologies)
   - Good: "Python", "React", "AWS", "Agile", "SQL", "Machine Learning"
   - Bad: "Programming", "Technical Skills", "Software Development"
5. skills_normalized: Lowercased canonical tokens (e.g., "postgresql", "fastapi")
6. total_years_experience: Total professional experience
   - Use number if clear (5), range if uncertain ("3-5"), null if unknown
7. years_by_skill: Only if explicitly stated; use numbers (years)
8. domains: Industry/domain tags (e.g., FinTech, Healthcare, B2B SaaS)
9. functions: Functional tags (backend, data, ML, product, DevOps, QA)
10. location: Include if explicit. Use nulls for missing fields.
11. certifications: Only include actual certifications (AWS, PMP, CPA, etc.)

confidence:
  - 0.9+: Clear, well-structured resume with explicit information
  - 0.7-0.9: Reasonable extraction with some inference
  - 0.5-0.7: Significant inference or unclear text
  - <0.5: Poor quality text or minimal extractable information

IMPORTANT:
- Return ONLY the JSON object, no explanations or markdown
- If text is not a resume or contains no extractable info, return minimal JSON with low confidence
- Prefer precision over recall - only include skills you're confident about"""

RESUME_EXTRACTION_USER = """Extract structured information from this resume text:

---
{resume_text}
---

Return JSON only:"""


# Configurable limits
EXTRACTION_MAX_INPUT_CHARS = int(os.getenv("EXTRACTION_MAX_INPUT_CHARS", "12000"))


def build_extraction_prompt(resume_text: str) -> tuple[str, str]:
    """Build extraction prompt for resume text.

    Args:
        resume_text: Raw resume text to extract from

    Returns:
        Tuple of (system_message, user_prompt)
    """
    # Truncate very long resumes to avoid token limits
    max_chars = EXTRACTION_MAX_INPUT_CHARS
    if len(resume_text) > max_chars:
        resume_text = resume_text[:max_chars] + "\n\n[... truncated ...]"

    user_prompt = RESUME_EXTRACTION_USER.format(resume_text=resume_text)
    return RESUME_EXTRACTION_SYSTEM, user_prompt


def get_extraction_version() -> str:
    """Get current extraction version from env or default."""
    return os.getenv("EXTRACTION_VERSION", EXTRACTION_PROMPT_VERSION)
