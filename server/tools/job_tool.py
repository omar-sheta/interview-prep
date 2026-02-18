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


# ============== JD Inference Function ==============

async def infer_job_requirements(
    job_title: str,
    company: str = "a top tech company"
) -> dict[str, Any]:
    """
    Infer job requirements from a job title and company.
    Uses LLM to generate realistic skill requirements.
    
    Args:
        job_title: The target job title (e.g., "Senior Software Engineer")
        company: The company name (e.g., "Google", "Meta")
        
    Returns:
        Structured job requirements dictionary
    """
    chat_model = get_chat_model()
    
    prompt = f"""As a Senior Recruiter, analyze the requirements for:
Job Title: {job_title}
Company: {company}

List the 10 must-have technical skills and 5 core responsibilities for this role.
Consider the company's tech stack and culture if known."""
    
    messages = [
        SystemMessage(content=JD_INFERENCE_SYSTEM_PROMPT),
        HumanMessage(content=prompt)
    ]
    
    # Generate response (proper async call)
    result = await chat_model.ainvoke(messages)
    response_text = result.content
    
    # Extract JSON from response
    try:
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            parsed = json.loads(json_match.group())
            # Ensure required fields exist
            parsed.setdefault("job_title", job_title)
            parsed.setdefault("company", company)
            parsed.setdefault("must_have_skills", [])
            parsed.setdefault("core_responsibilities", [])
            return parsed
        else:
            return {
                "job_title": job_title,
                "company": company,
                "must_have_skills": [],
                "core_responsibilities": [],
                "error": "Could not parse response"
            }
    except json.JSONDecodeError as e:
        return {
            "job_title": job_title,
            "company": company,
            "must_have_skills": [],
            "core_responsibilities": [],
            "error": f"JSON parse error: {e}"
        }


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
