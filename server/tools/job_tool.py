"""
Job Description Inference Tool.
Generates required skills and responsibilities based on job title and company.
"""

import asyncio
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from server.services.llm_factory import get_chat_model
from server.config import settings


# ============== JD Inference Prompt ==============

JD_INFERENCE_SYSTEM_PROMPT = """You are a Senior Technical Recruiter with 15+ years of experience at top tech companies.
You have deep knowledge of what skills and responsibilities are required for various technical roles.

When given a Job Title and Company, provide a comprehensive breakdown of requirements.
You MUST respond with ONLY valid JSON, no other text. Use this exact structure:

{
  "job_title": "the job title",
  "company": "the company name",
  "must_have_skills": [
    "10 essential technical skills that are absolutely required"
  ],
  "nice_to_have_skills": [
    "5 additional skills that would be beneficial"
  ],
  "core_responsibilities": [
    "5 main job responsibilities"
  ],
  "typical_experience": "typical years of experience required",
  "salary_range": "estimated salary range (if applicable)",
  "career_level": "entry/mid/senior/staff/principal",
  "interview_focus_areas": [
    "3-5 areas likely to be covered in interviews"
  ]
}

Be specific and realistic based on current industry standards."""


JD_ANALYSIS_SYSTEM_PROMPT = """You are a job description analyst.
Extract a clean hiring profile from the role details provided.
Return JSON only using this exact structure:
{
  "job_title": "the role title",
  "company": "the company name",
  "must_have_skills": ["required skills"],
  "nice_to_have_skills": ["preferred skills"],
  "core_responsibilities": ["key responsibilities"],
  "career_level": "entry|mid|senior|staff|principal",
  "interview_focus_areas": ["likely interview themes"]
}
Rules:
- Use the key career_level exactly.
- Keep must_have_skills to 6-12 items.
- Keep nice_to_have_skills to 0-8 items.
- Prefer concrete technical or role-execution skills over vague traits.
- If the job description is sparse, infer realistic skills from the title and company context."""


# ============== JD Analysis Functions ==============

async def analyze_job_description(
    job_title: str,
    company: str = "a top tech company",
    jd_text: str = ""
) -> dict[str, Any]:
    """
    Build a structured job profile from a job description or role metadata.
    """
    chat_model = get_chat_model()

    if jd_text and jd_text.strip():
        prompt = {
            "job_title": job_title,
            "company": company,
            "job_description": jd_text[:3000],
        }
    else:
        prompt = {
            "job_title": job_title,
            "company": company,
            "job_description": "",
            "instruction": "Infer a realistic hiring profile from the role title and company context.",
        }

    result = await chat_model.ainvoke(
        [
            SystemMessage(content=JD_ANALYSIS_SYSTEM_PROMPT),
            HumanMessage(content=json.dumps(prompt)),
        ],
        json_mode=True,
        max_tokens=min(int(getattr(settings, "LLM_JSON_MAX_TOKENS", 500)), 700),
    )
    response_text = result.content

    from server.tools.resume_tool import parse_json_safely

    parsed = parse_json_safely(response_text)
    if not parsed or not isinstance(parsed, dict):
        return {
            "job_title": job_title,
            "company": company,
            "must_have_skills": [],
            "nice_to_have_skills": [],
            "core_responsibilities": [],
            "career_level": estimate_role_level(job_title),
            "interview_focus_areas": [],
            "error": "Could not parse response",
        }

    parsed.setdefault("job_title", job_title)
    parsed.setdefault("company", company)
    parsed.setdefault("must_have_skills", [])
    parsed.setdefault("nice_to_have_skills", [])
    parsed.setdefault("core_responsibilities", [])
    parsed.setdefault("career_level", estimate_role_level(job_title))
    parsed.setdefault("interview_focus_areas", [])
    return parsed


async def infer_job_requirements(
    job_title: str,
    company: str = "a top tech company",
    job_description: str = ""
) -> dict[str, Any]:
    """
    Infer job requirements from a job title, company, and optional job description.
    If a job description is provided, the LLM extracts requirements from it directly.
    Otherwise it infers them from the title and company.
    """
    return await analyze_job_description(job_title=job_title, company=company, jd_text=job_description)


def infer_job_requirements_sync(job_title: str, company: str = "a top tech company") -> dict:
    """Synchronous wrapper for infer_job_requirements."""
    return asyncio.run(infer_job_requirements(job_title, company))


# ============== Role Level Estimation ==============

def estimate_role_level(job_title: str) -> str:
    """
    Estimate the career level from a job title.
    """
    title_lower = job_title.lower()
    
    if any(x in title_lower for x in ["principal", "distinguished", "fellow", "vp", "director"]):
        return "principal"
    elif any(x in title_lower for x in ["staff", "architect"]):
        return "staff"
    elif any(x in title_lower for x in ["senior", "lead", "sr"]):
        return "senior"
    elif any(x in title_lower for x in ["junior", "jr", "intern", "graduate", "associate"]):
        return "entry"
    else:
        return "mid"


def get_bridge_role_suggestions(
    target_title: str,
    target_level: str,
    current_skills: set[str]
) -> list[dict]:
    """
    Suggest bridge roles for someone not yet ready for target role.
    
    Args:
        target_title: The target job title
        target_level: Career level (entry/mid/senior/staff/principal)
        current_skills: Set of current skills
        
    Returns:
        List of bridge role suggestions
    """
    bridge_roles = []
    
    # Map target level to bridge levels
    level_mapping = {
        "principal": ["staff", "senior"],
        "staff": ["senior", "mid"],
        "senior": ["mid", "entry"],
        "mid": ["entry"],
        "entry": []
    }
    
    bridge_levels = level_mapping.get(target_level, [])
    
    # Extract base role from title
    base_role = target_title.lower()
    for prefix in ["principal", "staff", "senior", "lead", "jr", "junior"]:
        base_role = base_role.replace(prefix, "").strip()
    
    for level in bridge_levels[:2]:  # Max 2 suggestions
        if level == "senior":
            title = f"Senior {base_role.title()}"
        elif level == "mid":
            title = base_role.title()
        elif level == "entry":
            title = f"Junior {base_role.title()}"
        else:
            title = f"{level.title()} {base_role.title()}"
        
        bridge_roles.append({
            "title": title,
            "level": level,
            "reason": f"Build experience before advancing to {target_title}"
        })
    
    return bridge_roles
