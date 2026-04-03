"""
Interview Practice Agent Nodes.
Handles question generation, answer evaluation, and real-time coaching.
"""

import asyncio
import json
import re
from collections import Counter
from typing import Any, Callable, Literal, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
except Exception:
    HAS_PYDANTIC = False

    class BaseModel:  # type: ignore[override]
        """Fallback marker when pydantic is unavailable."""
        pass

    def Field(default=None, default_factory=None):  # type: ignore[override]
        if default_factory is not None:
            return default_factory()
        return default

from server.config import settings
from server.services.llm_factory import get_chat_model
from server.tools.resume_tool import parse_json_safely


# ============== Interview State Schema ==============

InterviewMode = Literal["practice", "coaching", "evaluation"]


class InterviewState(TypedDict):
    """State for interview practice session."""
    # Context from analysis
    job_title: str
    skill_gaps: list[str]
    readiness_score: float
    interview_type: str
    interviewer_persona: str
    question_count: int | None
    
    # Interview session
    mode: InterviewMode
    questions: list[dict]
    current_question_index: int
    
    # Current answer tracking
    current_answer: str
    answer_evaluations: list[dict]
    
    # Coaching state
    coaching_enabled: bool
    struggle_detected: bool
    hint_count: int


class GeneratedQuestionSchema(BaseModel):
    text: str
    category: str = "Technical"
    skill_tested: str = "Core competency"
    difficulty: str = "medium"
    expected_points: list[str] = Field(default_factory=list)
    time_estimate_minutes: int = 3


class GeneratedQuestionsSchema(BaseModel):
    questions: list[GeneratedQuestionSchema] = Field(default_factory=list)


class EvaluationBreakdownSchema(BaseModel):
    relevance: float = 5.0
    depth: float = 5.0
    structure: float = 5.0
    specificity: float = 5.0
    communication: float = 5.0


class EvaluationResponseSchema(BaseModel):
    evaluation_reasoning: str = ""
    score_breakdown: EvaluationBreakdownSchema = Field(default_factory=EvaluationBreakdownSchema)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    coaching_tip: str = ""
    model_answer: str = ""


class SummaryResponseSchema(BaseModel):
    overall_feedback: str = ""
    top_strengths: list[str] = Field(default_factory=list)
    areas_to_improve: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    communication_feedback: str = ""


def _dump_structured(value: Any) -> Any:
    """Convert pydantic or message objects into plain python dict/list values."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_dump_structured(item) for item in value]
    return value


EVAL_DIMENSIONS = ("relevance", "depth", "structure", "specificity", "communication")
EVAL_WEIGHTS = {"relevance": 0.25, "depth": 0.25, "structure": 0.15, "specificity": 0.20, "communication": 0.15}


def _compute_overall_breakdown(evaluations: list[dict]) -> dict:
    """
    Compute average score breakdown across all answered questions.
    Falls back to per-question score when a dimension is missing.
    """
    buckets: dict[str, list[float]] = {k: [] for k in EVAL_DIMENSIONS}

    for item in evaluations or []:
        evaluation = (item or {}).get("evaluation") or {}
        score_default = _clamp_score(evaluation.get("score", 0.0), default=0.0)
        breakdown = evaluation.get("score_breakdown") or {}

        for dim in EVAL_DIMENSIONS:
            value = _clamp_score(breakdown.get(dim, score_default), default=score_default)
            buckets[dim].append(value)

    result = {}
    for dim in EVAL_DIMENSIONS:
        values = buckets[dim]
        result[dim] = round(sum(values) / len(values), 1) if values else 0.0
    return result


async def _invoke_structured_output(messages: list, schema_model: type[BaseModel]) -> Optional[dict]:
    """
    Prefer schema-bound output when model/backend supports it.
    Falls back to parser path on unsupported providers/models.
    """
    if not HAS_PYDANTIC:
        return None
    try:
        model = get_chat_model()
        if not hasattr(model, "with_structured_output"):
            return None
        structured_model = model.with_structured_output(schema_model)
        response = await structured_model.ainvoke(messages)
        payload = _dump_structured(response)
        if isinstance(payload, dict):
            return payload
    except Exception as e:
        # Expected for LM Studio MLX — structured json_schema not supported; parser path handles it fine.
        pass
    return None


# ============== Question Generator ==============

def detect_role_type(job_title: str) -> str:
    """Classify role family for better interview question mix."""
    title = (job_title or "").lower()
    if any(k in title for k in ["engineer", "developer", "architect", "scientist", "analyst", "devops"]):
        return "tech"
    if any(k in title for k in ["nurse", "doctor", "clinical", "medical", "therapist"]):
        return "healthcare"
    if any(k in title for k in ["designer", "writer", "creative", "content", "brand"]):
        return "creative"
    if any(k in title for k in ["manager", "marketing", "sales", "finance", "consultant", "operations"]):
        return "business"
    return "general"


def _sanitize_questions(raw_questions: list, total_questions: int, job_title: str, skill_gap_names: list[str]) -> list[dict]:
    """Normalize generated question payload so downstream logic is stable."""
    cleaned: list[dict] = []
    for i, q in enumerate(raw_questions[:total_questions]):
        if not isinstance(q, dict):
            continue
        text = str(q.get("text", "")).strip()
        if not text:
            continue
        expected_points = q.get("expected_points") or []
        if not isinstance(expected_points, list):
            expected_points = [str(expected_points)]
        expected_points = [str(p).strip() for p in expected_points if str(p).strip()][:5]
        if len(expected_points) < 3:
            expected_points = expected_points + [
                "Clear structure and context",
                "Concrete reasoning and trade-offs",
                "Specific example from experience",
            ]
            expected_points = expected_points[:3]

        cleaned.append({
            "text": text,
            "category": str(q.get("category", "Technical")).strip() or "Technical",
            "skill_tested": str(q.get("skill_tested", skill_gap_names[i % len(skill_gap_names)] if skill_gap_names else "Core competency")).strip(),
            "difficulty": str(q.get("difficulty", "medium")).strip().lower(),
            "expected_points": expected_points,
            "time_estimate_minutes": int(q.get("time_estimate_minutes", 3) or 3),
            "is_followup": bool(q.get("is_followup", False))
        })

    if len(cleaned) >= total_questions:
        return cleaned[:total_questions]

    fallback_bank = [
        ("Behavioral", "medium", "Tell me about a time you faced ambiguity in a project. How did you create clarity and move forward?", ["Situation context", "Decision framework", "Stakeholder communication", "Outcome and lesson"]),
        ("Technical", "easy", f"Explain the core responsibilities of a {job_title} and how you prioritize them.", ["Core responsibilities", "Prioritization approach", "Trade-offs", "Example"]),
        ("Technical", "medium", "Walk me through a design or process decision you made and why you chose that approach over alternatives.", ["Problem framing", "Alternatives considered", "Reasoning and trade-offs", "Results"]),
        ("Behavioral", "medium", "Describe a difficult collaboration moment and how you handled disagreement constructively.", ["Conflict context", "Communication approach", "Resolution", "Takeaway"]),
        ("Technical", "hard", "If performance or quality dropped unexpectedly, how would you diagnose and recover?", ["Debug/triage plan", "Hypothesis-driven steps", "Metrics/signals", "Preventive actions"]),
        ("Behavioral", "medium", "Share an example of feedback you received that changed your approach.", ["Feedback source", "Behavior change", "Evidence of improvement", "Reflection"]),
        ("Technical", "hard", "What risks do teams overlook most often in this kind of work, and how do you mitigate them?", ["Risk identification", "Impact assessment", "Mitigations", "Monitoring"]),
    ]

    idx = 0
    while len(cleaned) < total_questions:
        category, difficulty, text, expected_points = fallback_bank[idx % len(fallback_bank)]
        skill_name = skill_gap_names[idx % len(skill_gap_names)] if skill_gap_names else "Core competency"
        cleaned.append({
            "text": text,
            "category": category,
            "skill_tested": skill_name,
            "difficulty": difficulty,
            "expected_points": expected_points[:5],
            "time_estimate_minutes": 3,
            "is_followup": False
        })
        idx += 1

    return cleaned[:total_questions]

async def generate_interview_questions(
    state: InterviewState,
    progress_callback: Optional[Callable] = None
) -> InterviewState:
    """
    Generate 5-10 personalized questions based on skill gaps.
    
    Logic:
    - If readiness < READINESS_LOW_CUTOFF: Generate fundamental/easy questions
    - If readiness in [READINESS_LOW_CUTOFF, READINESS_MID_CUTOFF): Mix of fundamental + intermediate
    - If readiness >= READINESS_MID_CUTOFF: Challenging questions
    """
    skill_gaps = state.get("skill_gaps", [])
    job_title = state.get("job_title", "Software Engineer")
    readiness = state.get("readiness_score", 0.5)
    interview_type = str(state.get("interview_type", "mixed") or "mixed").strip().lower()
    interviewer_persona = str(state.get("interviewer_persona", "friendly") or "friendly").strip().lower()
    if interviewer_persona not in {"friendly", "strict"}:
        interviewer_persona = "friendly"
    persona_profiles = {
        "friendly": {
            "label": "Friendly",
            "tone": "Warm, encouraging, and collaborative while still rigorous.",
            "rules": [
                "Use approachable language without reducing difficulty.",
                "Frame prompts in a supportive, confidence-building tone.",
            ],
        },
        "strict": {
            "label": "Strict",
            "tone": "Direct, high-bar, and precision-focused.",
            "rules": [
                "Use concise wording that demands specific, measurable answers.",
                "Prefer prompts that expose gaps in structure and rigor.",
            ],
        },
    }
    persona_profile = persona_profiles[interviewer_persona]

    # Extract skill names if they are dictionaries (new format)
    skill_gap_names = []
    for s in skill_gaps:
        if isinstance(s, dict):
            skill_gap_names.append(s.get("name", str(s)))
        else:
            skill_gap_names.append(str(s))
    
    async def emit(msg):
        if progress_callback:
            await progress_callback("status", msg)
        print(f"📊 {msg}")
    
    await emit(f"Generating adaptive questions for {job_title}...")

    requested_count = state.get("question_count")
    if requested_count is not None:
        try:
            requested_count = int(requested_count)
            requested_count = max(1, min(12, requested_count))
        except Exception:
            requested_count = None

    if requested_count is not None:
        total_questions = requested_count
        difficulty_mix = f"adaptive mix across {total_questions} question(s)"
    elif readiness < settings.READINESS_LOW_CUTOFF:
        total_questions = 5
        difficulty_mix = "3 easy, 2 medium, 0 hard"
    elif readiness < settings.READINESS_MID_CUTOFF:
        total_questions = 6
        difficulty_mix = "2 easy, 3 medium, 1 hard"
    else:
        total_questions = 7
        difficulty_mix = "1 easy, 3 medium, 3 hard"

    role_type = detect_role_type(job_title)
    role_mix = {
        "tech": "40% technical concepts, 25% system design, 20% behavioral, 15% troubleshooting",
        "business": "35% role-specific execution, 35% behavioral/situational, 20% strategy, 10% analytics",
        "healthcare": "40% clinical/role-specific judgement, 30% situational response, 20% communication, 10% ethics",
        "creative": "35% portfolio/process, 30% collaboration, 20% strategy, 15% delivery",
        "general": "35% role execution, 35% behavioral, 20% problem-solving, 10% communication"
    }[role_type]

    type_overrides = {
        "behavioral": {
            "mix": "70% behavioral/situational, 20% communication, 10% reflection/growth",
            "requirements": [
                "At least 3 behavioral/situational questions",
                "Use prompts that encourage STAR-style answers",
                "Minimize deeply technical architecture prompts",
            ],
        },
        "technical": {
            "mix": "65% technical reasoning, 25% troubleshooting, 10% behavioral",
            "requirements": [
                "At least 3 role-specific technical reasoning questions",
                "Include practical debugging and trade-off questions",
                "Avoid purely culture-fit prompts dominating the set",
            ],
        },
        "system_design": {
            "mix": "70% system design/architecture, 20% reliability/performance, 10% behavioral",
            "requirements": [
                "At least 3 architecture/scalability design prompts",
                "Emphasize trade-offs, bottlenecks, and failure modes",
                "Do not ask coding implementation questions",
            ],
        },
        "mixed": {
            "mix": role_mix,
            "requirements": [
                "At least 2 behavioral/situational questions",
                "At least 2 role-specific technical/reasoning questions",
                "Questions should progressively get harder",
            ],
        },
    }
    interview_track = type_overrides.get(interview_type, type_overrides["mixed"])
    effective_role_mix = interview_track["mix"]
    type_requirements = "\n".join([f"- {line}" for line in interview_track["requirements"]])

    # Get job description context if available
    job_description = state.get("job_description", "")
    jd_context = f"\n- Job Description: {job_description[:500]}" if job_description else ""
    is_cold_start = len(skill_gap_names) == 0

    # Cold-start: derive focus areas from JD instead of analysis
    if is_cold_start and job_description:
        skill_focus = "Derive from job description below"
        weak_area_focus = "key competencies extracted from the job description"
        cold_start_block = (
            "\nCOLD-START MODE (no prior skill analysis available):\n"
            "Carefully read the Job Description above and identify the 3-5 most "
            "critical competencies, technologies, or responsibilities it mentions. "
            "Use those as the primary focus areas for your questions. Ensure questions "
            "are tightly aligned to what this specific role demands.\n"
        )
    else:
        skill_focus = ', '.join(skill_gap_names[:8]) if skill_gap_names else 'General skills'
        weak_area_focus = ', '.join(skill_gap_names[:5]) if skill_gap_names else 'core role competencies'
        cold_start_block = ""

    system_prompt = f"""You are an expert interviewer for {job_title} positions.

CANDIDATE CONTEXT:
- Readiness Score: {int(readiness * 100)}%
- Role Family: {role_type}
- Selected Interview Type: {interview_type}
- Interviewer Persona: {persona_profile["label"]}
- Skill Gaps: {skill_focus}{jd_context}

TASK: Generate exactly {total_questions} interview questions for realistic interview practice.

PEDAGOGY REQUIREMENTS:
- Difficulty mix: {difficulty_mix}
- Category mix target: {effective_role_mix}
- Track-specific requirements:
{type_requirements}
- Focus at least half of questions on weak areas: {weak_area_focus}
- Persona tone: {persona_profile["tone"]}
- Persona rules:
{chr(10).join([f"- {rule}" for rule in persona_profile["rules"]])}
{cold_start_block}
CRITICAL RULES:
- Questions must be answerable by SPEAKING (not writing code)
- NO coding questions, NO "write a function", NO algorithm implementation
- Technical questions should test understanding and reasoning, not syntax
- Questions should relate to the candidate's skill gaps and the target role
- Include 3-5 expected talking points for evaluation
- Keep each question to one prompt (no multi-part nested prompts)
- Output ONLY valid JSON (no markdown, no prose)

OUTPUT FORMAT (JSON only, no markdown):
{{
  "questions": [
    {{
      "text": "Clear, specific question",
      "category": "Behavioral",
      "skill_tested": "specific skill",
      "difficulty": "medium",
      "expected_points": ["point 1", "point 2", "point 3"],
      "time_estimate_minutes": 3
    }},
    {{
      "text": "Clear, specific question",
      "category": "Technical",
      "skill_tested": "specific skill",
      "difficulty": "medium",
      "expected_points": ["point 1", "point 2", "point 3"],
      "time_estimate_minutes": 3
    }}
  ]
}}

"""

    user_msg = (
        f"Generate {total_questions} speech-based interview questions for {job_title}. "
        f"Interview type={interview_type}. "
        f"Interviewer persona={interviewer_persona}. "
        f"Readiness={int(readiness * 100)}%. "
        f"Prioritize these gaps: {', '.join(skill_gap_names[:5]) if skill_gap_names else 'competencies from the job description'}."
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg)
    ]

    try:
        structured_payload = await _invoke_structured_output(messages, GeneratedQuestionsSchema)
        if structured_payload and "questions" in structured_payload:
            questions = _sanitize_questions(
                raw_questions=structured_payload.get("questions", []),
                total_questions=total_questions,
                job_title=job_title,
                skill_gap_names=skill_gap_names
            )
            if questions:
                await emit(f"✅ Generated {len(questions)} questions (structured)")
                return {
                    **state,
                    "questions": questions,
                    "current_question_index": 0
                }

        chat_model = get_chat_model()
        
        print("\n🤖 Generating interview questions...")
        print("-" * 40)
        
        raw_content = ""
        async for chunk in chat_model.astream(messages):
            if chunk.content:
                print(chunk.content, end="", flush=True)
                raw_content += chunk.content
        
        print("\n" + "-" * 40)
        
        # Parse JSON
        questions_data = parse_json_safely(raw_content)
        
        if not questions_data or "questions" not in questions_data:
            raise ValueError("Failed to parse questions")

        questions = _sanitize_questions(
            raw_questions=questions_data.get("questions", []),
            total_questions=total_questions,
            job_title=job_title,
            skill_gap_names=skill_gap_names
        )

        await emit(f"✅ Generated {len(questions)} questions")
        
        return {
            **state,
            "questions": questions,
            "current_question_index": 0
        }
        
    except Exception as e:
        print(f"❌ Question generation error: {e}")
        
        fallback_questions = _sanitize_questions(
            raw_questions=[],
            total_questions=total_questions,
            job_title=job_title,
            skill_gap_names=skill_gap_names
        )
        
        return {
            **state,
            "questions": fallback_questions,
            "current_question_index": 0
        }


# ============== Struggle Detector ==============

async def detect_struggle_and_coach(
    transcript: str,
    silence_duration_seconds: float,
    question_context: dict
) -> Optional[dict]:
    """
    Detect if candidate is struggling and provide a hint.
    
    Struggle indicators:
    - Silence > configured silence threshold
    - Many filler words > configured filler limit
    - Very short answer after configured silence window
    
    Returns hint if struggling, None otherwise.
    """
    if not transcript:
        transcript = ""
    
    # Count filler words
    filler_words = ["um", "uh", "like", "you know", "basically", "I mean"]
    filler_count = sum(transcript.lower().count(word) for word in filler_words)
    word_count = len(transcript.split())
    
    # Determine if struggling
    is_struggling = (
        silence_duration_seconds > settings.COACH_SILENCE_SECONDS or
        filler_count > settings.COACH_FILLER_LIMIT or
        (word_count < settings.COACH_SHORT_ANSWER_WORDS and silence_duration_seconds > settings.COACH_SHORT_ANSWER_SILENCE_SECONDS)
    )
    
    if not is_struggling:
        return None
    
    # Determine trigger type
    if silence_duration_seconds > settings.COACH_SILENCE_SECONDS:
        trigger = "silence"
    elif filler_count > settings.COACH_FILLER_LIMIT:
        trigger = "filler_words"
    else:
        trigger = "short_answer"
    
    # Generate helpful hint
    system_prompt = """You are an interview coach watching a candidate struggle.

Give them a GENTLE HINT to get unstuck, but:
- Don't give away the answer
- Suggest a direction or framework to think about
- Be encouraging
- Keep it 1-2 sentences max

Example hints:
- "Think about breaking this into steps - what happens first?"
- "Consider the trade-offs between the different approaches"
- "What would be the impact on performance?"
"""

    user_msg = f"""QUESTION: {question_context.get('text', 'Unknown question')}

CANDIDATE SO FAR: "{transcript[:500]}"

They seem stuck ({trigger}). Give a helpful hint (not the answer)."""

    try:
        chat_model = get_chat_model()
        response = await chat_model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg)
        ])
        
        return {
            "type": "struggle_hint",
            "message": response.content.strip(),
            "icon": "💡",
            "trigger": trigger
        }
        
    except Exception as e:
        print(f"⚠️ Hint generation error: {e}")
        
        # Fallback hints based on trigger
        fallback_hints = {
            "silence": "Take your time - try breaking the problem into smaller parts.",
            "filler_words": "It's okay to pause and collect your thoughts before continuing.",
            "short_answer": "Can you elaborate on any specific examples from your experience?"
        }
        
        return {
            "type": "struggle_hint",
            "message": fallback_hints.get(trigger, "Take a deep breath and think about the key concepts."),
            "icon": "💡",
            "trigger": trigger
        }


# ============== Interview Summary Generator ==============

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "i", "if",
    "in", "is", "it", "of", "on", "or", "our", "that", "the", "their", "there", "they",
    "this", "to", "was", "we", "were", "what", "when", "where", "which", "who", "why",
    "with", "you", "your", "about", "into", "through", "while", "during", "did", "do",
}

STRUCTURE_MARKERS = {
    "first", "second", "third", "finally", "because", "therefore", "however", "then",
    "result", "outcome", "impact", "situation", "task", "action", "lesson", "tradeoff",
}

TECH_TOKEN_MAP = {
    "c++": "cpp",
    "cplusplus": "cpp",
    "c#": "csharp",
    "f#": "fsharp",
    ".net": "dotnet",
    "asp.net": "aspdotnet",
    "node.js": "nodejs",
    "next.js": "nextjs",
    "nuxt.js": "nuxtjs",
    "vue.js": "vuejs",
    "react.js": "reactjs",
    "ci/cd": "cicd",
}


def resolve_feedback_thresholds(overrides: Optional[dict] = None) -> dict:
    """Resolve strictness thresholds from settings with optional per-user overrides."""
    def _cfg(name: str, default: Any) -> Any:
        return getattr(settings, name, default)

    base = {
        "short_answer_words": int(_cfg("EVAL_SHORT_ANSWER_WORDS", 10)),
        "transcript_low_words": int(_cfg("EVAL_TRANSCRIPT_LOW_WORDS", 8)),
        "repetition_ratio_cap": float(_cfg("EVAL_REPETITION_RATIO_CAP", 0.42)),
        "quality_repetition_ratio_flag": float(_cfg("EVAL_QUALITY_REPETITION_RATIO_FLAG", 0.45)),
        "unique_word_ratio_min": float(_cfg("EVAL_UNIQUE_WORD_RATIO_MIN", 0.40)),
        "quality_unique_word_ratio_flag": float(_cfg("EVAL_QUALITY_UNIQUE_WORD_RATIO_FLAG", 0.35)),
        "gibberish_ratio_threshold": float(_cfg("EVAL_GIBBERISH_RATIO_THRESHOLD", 0.28)),
        "structure_markers_min": int(_cfg("EVAL_STRUCTURE_MARKERS_MIN", 2)),
        "structure_sentence_cap": int(_cfg("EVAL_STRUCTURE_SENTENCE_CAP", 2)),
        "low_relevance_threshold": float(_cfg("EVAL_LOW_RELEVANCE_THRESHOLD", 0.12)),
        "coverage_min": float(_cfg("EVAL_COVERAGE_MIN", 0.40)),
        "low_transcript_penalty": float(_cfg("EVAL_LOW_TRANSCRIPT_PENALTY", 1.0)),
        "low_transcript_confidence_cap": float(_cfg("EVAL_LOW_TRANSCRIPT_CONFIDENCE_CAP", 0.45)),
        "accuracy_cap_low_relevance": float(_cfg("EVAL_ACCURACY_CAP_LOW_RELEVANCE", 3.0)),
        "clarity_cap_repetition": float(_cfg("EVAL_CLARITY_CAP_REPETITION", 3.0)),
        "completeness_cap_low_coverage": float(_cfg("EVAL_COMPLETENESS_CAP_LOW_COVERAGE", 4.0)),
        "structure_cap_weak": float(_cfg("EVAL_STRUCTURE_CAP_WEAK", 4.0)),
        "expected_overlap_min": 0.35,
        "high_repetition_ngram_len": 3,
    }
    if not isinstance(overrides, dict):
        return base

    merged = dict(base)
    for key, default_value in base.items():
        if key not in overrides:
            continue
        try:
            if isinstance(default_value, int):
                merged[key] = int(overrides[key])
            elif isinstance(default_value, float):
                merged[key] = float(overrides[key])
        except Exception:
            continue

    # Boundaries
    merged["short_answer_words"] = max(1, min(50, merged["short_answer_words"]))
    merged["transcript_low_words"] = max(1, min(50, merged["transcript_low_words"]))
    merged["repetition_ratio_cap"] = max(0.1, min(0.95, merged["repetition_ratio_cap"]))
    merged["quality_repetition_ratio_flag"] = max(0.1, min(0.99, merged["quality_repetition_ratio_flag"]))
    merged["unique_word_ratio_min"] = max(0.1, min(0.95, merged["unique_word_ratio_min"]))
    merged["quality_unique_word_ratio_flag"] = max(0.1, min(0.95, merged["quality_unique_word_ratio_flag"]))
    merged["gibberish_ratio_threshold"] = max(0.05, min(0.95, merged["gibberish_ratio_threshold"]))
    merged["structure_markers_min"] = max(0, min(8, merged["structure_markers_min"]))
    merged["structure_sentence_cap"] = max(1, min(8, merged["structure_sentence_cap"]))
    merged["low_relevance_threshold"] = max(0.01, min(0.9, merged["low_relevance_threshold"]))
    merged["coverage_min"] = max(0.05, min(0.95, merged["coverage_min"]))
    merged["low_transcript_penalty"] = max(0.0, min(4.0, merged["low_transcript_penalty"]))
    merged["low_transcript_confidence_cap"] = max(0.1, min(0.95, merged["low_transcript_confidence_cap"]))
    merged["accuracy_cap_low_relevance"] = max(0.0, min(10.0, merged["accuracy_cap_low_relevance"]))
    merged["clarity_cap_repetition"] = max(0.0, min(10.0, merged["clarity_cap_repetition"]))
    merged["completeness_cap_low_coverage"] = max(0.0, min(10.0, merged["completeness_cap_low_coverage"]))
    merged["structure_cap_weak"] = max(0.0, min(10.0, merged["structure_cap_weak"]))
    merged["expected_overlap_min"] = max(0.1, min(0.95, merged["expected_overlap_min"]))
    merged["high_repetition_ngram_len"] = max(2, min(6, merged["high_repetition_ngram_len"]))
    return merged


def _tokenize_words(text: str) -> list[str]:
    normalized_text = (text or "").lower()
    # Normalize tech terms before tokenization so punctuation-heavy tokens survive.
    for raw, mapped in sorted(TECH_TOKEN_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        normalized_text = normalized_text.replace(raw, mapped)

    raw_tokens = re.findall(r"[a-z0-9][a-z0-9+#./'-]*", normalized_text)
    normalized_tokens: list[str] = []
    for token in raw_tokens:
        t = token.strip(".'-")
        if not t:
            continue
        t = TECH_TOKEN_MAP.get(t, t)
        t = (
            t.replace("node.js", "nodejs")
             .replace("next.js", "nextjs")
             .replace("react.js", "reactjs")
             .replace(".net", "dotnet")
             .replace("c++", "cpp")
             .replace("c#", "csharp")
        )
        t = t.replace("/", "")
        t = re.sub(r"[^a-z0-9+#']", "", t)
        if t:
            normalized_tokens.append(t)
    return normalized_tokens


def _keywordize(text: str) -> list[str]:
    return [w for w in _tokenize_words(text) if len(w) > 2 and w not in STOPWORDS]


def _estimate_relevance(question_text: str, answer_text: str) -> float:
    q = set(_keywordize(question_text))
    a = set(_keywordize(answer_text))
    if not q:
        return 0.5
    overlap = len(q & a)
    return overlap / len(q)


def _split_answer_chunks(answer_text: str) -> list[str]:
    text = (answer_text or "").strip()
    if not text:
        return []
    chunks = [c.strip() for c in re.split(r"(?<=[.!?])\s+|\n+", text) if c.strip()]
    if chunks:
        return chunks
    words = text.split()
    return [" ".join(words[i:i + 18]) for i in range(0, len(words), 18)]


def _longest_repeated_ngram(tokens: list[str], n: int = 3) -> int:
    if len(tokens) < n:
        return 0
    grams = [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]
    counts = Counter(grams)
    repeated = [len(g.split()) for g, c in counts.items() if c > 1]
    return max(repeated) if repeated else 0


def _estimate_gibberish_ratio(tokens: list[str]) -> float:
    if not tokens:
        return 1.0
    weird = 0
    for token in tokens:
        has_vowel = bool(re.search(r"[aeiou]", token))
        repeats = bool(re.search(r"(.)\1\1\1", token))
        if (not has_vowel and len(token) > 3) or repeats:
            weird += 1
    return weird / max(len(tokens), 1)


def compute_quality_signals(answer: str, thresholds: Optional[dict] = None) -> dict:
    t = resolve_feedback_thresholds(thresholds)
    words = _tokenize_words(answer)
    unique_ratio = len(set(words)) / max(len(words), 1)
    sentence_count = len(_split_answer_chunks(answer))
    repetition_ratio = 1.0 - unique_ratio if words else 1.0
    repeated_ngram = _longest_repeated_ngram(words, n=t["high_repetition_ngram_len"])
    gibberish_ratio = _estimate_gibberish_ratio(words)
    markers_hit = len({w for w in words if w in STRUCTURE_MARKERS})

    flags: list[str] = []
    if len(words) < t["short_answer_words"]:
        flags.append("short_answer")
    if repetition_ratio > t["quality_repetition_ratio_flag"] or repeated_ngram >= t["high_repetition_ngram_len"]:
        flags.append("high_repetition")
    if unique_ratio < t["quality_unique_word_ratio_flag"]:
        flags.append("low_lexical_diversity")
    if markers_hit < t["structure_markers_min"] and sentence_count <= t["structure_sentence_cap"]:
        flags.append("weak_structure")
    if gibberish_ratio > t["gibberish_ratio_threshold"]:
        flags.append("possible_gibberish")
    if (
        len(words) < t["transcript_low_words"]
        or gibberish_ratio > t["gibberish_ratio_threshold"]
        or (unique_ratio < t["quality_unique_word_ratio_flag"] and repetition_ratio > t["quality_repetition_ratio_flag"])
    ):
        flags.append("low_transcript_quality")

    confidence = 0.9
    if "low_transcript_quality" in flags:
        confidence = 0.35
    elif "high_repetition" in flags:
        confidence = 0.55
    elif "weak_structure" in flags:
        confidence = 0.65

    return {
        "word_count": len(words),
        "unique_word_ratio": round(unique_ratio, 3),
        "repetition_ratio": round(repetition_ratio, 3),
        "sentence_count": sentence_count,
        "longest_repeated_ngram": repeated_ngram,
        "gibberish_ratio": round(gibberish_ratio, 3),
        "structure_markers_hit": markers_hit,
        "quality_flags": flags,
        "confidence": round(max(0.1, min(0.95, confidence)), 2),
    }


def _evaluate_expected_point_coverage(
    answer: str,
    expected_points: list[str],
    thresholds: Optional[dict] = None
) -> tuple[list[str], list[str], float]:
    if not expected_points:
        return [], [], 0.5
    t = resolve_feedback_thresholds(thresholds)

    answer_keywords = set(_keywordize(answer))
    hits: list[str] = []
    misses: list[str] = []
    for point in expected_points:
        point_text = str(point).strip()
        point_keywords = set(_keywordize(point_text))
        if not point_keywords:
            misses.append(point_text)
            continue
        overlap_ratio = len(answer_keywords & point_keywords) / len(point_keywords)
        if overlap_ratio >= t["expected_overlap_min"]:
            hits.append(point_text)
        else:
            misses.append(point_text)

    coverage = len(hits) / max(len(expected_points), 1)
    return hits, misses, round(coverage, 3)


def _extract_evidence_quotes(answer: str, expected_points: list[str], max_quotes: int = 2) -> list[str]:
    chunks = _split_answer_chunks(answer)
    if not chunks:
        return []

    keywords = set()
    for point in expected_points[:6]:
        keywords.update(_keywordize(point))

    ranked: list[tuple[int, str]] = []
    for chunk in chunks:
        chunk_tokens = set(_keywordize(chunk))
        hit_count = len(chunk_tokens & keywords)
        ranked.append((hit_count, chunk))

    ranked.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    selected = []
    for _, chunk in ranked:
        quote = chunk.strip()
        if len(quote) > 180:
            quote = f"{quote[:177]}..."
        if quote and quote not in selected:
            selected.append(quote)
        if len(selected) >= max_quotes:
            break

    return selected


def _build_improvement_plan(rubric_misses: list[str], expected_points: list[str], question_text: str) -> dict:
    misses = [m for m in rubric_misses if m][:3]
    if not misses:
        misses = [str(p).strip() for p in expected_points[:2] if str(p).strip()]

    focus = misses[0] if misses else "structured, evidence-based response"
    steps = [
        f"Lead with a direct answer to the question about {focus}.",
        "Add one concrete example from your experience with context and constraints.",
        "Close with measurable impact and one trade-off you considered.",
    ]
    success_criteria = [
        "Mentions at least 2 expected points explicitly.",
        "Includes one concrete metric, result, or business impact.",
        "Follows clear structure: context -> action -> outcome.",
    ]
    drill_prompt = (
        f"Retry this question in 90 seconds: {question_text}. "
        f"Prioritize: {', '.join(misses[:3])}."
    ).strip()

    return {
        "focus": focus,
        "steps": steps,
        "success_criteria": success_criteria,
        "retry_drill": {
            "prompt": drill_prompt,
            "target_points": misses[:3] if misses else expected_points[:3],
        },
    }


def analyze_transcript(transcript: str, duration_seconds: float) -> dict:
    """
    Analyze a transcript for speech patterns: filler words and confidence.
    Works on the raw transcription text.
    """
    if not transcript or not transcript.strip():
        return {
            "filler_word_count": 0,
            "filler_words_detail": {},
            "word_count": 0,
            "confidence_level": "N/A",
            "avg_sentence_length": 0,
        }

    words = transcript.split()
    word_count = len(words)

    # Filler word detection
    filler_patterns = {
        "um": r'\bum\b', "uh": r'\buh\b', "like": r'\blike\b',
        "you know": r'\byou know\b', "basically": r'\bbasically\b',
        "I mean": r'\bi mean\b', "sort of": r'\bsort of\b',
        "kind of": r'\bkind of\b', "right": r'\bright\b',
        "actually": r'\bactually\b',
    }
    filler_detail = {}
    total_fillers = 0
    lower_text = transcript.lower()
    for word, pattern in filler_patterns.items():
        count = len(re.findall(pattern, lower_text))
        if count > 0:
            filler_detail[word] = count
            total_fillers += count

    # Sentence analysis
    sentences = re.split(r'[.!?]+', transcript)
    sentences = [s.strip() for s in sentences if s.strip()]
    avg_sentence_len = round(sum(len(s.split()) for s in sentences) / max(len(sentences), 1), 1)

    # Confidence heuristic based on fillers-per-100-words and sentence structure
    filler_rate = (total_fillers / max(word_count, 1)) * 100
    if filler_rate < 2 and avg_sentence_len >= 8:
        confidence = "High"
    elif filler_rate < 5:
        confidence = "Steady"
    elif filler_rate < 10:
        confidence = "Moderate"
    else:
        confidence = "Low"

    return {
        "filler_word_count": total_fillers,
        "filler_words_detail": filler_detail,
        "word_count": word_count,
        "confidence_level": confidence,
        "avg_sentence_length": avg_sentence_len,
    }


def _detect_star_components(answer: str) -> dict:
    """Detect STAR (Situation, Task, Action, Result) framework components in answer."""
    lower = answer.lower()
    components = {
        "situation": bool(re.search(r'\b(situation|context|background|when i was|at my|in my role|we had|there was|the team|the project)\b', lower)),
        "task": bool(re.search(r'\b(task|responsible for|needed to|goal was|challenge was|objective|asked to|had to|my role was)\b', lower)),
        "action": bool(re.search(r'\b(i (did|built|created|designed|implemented|led|wrote|developed|fixed|improved|optimized|migrated|deployed|configured|set up)|my approach|i decided|steps i took)\b', lower)),
        "result": bool(re.search(r'\b(result|outcome|impact|led to|reduced|increased|improved|saved|achieved|delivered|success|growth|performance)\b', lower)),
    }
    components["score"] = sum(components.values())
    components["complete"] = components["score"] >= 3
    return components


def _detect_hedge_words(answer: str) -> dict:
    """Detect hedge words that weaken answers."""
    lower = answer.lower()
    hedge_patterns = {
        "maybe": r'\bmaybe\b', "probably": r'\bprobably\b',
        "I think": r'\bi think\b', "I guess": r'\bi guess\b',
        "sort of": r'\bsort of\b', "kind of": r'\bkind of\b',
        "not sure": r'\bnot sure\b', "I believe": r'\bi believe\b',
    }
    detail = {}
    total = 0
    for word, pattern in hedge_patterns.items():
        count = len(re.findall(pattern, lower))
        if count > 0:
            detail[word] = count
            total += count
    return {"count": total, "detail": detail}


async def generate_interview_summary(evaluations: list[dict]) -> dict:
    """Generate an LLM-powered overall summary of the interview performance."""
    empty_breakdown = {dim: 0.0 for dim in EVAL_DIMENSIONS}
    if not evaluations:
        return {
            "total_questions": 0,
            "answered_questions": 0,
            "skipped_questions": 0,
            "average_score": 0,
            "overall_breakdown": empty_breakdown,
            "score_breakdown": empty_breakdown,
            "top_strengths": [],
            "strengths": [],
            "areas_to_improve": [],
            "action_items": [],
            "communication_feedback": "",
            "overall_feedback": "No questions were answered.",
            "priority_focus": "Provide structured answers with concrete evidence",
            "quality_risks": [],
            "performance_breakdown": {"excellent": 0, "good": 0, "needs_work": 0},
            "evaluation_status": "no_data",
            "telemetry": {
                "fillerWords": 0, "fillersPerMinute": 0,
                "confidence": "N/A", "word_count": 0, "filler_detail": {},
                "avg_sentence_length": 0, "hedge_words": 0, "hedge_detail": {},
                "star_analysis": {"score": 0, "complete": False},
            },
        }

    def _is_skipped(entry: dict) -> bool:
        if bool(entry.get("skipped")):
            return True
        answer = str(entry.get("answer", "")).strip().lower()
        if answer in {"(skipped)", "skipped"}:
            return True
        eval_data = entry.get("evaluation", {}) or {}
        quality_flags = eval_data.get("quality_flags", []) or []
        return any(str(flag).strip().lower() == "skipped" for flag in quality_flags)

    total_questions = len(evaluations)
    skipped_evaluations = [e for e in evaluations if _is_skipped(e)]
    answered_evaluations = [e for e in evaluations if not _is_skipped(e)]
    answered_count = len(answered_evaluations)
    skipped_count = len(skipped_evaluations)

    if answered_count == 0:
        return {
            "total_questions": total_questions,
            "answered_questions": 0,
            "skipped_questions": skipped_count,
            "average_score": 0.0,
            "overall_breakdown": empty_breakdown,
            "score_breakdown": empty_breakdown,
            "top_strengths": [],
            "strengths": [],
            "areas_to_improve": ["Provide answers for the interview questions"],
            "action_items": [
                "Answer each prompt with at least a short, direct response.",
                "Use a simple structure: context -> action -> outcome.",
                "Practice one timed mock round without skipping questions.",
            ],
            "communication_feedback": "",
            "overall_feedback": "No scorable answers were submitted in this session, so a technical performance score could not be computed.",
            "performance_breakdown": {"excellent": 0, "good": 0, "needs_work": 0},
            "priority_focus": "Provide answers for the interview questions",
            "quality_risks": ["insufficient_answer_data"],
            "evaluation_status": "insufficient_data",
            "telemetry": {
                "fillerWords": 0,
                "fillersPerMinute": 0.0,
                "confidence": "N/A",
                "word_count": 0,
                "filler_detail": {},
                "avg_sentence_length": 0.0,
                "hedge_words": 0,
                "hedge_detail": {},
                "star_analysis": {
                    "situation": False,
                    "task": False,
                    "action": False,
                    "result": False,
                    "score": 0,
                    "complete": False,
                },
            },
        }

    # ---------- basic stats ----------
    scores = [e.get("evaluation", {}).get("score", 0) for e in answered_evaluations]
    avg_score = sum(scores) / len(scores) if scores else 0
    overall_breakdown = _compute_overall_breakdown(answered_evaluations)

    all_strengths = []
    all_gaps = []
    all_quality_flags = []
    for e in answered_evaluations:
        eval_data = e.get("evaluation", {})
        all_strengths.extend(eval_data.get("strengths", []))
        all_gaps.extend(eval_data.get("gaps", []) or eval_data.get("rubric_misses", []) or eval_data.get("missing_concepts", []))
        all_quality_flags.extend(eval_data.get("quality_flags", []))
    if skipped_count > 0:
        all_gaps.append("Provide answers for skipped questions")

    top_strengths = [item for item, _ in Counter(all_strengths).most_common(5)]
    areas_to_improve = [item for item, _ in Counter(all_gaps).most_common(5)]
    top_quality_risks = [item for item, _ in Counter(all_quality_flags).most_common(3)]
    if skipped_count > 0 and "skipped_questions" not in top_quality_risks:
        top_quality_risks = (top_quality_risks + ["skipped_questions"])[:3]

    # ---------- transcript analytics ----------
    combined_transcript = " ".join(e.get("answer", "") for e in answered_evaluations)
    total_duration = sum(e.get("duration", 0) for e in answered_evaluations)
    telemetry = analyze_transcript(combined_transcript, max(total_duration, 1))
    star_analysis = _detect_star_components(combined_transcript)
    hedge_analysis = _detect_hedge_words(combined_transcript)
    duration_min = max(total_duration / 60.0, 0.1)
    fillers_per_min = round(telemetry["filler_word_count"] / duration_min, 1)

    # ---------- LLM-powered summary ----------
    qa_digest = []
    for i, e in enumerate(answered_evaluations, 1):
        q_text = e.get("question", {}).get("text", "?")
        score = e.get("evaluation", {}).get("score", 0)
        answer_snippet = (e.get("answer", "") or "")[:300]
        strengths = e.get("evaluation", {}).get("strengths", [])
        gaps = e.get("evaluation", {}).get("gaps", []) or e.get("evaluation", {}).get("rubric_misses", [])
        qa_digest.append(
            f"Q{i}: {q_text}\n"
            f"  Score: {score}/10 | Strengths: {', '.join(strengths[:3])} | Gaps: {', '.join(gaps[:3])}\n"
            f"  Answer excerpt: \"{answer_snippet}\""
        )

    system_prompt = """You are a senior interview coach writing a performance debrief.
Given the candidate's question-by-question results and speech analytics, produce a JSON summary.

IMPORTANT: Output ONLY valid JSON, no markdown code blocks, no extra text.
Lead with strengths before addressing gaps (strengths-first framing).

JSON Schema (follow exactly):
{
  "overall_feedback": "<3-5 sentence holistic performance summary, start with what went well>",
  "top_strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "areas_to_improve": ["<area 1>", "<area 2>", "<area 3>"],
  "action_items": ["<specific actionable recommendation 1>", "<rec 2>", "<rec 3>"],
  "communication_feedback": "<1-2 sentences on speaking style based on fillers/confidence>"
}"""

    user_prompt = f"""INTERVIEW RESULTS (avg score: {avg_score:.1f}/10):
{chr(10).join(qa_digest)}
Answered questions: {answered_count}
Skipped questions: {skipped_count}

SPEECH ANALYTICS:
- Filler words per minute: {fillers_per_min}
- Hedge words: {hedge_analysis['count']} ({hedge_analysis['detail']})
- STAR framework usage: {star_analysis['score']}/4 components detected
- Confidence level: {telemetry['confidence_level']}

Provide a holistic, constructive summary. Start with strengths. Output valid JSON only:"""

    llm_summary = None
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    try:
        llm_summary = await _invoke_structured_output(messages, SummaryResponseSchema)
    except Exception:
        llm_summary = None

    if llm_summary is None:
        try:
            chat_model = get_chat_model()
            raw = ""
            async for chunk in chat_model.astream(messages):
                if chunk.content:
                    raw += chunk.content
            clean = raw.strip()
            clean = re.sub(r'<think>[\s\S]*?</think>', '', clean).strip()
            if "```" in clean:
                match = re.search(r'```(?:json)?\s*([\s\S]*?)```', clean)
                if match:
                    clean = match.group(1).strip()
            try:
                llm_summary = json.loads(clean)
            except json.JSONDecodeError:
                try:
                    from json_repair import repair_json
                    llm_summary = json.loads(repair_json(clean))
                except Exception:
                    llm_summary = None
        except Exception as e:
            print(f"LLM summary generation failed, using stats-only: {e}")

    if llm_summary:
        overall_feedback = llm_summary.get("overall_feedback", "")
        top_strengths = llm_summary.get("top_strengths", top_strengths[:3])
        areas_to_improve = llm_summary.get("areas_to_improve", areas_to_improve[:3])
        action_items = llm_summary.get("action_items", [])
        communication_feedback = llm_summary.get("communication_feedback", "")
    else:
        if avg_score >= 8:
            overall_feedback = "Strong performance across the board. Your answers showed depth and real-world experience."
        elif avg_score >= 6:
            overall_feedback = "Solid foundation demonstrated. Adding more specific examples and structured responses will elevate your answers."
        else:
            overall_feedback = "Good effort getting started. Focus on the STAR framework (Situation, Task, Action, Result) to structure your answers with concrete examples."
        action_items = []
        communication_feedback = ""

    return {
        "total_questions": total_questions,
        "answered_questions": answered_count,
        "skipped_questions": skipped_count,
        "average_score": round(avg_score, 1),
        "overall_breakdown": overall_breakdown,
        "score_breakdown": overall_breakdown,
        "top_strengths": top_strengths[:3],
        "strengths": top_strengths[:3],
        "areas_to_improve": areas_to_improve[:3],
        "overall_feedback": overall_feedback,
        "action_items": action_items,
        "communication_feedback": communication_feedback,
        "performance_breakdown": {
            "excellent": sum(1 for s in scores if s >= 8),
            "good": sum(1 for s in scores if 6 <= s < 8),
            "needs_work": sum(1 for s in scores if s < 6),
        },
        "priority_focus": (areas_to_improve[0] if areas_to_improve else "Provide clearer structure and evidence"),
        "quality_risks": top_quality_risks,
        "evaluation_status": ("partial" if skipped_count > 0 else "complete"),
        "telemetry": {
            "fillerWords": telemetry["filler_word_count"],
            "fillersPerMinute": fillers_per_min,
            "confidence": telemetry["confidence_level"],
            "word_count": telemetry["word_count"],
            "filler_detail": telemetry["filler_words_detail"],
            "avg_sentence_length": telemetry["avg_sentence_length"],
            "hedge_words": hedge_analysis["count"],
            "hedge_detail": hedge_analysis["detail"],
            "star_analysis": {
                "situation": star_analysis["situation"],
                "task": star_analysis["task"],
                "action": star_analysis["action"],
                "result": star_analysis["result"],
                "score": star_analysis["score"],
                "complete": star_analysis["complete"],
            },
        },
    }

def _clamp_score(value: Any, default: float = 5.0) -> float:
    try:
        score = float(value)
    except Exception:
        score = float(default)
    return max(0.0, min(10.0, score))


def _normalize_evaluation_payload(
    evaluation: dict,
    expected_points: list[str],
    question_text: str,
    answer_text: str,
    thresholds: Optional[dict] = None
) -> dict:
    """Normalize LLM evaluation into stable shape with deterministic guardrails."""
    t = resolve_feedback_thresholds(thresholds)
    breakdown = evaluation.get("score_breakdown") or {}
    fallback_score = evaluation.get("score", 5)

    # Extract 5-dimension scores (with backward compat for old 4-dim evals)
    relevance = _clamp_score(breakdown.get("relevance", breakdown.get("accuracy", fallback_score)), fallback_score)
    depth = _clamp_score(breakdown.get("depth", breakdown.get("completeness", fallback_score)), fallback_score)
    structure = _clamp_score(breakdown.get("structure", fallback_score), fallback_score)
    specificity = _clamp_score(breakdown.get("specificity", breakdown.get("clarity", fallback_score)), fallback_score)
    communication = _clamp_score(breakdown.get("communication", fallback_score), fallback_score)

    # Extract strengths/gaps from LLM
    strengths = evaluation.get("strengths") or []
    if not isinstance(strengths, list):
        strengths = [str(strengths)]
    strengths = list(dict.fromkeys([str(x).strip() for x in strengths if str(x).strip()]))[:6]

    gaps = evaluation.get("gaps") or evaluation.get("rubric_misses") or evaluation.get("missing_concepts") or []
    if not isinstance(gaps, list):
        gaps = [str(gaps)]
    gaps = list(dict.fromkeys([str(x).strip() for x in gaps if str(x).strip()]))[:6]

    # Deterministic quality signals
    quality_signals = compute_quality_signals(answer_text, thresholds=t)
    keyword_relevance = _estimate_relevance(question_text, answer_text)
    auto_hits, auto_misses, coverage = _evaluate_expected_point_coverage(answer_text, expected_points, thresholds=t)

    # Merge auto-detected gaps
    gaps = list(dict.fromkeys(gaps + auto_misses))[:6]

    quality_flags = list(dict.fromkeys(
        quality_signals.get("quality_flags", []) + [str(x).strip() for x in (evaluation.get("quality_flags") or []) if str(x).strip()]
    ))

    # Deterministic guardrails: cap inflated scores when signals disagree
    if settings.FEEDBACK_LOOP_V2:
        if keyword_relevance < t["low_relevance_threshold"]:
            relevance = min(relevance, t.get("accuracy_cap_low_relevance", 5.0))
            quality_flags.append("low_relevance")
        if quality_signals["repetition_ratio"] > t["repetition_ratio_cap"]:
            communication = min(communication, t.get("clarity_cap_repetition", 6.0))
        if coverage < t["coverage_min"]:
            depth = min(depth, t.get("completeness_cap_low_coverage", 6.0))
        if quality_signals["structure_markers_hit"] < t["structure_markers_min"] and quality_signals["sentence_count"] <= t["structure_sentence_cap"]:
            structure = min(structure, t.get("structure_cap_weak", 5.5))

    # Weighted score
    weighted = round(
        EVAL_WEIGHTS["relevance"] * relevance
        + EVAL_WEIGHTS["depth"] * depth
        + EVAL_WEIGHTS["structure"] * structure
        + EVAL_WEIGHTS["specificity"] * specificity
        + EVAL_WEIGHTS["communication"] * communication,
        1
    )

    if settings.FEEDBACK_LOOP_V2 and "low_transcript_quality" in quality_flags:
        weighted = max(0.0, round(weighted - t["low_transcript_penalty"], 1))

    # Evidence quotes
    evidence_quotes = _extract_evidence_quotes(answer_text, expected_points, max_quotes=2)

    # Fallback defaults
    if not strengths:
        strengths = ["Attempted to answer the question"]

    # Build improvement plan
    derived_plan = _build_improvement_plan(gaps, expected_points, question_text)

    # Confidence from quality signals
    confidence = quality_signals.get("confidence", 0.65)
    if settings.FEEDBACK_LOOP_V2 and "low_transcript_quality" in quality_flags:
        confidence = min(confidence, t.get("low_transcript_confidence_cap", 0.4))

    quality_flags = list(dict.fromkeys([f for f in quality_flags if f]))[:6]

    score_breakdown = {
        "relevance": round(relevance, 1),
        "depth": round(depth, 1),
        "structure": round(structure, 1),
        "specificity": round(specificity, 1),
        "communication": round(communication, 1),
        # Backward-compatible aliases for pre-v2 consumers/tests.
        "accuracy": round(relevance, 1),
        "completeness": round(depth, 1),
        "clarity": round(communication, 1),
    }
    rubric_hits = list(
        dict.fromkeys(
            [str(item).strip() for item in (evaluation.get("rubric_hits") or []) if str(item).strip()]
            + auto_hits
        )
    )[:6]
    rubric_misses = list(
        dict.fromkeys(
            [str(item).strip() for item in (evaluation.get("rubric_misses") or []) if str(item).strip()]
            + gaps
        )
    )[:6]
    improvement_plan = {
        "focus": derived_plan["focus"],
        "steps": derived_plan["steps"],
        "success_criteria": derived_plan["success_criteria"],
    }
    coaching_tip = str(
        evaluation.get("coaching_tip")
        or "Structure your answer: context, action, result. Add specific evidence."
    )
    model_answer = str(
        evaluation.get("model_answer")
        or evaluation.get("optimized_answer")
        or "A strong answer defines the concept, explains trade-offs, and anchors with a concrete example."
    )
    evaluation_reasoning = str(
        evaluation.get("evaluation_reasoning") or evaluation.get("feedback") or ""
    )

    return {
        "evaluation_version": "v2",
        "score": weighted,
        "score_breakdown": score_breakdown,
        "strengths": strengths[:6],
        "gaps": gaps[:6],
        "missing_concepts": gaps[:6],
        "quality_flags": quality_flags,
        "confidence": round(confidence, 2),
        "coverage_ratio": coverage,
        "rubric_hits": rubric_hits,
        "rubric_misses": rubric_misses,
        "evidence_quotes": evidence_quotes,
        "improvement_plan": improvement_plan,
        "retry_drill": derived_plan["retry_drill"],
        "coaching_tip": coaching_tip,
        "model_answer": model_answer,
        "optimized_answer": model_answer,
        "evaluation_reasoning": evaluation_reasoning,
        "feedback": evaluation_reasoning,
    }


async def evaluate_answer_stream(question, answer, callback, thresholds: Optional[dict] = None):
    """
    Evaluate user's answer with streaming feedback and detailed coaching.
    
    Args:
        question: dict with question text and expected concepts
        answer: user's transcribed answer
        callback: async function(msg_type, content) for streaming
        
    Returns:
        dict with score, breakdown, feedback, and coaching tips
    """
    await callback("status", "Analyzing your answer...")
    
    from server.services.llm_factory import get_chat_model
    from langchain_core.messages import SystemMessage, HumanMessage
    
    llm = get_chat_model()
    resolved_thresholds = resolve_feedback_thresholds(thresholds)

    question_text = question.get('text', 'Unknown question')
    expected_points = question.get('expected_points', [])
    category = question.get('category', 'General')
    skill = question.get('skill_tested', 'General knowledge')
    
    system_prompt = """You are an expert interview evaluator using structured rubric-based assessment.
This answer was captured via speech-to-text. IGNORE transcription artifacts (filler words, repeated words, missing punctuation). Evaluate SUBSTANCE only.

## Evaluation Steps (think through each before assigning scores):
1. Read the question and identify what a strong answer would cover
2. Read the candidate's answer and identify what they actually communicated
3. For each dimension below, determine which anchor range the answer falls in
4. Assign scores based on evidence from the answer, not overall impression

## Scoring Dimensions (0-10 each):

RELEVANCE - Does the answer directly address the question?
  9-10: Focused, on-topic, directly answers what was asked
  6-8: Mostly relevant with minor tangents
  3-5: Partially addresses the question, significant off-topic content
  0-2: Does not address the question

DEPTH - How thorough is the analysis?
  9-10: Covers key concepts with nuanced understanding
  6-8: Good coverage of main points, some depth
  3-5: Surface-level, missing important concepts
  0-2: Extremely shallow or empty

STRUCTURE - Is the answer well-organized?
  9-10: Clear flow (context -> action -> result), easy to follow
  6-8: Generally organized with some flow issues
  3-5: Rambling or hard to follow
  0-2: No discernible structure

SPECIFICITY - Does the answer include concrete evidence?
  9-10: Specific examples, numbers, real scenarios
  6-8: Some examples but could be more concrete
  3-5: Mostly generic or abstract statements
  0-2: No examples or evidence

COMMUNICATION - Is the delivery clear and effective?
  9-10: Clear, confident, concise
  6-8: Generally clear with minor issues
  3-5: Unclear in places, verbose or too brief
  0-2: Very unclear or incoherent

## Debiasing Rules:
- Longer answers are NOT automatically better. Concise and focused can score 10/10.
- Do NOT penalize speech-to-text artifacts (um, uh, repeated words).
- Score based on CONTENT quality, not vocabulary sophistication.
- One excellent specific example beats five vague ones.

IMPORTANT: Output ONLY valid JSON, no markdown code blocks, no extra text.

JSON Schema:
{
  "evaluation_reasoning": "<2-3 sentences: what the candidate did well and what they missed>",
  "score_breakdown": {
    "relevance": <0-10>,
    "depth": <0-10>,
    "structure": <0-10>,
    "specificity": <0-10>,
    "communication": <0-10>
  },
  "strengths": ["<specific strength from the answer>", "<another>"],
  "gaps": ["<specific concept or point they missed>", "<another>"],
  "coaching_tip": "<one actionable improvement suggestion>",
  "model_answer": "<2-3 sentence example of what a strong answer would include>"
}"""

    user_prompt = f"""QUESTION: {question_text}
CATEGORY: {category}
SKILL TESTED: {skill}
EXPECTED KEY POINTS: {', '.join(expected_points[:5]) if expected_points else 'Clear explanation with concrete examples'}

CANDIDATE'S SPOKEN ANSWER (transcribed): "{answer}"

Evaluate this answer against the rubric. Output valid JSON only:"""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]

    full_response = ""
    try:
        structured_payload = await _invoke_structured_output(messages, EvaluationResponseSchema)
        if structured_payload:
            evaluation = _normalize_evaluation_payload(
                evaluation=structured_payload,
                expected_points=expected_points,
                question_text=question_text,
                answer_text=answer,
                thresholds=resolved_thresholds,
            )
            print(f"📝 Evaluation: Score {evaluation.get('score', 0)}/10 (structured)")
            print(
                "📈 Eval v2 flags=%s confidence=%.2f"
                % (evaluation.get("quality_flags", []), float(evaluation.get("confidence", 0.0)))
            )
            return evaluation

        # Stream response
        async for chunk in llm.astream(messages):
            content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            await callback("token", content)
            full_response += content
        
        # Parse JSON from response
        import json
        import re
        
        # Clean the response
        clean_response = full_response.strip()

        # Strip <think>...</think> blocks (qwen3 reasoning traces)
        clean_response = re.sub(r'<think>[\s\S]*?</think>', '', clean_response).strip()

        # Remove markdown code blocks if present
        if "```" in clean_response:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)```', clean_response)
            if match:
                clean_response = match.group(1).strip()
        
        # Try to parse
        try:
            evaluation = json.loads(clean_response)
        except json.JSONDecodeError:
            # Try json_repair
            try:
                from json_repair import repair_json
                evaluation = json.loads(repair_json(clean_response))
            except Exception:
                # Manual extraction as last resort — use normalize to compute real scores
                evaluation = {
                    "score": 5,
                    "score_breakdown": {},
                    "strengths": [],
                    "gaps": [],
                    "coaching_tip": "Structure your answer: context, action, result. Add specific evidence.",
                    "model_answer": "",
                    "evaluation_reasoning": clean_response[:200] if clean_response else ""
                }
        
        evaluation = _normalize_evaluation_payload(
            evaluation=evaluation,
            expected_points=expected_points,
            question_text=question_text,
            answer_text=answer,
            thresholds=resolved_thresholds,
        )
        print(f"📝 Evaluation: Score {evaluation.get('score', 0)}/10")
        print(
            "📈 Eval v2 flags=%s confidence=%.2f"
            % (evaluation.get("quality_flags", []), float(evaluation.get("confidence", 0.0)))
        )
        return evaluation
        
    except Exception as e:
        print(f"❌ Error in evaluate_answer_stream: {e}")
        import traceback
        traceback.print_exc()
        # Use empty breakdown so normalize computes scores from deterministic signals
        fallback = {
            "score": 5,
            "score_breakdown": {},
            "strengths": [],
            "gaps": [],
            "coaching_tip": "Structure your answer: context, action, result. Add specific evidence.",
            "model_answer": "",
            "evaluation_reasoning": "Evaluation encountered an error; scores computed from content analysis.",
        }
        return _normalize_evaluation_payload(
            evaluation=fallback,
            expected_points=expected_points,
            question_text=question_text,
            answer_text=answer,
            thresholds=resolved_thresholds,
        )
