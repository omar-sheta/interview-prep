"""
Agent Nodes for Career Analysis LangGraph.
Contains skill mapping, mindmap generation, and analysis nodes.
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Callable, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from server.agents.state import InterviewState
from server.services.llm_factory import get_chat_model
# CHANGED: Updated imports to match the new resume_tool function names
from server.tools.resume_tool import get_all_skills, parse_resume_node, extract_text_from_pdf_bytes, parse_json_safely
from server.tools.job_tool import get_bridge_role_suggestions, estimate_role_level


# ============== Career Analysis State ==============

class CareerAnalysisState(TypedDict):
    """State for the career analysis LangGraph."""
    resume_data: dict
    job_requirements: dict
    skill_mapping: dict
    readiness_score: float
    mindmap: str
    bridge_roles: list
    suggested_sessions: list[dict]
    practice_plan: dict
    skill_gaps: list
    job_description: str
    error: str | None


# ============== Helper Functions ==============

def sanitize_mermaid_text(text: str, max_length: int = 50) -> str:
    """
    Sanitize text for Mermaid.js while preserving technical characters.
    Keeps: letters, numbers, spaces, +, #, ., /, -
    """
    if not text:
        return ""
    # Preserve common tech chars: C++, C#, Node.js, CI/CD
    safe_text = re.sub(r'[^a-zA-Z0-9\s\+\#\.\-\/]', '', str(text)).strip()
    # Truncate if strictly longer than max_length
    if len(safe_text) > max_length:
        safe_text = safe_text[:max_length-3] + "..."
    return safe_text or "Unknown"


def group_skills_by_type(skills: list) -> dict:
    """
    Group skills into categories using keyword matching.
    Returns: {"Languages": [...], "Frameworks": [...], "Cloud & DevOps": [...], "Databases": [...], "Other": [...]}
    """
    categories = {
        "Languages": [],
        "Frameworks": [],
        "Cloud & DevOps": [],
        "Databases": [],
        "Other": []
    }
    
    # Keyword patterns for categorization
    language_keywords = ['python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'rust', 'ruby', 'php', 'swift', 'kotlin', 'scala', 'r', 'sql']
    framework_keywords = ['react', 'angular', 'vue', 'django', 'flask', 'fastapi', 'spring', 'node', 'express', 'rails', 'laravel', 'next', 'nuxt', 'svelte', 'pytorch', 'tensorflow', 'pandas']
    cloud_keywords = ['aws', 'azure', 'gcp', 'docker', 'kubernetes', 'k8s', 'ci/cd', 'jenkins', 'terraform', 'ansible', 'linux', 'devops', 'cloud', 'serverless', 'lambda']
    db_keywords = ['mysql', 'postgres', 'mongodb', 'redis', 'elasticsearch', 'dynamodb', 'cassandra', 'oracle', 'sqlite', 'nosql', 'database', 'sql']
    
    for skill in skills:
        skill_lower = str(skill).lower()
        if any(kw in skill_lower for kw in language_keywords):
            categories["Languages"].append(skill)
        elif any(kw in skill_lower for kw in framework_keywords):
            categories["Frameworks"].append(skill)
        elif any(kw in skill_lower for kw in cloud_keywords):
            categories["Cloud & DevOps"].append(skill)
        elif any(kw in skill_lower for kw in db_keywords):
            categories["Databases"].append(skill)
        else:
            categories["Other"].append(skill)
    
    return categories


def _looks_like_question_text(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    lowered = value.lower()
    if "?" in lowered:
        return True
    if len(lowered) > 90:
        return True
    return bool(re.match(r"^(can|could|would|should|what|why|how|when|where|which|tell|describe|explain|walk me)\b", lowered))


def _clean_title(text: str, max_len: int = 72) -> str:
    value = " ".join(str(text or "").strip().split())
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def _infer_focus_from_question(question_text: str) -> str:
    text = str(question_text or "").strip()
    if not text:
        return ""
    text = re.sub(r"^[\"'`\s]+|[\"'`\s]+$", "", text)
    text = re.sub(
        r"^(can you|could you|would you|tell me about|describe|explain|walk me through|how would you|how do you)\s+",
        "",
        text,
        flags=re.IGNORECASE
    )
    text = text.replace("?", "")
    text = " ".join(text.split())
    words = text.split()
    if len(words) < 3:
        return ""
    return _clean_title(" ".join(words[:8]).capitalize(), max_len=56)


def _session_title_prefix(session_type: str, round_index: int) -> str:
    t = str(session_type or "").lower()
    if t == "behavioral":
        return "Behavioral Scenario"
    if t in {"technical", "system_design", "system design"}:
        return "Technical Deep Dive"
    if round_index == 0:
        return "Behavioral Scenario"
    if round_index == 1:
        return "Technical Deep Dive"
    return "Interview Session"


def normalize_practice_plan_titles(practice_plan: Optional[dict]) -> dict:
    """
    Ensure each session has a concise, non-question title.
    Keeps question-like text in focus_topic/source_prompt and stores generated title in `title`.
    """
    plan = practice_plan if isinstance(practice_plan, dict) else {}
    rounds = plan.get("rounds")
    if not isinstance(rounds, list):
        plan["rounds"] = []
        return plan

    for round_index, round_obj in enumerate(rounds):
        if not isinstance(round_obj, dict):
            rounds[round_index] = {"id": f"r{round_index + 1}", "name": f"Round {round_index + 1}", "sessions": []}
            round_obj = rounds[round_index]

        sessions = round_obj.get("sessions")
        if not isinstance(sessions, list):
            round_obj["sessions"] = []
            continue

        for session_index, session in enumerate(sessions):
            if not isinstance(session, dict):
                sessions[session_index] = {}
                session = sessions[session_index]

            raw_title = str(session.get("title") or "").strip()
            title_is_question = _looks_like_question_text(raw_title)
            prefix = _session_title_prefix(session.get("type"), round_index)

            if title_is_question:
                inferred_focus = _infer_focus_from_question(raw_title)
                if raw_title and not session.get("source_prompt"):
                    session["source_prompt"] = raw_title
                if inferred_focus and not session.get("focus_topic"):
                    session["focus_topic"] = inferred_focus
                title_focus = str(session.get("focus_topic") or inferred_focus or "").strip()
                if title_focus and not _looks_like_question_text(title_focus):
                    session["title"] = _clean_title(f"{prefix}: {title_focus}", max_len=72)
                else:
                    session["title"] = f"{prefix} {session_index + 1}"
            else:
                session["title"] = _clean_title(raw_title, max_len=72)

    return plan


# ============== Skill Mapping Helpers ==============

SKILL_LEVEL_ORDER = {
    "none": 0,
    "basic": 1,
    "intermediate": 2,
    "advanced": 3,
    "expert": 4,
}

SKILL_STATUS_SCORE = {
    "strong": 1.0,
    "meets": 0.85,
    "borderline": 0.55,
    "uncertain": 0.35,
    "missing": 0.0,
}

SKILL_STATUS_RANK = {
    "missing": 0,
    "uncertain": 1,
    "borderline": 2,
    "meets": 3,
    "strong": 4,
}

SKILL_ALIAS_MAP = {
    "js": "javascript",
    "ts": "typescript",
    "node": "node.js",
    "nodejs": "node.js",
    "reactjs": "react",
    "react.js": "react",
    "nextjs": "next.js",
    "next": "next.js",
    "postgresql": "postgres",
    "postgres": "postgres",
    "gcp": "google cloud",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "llms": "large language models",
    "nlp": "natural language processing",
    "k8s": "kubernetes",
    "ci cd": "ci/cd",
    "rest": "rest api design",
    "restful": "rest api design",
    "restful api": "rest api design",
    "systemdesign": "system design",
}

SKILL_DISPLAY_MAP = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "node.js": "Node.js",
    "next.js": "Next.js",
    "react": "React",
    "postgres": "Postgres",
    "google cloud": "Google Cloud",
    "aws": "AWS",
    "azure": "Azure",
    "ci/cd": "CI/CD",
    "rest api design": "REST API Design",
    "system design": "System Design",
    "sql": "SQL",
    "nosql": "NoSQL",
    "machine learning": "Machine Learning",
    "large language models": "Large Language Models",
    "natural language processing": "Natural Language Processing",
}

DEFAULT_LEARNING_TIPS = {
    "system design": "Run one architecture deep-dive weekly and defend trade-offs in writing.",
    "rest api design": "Design one CRUD API end-to-end including auth, pagination, and error contracts.",
    "kubernetes": "Deploy a small service to a local Kubernetes cluster and debug one failure scenario.",
    "sql": "Practice analytical SQL on medium datasets with joins, windows, and query plans.",
    "machine learning": "Build one baseline model and explain feature, metric, and error trade-offs.",
    "large language models": "Ship one LLM feature with evals, guardrails, and latency/cost tracking.",
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_text_list(value: Any, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def _normalize_skill_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.replace("&", " and ")
    text = text.replace("/", " ")
    text = re.sub(r"\bframeworks?\b", "", text)
    text = re.sub(r"\btechnology\b", "", text)
    text = re.sub(r"[^a-z0-9\+\#\.\-\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _canonical_skill_name(value: Any) -> str:
    key = _normalize_skill_key(value)
    if not key:
        return ""
    compact = key.replace(" ", "")
    if compact in SKILL_ALIAS_MAP:
        return SKILL_ALIAS_MAP[compact]
    if key in SKILL_ALIAS_MAP:
        return SKILL_ALIAS_MAP[key]
    return key


def _display_skill_name(value: Any) -> str:
    canonical = _canonical_skill_name(value)
    if not canonical:
        return "Unknown"
    if canonical in SKILL_DISPLAY_MAP:
        return SKILL_DISPLAY_MAP[canonical]
    return " ".join([piece.capitalize() for piece in canonical.split(" ")])


def _normalize_skill_level(value: Any, default: str = "basic") -> str:
    raw = _normalize_skill_key(value)
    if not raw:
        return default
    mapping = {
        "beginner": "basic",
        "entry": "basic",
        "junior": "basic",
        "mid": "intermediate",
        "midlevel": "intermediate",
        "competent": "intermediate",
        "strong": "advanced",
        "senior": "advanced",
        "staff": "expert",
        "principal": "expert",
    }
    if raw in SKILL_LEVEL_ORDER:
        return raw
    if raw in mapping:
        return mapping[raw]
    return default


def _normalize_priority(value: Any, default: str = "must_have") -> str:
    text = _normalize_skill_key(value)
    if text in {"must", "must have", "core", "required", "critical", "essential", "must_have"}:
        return "must_have"
    if text in {"nice", "nice to have", "preferred", "bonus", "optional", "nice_to_have"}:
        return "nice_to_have"
    return default


def _extract_required_skill_seed(job_reqs: dict) -> list[dict]:
    seed: list[dict] = []
    must_have = _as_text_list(job_reqs.get("must_have_skills", []), limit=40)
    nice_to_have = _as_text_list(job_reqs.get("nice_to_have_skills", []), limit=30)
    for idx, skill in enumerate(must_have):
        seed.append({
            "skill": skill,
            "priority": "must_have",
            "required_level": "intermediate",
            "importance": _clamp(0.95 - (idx * 0.03), 0.65, 0.98),
            "evidence_from_jd": "Listed as required skill",
        })
    for idx, skill in enumerate(nice_to_have):
        seed.append({
            "skill": skill,
            "priority": "nice_to_have",
            "required_level": "basic",
            "importance": _clamp(0.6 - (idx * 0.03), 0.25, 0.7),
            "evidence_from_jd": "Listed as preferred skill",
        })
    return seed


def _normalize_required_skill_rows(required_skills: Any) -> list[dict]:
    if not isinstance(required_skills, list):
        return []
    merged: dict[str, dict] = {}
    for raw_item in required_skills:
        if isinstance(raw_item, dict):
            raw_skill = (
                raw_item.get("skill")
                or raw_item.get("name")
                or raw_item.get("label")
                or raw_item.get("title")
            )
            priority = _normalize_priority(raw_item.get("priority"), default="must_have")
            required_level = _normalize_skill_level(
                raw_item.get("required_level"),
                default="intermediate" if priority == "must_have" else "basic"
            )
            importance = _clamp(
                _safe_float(raw_item.get("importance"), 0.75 if priority == "must_have" else 0.45),
                0.2,
                1.0
            )
            evidence_from_jd = str(raw_item.get("evidence_from_jd") or raw_item.get("evidence") or "").strip()
        else:
            raw_skill = raw_item
            priority = "must_have"
            required_level = "intermediate"
            importance = 0.75
            evidence_from_jd = ""
        canonical = _canonical_skill_name(raw_skill)
        if not canonical:
            continue
        existing = merged.get(canonical)
        if not existing:
            merged[canonical] = {
                "skill": canonical,
                "display_name": _display_skill_name(canonical),
                "priority": priority,
                "required_level": required_level,
                "importance": round(importance, 3),
                "evidence_from_jd": evidence_from_jd,
            }
            continue
        existing_priority = existing.get("priority", "nice_to_have")
        if existing_priority != "must_have" and priority == "must_have":
            existing["priority"] = "must_have"
        if SKILL_LEVEL_ORDER.get(required_level, 0) > SKILL_LEVEL_ORDER.get(existing.get("required_level"), 0):
            existing["required_level"] = required_level
        existing["importance"] = round(max(_safe_float(existing.get("importance"), 0.2), importance), 3)
        if evidence_from_jd and not existing.get("evidence_from_jd"):
            existing["evidence_from_jd"] = evidence_from_jd

    rows = list(merged.values())
    rows.sort(key=lambda item: (_safe_float(item.get("importance"), 0), item.get("priority") == "must_have"), reverse=True)
    return rows[:24]


def _extract_candidate_skill_seed(resume_data: dict) -> list[dict]:
    scores: dict[str, dict] = {}

    def _register(skill_value: Any, evidence: str, category_bonus: float = 0.0):
        canonical = _canonical_skill_name(skill_value)
        if not canonical:
            return
        row = scores.setdefault(canonical, {
            "skill": canonical,
            "display_name": _display_skill_name(canonical),
            "score": 0.0,
            "evidence": [],
        })
        row["score"] += 1.0 + category_bonus
        if evidence and evidence not in row["evidence"] and len(row["evidence"]) < 4:
            row["evidence"].append(evidence)

    skills_block = resume_data.get("skills", {})
    if isinstance(skills_block, dict):
        for category, items in skills_block.items():
            category_name = str(category or "")
            category_bonus = 0.2 if category_name in {"hard_skills", "tools_and_tech"} else 0.0
            for skill_value in _as_text_list(items, limit=80):
                _register(skill_value, f"resume:{category_name}", category_bonus=category_bonus)

    for exp in resume_data.get("experience", [])[:10]:
        if not isinstance(exp, dict):
            continue
        title = str(exp.get("title") or "").strip()
        company = str(exp.get("company") or "").strip()
        evidence = f"experience:{title or 'role'}{f' @ {company}' if company else ''}"
        for skill_value in _as_text_list(exp.get("skills_used", []), limit=30):
            _register(skill_value, evidence, category_bonus=0.4)

    output: list[dict] = []
    for item in scores.values():
        raw_score = _safe_float(item.get("score"), 0.0)
        if raw_score >= 4.0:
            level = "advanced"
        elif raw_score >= 2.0:
            level = "intermediate"
        else:
            level = "basic"
        confidence = _clamp(0.35 + (raw_score * 0.12), 0.25, 0.95)
        output.append({
            "skill": item["skill"],
            "display_name": item["display_name"],
            "candidate_level": level,
            "confidence": round(confidence, 2),
            "evidence": item.get("evidence", [])[:3],
        })

    output.sort(key=lambda item: _safe_float(item.get("confidence"), 0), reverse=True)
    return output[:60]


def _normalize_candidate_skill_rows(rows: Any) -> list[dict]:
    if not isinstance(rows, list):
        return []
    merged: dict[str, dict] = {}
    for raw in rows:
        if isinstance(raw, dict):
            raw_skill = raw.get("skill") or raw.get("name") or raw.get("label")
            level = _normalize_skill_level(raw.get("candidate_level"), default="basic")
            confidence = _clamp(_safe_float(raw.get("confidence"), 0.55), 0.05, 0.99)
            evidence = raw.get("evidence")
            if isinstance(evidence, list):
                evidence_list = _as_text_list(evidence, limit=4)
            else:
                evidence_list = _as_text_list([evidence], limit=4)
        else:
            raw_skill = raw
            level = "basic"
            confidence = 0.5
            evidence_list = []
        canonical = _canonical_skill_name(raw_skill)
        if not canonical:
            continue
        existing = merged.get(canonical)
        if not existing:
            merged[canonical] = {
                "skill": canonical,
                "display_name": _display_skill_name(canonical),
                "candidate_level": level,
                "confidence": round(confidence, 2),
                "evidence": evidence_list,
            }
            continue
        if SKILL_LEVEL_ORDER[level] > SKILL_LEVEL_ORDER.get(existing.get("candidate_level"), 0):
            existing["candidate_level"] = level
        existing["confidence"] = round(max(_safe_float(existing.get("confidence"), 0.0), confidence), 2)
        for snippet in evidence_list:
            if snippet not in existing["evidence"] and len(existing["evidence"]) < 4:
                existing["evidence"].append(snippet)

    rows = list(merged.values())
    rows.sort(key=lambda item: _safe_float(item.get("confidence"), 0), reverse=True)
    return rows


def _merge_candidate_skill_rows(seed_rows: list[dict], llm_rows: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in seed_rows + llm_rows:
        canonical = _canonical_skill_name(row.get("skill"))
        if not canonical:
            continue
        existing = merged.get(canonical)
        if not existing:
            merged[canonical] = {
                "skill": canonical,
                "display_name": _display_skill_name(canonical),
                "candidate_level": _normalize_skill_level(row.get("candidate_level"), default="basic"),
                "confidence": round(_clamp(_safe_float(row.get("confidence"), 0.5), 0.05, 0.99), 2),
                "evidence": _as_text_list(row.get("evidence", []), limit=4),
            }
            continue
        incoming_level = _normalize_skill_level(row.get("candidate_level"), default=existing["candidate_level"])
        if SKILL_LEVEL_ORDER[incoming_level] > SKILL_LEVEL_ORDER.get(existing.get("candidate_level"), 0):
            existing["candidate_level"] = incoming_level
        existing["confidence"] = round(max(_safe_float(existing.get("confidence"), 0.0), _safe_float(row.get("confidence"), 0.0)), 2)
        for snippet in _as_text_list(row.get("evidence", []), limit=4):
            if snippet not in existing["evidence"] and len(existing["evidence"]) < 4:
                existing["evidence"].append(snippet)

    rows = list(merged.values())
    rows.sort(key=lambda item: (_safe_float(item.get("confidence"), 0), SKILL_LEVEL_ORDER.get(item.get("candidate_level"), 0)), reverse=True)
    return rows[:70]


def _status_reason(
    status: str,
    skill_name: str,
    required_level: str,
    candidate_level: str,
    confidence: float
) -> str:
    if status == "strong":
        return f"Evidence indicates {skill_name} exceeds the role's {required_level} requirement."
    if status == "meets":
        return f"Evidence suggests {skill_name} meets the required {required_level} proficiency."
    if status == "borderline":
        return f"{skill_name} appears below the target depth ({candidate_level} vs {required_level})."
    if status == "uncertain":
        return f"{skill_name} appears in the resume, but evidence confidence is only {int(confidence * 100)}%."
    return f"{skill_name} is required at {required_level}, but no reliable evidence was found."


def _build_skill_coverage_board(required_skills: list[dict], candidate_skills: list[dict]) -> dict:
    candidate_index = {row["skill"]: row for row in candidate_skills}
    required_set = {row["skill"] for row in required_skills}
    board: list[dict] = []
    weighted_score = 0.0
    weighted_total = 0.0
    must_weighted_score = 0.0
    must_weighted_total = 0.0
    nice_weighted_score = 0.0
    nice_weighted_total = 0.0

    for req in required_skills:
        skill = req["skill"]
        display = req.get("display_name") or _display_skill_name(skill)
        required_level = _normalize_skill_level(req.get("required_level"), default="intermediate")
        priority = _normalize_priority(req.get("priority"), default="must_have")
        importance = _clamp(_safe_float(req.get("importance"), 0.7), 0.2, 1.0)
        candidate = candidate_index.get(skill)
        candidate_level = _normalize_skill_level(candidate.get("candidate_level"), default="none") if candidate else "none"
        confidence = _clamp(_safe_float(candidate.get("confidence"), 0.2 if candidate else 0.05), 0.05, 0.99)
        req_idx = SKILL_LEVEL_ORDER.get(required_level, 2)
        cand_idx = SKILL_LEVEL_ORDER.get(candidate_level, 0)

        if not candidate:
            status = "missing"
        elif confidence < 0.45:
            status = "uncertain"
        else:
            delta = cand_idx - req_idx
            if delta >= 1:
                status = "strong"
            elif delta >= 0:
                status = "meets"
            elif delta == -1:
                status = "borderline"
            else:
                status = "missing"

        weighted_score += importance * SKILL_STATUS_SCORE[status]
        weighted_total += importance
        if priority == "must_have":
            must_weighted_score += importance * SKILL_STATUS_SCORE[status]
            must_weighted_total += importance
        else:
            nice_weighted_score += importance * SKILL_STATUS_SCORE[status]
            nice_weighted_total += importance

        board.append({
            "skill": skill,
            "name": display,
            "priority": priority,
            "required_level": required_level,
            "importance": round(importance, 2),
            "candidate_level": candidate_level,
            "confidence": round(confidence, 2),
            "status": status.title(),
            "reason": _status_reason(status, display, required_level, candidate_level, confidence),
            "evidence_required": str(req.get("evidence_from_jd") or "").strip(),
            "evidence_candidate": _as_text_list((candidate or {}).get("evidence", []), limit=3),
            "learning_tip": str(req.get("learning_tip") or DEFAULT_LEARNING_TIPS.get(skill) or f"Practice one project focused on {display} and review the trade-offs out loud.").strip(),
            "gap_level": max(0, req_idx - cand_idx),
        })

    board.sort(
        key=lambda row: (
            _safe_float(row.get("importance"), 0),
            -SKILL_STATUS_RANK.get(str(row.get("status", "Missing")).lower(), 0)
        ),
        reverse=True
    )

    extras = []
    for row in candidate_skills:
        if row["skill"] in required_set:
            continue
        extras.append({
            "name": row.get("display_name") or _display_skill_name(row["skill"]),
            "candidate_level": row.get("candidate_level", "basic"),
            "confidence": round(_safe_float(row.get("confidence"), 0.5), 2),
            "evidence": _as_text_list(row.get("evidence", []), limit=2),
        })
    extras.sort(key=lambda item: _safe_float(item.get("confidence"), 0), reverse=True)

    readiness_score = 0.5 if weighted_total <= 0 else _clamp(weighted_score / weighted_total, 0.0, 1.0)
    must_cov = 0.0 if must_weighted_total <= 0 else _clamp(must_weighted_score / must_weighted_total, 0.0, 1.0)
    nice_cov = 0.0 if nice_weighted_total <= 0 else _clamp(nice_weighted_score / nice_weighted_total, 0.0, 1.0)

    return {
        "board": board,
        "extras": extras[:8],
        "readiness_score": round(readiness_score, 2),
        "coverage_summary": {
            "required_skills_count": len(required_skills),
            "candidate_skills_count": len(candidate_skills),
            "must_have_coverage": round(must_cov, 2),
            "nice_to_have_coverage": round(nice_cov, 2),
        }
    }


def _skill_mapping_from_board(board_payload: dict) -> dict:
    board = board_payload.get("board", [])
    extras = board_payload.get("extras", [])
    matched: list[dict] = []
    partial: list[dict] = []
    missing: list[dict] = []

    for row in board:
        name = row.get("name") or _display_skill_name(row.get("skill"))
        status = str(row.get("status") or "Missing").lower()
        item = {
            "name": name,
            "status": status,
            "priority": row.get("priority"),
            "required_level": row.get("required_level"),
            "candidate_level": row.get("candidate_level"),
            "importance": round(_safe_float(row.get("importance"), 0.0), 2),
            "confidence": round(_safe_float(row.get("confidence"), 0.0), 2),
            "reason": row.get("reason", ""),
            "learning_tip": row.get("learning_tip", ""),
        }
        if status in {"strong", "meets"}:
            matched.append(item)
        elif status in {"borderline", "uncertain"}:
            partial.append(item)
        else:
            missing.append(item)

    return {
        "matched": matched,
        "partial": partial,
        "missing": missing,
        "candidate_extra_skills": extras,
        "coverage_board": board,
        "coverage_summary": board_payload.get("coverage_summary", {}),
    }


def _derive_followup_targets(board: list[dict], limit: int = 6) -> list[dict]:
    candidates = []
    for row in board:
        status = str(row.get("status") or "").lower()
        if status not in {"missing", "uncertain", "borderline"}:
            continue
        candidates.append({
            "skill": row.get("skill"),
            "name": row.get("name"),
            "status": status,
            "priority": row.get("priority", "must_have"),
            "importance": round(_safe_float(row.get("importance"), 0), 2),
            "confidence": round(_safe_float(row.get("confidence"), 0), 2),
            "reason": row.get("reason", ""),
            "learning_tip": row.get("learning_tip", ""),
        })
    candidates.sort(
        key=lambda item: (
            _safe_float(item.get("importance"), 0),
            1 if item.get("priority") == "must_have" else 0,
            -SKILL_STATUS_RANK.get(item.get("status", "missing"), 0)
        ),
        reverse=True
    )
    return candidates[:limit]


def _default_followup_questions(job_title: str, targets: list[dict]) -> list[dict]:
    questions = []
    for target in targets[:6]:
        skill_name = target.get("name") or _display_skill_name(target.get("skill"))
        status = str(target.get("status") or "missing")
        if status == "missing":
            prompt = f"Walk me through how you would build practical capability in {skill_name} for a {job_title} role over the next 30 days."
            intent = "Plan building concrete skill development and execution."
        elif status == "uncertain":
            prompt = f"Describe one project where you applied {skill_name}, including your exact contribution and measurable outcome."
            intent = "Validate claimed skill depth with concrete evidence."
        else:
            prompt = f"Explain a trade-off you handled using {skill_name} and how you decided between options."
            intent = "Test depth and decision quality under real constraints."
        questions.append({
            "skill": skill_name,
            "question": prompt,
            "intent": intent,
        })
    return questions


async def _llm_extract_required_skills(
    job_title: str,
    company: str,
    job_reqs: dict,
    job_description: str
) -> list[dict]:
    must_have = _as_text_list(job_reqs.get("must_have_skills", []), limit=20)
    nice_to_have = _as_text_list(job_reqs.get("nice_to_have_skills", []), limit=15)
    focus_areas = _as_text_list(job_reqs.get("interview_focus_areas", []), limit=12)
    if not must_have and not nice_to_have and not job_description.strip():
        return []

    system_prompt = """You are a hiring rubric designer. Build a normalized required-skill list from job data.
Return JSON only:
{
  "required_skills": [
    {
      "skill": "canonical skill name",
      "priority": "must_have|nice_to_have",
      "required_level": "basic|intermediate|advanced|expert",
      "importance": 0.2-1.0,
      "evidence_from_jd": "short quote or reason"
    }
  ]
}
Rules:
- Deduplicate aliases (e.g., JS/Javascript).
- Keep 8-18 skills max.
- Use concrete technical/professional skills only.
- Higher importance for must-have and core role execution capabilities."""

    user_payload = {
        "job_title": job_title,
        "company": company,
        "must_have_skills": must_have,
        "nice_to_have_skills": nice_to_have,
        "interview_focus_areas": focus_areas,
        "job_description_excerpt": str(job_description or "")[:1800],
    }
    chat_model = get_chat_model()
    response = await chat_model.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(user_payload))
    ])
    parsed = parse_json_safely(response.content)
    if not isinstance(parsed, dict):
        return []
    return _normalize_required_skill_rows(parsed.get("required_skills", []))


async def _llm_extract_candidate_skills(
    resume_data: dict,
    required_skills: list[dict],
    target_role: str
) -> list[dict]:
    required_names = [row.get("display_name") or _display_skill_name(row.get("skill")) for row in required_skills[:20]]
    skills_block = resume_data.get("skills", {})
    experience = resume_data.get("experience", [])
    if not isinstance(experience, list):
        experience = []

    compact_experience = []
    for exp in experience[:6]:
        if not isinstance(exp, dict):
            continue
        compact_experience.append({
            "title": exp.get("title"),
            "company": exp.get("company"),
            "skills_used": _as_text_list(exp.get("skills_used", []), limit=8),
            "responsibilities": _as_text_list(exp.get("responsibilities", []), limit=3),
        })

    prompt = {
        "target_role": target_role,
        "required_skills": required_names,
        "resume_summary": str(resume_data.get("summary", ""))[:600],
        "resume_skills_block": skills_block,
        "experience": compact_experience,
    }

    system_prompt = """You are a technical recruiter extracting candidate proficiency evidence from a resume.
Return JSON only:
{
  "candidate_skills": [
    {
      "skill": "canonical skill",
      "candidate_level": "basic|intermediate|advanced|expert",
      "confidence": 0.05-0.99,
      "evidence": ["short evidence snippets"]
    }
  ]
}
Rules:
- Prefer concrete and defensible evidence.
- If evidence is weak, lower confidence.
- Include required skills when possible and up to 12 useful extras."""

    chat_model = get_chat_model()
    response = await chat_model.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(prompt))
    ])
    parsed = parse_json_safely(response.content)
    if not isinstance(parsed, dict):
        return []
    return _normalize_candidate_skill_rows(parsed.get("candidate_skills", []))


async def _llm_adjudicate_coverage(
    job_title: str,
    coverage_board: list[dict]
) -> list[dict]:
    weak_rows = []
    for row in coverage_board:
        if str(row.get("status", "")).lower() in {"strong", "meets"} and _safe_float(row.get("confidence"), 0) >= 0.6:
            continue
        weak_rows.append({
            "skill": row.get("name"),
            "status": row.get("status"),
            "required_level": row.get("required_level"),
            "candidate_level": row.get("candidate_level"),
            "confidence": row.get("confidence"),
            "evidence_required": row.get("evidence_required"),
            "evidence_candidate": row.get("evidence_candidate", []),
        })
        if len(weak_rows) >= 18:
            break
    if not weak_rows:
        return []

    system_prompt = """You are a conservative hiring reviewer. Re-check weak skills and adjust confidence/status only when evidence is insufficient.
Return JSON only:
{
  "adjustments": [
    {
      "skill": "skill name",
      "status": "missing|uncertain|borderline|meets|strong",
      "confidence": 0.05-0.99,
      "reason": "short reason"
    }
  ]
}
Rules:
- Be conservative.
- Prefer lowering over raising confidence when evidence is unclear.
- Include at most 8 adjustments."""
    payload = {"job_title": job_title, "skills": weak_rows}
    chat_model = get_chat_model()
    response = await chat_model.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(payload))
    ])
    parsed = parse_json_safely(response.content)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("adjustments"), list):
        return []
    adjustments: list[dict] = []
    for raw in parsed.get("adjustments", []):
        if not isinstance(raw, dict):
            continue
        adjustments.append({
            "skill": raw.get("skill"),
            "status": str(raw.get("status") or "").strip().lower(),
            "confidence": _clamp(_safe_float(raw.get("confidence"), 0.5), 0.05, 0.99),
            "reason": str(raw.get("reason") or "").strip(),
        })
    return adjustments[:8]


def _apply_adjudication_adjustments(coverage_board: list[dict], adjustments: list[dict]) -> list[dict]:
    by_skill = {_canonical_skill_name(row.get("skill")): row for row in coverage_board}
    for adj in adjustments:
        canonical = _canonical_skill_name(adj.get("skill"))
        if not canonical:
            continue
        row = by_skill.get(canonical)
        if not row:
            continue
        current_status = str(row.get("status") or "Missing").lower()
        next_status = str(adj.get("status") or "").lower()
        if next_status not in SKILL_STATUS_RANK:
            continue
        # Conservative rule: allow status only if same or lower confidence rank than current.
        if SKILL_STATUS_RANK[next_status] > SKILL_STATUS_RANK.get(current_status, 0):
            continue
        row["status"] = next_status.title()
        row["confidence"] = round(min(_safe_float(row.get("confidence"), 0.5), _safe_float(adj.get("confidence"), 0.5)), 2)
        reason = str(adj.get("reason") or "").strip()
        if reason:
            row["reason"] = f"{row.get('reason', '')} Review note: {reason}".strip()
    return coverage_board


async def _llm_generate_followup_questions(job_title: str, targets: list[dict]) -> list[dict]:
    if not targets:
        return []
    payload = {
        "job_title": job_title,
        "targets": [
            {
                "skill": t.get("name") or _display_skill_name(t.get("skill")),
                "status": t.get("status"),
                "importance": t.get("importance"),
                "reason": t.get("reason"),
            }
            for t in targets[:6]
        ],
    }
    system_prompt = """You design short spoken interview follow-up questions for skill validation.
Return JSON only:
{
  "questions": [
    {"skill": "skill name", "question": "one speaking prompt", "intent": "what this validates"}
  ]
}
Rules:
- Questions must be answerable verbally.
- Keep each question single-part and concrete.
- Prioritize high-importance missing/uncertain skills."""
    chat_model = get_chat_model()
    response = await chat_model.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(payload))
    ])
    parsed = parse_json_safely(response.content)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("questions"), list):
        return []
    questions: list[dict] = []
    for raw in parsed.get("questions", []):
        if not isinstance(raw, dict):
            continue
        skill_name = str(raw.get("skill") or "").strip()
        question_text = str(raw.get("question") or "").strip()
        intent = str(raw.get("intent") or "").strip()
        if not question_text:
            continue
        questions.append({
            "skill": skill_name or "Core competency",
            "question": question_text,
            "intent": intent or "Validate practical depth and decision-making.",
        })
    return questions[:8]


# ============== Skill Mapping Node (Hybrid Multi-Pass) ==============

async def map_skills_node(state: CareerAnalysisState) -> CareerAnalysisState:
    """
    Multi-pass skill analysis:
    1) Parse required skills from JD metadata
    2) Normalize aliases and levels
    3) Extract candidate skills/evidence from resume
    4) Deterministic gap scoring board
    5) LLM adjudication pass for weak/ambiguous evidence
    6) Follow-up target generation for interview focus
    """
    resume_data = state.get("resume_data", {})
    job_reqs = state.get("job_requirements", {})

    if not resume_data or not job_reqs:
        return {
            **state,
            "skill_mapping": {"matched": [], "partial": [], "missing": []},
            "readiness_score": 0.0,
            "error": "Missing resume or job data",
        }

    target_role = str(job_reqs.get("job_title") or state.get("target_role") or "Unknown Role")
    target_company = str(job_reqs.get("company") or job_reqs.get("target_company") or state.get("target_company") or "")
    job_description = str(state.get("job_description") or job_reqs.get("job_description") or "")

    required_seed = _normalize_required_skill_rows(_extract_required_skill_seed(job_reqs))
    required_llm: list[dict] = []
    try:
        required_llm = await _llm_extract_required_skills(
            job_title=target_role,
            company=target_company,
            job_reqs=job_reqs,
            job_description=job_description,
        )
    except Exception as e:
        print(f"⚠️ Required skill extraction fallback used: {e}")

    required_skills = _normalize_required_skill_rows(required_seed + required_llm)
    if not required_skills:
        fallback = []
        for skill_name in list(get_all_skills(resume_data))[:8]:
            fallback.append({
                "skill": skill_name,
                "priority": "must_have",
                "required_level": "basic",
                "importance": 0.35,
                "evidence_from_jd": "Fallback inferred from candidate context",
            })
        required_skills = _normalize_required_skill_rows(fallback)

    candidate_seed = _normalize_candidate_skill_rows(_extract_candidate_skill_seed(resume_data))
    candidate_llm: list[dict] = []
    try:
        candidate_llm = await _llm_extract_candidate_skills(
            resume_data=resume_data,
            required_skills=required_skills,
            target_role=target_role,
        )
    except Exception as e:
        print(f"⚠️ Candidate skill extraction fallback used: {e}")

    candidate_skills = _merge_candidate_skill_rows(candidate_seed, candidate_llm)

    coverage_payload = _build_skill_coverage_board(required_skills, candidate_skills)
    coverage_board = coverage_payload.get("board", [])

    try:
        adjustments = await _llm_adjudicate_coverage(target_role, coverage_board)
        if adjustments:
            coverage_board = _apply_adjudication_adjustments(coverage_board, adjustments)
            coverage_payload["board"] = coverage_board
            # Recalculate score after conservative adjudication updates.
            weighted_score = 0.0
            weighted_total = 0.0
            must_weighted_score = 0.0
            must_weighted_total = 0.0
            nice_weighted_score = 0.0
            nice_weighted_total = 0.0
            for row in coverage_board:
                status = str(row.get("status") or "Missing").lower()
                importance = _clamp(_safe_float(row.get("importance"), 0.3), 0.2, 1.0)
                priority = _normalize_priority(row.get("priority"), default="must_have")
                weighted_score += importance * SKILL_STATUS_SCORE.get(status, 0.0)
                weighted_total += importance
                if priority == "must_have":
                    must_weighted_score += importance * SKILL_STATUS_SCORE.get(status, 0.0)
                    must_weighted_total += importance
                else:
                    nice_weighted_score += importance * SKILL_STATUS_SCORE.get(status, 0.0)
                    nice_weighted_total += importance
            coverage_payload["readiness_score"] = round(0.5 if weighted_total <= 0 else _clamp(weighted_score / weighted_total, 0.0, 1.0), 2)
            coverage_payload["coverage_summary"] = {
                "required_skills_count": len(required_skills),
                "candidate_skills_count": len(candidate_skills),
                "must_have_coverage": round(0.0 if must_weighted_total <= 0 else _clamp(must_weighted_score / must_weighted_total, 0.0, 1.0), 2),
                "nice_to_have_coverage": round(0.0 if nice_weighted_total <= 0 else _clamp(nice_weighted_score / nice_weighted_total, 0.0, 1.0), 2),
            }
    except Exception as e:
        print(f"⚠️ Adjudication pass skipped: {e}")

    followup_targets = _derive_followup_targets(coverage_board, limit=6)
    followup_questions = []
    try:
        followup_questions = await _llm_generate_followup_questions(target_role, followup_targets)
    except Exception as e:
        print(f"⚠️ Follow-up question generation fallback used: {e}")
    if not followup_questions:
        followup_questions = _default_followup_questions(target_role, followup_targets)

    skill_mapping = _skill_mapping_from_board(coverage_payload)
    skill_mapping["required_skills"] = required_skills
    skill_mapping["candidate_skills"] = candidate_skills[:30]
    skill_mapping["followup_targets"] = followup_targets
    skill_mapping["followup_questions"] = followup_questions

    readiness = round(_safe_float(coverage_payload.get("readiness_score"), 0.5), 2)
    print(
        f"🔍 Skill board built: required={len(required_skills)} "
        f"candidate={len(candidate_skills)} missing={len(skill_mapping.get('missing', []))} "
        f"partial={len(skill_mapping.get('partial', []))} readiness={int(readiness * 100)}%"
    )

    return {
        **state,
        "job_requirements": {
            **job_reqs,
            "required_skills": required_skills,
        },
        "skill_mapping": skill_mapping,
        "readiness_score": readiness,
    }


# ---------------------------------------------------------
# NEW: The Architect Node (Replaces generate_dynamic_suggestions)
# ---------------------------------------------------------
async def generate_interview_loop_node(state: CareerAnalysisState) -> CareerAnalysisState:
    """
    Uses LLM to generate a custom 3-Round Interview Cycle based on
    Resume, Job Description, and Company Culture.
    """
    print("🏗️  Architecting custom interview loop...")
    
    resume_summary = state.get("resume_data", {}).get("summary", "Candidate")
    job_reqs = state.get("job_requirements", {})
    target_role = job_reqs.get("job_title", "Professional")
    company = job_reqs.get("target_company", "the company")
    
    # Get top gaps for context
    missing = state.get("skill_mapping", {}).get("missing", [])
    gaps_text = ', '.join([s['name'] for s in missing[:3]])
    
    system_prompt = """You are an Expert Hiring Manager designing an interview loop.
    Create a 2-Round Interview for this specific candidate and role.

    STRUCTURE:
    1. Round 1 (Behavioral): Assess cultural fit, leadership, and communication. Questions must be answerable by speaking (NO coding).
    2. Round 2 (Technical): Assess technical knowledge, system design thinking, and problem-solving. Questions must be answerable by speaking (NO coding, NO whiteboard).

    OUTPUT JSON ONLY:
    {
      "goal": "Role Name",
      "rounds": [
        {
          "id": "r1", "name": "Round 1: [Creative Title]", "description": "...", "status": "active",
          "sessions": [{"id": "s1", "title": "...", "type": "behavioral", "duration": "5m", "status": "pending"}]
        },
        {
          "id": "r2", "name": "Round 2: [Creative Title]", "description": "...", "status": "active",
          "sessions": [{"id": "s2", "title": "...", "type": "technical", "duration": "5m", "status": "pending"}]
        }
      ]
    }
    """
    
    user_msg = f"ROLE: {target_role} at {company}\nCANDIDATE GAPS: {gaps_text}"

    try:
        from server.services.llm_factory import get_chat_model
        chat_model = get_chat_model()
        response = await chat_model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg)
        ])

        # Parse JSON safely — robust cleanup for qwen3 quirks
        content = response.content.strip()

        # Strip <think>...</think> blocks (qwen3 reasoning traces)
        if "<think>" in content:
            content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()

        # Strip markdown code fences
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        content = content.strip()

        # Remove trailing commas before } or ]
        content = re.sub(r',(\s*[\}\]])', r'\1', content)
        # Remove single-line comments
        content = re.sub(r'//.*', '', content)

        try:
            loop_plan = json.loads(content)
        except json.JSONDecodeError:
            # Try json_repair as last resort
            from json_repair import repair_json
            loop_plan = json.loads(repair_json(content))
        loop_plan["created_at"] = str(datetime.now())
        
        # --- ENFORCE STABLE IDs (Fix for Caching) ---
        # Regardless of what LLM output, force s1, s2, s3...
        try:
             session_count = 1
             if "rounds" in loop_plan:
                 for round_ in loop_plan["rounds"]:
                     if "sessions" in round_:
                         for sess in round_["sessions"]:
                             sess["id"] = f"s{session_count}"
                             session_count += 1
        except Exception as e:
            print(f"⚠️ Failed to re-index session IDs: {e}")
            
        # Normalize titles so sessions are saved with stable, readable labels.
        loop_plan = normalize_practice_plan_titles(loop_plan)

        # Save to state
        return {**state, "practice_plan": loop_plan}

    except Exception as e:
        print(f"❌ Architect Failed: {e}")
        return {**state, "practice_plan": _fallback_loop(target_role)}

def _fallback_loop(role):
    """Fallback if LLM fails."""
    return {
        "goal": role,
        "rounds": [
            {
                "id": "r1", "name": "Round 1: Behavioral", "description": "Assess cultural fit, leadership, and communication skills.", "status": "active",
                "sessions": [{"id": "s1", "title": "Behavioral Interview", "type": "behavioral", "duration": "5m", "status": "pending"}]
            },
            {
                "id": "r2", "name": "Round 2: Technical", "description": "Evaluate technical knowledge and problem-solving approach.", "status": "active",
                "sessions": [{"id": "s2", "title": "Technical Discussion", "type": "technical", "duration": "5m", "status": "pending"}]
            }
        ]
    }


# Track active background generation tasks to prevent duplicates
_active_background_tasks: set[str] = set()
_background_generation_tasks: dict[str, asyncio.Task] = {}
# Time-based cooldown: user_id -> last trigger timestamp
_generation_cooldowns: dict[str, float] = {}
# Cooldown period in seconds
_GENERATION_COOLDOWN_SECONDS = 60

def trigger_background_generation(
    user_id: str,
    state: CareerAnalysisState,
    force_refresh: bool = False
):
    """
    Fire-and-forget task to pre-generate questions for all sessions.
    Handles both practice_plan (new) and suggested_sessions (legacy) formats.
    Includes deduplication and time-based cooldown.
    """
    import time
    from server.services.cache import get_question_cache

    # Cooldown check (skip on force refresh)
    now = time.time()
    last_trigger = _generation_cooldowns.get(user_id, 0)
    if not force_refresh and (now - last_trigger < _GENERATION_COOLDOWN_SECONDS):
        return

    # Active task check (force refresh cancels stale task)
    existing_task = _background_generation_tasks.get(user_id)
    if existing_task and not existing_task.done():
        if force_refresh:
            existing_task.cancel()
            _active_background_tasks.discard(user_id)
            _background_generation_tasks.pop(user_id, None)
            print(f"🔄 Cancelled existing background generation for {user_id}")
        else:
            return

    if user_id in _active_background_tasks:
        return

    cache = get_question_cache()
    persona_for_generation = "friendly"
    try:
        from server.services.user_database import get_user_db
        prefs = get_user_db().get_user_preferences(user_id) or {}
        incoming_persona = str(prefs.get("interviewer_persona") or "friendly").strip().lower()
        if incoming_persona in {"friendly", "strict", "rapid_fire", "skeptical"}:
            persona_for_generation = incoming_persona
    except Exception:
        persona_for_generation = "friendly"
    persona_suffix = f"_p{persona_for_generation}"
    uncached_sessions = []
    seen_session_ids: set[str] = set()
    job_title = state.get("job_requirements", {}).get("job_title", "generic")
    safe_title = re.sub(r'[^a-zA-Z0-9]', '_', job_title).lower()

    def _add_session(sess: dict):
        sess_id = sess.get("id")
        if not sess_id or sess_id in seen_session_ids:
            return

        simple_key = f"{user_id}_{sess_id}"
        full_key = f"{user_id}_{safe_title}_{sess_id}"
        persona_simple_key = f"{simple_key}{persona_suffix}"
        persona_full_key = f"{full_key}{persona_suffix}"

        if force_refresh:
            uncached_sessions.append(sess)
            seen_session_ids.add(sess_id)
            return

        if cache.get(persona_simple_key) or cache.get(persona_full_key):
            return
        # Friendly persona keeps legacy cache compatibility.
        if persona_for_generation == "friendly" and (cache.get(simple_key) or cache.get(full_key)):
            return

        uncached_sessions.append(sess)
        seen_session_ids.add(sess_id)

    # Collect sessions from practice_plan (new format)
    practice_plan = state.get("practice_plan", {})
    if practice_plan and "rounds" in practice_plan:
        for round_obj in practice_plan["rounds"]:
            for sess in round_obj.get("sessions", []):
                _add_session(sess)

    # Also collect from suggested_sessions (legacy format)
    suggestions = state.get("suggested_sessions", [])
    if suggestions:
        for sess in suggestions:
            _add_session(sess)

    if not uncached_sessions:
        _generation_cooldowns[user_id] = now
        return

    # Mark as active and update cooldown
    _active_background_tasks.add(user_id)
    _generation_cooldowns[user_id] = now

    async def _generate_task():
        from server.agents.interview_nodes import generate_interview_questions

        try:
            print(f"🚀 Generating questions for {len(uncached_sessions)} session(s)...")

            for sess in uncached_sessions:
                try:
                    job_title = state.get("job_requirements", {}).get("job_title", "Professional")

                    # Determine focus based on session type
                    focus = []
                    if sess.get("type") == "behavioral":
                        focus = [{"name": "Behavioral Questions"}]
                    elif sess.get("focus_topic"):
                        focus = [{"name": sess["focus_topic"]}]

                    interview_state = {
                        "job_title": job_title,
                        "skill_gaps": focus or state.get("skill_mapping", {}).get("missing", []),
                        "readiness_score": state.get("readiness_score", 0.5),
                        "mode": "practice",
                        "interviewer_persona": persona_for_generation,
                        "questions": [],
                        "current_question_index": 0
                    }

                    print(f"⚡ Pre-generating for [{sess.get('title', sess.get('id'))}]...")
                    result_state = await generate_interview_questions(interview_state)

                    questions = result_state.get("questions", [])
                    if questions:
                        # Cache with both key formats for compatibility.
                        # On force refresh, clear existing keys first to avoid stale reads.
                        simple_key = f"{user_id}_{sess['id']}"
                        persona_simple_key = f"{simple_key}{persona_suffix}"
                        if force_refresh:
                            cache.delete(persona_simple_key)
                        cache.set(persona_simple_key, questions, user_id=user_id, job_title=job_title, session_id=sess["id"])

                        if force_refresh:
                            cache.delete(simple_key)
                        if persona_for_generation == "friendly":
                            cache.set(simple_key, questions, user_id=user_id, job_title=job_title, session_id=sess["id"])

                        full_key = f"{user_id}_{safe_title}_{sess['id']}"
                        persona_full_key = f"{full_key}{persona_suffix}"
                        if full_key != simple_key:
                            if force_refresh:
                                cache.delete(persona_full_key)
                            cache.set(persona_full_key, questions, user_id=user_id, job_title=job_title, session_id=sess["id"])

                        if full_key != simple_key:
                            if force_refresh:
                                cache.delete(full_key)
                            if persona_for_generation == "friendly":
                                cache.set(full_key, questions, user_id=user_id, job_title=job_title, session_id=sess["id"])

                        print(f"💾 Cached {len(questions)} Qs for {sess['id']} [{persona_for_generation}]")

                        # Persist to DB plan if applicable
                        try:
                            from server.services.user_database import get_user_db
                            user_db = get_user_db()
                            if practice_plan and "rounds" in practice_plan:
                                for round_ in practice_plan["rounds"]:
                                    for s in round_.get("sessions", []):
                                        if s.get("id") == sess["id"]:
                                            by_persona = s.get("questions_by_persona")
                                            if not isinstance(by_persona, dict):
                                                by_persona = {}
                                            by_persona[persona_for_generation] = questions
                                            s["questions_by_persona"] = by_persona
                                            # Keep legacy slot for friendly compatibility only.
                                            if persona_for_generation == "friendly":
                                                s["questions"] = questions
                                user_db.update_latest_analysis_plan(user_id, practice_plan)
                        except Exception as e:
                            print(f"⚠️ Failed to persist questions to DB: {e}")

                except Exception as e:
                    print(f"⚠️ Failed to pre-generate for session {sess.get('id')}: {e}")

            print("✅ Background generation complete.")
        except Exception as e:
            print(f"❌ Background generation error: {e}")
        finally:
            _active_background_tasks.discard(user_id)
            _background_generation_tasks.pop(user_id, None)

    # Launch in background
    task = asyncio.create_task(_generate_task())
    _background_generation_tasks[user_id] = task


# ============== Mindmap Generator Node ==============

async def generate_mindmap_node(state: CareerAnalysisState) -> CareerAnalysisState:
    """Generate a Mermaid.js flowchart visualization of skill gaps with adaptive layout."""
    skill_mapping = state.get("skill_mapping", {})
    job_requirements = state.get("job_requirements", {})
    readiness_score = state.get("readiness_score", 0.0)
    
    job_title = job_requirements.get("job_title", "Target Role")
    safe_title = sanitize_mermaid_text(job_title, max_length=40)
    
    def get_skill_name(skill_obj):
        if isinstance(skill_obj, dict):
            return skill_obj.get("name", "Unknown")
        return str(skill_obj)

    matched = skill_mapping.get("matched", [])[:10]
    partial = skill_mapping.get("partial", [])[:10]
    missing = skill_mapping.get("missing", [])[:10]
    extra = skill_mapping.get("candidate_extra_skills", [])[:5]
    
    total_skills = len(matched) + len(partial) + len(missing) + len(extra)
    layout = "TD" if total_skills > 15 else "LR"
    
    lines = [
        f"flowchart {layout}",
        "",
        "    classDef green fill:#065f46,stroke:#10b981,stroke-width:2px,color:#fff",
        "    classDef yellow fill:#854d0e,stroke:#eab308,stroke-width:2px,color:#fff",
        "    classDef red fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#fff",
        "    classDef blue fill:#1e3a5f,stroke:#3b82f6,stroke-width:2px,color:#fff",
        "    classDef root fill:#7c2d12,stroke:#f97316,stroke-width:3px,color:#fff",
        "",
        f"    ROOT[({safe_title}<br/>Score: {int(readiness_score * 100)}%)]:::root",
    ]
    
    node_id = 0
    
    if matched:
        lines.append(f"    ROOT --> STRENGTHS[✓ Strengths ({len(matched)})]:::green")
        for skill in matched:
            safe_skill = sanitize_mermaid_text(get_skill_name(skill))
            if safe_skill and safe_skill != "Unknown":
                lines.append(f"    STRENGTHS --> S{node_id}[{safe_skill}]:::green")
                node_id += 1
    
    if partial:
        lines.append(f"    ROOT --> DEVELOPING[◐ Developing ({len(partial)})]:::yellow")
        for skill in partial:
            safe_skill = sanitize_mermaid_text(get_skill_name(skill))
            if safe_skill and safe_skill != "Unknown":
                lines.append(f"    DEVELOPING --> D{node_id}[{safe_skill}]:::yellow")
                node_id += 1
    
    if missing:
        lines.append(f"    ROOT --> GAPS[✗ Gaps ({len(missing)})]:::red")
        for skill in missing:
            safe_skill = sanitize_mermaid_text(get_skill_name(skill))
            if safe_skill and safe_skill != "Unknown":
                lines.append(f"    GAPS --> G{node_id}[{safe_skill}]:::red")
                node_id += 1
    
    if extra:
        lines.append(f"    ROOT --> BONUS[★ Bonus ({len(extra)})]:::blue")
        for skill in extra:
            safe_skill = sanitize_mermaid_text(get_skill_name(skill))
            if safe_skill and safe_skill != "Unknown":
                lines.append(f"    BONUS --> B{node_id}[{safe_skill}]:::blue")
                node_id += 1
    
    diagram = "\n".join(lines)
    
    return {
        **state,
        "mindmap": diagram
    }


# ============== Bridge Role Suggester Node ==============

async def suggest_bridge_roles_node(state: CareerAnalysisState) -> CareerAnalysisState:
    """Suggest bridge roles if readiness score < 0.6."""
    readiness_score = state.get("readiness_score", 0.0)
    job_requirements = state.get("job_requirements", {})
    resume_data = state.get("resume_data", {})
    
    bridge_roles = []
    
    if readiness_score < 0.6:
        job_title = job_requirements.get("job_title", "")
        target_level = job_requirements.get("career_level", estimate_role_level(job_title))
        current_skills = get_all_skills(resume_data)
        
        bridge_roles = get_bridge_role_suggestions(
            job_title,
            target_level,
            current_skills
        )
        
        missing_skills = state.get("skill_mapping", {}).get("missing", [])
        for role in bridge_roles:
            role["skills_to_develop"] = missing_skills[:3]
    
    return {
        **state,
        "bridge_roles": bridge_roles
    }


# ============== Full Analysis Pipeline with Progress Callbacks ==============

async def analyze_career_path(
    resume_text: str | bytes,
    target_role: str,
    target_company: str = "a top tech company",
    job_description: str = "",
    emit_progress: Optional[Callable[[str, str], Any]] = None
) -> CareerAnalysisState:
    """
    OPTIMIZED Career Analysis Pipeline with Parallel Execution.
    
    Pipeline: 
    1. Extract PDF text (if needed)
    2. PARALLEL: Parse resume (LLM) + Infer job requirements (LLM)
    3. Map skills with streaming (LLM)
    4. Generate mindmap (rule-based)
    5. Suggest bridge roles (rule-based)
    """
    from server.tools.job_tool import infer_job_requirements
    # CHANGED: Use the correct function name here
    from server.tools.resume_tool import parse_resume_node, extract_text_from_pdf_bytes
    
    async def _emit(stage: str, message: str):
        if emit_progress:
            await emit_progress(stage, message)
        print(f"📊 [{stage}] {message}")
    
    # Initialize state
    state: CareerAnalysisState = {
        "resume_data": {},
        "job_requirements": {},
        "skill_mapping": {},
        "readiness_score": 0.0,
        "mindmap": "",
        "bridge_roles": [],
        "suggested_sessions": [],
        "practice_plan": {},
        "skill_gaps": [],
        "job_description": job_description,
        "error": None
    }
    
    try:
        # ========== Step 1: Prepare Resume Text ==========
        await _emit("step_1", "📄 Processing resume...")
        
        final_resume_text = ""
        if isinstance(resume_text, bytes):
             await _emit("step_1", "📄 Extracting text from resume PDF...")
             # CHANGED: Call the correct function
             final_resume_text = extract_text_from_pdf_bytes(resume_text)
        else:
             final_resume_text = resume_text

        if not final_resume_text.strip():
            state["error"] = "Could not extract text from resume"
            return state
        
        await _emit("step_1_done", f"✅ Processed {len(final_resume_text)} characters")
        
        # ========== Step 2: PARALLEL - Parse resume + Infer job requirements ==========
        await _emit("step_2", f"🚀 Parallel processing: parsing resume AND analyzing {target_role} requirements...")
        
        resume_bytes_for_parsing = final_resume_text.encode('utf-8')
        resume_task = parse_resume_node(resume_bytes_for_parsing, mime_type="text/plain")
        job_task = infer_job_requirements(target_role, target_company, job_description)
        
        resume_data, job_requirements = await asyncio.gather(
            resume_task,
            job_task,
            return_exceptions=True
        )
        
        if isinstance(resume_data, Exception):
            await _emit("error", f"❌ Resume parsing failed: {resume_data}")
            resume_data = {"skills": {}, "experience": []}
        
        state["resume_data"] = resume_data
        
        if isinstance(job_requirements, Exception):
            await _emit("error", f"❌ Job inference failed: {job_requirements}")
            job_requirements = {
                "job_title": target_role, 
                "must_have_skills": [], 
                "nice_to_have_skills": []
            }
        
        state["job_requirements"] = job_requirements
        
        # ========== Step 3: Multi-pass skill mapping ==========
        await _emit("step_3", "🎯 Building required-vs-candidate skill board...")
        state = await map_skills_node(state)
        await _emit("step_3_done", "✅ Skill board and readiness scoring complete")
        missing_skills = state.get("skill_mapping", {}).get("missing", [])
        partial_skills = state.get("skill_mapping", {}).get("partial", [])
        uncertain_partial = [item for item in partial_skills if str(item.get("status") or "").lower() == "uncertain"]
        state["skill_gaps"] = (missing_skills + uncertain_partial)[:12]
        
        # ========== Step 4: Generate mindmap ==========
        await _emit("step_4", "🗺️ Generating visual mindmap...")
        state = await generate_mindmap_node(state)
        await _emit("step_4_done", "✅ Mindmap generated")
        
        # ========== Step 5: Suggest bridge roles ==========
        if state["readiness_score"] < 0.6:
            await _emit("step_5", "🌉 Analyzing career path options...")
            state = await suggest_bridge_roles_node(state)

        # ========== Step 6: Generate Interview Loop (LLM-Driven) ==========
        await _emit("step_6", "🏗️ Architecting your interview loop...")
        state = await generate_interview_loop_node(state)
        
        # Also generate legacy suggestions for backwards compatibility + follow-up drill targets.
        missing_skills = state["skill_mapping"].get("missing", [])
        suggestions = generate_dynamic_suggestions(target_role, target_company, missing_skills)
        followup_targets = state.get("skill_mapping", {}).get("followup_targets", [])
        followup_drills: list[dict] = []
        for idx, target in enumerate(followup_targets[:2], start=1):
            skill_name = str(target.get("name") or target.get("skill") or "Core competency").strip()
            if not skill_name:
                continue
            followup_drills.append({
                "id": f"focus_{idx}",
                "title": f"Validation Drill: {skill_name}",
                "subtitle": "Targeted evidence practice",
                "description": f"Validate depth in {skill_name} with concrete project examples and trade-offs.",
                "icon": "FactCheck",
                "color": "orange",
                "duration": "12 min",
                "type": "drill",
                "focus_topic": skill_name,
            })
        if followup_drills:
            suggestions = followup_drills + suggestions
        state["suggested_sessions"] = suggestions[:6]
        
        # ========== Done! ==========
        score = int(state["readiness_score"] * 100)
        await _emit("complete", f"🎉 Analysis complete! Readiness: {score}%")
        
        return state
        
    except Exception as e:
        await _emit("error", f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        state["error"] = str(e)
        return state


# ============== Regeneration & Background Logic ==============

async def regenerate_suggestions(
    old_state: CareerAnalysisState,
    user_prompt: str
) -> list[dict]:
    """
    Regenerate interview suggestions based on user prompt.
    E.g. "Give me harder system design questions" or "Focus on Python only".
    """
    resume_data = old_state.get("resume_data", {})
    job_requirements = old_state.get("job_requirements", {})
    skill_mapping = old_state.get("skill_mapping", {})
    
    job_title = job_requirements.get("job_title", "Software Engineer")
    company = job_requirements.get("target_company", "a top tech company")
    
    # Extract skills
    missing = []
    for item in skill_mapping.get("missing", [])[:5]:
        if isinstance(item, dict):
            name = item.get("name")
        else:
            name = str(item)
        if name:
            missing.append(str(name))
    matched = []
    for item in skill_mapping.get("matched", [])[:5]:
        if isinstance(item, dict):
            name = item.get("name")
        else:
            name = str(item)
        if name:
            matched.append(str(name))
    
    system_prompt = f"""You are an expert interview coach for {job_title} roles at {company}.
    
    CONTEXT:
    - User Strengths: {', '.join(matched)}
    - User Gaps: {', '.join(missing)}
    
    CURRENT TASK:
    Generate 3 NEW, distinct interview session suggestions based on this user request:
    "{user_prompt}"
    
    OUTPUT JSON ONLY (List of 3 objects):
    [
      {{
        "id": "s1",  // ALWAYS use s1, s2, s3 for the 3 items
        "title": "Short Title",
        "subtitle": "Subtitle",
        "description": "1 sentence description",
        "icon": "Material Icon Name (e.g. Code, Storage, Security, Psychology)",
        "color": "blue|red|green|orange|purple",
        "duration": "15 min",
        "type": "technical|behavioral|drill",
        "focus_topic": "Specific topic if drill/technical"
      }}
    ]
    """
    
    try:
        from server.services.llm_factory import get_chat_model
        chat_model = get_chat_model()
        
        response = await chat_model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content="Generate new suggestions.")
        ])
        
        from server.tools.resume_tool import parse_json_safely
        new_suggestions = parse_json_safely(response.content)
        
        if not new_suggestions or not isinstance(new_suggestions, list):
            raise ValueError("Invalid suggestion format")
            
        return new_suggestions
        
    except Exception as e:
        print(f"❌ Regeneration failed: {e}")
        # Fallback to defaults
        return generate_dynamic_suggestions(job_title, company, skill_mapping.get("missing", []))


# NOTE: Duplicate trigger_background_generation and globals removed.
# The unified version above (using shared _active_background_tasks, _generation_cooldowns)
# handles both practice_plan (new) and suggested_sessions (legacy) formats.


# ============== Legacy Session Generator (Kept for backwards compatibility) ==============

def generate_dynamic_suggestions(target_role: str, company: str, missing_skills: list) -> list[dict]:
    """
    Generate 3 personalized session cards based on role and gaps.
    DEPRECATED: Use generate_interview_loop_node instead.
    """
    suggestions = []
    role_lower = target_role.lower()

    # --- Card 1: Resume Deep Dive (Always valuable) ---
    suggestions.append({
        "id": "resume",
        "title": "Resume Deep Dive",
        "subtitle": "Based on your experience",
        "description": "AI will quiz you on specific projects and claims found in your resume.",
        "icon": "Description",
        "color": "purple",
        "duration": "15 min",
        "type": "resume"
    })

    # --- Card 2: Role-Specific Core ---
    if any(x in role_lower for x in ["nurse", "medical", "doctor", "clinical"]):
        # Healthcare
        suggestions.append({
            "id": "clinical_core",
            "title": "Clinical Scenarios",
            "subtitle": f"Core {target_role} Skills",
            "description": "Patient triage, bedside manner, and situational judgement questions.",
            "icon": "LocalHospital",
            "color": "red",
            "duration": "20 min",
            "type": "technical"
        })
    elif any(x in role_lower for x in ["sales", "account", "business", "marketing"]):
        # Business
        suggestions.append({
            "id": "business_case",
            "title": "Mock Pitch & Strategy",
            "subtitle": f"For {company}",
            "description": "Value proposition, objection handling, and strategic thinking.",
            "icon": "TrendingUp",
            "color": "green",
            "duration": "20 min",
            "type": "technical"
        })
    elif any(x in role_lower for x in ["engineer", "developer", "data", "scientist"]):
        # Tech
        suggestions.append({
            "id": "tech_core",
            "title": "Technical Core",
            "subtitle": f"{target_role} Fundamentals",
            "description": "Algorithms, system design, and technical concepts for this role.",
            "icon": "Code",
            "color": "blue",
            "duration": "20 min",
            "type": "technical"
        })
    else:
        # General / Universal
        suggestions.append({
            "id": "role_core",
            "title": f"{target_role} Core",
            "subtitle": "Role Competencies",
            "description": f"Standard interview questions tailored for {target_role} positions.",
            "icon": "Work",
            "color": "blue",
            "duration": "20 min",
            "type": "technical"
        })

    # --- Card 3: Targeted Weakness Drill ---
    if missing_skills:
        # Pick the first major gap
        try:
            gap_name = missing_skills[0].get("name", "General") if isinstance(missing_skills[0], dict) else str(missing_skills[0])
        except (IndexError, AttributeError):
            gap_name = "General"
            
        suggestions.append({
            "id": "gap_drill",
            "title": f"Drill: {gap_name}",
            "subtitle": "Focus on your Gap",
            "description": f"Intensive practice session to improve your knowledge of {gap_name}.",
            "icon": "Warning",
            "color": "orange",
            "duration": "15 min",
            "type": "drill",
            "focus_topic": gap_name
        })
    else:
        # Fallback if no gaps (Behavioral)
        suggestions.append({
            "id": "behavioral",
            "title": "Behavioral Fit",
            "subtitle": f"Culture at {company}",
            "description": "STAR method practice and culture-fit questions.",
            "icon": "EmojiPeople",
            "color": "orange",
            "duration": "15 min",
            "type": "behavioral"
        })

    return suggestions
