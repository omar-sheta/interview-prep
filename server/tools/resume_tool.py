"""
Resume Parser Tool for CV Analysis.
Extracts text from PDF resumes and uses LLM to structure the data.
Universal support for Tech, Healthcare, Business, and Creative industries.
"""

import asyncio
import io
import json
import re
from typing import Any, Optional

from pypdf import PdfReader

from server.services.llm_factory import get_chat_model
from server.config import settings
from langchain_core.messages import HumanMessage, SystemMessage


# ============== JSON Cleaning Utility ==============

def clean_json_output(text: str) -> str:
    """
    Clean LLM output to extract valid JSON.
    Handles common LLM errors like markdown blocks, trailing commas, comments,
    and qwen3-style <think>...</think> reasoning blocks.
    """
    # Strip <think>...</think> blocks (qwen3 reasoning traces)
    text = re.sub(r'<think>[\s\S]*?</think>', '', text)
    
    # Strip DeepSeek/LM Studio style "Thinking Process:" blocks
    text = re.sub(r'(?i)(?:Thinking|Reasoning)\s+Process:.*?(\n\s*\{|\n\s*\[)', r'\1', text, flags=re.DOTALL)

    # Remove markdown code blocks
    text = re.sub(r'```(?:json)?\s*([\s\S]*?)```', r'\1', text)
    text = text.strip()
    
    # Remove single-line comments (// ...)
    text = re.sub(r'//.*', '', text)
    
    # Remove trailing commas before ] or }
    text = re.sub(r',(\s*[\}\]])', r'\1', text)
    
    # Fix common LLM mistakes
    text = re.sub(r'"null"', 'null', text)
    
    # Try to extract the first JSON object or array
    json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
    if json_match:
        return json_match.group(1)
    
    return text


def parse_json_safely(text: str) -> Optional[dict]:
    """
    Attempt to parse JSON with multiple fallback strategies.
    """
    if not text:
        return None

    # First, clean the text
    cleaned = clean_json_output(text)

    # Fix malformed keys like: " "text": ... or ""text":
    fixed_keys = re.sub(r'"\s+"([A-Za-z_][A-Za-z0-9_]*)"\s*:', r'"\1":', cleaned)
    fixed_keys = re.sub(r'""([A-Za-z_][A-Za-z0-9_]*)"\s*:', r'"\1":', fixed_keys)

    candidates = [
        cleaned,
        fixed_keys,
        fixed_keys.replace("'", '"'),
    ]

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    # Last resort: attempt structural repair for minor JSON corruption.
    try:
        from json_repair import repair_json
        repaired = repair_json(fixed_keys)
        return json.loads(repaired)
    except Exception:
        pass

    return None


# ============== PDF Text Extraction ==============

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extract text content from a PDF file bytes.
    RENAMED from extract_text_from_pdf to fix import error.
    """
    pdf_file = io.BytesIO(pdf_bytes)
    reader = PdfReader(pdf_file)
    
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    
    return "\n".join(text_parts)


def extract_text_from_pdf_path(pdf_path: str) -> str:
    """
    Extract text from a PDF file path.
    """
    with open(pdf_path, "rb") as f:
        return extract_text_from_pdf_bytes(f.read())


# ============== Resume Parsing Prompt (Universal) ==============

RESUME_PARSER_SYSTEM_PROMPT = """You are an expert career analyst capable of parsing resumes from ANY industry (Tech, Healthcare, Finance, Construction, Arts, etc.).
Your task is to analyze the resume text and extract structured information.

You MUST respond with ONLY valid JSON. Use this industry-agnostic structure:

{
  "personal_info": {
    "name": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "location": "string or null",
    "linkedin": "string or null",
    "portfolio_or_website": "string or null"
  },
  "summary": "Brief professional summary extracted or inferred",
  "skills": {
    "hard_skills": ["List of core professional skills (e.g. Project Management, Phlebotomy, SEO, Python)"],
    "tools_and_tech": ["Software, hardware, or machinery used (e.g. Excel, Forklift, Salesforce, AWS)"],
    "soft_skills": ["Interpersonal skills (e.g. Leadership, Communication)"],
    "languages": ["Spoken languages (e.g. Spanish, English)"],
    "certifications": ["Professional certifications or licenses"]
  },
  "experience": [
    {
      "company": "string",
      "title": "string",
      "duration": "string",
      "responsibilities": ["list of key achievements and duties"],
      "skills_used": ["specific skills applied in this role"]
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string",
      "field": "string",
      "year": "string or null"
    }
  ],
  "years_of_experience": 0
}

CRITICAL RULES:
1. Return RAW JSON only. No markdown.
2. If the resume is non-technical, do NOT force technical fields. Put relevant skills in "hard_skills".
3. "years_of_experience" must be a number. Estimate if not explicit.
4. "skills_used" in experience should link skills to context.
"""


# ============== Resume Parser Node ==============

async def parse_resume_node(
    resume_bytes: bytes,
    mime_type: str = "application/pdf"
) -> dict[str, Any]:
    """
    Parse a resume PDF and extract structured data using LLM.
    """
    # Extract text
    try:
        if mime_type == "application/pdf":
            resume_text = extract_text_from_pdf_bytes(resume_bytes)
        else:
            resume_text = resume_bytes.decode("utf-8")
    except Exception as e:
        print(f"Error extracting text: {e}")
        return {"error": "Failed to read file content"}
    
    if not resume_text.strip():
        return {"error": "Could not extract text from resume"}
    
    # Use LLM
    chat_model = get_chat_model()
    
    messages = [
        SystemMessage(content=RESUME_PARSER_SYSTEM_PROMPT),
        HumanMessage(content=f"Parse the following resume:\n\n{resume_text}")
    ]
    
    # Generate response (proper async call)
    try:
        result = await chat_model.ainvoke(
            messages,
            json_mode=True,
            max_tokens=getattr(settings, "LLM_JSON_MAX_TOKENS", 500),
        )
        response_text = result.content
        print(f"RAW RESUME PARSE RESPONSE:\n{response_text[:800]}...\n")
        
        # Parse JSON
        parsed = parse_json_safely(response_text)
        
        if parsed and isinstance(parsed, dict):
            return parsed
            
    except Exception as e:
        print(f"LLM Error: {e}")

    # Fallback if LLM fails
    print(f"⚠️ JSON parse failed, using fallback extraction")
    return {
        "skills": {
            "hard_skills": extract_capitalized_phrases(resume_text), # Basic NLP fallback
            "tools_and_tech": [],
            "soft_skills": []
        },
        "experience": [],
        "education": [],
        "personal_info": {},
        "summary": "Could not fully parse resume via AI",
        "years_of_experience": 0
    }


def extract_capitalized_phrases(text: str) -> list[str]:
    """
    Simple fallback to grab potential skills (Capitalized Words)
    Useful for non-tech resumes where keywords vary wildly.
    """
    # Remove common stop words at start of sentences
    stop_words = {"The", "A", "An", "In", "On", "At", "To", "For", "I", "He", "She", "It"}
    
    words = text.split()
    candidates = set()
    
    for i in range(len(words)-1):
        w1 = words[i].strip(".,;:()")
        w2 = words[i+1].strip(".,;:()")
        
        # Look for 2-word capitalized phrases (e.g. "Project Management", "Financial Analysis")
        if w1.istitle() and w2.istitle() and w1 not in stop_words:
            candidates.add(f"{w1} {w2}")
            
    return list(candidates)[:15] # Return top 15 found


def parse_resume_sync(resume_bytes: bytes, mime_type: str = "application/pdf") -> dict:
    """Synchronous wrapper."""
    return asyncio.run(parse_resume_node(resume_bytes, mime_type))


# ============== Mega-Prompt: Combined Resume + Job Analysis ==============

MEGA_ANALYSIS_SYSTEM_PROMPT = """You are a Senior Career Analyst and Technical Recruiter.
You will receive a candidate's resume text, a target job title, company, and optionally a job description.

Perform ALL of the following in a SINGLE response:
1. Parse the resume into structured data
2. Identify required skills for the target role
3. Match candidate skills against requirements
4. Score readiness

You MUST respond with ONLY valid JSON. Use this EXACT structure:

{
  "personal_info": {
    "name": "string or null",
    "email": "string or null",
    "phone": "string or null",
    "location": "string or null"
  },
  "summary": "1-2 sentence professional summary",
  "skills": {
    "hard_skills": ["core professional skills"],
    "tools_and_tech": ["software, tools, frameworks"],
    "soft_skills": ["interpersonal skills"],
    "certifications": ["certifications or licenses"]
  },
  "experience": [
    {
      "company": "string",
      "title": "string",
      "duration": "string",
      "responsibilities": ["key achievements"],
      "skills_used": ["skills applied"]
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string",
      "field": "string",
      "year": "string or null"
    }
  ],
  "years_of_experience": 0,
  "job_requirements": {
    "must_have_skills": ["10 essential skills for the target role"],
    "nice_to_have_skills": ["5 beneficial but not required skills"],
    "core_responsibilities": ["5 main job responsibilities"],
    "career_level": "entry/mid/senior/staff/principal",
    "interview_focus_areas": ["3-5 areas covered in interviews"]
  },
  "skill_analysis": [
    {
      "skill": "skill name",
      "priority": "must_have or nice_to_have",
      "status": "strong_match or partial_match or missing",
      "candidate_level": "none/basic/intermediate/advanced/expert",
      "required_level": "basic/intermediate/advanced/expert",
      "evidence": "specific evidence from resume, or empty string",
      "confidence": 0.8
    }
  ],
  "readiness_score": 0.65,
  "top_gaps": ["skill1", "skill2", "skill3"]
}

RULES:
1. RAW JSON only. No markdown, no explanations.
2. skill_analysis MUST cover ALL must_have_skills and nice_to_have_skills.
3. readiness_score is 0.0-1.0 based on skill coverage.
4. top_gaps lists the 3-6 most critical missing or weak skills.
5. Be specific with evidence — cite actual resume content.
6. status meanings: strong_match = clearly demonstrated, partial_match = some evidence but weak, missing = no evidence found."""


async def analyze_resume_and_job(
    resume_text: str,
    job_title: str,
    company: str = "a top tech company",
    job_description: str = "",
) -> dict:
    """
    Single mega-prompt that combines resume parsing + job analysis + skill matching.
    Uses LM Studio's constrained decoding (json_schema) to guarantee valid JSON.
    Replaces 5 separate LLM calls with 1.
    """
    chat_model = get_chat_model()

    user_content = f"Target Role: {job_title}\nCompany: {company}\n"
    if job_description and job_description.strip():
        user_content += f"\nJOB DESCRIPTION:\n{job_description[:2000]}\n"
    user_content += f"\nRESUME:\n{resume_text[:4000]}"

    messages = [
        SystemMessage(content=MEGA_ANALYSIS_SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]

    # Hand-crafted JSON schema for LM Studio constrained decoding.
    # Kept intentionally flat to avoid schema-complexity issues.
    mega_schema = {
        "name": "career_analysis",
        "type": "object",
        "properties": {
            "personal_info": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["name", "email", "phone", "location"],
                "additionalProperties": False,
            },
            "summary": {"type": "string"},
            "skills": {
                "type": "object",
                "properties": {
                    "hard_skills": {"type": "array", "items": {"type": "string"}},
                    "tools_and_tech": {"type": "array", "items": {"type": "string"}},
                    "soft_skills": {"type": "array", "items": {"type": "string"}},
                    "certifications": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["hard_skills", "tools_and_tech", "soft_skills", "certifications"],
                "additionalProperties": False,
            },
            "experience": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "title": {"type": "string"},
                        "duration": {"type": "string"},
                        "responsibilities": {"type": "array", "items": {"type": "string"}},
                        "skills_used": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["company", "title", "duration", "responsibilities", "skills_used"],
                    "additionalProperties": False,
                },
            },
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "institution": {"type": "string"},
                        "degree": {"type": "string"},
                        "field": {"type": "string"},
                        "year": {"type": "string"},
                    },
                    "required": ["institution", "degree", "field", "year"],
                    "additionalProperties": False,
                },
            },
            "years_of_experience": {"type": "number"},
            "job_requirements": {
                "type": "object",
                "properties": {
                    "must_have_skills": {"type": "array", "items": {"type": "string"}},
                    "nice_to_have_skills": {"type": "array", "items": {"type": "string"}},
                    "core_responsibilities": {"type": "array", "items": {"type": "string"}},
                    "career_level": {"type": "string"},
                    "interview_focus_areas": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["must_have_skills", "nice_to_have_skills", "core_responsibilities", "career_level", "interview_focus_areas"],
                "additionalProperties": False,
            },
            "skill_analysis": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "skill": {"type": "string"},
                        "priority": {"type": "string"},
                        "status": {"type": "string"},
                        "candidate_level": {"type": "string"},
                        "required_level": {"type": "string"},
                        "evidence": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["skill", "priority", "status", "candidate_level", "required_level", "evidence", "confidence"],
                    "additionalProperties": False,
                },
            },
            "readiness_score": {"type": "number"},
            "top_gaps": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "personal_info", "summary", "skills", "experience", "education",
            "years_of_experience", "job_requirements", "skill_analysis",
            "readiness_score", "top_gaps",
        ],
        "additionalProperties": False,
    }

    try:
        result = await chat_model.ainvoke(
            messages,
            json_schema=mega_schema,
            max_tokens=int(getattr(settings, "LLM_JSON_MAX_TOKENS", 6000)),
        )
        response_text = result.content
        print(f"📊 MEGA ANALYSIS RESPONSE ({len(response_text)} chars):\n{response_text[:500]}...\n")

        parsed = parse_json_safely(response_text)
        if parsed and isinstance(parsed, dict):
            # Ensure all top-level keys exist with defaults
            parsed.setdefault("personal_info", {})
            parsed.setdefault("summary", "")
            parsed.setdefault("skills", {"hard_skills": [], "tools_and_tech": [], "soft_skills": []})
            parsed.setdefault("experience", [])
            parsed.setdefault("education", [])
            parsed.setdefault("years_of_experience", 0)
            parsed.setdefault("job_requirements", {
                "must_have_skills": [],
                "nice_to_have_skills": [],
                "core_responsibilities": [],
            })
            parsed.setdefault("skill_analysis", [])
            parsed.setdefault("readiness_score", 0.5)
            parsed.setdefault("top_gaps", [])
            return parsed

    except Exception as e:
        print(f"❌ Mega analysis LLM error: {e}")
        import traceback
        traceback.print_exc()

    # Fallback: return minimal structure
    print("⚠️ Mega analysis failed, using empty fallback")
    return {
        "personal_info": {},
        "summary": "Could not fully parse resume via AI",
        "skills": {"hard_skills": extract_capitalized_phrases(resume_text), "tools_and_tech": [], "soft_skills": []},
        "experience": [],
        "education": [],
        "years_of_experience": 0,
        "job_requirements": {
            "job_title": job_title,
            "company": company,
            "must_have_skills": [],
            "nice_to_have_skills": [],
            "core_responsibilities": [],
        },
        "skill_analysis": [],
        "readiness_score": 0.5,
        "top_gaps": [],
    }


# ============== Skill Extraction Utilities ==============

def get_all_skills(resume_data: dict) -> set[str]:
    """
    Extract all skills from parsed resume data as a flat set.
    Normalizes skill names to lowercase.
    Updated for Universal Schema (hard_skills, tools_and_tech).
    """
    skills = set()
    
    # 1. Extract from new universal schema
    skill_categories = resume_data.get("skills", {})
    if isinstance(skill_categories, dict):
        # Loop through whatever categories exist (hard_skills, soft_skills, tools_and_tech)
        for category, skill_list in skill_categories.items():
            if isinstance(skill_list, list):
                skills.update(str(s).lower().strip() for s in skill_list if s)
    
    # 2. Extract from experience (skills_used)
    for exp in resume_data.get("experience", []):
        techs = exp.get("skills_used", [])
        if isinstance(techs, list):
            skills.update(str(t).lower().strip() for t in techs if t)

    # 3. Backward compatibility (if old resume format exists in DB)
    old_keys = ["programming_languages", "frameworks", "databases", "tools"]
    if isinstance(skill_categories, dict):
        for key in old_keys:
            if key in skill_categories:
                val = skill_categories[key]
                if isinstance(val, list):
                    skills.update(str(s).lower().strip() for s in val if s)
    
    return skills
