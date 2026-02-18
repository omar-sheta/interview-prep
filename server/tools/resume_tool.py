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
from langchain_core.messages import HumanMessage, SystemMessage


# ============== JSON Cleaning Utility ==============

def clean_json_output(text: str) -> str:
    """
    Clean LLM output to extract valid JSON.
    Handles common LLM errors like markdown blocks, trailing commas, comments.
    """
    # Remove markdown code blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    text = text.strip()
    
    # Remove single-line comments (// ...)
    text = re.sub(r'//.*', '', text)
    
    # Remove trailing commas before ] or }
    text = re.sub(r',(\s*[\}\]])', r'\1', text)
    
    # Fix common LLM mistakes
    text = re.sub(r'"null"', 'null', text)
    
    # Try to extract JSON object
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        return json_match.group()
    
    return text


def parse_json_safely(text: str) -> Optional[dict]:
    """
    Attempt to parse JSON with multiple fallback strategies.
    """
    # First, clean the text
    cleaned = clean_json_output(text)
    
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Try with additional fixes
    try:
        fixed = cleaned.replace("'", '"')
        return json.loads(fixed)
    except json.JSONDecodeError:
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
        result = await chat_model.ainvoke(messages)
        response_text = result.content
        
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