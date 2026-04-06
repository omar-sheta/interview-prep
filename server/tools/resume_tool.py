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

try:
    import fitz
except Exception:
    fitz = None

from pypdf import PdfReader

from server.services.llm_factory import get_chat_model
from server.services.vector_service import match_skills_semantically
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
    Prefer block-based PyMuPDF extraction for layout preservation,
    then fall back to pypdf when needed.
    """
    if fitz is not None:
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_text_parts: list[str] = []
            for page in doc:
                blocks = page.get_text("blocks")
                if not blocks:
                    continue
                ordered_blocks = sorted(blocks, key=lambda block: (round(float(block[1]), 1), round(float(block[0]), 1)))
                block_texts: list[str] = []
                for block in ordered_blocks:
                    text = str(block[4] or "").strip()
                    if text:
                        block_texts.append(text)
                if block_texts:
                    page_text_parts.append("\n\n".join(block_texts))
            doc.close()
            merged = "\n\n".join(page_text_parts).strip()
            if merged:
                return merged
        except Exception as e:
            print(f"⚠️ PyMuPDF extraction failed, falling back to pypdf: {e}")

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


HOLISTIC_RESUME_JOB_TRIAL_PROMPT = """You are an expert technical recruiter and research hiring evaluator.
Analyze the candidate resume and the target job description together in ONE pass.
Return RAW JSON only using this exact structure:
{
  "personal_info": {
    "name": "string",
    "email": "string",
    "phone": "string",
    "location": "string"
  },
  "summary": "1-2 sentence fit summary",
  "skills": {
    "hard_skills": ["skills"],
    "tools_and_tech": ["tools"],
    "soft_skills": ["soft skills"],
    "certifications": ["certifications"]
  },
  "experience": [
    {
      "company": "string",
      "title": "string",
      "duration": "string",
      "responsibilities": ["key responsibilities"],
      "skills_used": ["skills used"]
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string",
      "field": "string",
      "year": "string"
    }
  ],
  "years_of_experience": 0,
  "job_requirements": {
    "must_have_skills": ["short canonical skills"],
    "nice_to_have_skills": ["short canonical skills"],
    "core_responsibilities": ["short responsibilities"],
    "career_level": "entry|mid|senior|staff|principal",
    "interview_focus_areas": ["focus areas"]
  },
  "skill_analysis": [
    {
      "skill": "short canonical skill",
      "priority": "must_have|nice_to_have",
      "status": "strong_match|partial_match|missing",
      "candidate_level": "none|basic|intermediate|advanced|expert",
      "required_level": "basic|intermediate|advanced|expert",
      "evidence": "specific evidence from the resume",
      "confidence": 0.0
    }
  ],
  "readiness_score": 0.0,
  "top_gaps": ["skill names"]
}
Rules:
- Use short, human skill names like "Python", "Large Language Models", "AI Safety", "RAG", "PyTorch".
- Do NOT treat qualifications, degree enrollment, reference letters, location constraints, or application logistics as skills.
- Prefer evidence-backed matches. If the resume strongly supports a skill, do not mark it missing.
- Use partial_match when the resume is adjacent or relevant but not explicit enough.
- Keep must_have_skills tightly grounded in the job description, not generic filler.
- Keep skill_analysis to the 8-14 most relevant skills for this role.
- Readiness must reflect the actual fit, not a default midpoint.
"""


def _holistic_resume_trial_schema() -> dict[str, Any]:
    return {
        "name": "holistic_resume_job_trial",
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
            "personal_info",
            "summary",
            "skills",
            "experience",
            "education",
            "years_of_experience",
            "job_requirements",
            "skill_analysis",
            "readiness_score",
            "top_gaps",
        ],
        "additionalProperties": False,
    }


async def parse_resume_text_node(resume_text: str) -> dict[str, Any]:
    """
    Parse raw resume text into the standard resume schema.
    Used as a fallback when the larger combined analysis is too long.
    """
    if not str(resume_text or "").strip():
        return {"error": "Could not extract text from resume"}

    chat_model = get_chat_model()
    messages = [
        SystemMessage(content=RESUME_PARSER_SYSTEM_PROMPT),
        HumanMessage(content=f"Parse the following resume:\n\n{resume_text[:5000]}")
    ]

    try:
        result = await chat_model.ainvoke(
            messages,
            json_mode=True,
            max_tokens=min(int(getattr(settings, "LLM_JSON_MAX_TOKENS", 500)), 900),
        )
        parsed = parse_json_safely(result.content)
        if parsed and isinstance(parsed, dict):
            return parsed
    except Exception as e:
        print(f"⚠️ Resume text parse fallback failed: {e}")

    return {
        "skills": {
            "hard_skills": extract_capitalized_phrases(resume_text),
            "tools_and_tech": [],
            "soft_skills": [],
            "languages": [],
            "certifications": [],
        },
        "experience": [],
        "education": [],
        "personal_info": {},
        "summary": "Could not fully parse resume via AI",
        "years_of_experience": 0,
    }


def _normalized_analysis_skills_block(skills_block: dict[str, Any]) -> dict[str, list[str]]:
    src = skills_block if isinstance(skills_block, dict) else {}
    return {
        "hard_skills": [str(item).strip() for item in src.get("hard_skills", []) if str(item).strip()],
        "tools_and_tech": [str(item).strip() for item in src.get("tools_and_tech", []) if str(item).strip()],
        "soft_skills": [str(item).strip() for item in src.get("soft_skills", []) if str(item).strip()],
        "certifications": [str(item).strip() for item in src.get("certifications", []) if str(item).strip()],
    }


def _normalized_resume_profile(resume_data: dict[str, Any]) -> dict[str, Any]:
    return {
        "personal_info": dict(resume_data.get("personal_info", {}) or {}),
        "summary": str(resume_data.get("summary", "") or ""),
        "skills": _normalized_analysis_skills_block(resume_data.get("skills", {}) or {}),
        "experience": list(resume_data.get("experience", []) or []),
        "education": list(resume_data.get("education", []) or []),
        "years_of_experience": resume_data.get("years_of_experience", 0) or 0,
    }


def _semantic_candidate_rows(
    semantic_matches: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for required_skill, match in semantic_matches.items():
        candidate_skill = str(match.get("candidate_skill") or "").strip()
        score = float(match.get("score") or 0.0)
        if not candidate_skill:
            continue
        if score >= 0.9:
            candidate_level = "advanced"
            confidence = max(0.78, min(0.99, score))
        elif score >= 0.8:
            candidate_level = "intermediate"
            confidence = max(0.62, min(0.88, score))
        elif score >= 0.68:
            candidate_level = "basic"
            confidence = max(0.45, min(0.7, score))
        else:
            candidate_level = "basic"
            confidence = max(0.3, min(0.45, score))
        rows.append({
            "skill": required_skill,
            "candidate_level": candidate_level,
            "confidence": round(confidence, 2),
            "evidence": [f"Semantic match: required '{required_skill}' mapped to resume skill '{candidate_skill}' ({round(score, 2)})"],
            "matched_candidate_skill": candidate_skill,
            "matched_required_skill": required_skill,
        })
    return rows


def _coverage_to_skill_analysis(coverage_board: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in coverage_board:
        status_key = str(row.get("status") or "").strip().lower()
        if status_key in {"strong", "meets"}:
            status = "strong_match"
        elif status_key in {"borderline", "uncertain"}:
            status = "partial_match"
        else:
            status = "missing"
        evidence_items = row.get("evidence_candidate", []) or []
        evidence = "; ".join([str(item).strip() for item in evidence_items if str(item).strip()][:3])
        if not evidence and status == "missing":
            evidence = ""
        output.append({
            "skill": row.get("name") or row.get("skill") or "",
            "priority": row.get("priority", "must_have"),
            "status": status,
            "candidate_level": row.get("candidate_level", "none"),
            "required_level": row.get("required_level", "intermediate"),
            "evidence": evidence,
            "confidence": round(float(row.get("confidence") or 0.0), 2),
        })
    return output


def _top_gaps_from_board(coverage_board: list[dict[str, Any]], limit: int = 6) -> list[str]:
    ranked = []
    for row in coverage_board:
        status_key = str(row.get("status") or "").strip().lower()
        if status_key in {"strong", "meets"}:
            continue
        ranked.append(row)
    ranked.sort(
        key=lambda row: (
            float(row.get("importance") or 0.0),
            1 if str(row.get("priority") or "must_have") == "must_have" else 0,
            1 if str(row.get("status") or "").lower() == "missing" else 0,
        ),
        reverse=True,
    )
    return [str(row.get("name") or row.get("skill") or "").strip() for row in ranked if str(row.get("name") or row.get("skill") or "").strip()][:limit]


def _importance_for_index(priority: str, index: int) -> float:
    if priority == "must_have":
        return round(max(0.5, 0.95 - (index * 0.04)), 2)
    return round(max(0.2, 0.6 - (index * 0.04)), 2)


def _reason_from_trial_status(skill_name: str, status: str, required_level: str, candidate_level: str, evidence: str) -> str:
    if status == "strong_match":
        return f"The resume shows strong evidence for {skill_name} at or above the expected {required_level} level."
    if status == "partial_match":
        if evidence:
            return f"The resume suggests relevant experience for {skill_name}, but the depth is not fully explicit."
        return f"{skill_name} appears relevant, but stronger proof is still needed for this role."
    if evidence:
        return f"{skill_name} is important for this role, but the resume evidence is still limited."
    return f"{skill_name} is expected for this role, but it is not clearly evidenced in the resume."


def _learning_tip_for_skill(skill_name: str) -> str:
    canonical = str(skill_name or "").strip().lower()
    custom = {
        "large language models": "Prepare 2-3 concrete LLM project stories covering model choice, evaluation, and failure analysis.",
        "ai safety": "Bring one example of how you measured, mitigated, or red-teamed model failures in practice.",
        "adversarial robustness": "Prepare one example showing the threat model, attack setup, metric, and mitigation trade-offs.",
        "rag": "Practice explaining retrieval setup, failure modes, grounding, and evaluation choices end to end.",
        "research publications": "Summarize your strongest paper or manuscript in problem-method-results-impact format.",
        "python": "Be ready to discuss the exact Python tooling, libraries, and experiments you personally implemented.",
    }
    if canonical in custom:
        return custom[canonical]
    return f"Prepare one concrete example that demonstrates {skill_name} with clear outcomes and trade-offs."


def _details_from_single_call_result(result: dict[str, Any], job_title: str, company: str) -> dict[str, Any]:
    from server.agents.nodes import _default_followup_questions

    resume_data = {
        "personal_info": dict(result.get("personal_info", {}) or {}),
        "summary": str(result.get("summary", "") or ""),
        "skills": _normalized_analysis_skills_block(result.get("skills", {}) or {}),
        "experience": list(result.get("experience", []) or []),
        "education": list(result.get("education", []) or []),
        "years_of_experience": result.get("years_of_experience", 0) or 0,
    }
    job_requirements = {
        **dict(result.get("job_requirements", {}) or {}),
        "job_title": job_title,
        "company": company,
    }
    job_requirements.setdefault("must_have_skills", [])
    job_requirements.setdefault("nice_to_have_skills", [])
    job_requirements.setdefault("core_responsibilities", [])
    job_requirements.setdefault("career_level", "mid")
    job_requirements.setdefault("interview_focus_areas", [])

    skill_analysis = list(result.get("skill_analysis", []) or [])
    matched: list[dict[str, Any]] = []
    partial: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    coverage_board: list[dict[str, Any]] = []

    for idx, item in enumerate(skill_analysis):
        if not isinstance(item, dict):
            continue
        skill_name = str(item.get("skill") or "").strip()
        if not skill_name:
            continue
        priority = str(item.get("priority") or "must_have").strip().lower()
        status = str(item.get("status") or "missing").strip().lower()
        candidate_level = str(item.get("candidate_level") or "none").strip().lower()
        required_level = str(item.get("required_level") or ("intermediate" if priority == "must_have" else "basic")).strip().lower()
        evidence = str(item.get("evidence") or "").strip()
        confidence = max(0.1, min(0.99, float(item.get("confidence") or 0.2)))
        board_status = {
            "strong_match": "Strong",
            "partial_match": "Borderline" if confidence >= 0.5 else "Uncertain",
            "missing": "Missing",
        }.get(status, "Missing")
        board_row = {
            "skill": skill_name.lower(),
            "name": skill_name,
            "priority": priority,
            "required_level": required_level,
            "importance": _importance_for_index(priority, idx),
            "candidate_level": candidate_level,
            "confidence": round(confidence, 2),
            "status": board_status,
            "reason": _reason_from_trial_status(skill_name, status, required_level, candidate_level, evidence),
            "evidence_required": "Derived from the job description",
            "evidence_candidate": [evidence] if evidence else [],
            "learning_tip": _learning_tip_for_skill(skill_name),
            "gap_level": 0 if status == "strong_match" else (1 if status == "partial_match" else 2),
        }
        coverage_board.append(board_row)
        list_item = {
            "name": skill_name,
            "status": board_status.lower(),
            "priority": priority,
            "required_level": required_level,
            "candidate_level": candidate_level,
            "importance": board_row["importance"],
            "confidence": round(confidence, 2),
            "reason": board_row["reason"],
            "learning_tip": board_row["learning_tip"],
        }
        if status == "strong_match":
            matched.append(list_item)
        elif status == "partial_match":
            partial.append(list_item)
        else:
            missing.append(list_item)

    coverage_summary = {
        "required_skills_count": len(coverage_board),
        "candidate_skills_count": len(get_all_skills(resume_data)),
        "must_have_coverage": round(len([row for row in coverage_board if row["priority"] == "must_have" and row["status"] in {"Strong", "Meets"}]) / max(len([row for row in coverage_board if row["priority"] == "must_have"]), 1), 2),
        "nice_to_have_coverage": round(len([row for row in coverage_board if row["priority"] == "nice_to_have" and row["status"] in {"Strong", "Meets"}]) / max(len([row for row in coverage_board if row["priority"] == "nice_to_have"]), 1), 2),
    }
    followup_targets = [item for item in (missing + partial)[:6]]
    followup_questions = _default_followup_questions(job_title, followup_targets)

    return {
        "resume_data": resume_data,
        "job_requirements": job_requirements,
        "skill_mapping": {
            "matched": matched,
            "partial": partial,
            "missing": missing,
            "candidate_extra_skills": [],
            "coverage_board": coverage_board,
            "coverage_summary": coverage_summary,
            "required_skills": job_requirements.get("must_have_skills", []) + job_requirements.get("nice_to_have_skills", []),
            "candidate_skills": list(get_all_skills(resume_data)),
            "followup_targets": followup_targets,
            "followup_questions": followup_questions,
        },
        "readiness_score": round(float(result.get("readiness_score") or 0.5), 2),
        "skill_gaps": followup_targets,
    }


async def _run_holistic_resume_analysis_trial(
    resume_text: str,
    job_title: str,
    company: str,
    job_description: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    chat_model = get_chat_model()
    schema = _holistic_resume_trial_schema()

    async def _invoke_once(resume_limit: int, jd_limit: int) -> dict[str, Any]:
        resume_excerpt = str(resume_text or "")[:resume_limit]
        jd_excerpt = str(job_description or "")[:jd_limit]
        messages = [
            SystemMessage(content=HOLISTIC_RESUME_JOB_TRIAL_PROMPT),
            HumanMessage(
                content=(
                    f"Target Role: {job_title}\n"
                    f"Company: {company}\n\n"
                    f"JOB DESCRIPTION:\n{jd_excerpt}\n\n"
                    f"RESUME:\n{resume_excerpt}"
                )
            ),
        ]
        result = await chat_model.ainvoke(
            messages,
            json_schema=schema,
            max_tokens=min(int(getattr(settings, "LLM_JSON_MAX_TOKENS", 6000)), 2800),
        )
        parsed = parse_json_safely(result.content)
        if not isinstance(parsed, dict):
            preview = str(result.content or "")[:400]
            raise ValueError(f"Holistic resume analysis trial returned invalid JSON. Preview: {preview}")
        return parsed

    first_resume_limit = int(getattr(settings, "RESUME_ANALYSIS_TRIAL_RESUME_CHARS", 6500))
    first_jd_limit = int(getattr(settings, "RESUME_ANALYSIS_TRIAL_JD_CHARS", 4500))
    try:
        parsed = await _invoke_once(first_resume_limit, first_jd_limit)
    except Exception:
        parsed = await _invoke_once(min(first_resume_limit, 4200), min(first_jd_limit, 2800))

    parsed.setdefault("personal_info", {})
    parsed.setdefault("summary", "")
    parsed.setdefault("skills", {"hard_skills": [], "tools_and_tech": [], "soft_skills": [], "certifications": []})
    parsed.setdefault("experience", [])
    parsed.setdefault("education", [])
    parsed.setdefault("years_of_experience", 0)
    parsed.setdefault("job_requirements", {
        "must_have_skills": [],
        "nice_to_have_skills": [],
        "core_responsibilities": [],
        "career_level": "mid",
        "interview_focus_areas": [],
    })
    parsed.setdefault("skill_analysis", [])
    parsed.setdefault("readiness_score", 0.5)
    parsed.setdefault("top_gaps", [])
    return parsed, _details_from_single_call_result(parsed, job_title, company)


async def _run_resume_analysis_pipeline(
    resume_text: str,
    job_title: str,
    company: str = "a top tech company",
    job_description: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    if bool(getattr(settings, "RESUME_ANALYSIS_SINGLE_LLM_TRIAL", False)):
        try:
            return await _run_holistic_resume_analysis_trial(
                resume_text=resume_text,
                job_title=job_title,
                company=company,
                job_description=job_description,
            )
        except Exception as e:
            print(f"⚠️ Holistic resume analysis trial failed, falling back to structured pipeline: {e}")

    from server.tools.job_tool import analyze_job_description
    from server.agents.nodes import (
        _build_skill_coverage_board,
        _derive_followup_targets,
        _extract_candidate_skill_seed,
        _extract_required_skill_seed,
        _merge_candidate_skill_rows,
        _normalize_candidate_skill_rows,
        _normalize_required_skill_rows,
        _skill_mapping_from_board,
        _default_followup_questions,
    )

    resume_data = _normalized_resume_profile(await parse_resume_text_node(resume_text))
    job_profile = await analyze_job_description(job_title=job_title, company=company, jd_text=job_description)
    job_requirements = {
        "must_have_skills": list(job_profile.get("must_have_skills", []) or []),
        "nice_to_have_skills": list(job_profile.get("nice_to_have_skills", []) or []),
        "core_responsibilities": list(job_profile.get("core_responsibilities", []) or []),
        "career_level": str(job_profile.get("career_level") or "mid"),
        "interview_focus_areas": list(job_profile.get("interview_focus_areas", []) or []),
    }

    required_skills = _normalize_required_skill_rows(_extract_required_skill_seed(job_requirements))
    candidate_seed = _normalize_candidate_skill_rows(_extract_candidate_skill_seed(resume_data))

    candidate_skill_names = sorted(get_all_skills(resume_data))
    required_skill_names = [str(row.get("display_name") or row.get("skill") or "").strip() for row in required_skills if str(row.get("display_name") or row.get("skill") or "").strip()]
    semantic_matches = match_skills_semantically(candidate_skill_names, required_skill_names, threshold=0.62)
    semantic_rows = _normalize_candidate_skill_rows(_semantic_candidate_rows(semantic_matches))
    candidate_skills = _merge_candidate_skill_rows(candidate_seed, semantic_rows)

    coverage_payload = _build_skill_coverage_board(required_skills, candidate_skills)
    coverage_board = coverage_payload.get("board", [])
    skill_mapping = _skill_mapping_from_board(coverage_payload)
    followup_targets = _derive_followup_targets(coverage_board, limit=6)
    followup_questions = _default_followup_questions(job_title, followup_targets)
    skill_mapping["followup_targets"] = followup_targets
    skill_mapping["followup_questions"] = followup_questions
    skill_mapping["required_skills"] = required_skills
    skill_mapping["candidate_skills"] = candidate_skills[:30]
    skill_mapping["semantic_matches"] = semantic_matches

    result = {
        "personal_info": resume_data.get("personal_info", {}),
        "summary": resume_data.get("summary", ""),
        "skills": _normalized_analysis_skills_block(resume_data.get("skills", {})),
        "experience": resume_data.get("experience", []),
        "education": resume_data.get("education", []),
        "years_of_experience": resume_data.get("years_of_experience", 0),
        "job_requirements": job_requirements,
        "skill_analysis": _coverage_to_skill_analysis(coverage_board),
        "readiness_score": round(float(coverage_payload.get("readiness_score") or 0.5), 2),
        "top_gaps": _top_gaps_from_board(coverage_board, limit=6),
    }
    details = {
        "resume_data": resume_data,
        "job_requirements": {
            **job_requirements,
            "job_title": job_title,
            "company": company,
        },
        "skill_mapping": skill_mapping,
        "readiness_score": result["readiness_score"],
        "skill_gaps": [item for item in followup_targets],
    }
    return result, details


async def analyze_resume_and_job(
    resume_text: str,
    job_title: str,
    company: str = "a top tech company",
    job_description: str = "",
) -> dict:
    """
    Decoupled resume analysis pipeline:
    1. Parse resume text into candidate JSON
    2. Analyze job description into job JSON
    3. Match skills semantically
    4. Score readiness using deterministic coverage helpers
    """
    try:
        result, _details = await _run_resume_analysis_pipeline(
            resume_text=resume_text,
            job_title=job_title,
            company=company,
            job_description=job_description,
        )
        return result
    except Exception as e:
        print(f"❌ Resume analysis pipeline error: {e}")
        import traceback
        traceback.print_exc()

    return {
        "personal_info": {},
        "summary": "Could not fully parse resume via AI",
        "skills": {
            "hard_skills": extract_capitalized_phrases(resume_text),
            "tools_and_tech": [],
            "soft_skills": [],
            "certifications": [],
        },
        "experience": [],
        "education": [],
        "years_of_experience": 0,
        "job_requirements": {
            "must_have_skills": [],
            "nice_to_have_skills": [],
            "core_responsibilities": [],
            "career_level": "mid",
            "interview_focus_areas": [],
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
