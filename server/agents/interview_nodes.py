"""
Interview Practice Agent Nodes.
Handles question generation, answer evaluation, and real-time coaching.
"""

import asyncio
import json
import re
from typing import Any, Callable, Literal, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

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


# ============== Question Generator ==============

async def generate_interview_questions(
    state: InterviewState,
    progress_callback: Optional[Callable] = None
) -> InterviewState:
    """
    Generate 5-10 personalized questions based on skill gaps.
    
    Logic:
    - If readiness < 0.5: Generate fundamental/easy questions
    - If readiness 0.5-0.7: Mix of fundamental + intermediate
    - If readiness > 0.7: Challenging questions
    """
    skill_gaps = state.get("skill_gaps", [])
    job_title = state.get("job_title", "Software Engineer")
    readiness = state.get("readiness_score", 0.5)

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
    
    await emit(f"Generating questions for {job_title}...")
    
    # Determine difficulty distribution (3 questions for testing)
    if readiness < 0.5:
        difficulty_mix = {"easy": 2, "medium": 1, "hard": 0}
        total_questions = 3
    elif readiness < 0.7:
        difficulty_mix = {"easy": 1, "medium": 1, "hard": 1}
        total_questions = 3
    else:
        difficulty_mix = {"easy": 0, "medium": 2, "hard": 1}
        total_questions = 3
    
    system_prompt = f"""You are an expert technical interviewer for {job_title} positions.

CANDIDATE CONTEXT:
- Readiness Score: {int(readiness * 100)}%
- Skill Gaps: {', '.join(skill_gap_names[:8]) if skill_gap_names else 'General skills'}

TASK: Generate {total_questions} interview questions that:
1. Focus on their weak areas ({', '.join(skill_gap_names[:3]) if skill_gap_names else 'core competencies'})
2. Follow this difficulty distribution: {difficulty_mix}
3. Cover different question types (60% technical, 30% system design, 10% behavioral)

OUTPUT FORMAT (JSON only, no markdown):
{{
  "questions": [
    {{
      "text": "Clear, specific question",
      "category": "Core Concepts|System Design|Behavioral|Debugging",
      "skill_tested": "specific skill",
      "difficulty": "easy|medium|hard",
      "expected_points": ["point 1", "point 2", "point 3"],
      "time_estimate_minutes": 3
    }}
  ]
}}

RULES:
- Questions must be specific and testable
- Include 3-5 expected talking points for evaluation
- Easy questions: definition/explanation
- Medium questions: implementation/comparison
- Hard questions: design/optimization/edge cases
- Output ONLY valid JSON, no markdown code blocks"""

    user_msg = f"Generate {total_questions} interview questions for: {job_title}\nFocus on: {', '.join(skill_gap_names[:5]) if skill_gap_names else 'general technical skills'}"

    try:
        chat_model = get_chat_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg)
        ]
        
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
        
        await emit(f"✅ Generated {len(questions_data['questions'])} questions")
        
        return {
            **state,
            "questions": questions_data["questions"],
            "current_question_index": 0
        }
        
    except Exception as e:
        print(f"❌ Question generation error: {e}")
        
        # Fallback questions
        fallback_questions = [
            {
                "text": f"Tell me about your experience with {skill_gap_names[0] if skill_gap_names else 'your main technology stack'}.",
                "category": "Behavioral",
                "skill_tested": skill_gap_names[0] if skill_gap_names else "General",
                "difficulty": "easy",
                "expected_points": ["Background", "Specific projects", "Lessons learned"],
                "time_estimate_minutes": 3
            },
            {
                "text": f"What are the key considerations when designing a scalable system?",
                "category": "System Design",
                "skill_tested": "System Design",
                "difficulty": "medium",
                "expected_points": ["Load balancing", "Caching", "Database sharding", "Horizontal scaling"],
                "time_estimate_minutes": 5
            },
            {
                "text": "Walk me through how you would debug a production issue that only occurs intermittently.",
                "category": "Debugging",
                "skill_tested": "Problem Solving",
                "difficulty": "medium",
                "expected_points": ["Logging", "Monitoring", "Reproduction steps", "Root cause analysis"],
                "time_estimate_minutes": 4
            }
        ]
        
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
    - Silence > 8 seconds
    - Many filler words (um, uh, like > 8 occurrences)
    - Answer length < 20 words after 30 seconds
    
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
        silence_duration_seconds > 8.0 or
        filler_count > 8 or
        (word_count < 15 and silence_duration_seconds > 25)
    )
    
    if not is_struggling:
        return None
    
    # Determine trigger type
    if silence_duration_seconds > 8.0:
        trigger = "silence"
    elif filler_count > 8:
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

def analyze_transcript(transcript: str, duration_seconds: float) -> dict:
    """
    Analyze a transcript for speech patterns: filler words, pace, confidence.
    Works on the raw transcription text.
    """
    if not transcript or not transcript.strip():
        return {
            "filler_word_count": 0,
            "filler_words_detail": {},
            "word_count": 0,
            "words_per_minute": 0,
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

    # Speaking pace (words per minute)
    duration_min = max(duration_seconds / 60.0, 0.1)
    wpm = round(word_count / duration_min)

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
        "words_per_minute": wpm,
        "confidence_level": confidence,
        "avg_sentence_length": avg_sentence_len,
    }


async def generate_interview_summary(evaluations: list[dict]) -> dict:
    """Generate an LLM-powered overall summary of the interview performance."""
    from collections import Counter

    if not evaluations:
        return {
            "total_questions": 0,
            "average_score": 0,
            "top_strengths": [],
            "areas_to_improve": [],
            "overall_feedback": "No questions were answered.",
            "telemetry": {
                "pace": 0, "fillerWords": 0, "confidence": "N/A",
                "word_count": 0, "filler_detail": {},
            },
        }

    # ---------- basic stats ----------
    scores = [e.get("evaluation", {}).get("score", 0) for e in evaluations]
    avg_score = sum(scores) / len(scores) if scores else 0

    all_strengths = []
    all_missing = []
    for e in evaluations:
        eval_data = e.get("evaluation", {})
        all_strengths.extend(eval_data.get("strengths", []))
        all_missing.extend(eval_data.get("missing_concepts", []))

    top_strengths = [item for item, _ in Counter(all_strengths).most_common(5)]
    areas_to_improve = [item for item, _ in Counter(all_missing).most_common(5)]

    # ---------- transcript analytics ----------
    combined_transcript = " ".join(e.get("answer", "") for e in evaluations)
    total_duration = sum(e.get("duration", 0) for e in evaluations)
    telemetry = analyze_transcript(combined_transcript, max(total_duration, 1))

    # ---------- LLM-powered summary ----------
    # Build a compact digest for the LLM
    qa_digest = []
    for i, e in enumerate(evaluations, 1):
        q_text = e.get("question", {}).get("text", "?")
        score = e.get("evaluation", {}).get("score", 0)
        answer_snippet = (e.get("answer", "") or "")[:300]
        strengths = e.get("evaluation", {}).get("strengths", [])
        missing = e.get("evaluation", {}).get("missing_concepts", [])
        qa_digest.append(
            f"Q{i}: {q_text}\n"
            f"  Score: {score}/10 | Strengths: {', '.join(strengths[:3])} | Gaps: {', '.join(missing[:3])}\n"
            f"  Answer excerpt: \"{answer_snippet}\""
        )

    system_prompt = """You are a senior interview coach writing a performance debrief.
Given the candidate's question-by-question results and speech analytics, produce a JSON summary.

IMPORTANT: Output ONLY valid JSON, no markdown code blocks, no extra text.

JSON Schema (follow exactly):
{
  "overall_feedback": "<3-5 sentence holistic performance summary>",
  "top_strengths": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "areas_to_improve": ["<area 1>", "<area 2>", "<area 3>"],
  "action_items": ["<specific study/practice recommendation 1>", "<rec 2>", "<rec 3>"],
  "communication_feedback": "<1-2 sentences on speaking style based on pace/fillers/confidence>"
}"""

    user_prompt = f"""INTERVIEW RESULTS (avg score: {avg_score:.1f}/10):
{chr(10).join(qa_digest)}

SPEECH ANALYTICS:
- Words per minute: {telemetry['words_per_minute']}
- Filler words: {telemetry['filler_word_count']} ({telemetry['filler_words_detail']})
- Confidence level: {telemetry['confidence_level']}
- Avg sentence length: {telemetry['avg_sentence_length']} words

Provide a holistic summary. Output valid JSON only:"""

    llm_summary = None
    try:
        chat_model = get_chat_model()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        raw = ""
        async for chunk in chat_model.astream(messages):
            if chunk.content:
                raw += chunk.content

        # Parse
        clean = raw.strip()
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
        print(f"⚠️ LLM summary generation failed, using stats-only: {e}")

    # Merge LLM insights with computed stats
    if llm_summary:
        overall_feedback = llm_summary.get("overall_feedback", "")
        top_strengths = llm_summary.get("top_strengths", top_strengths[:3])
        areas_to_improve = llm_summary.get("areas_to_improve", areas_to_improve[:3])
        action_items = llm_summary.get("action_items", [])
        communication_feedback = llm_summary.get("communication_feedback", "")
    else:
        # Fallback to rule-based
        if avg_score >= 8:
            overall_feedback = "Excellent performance! You demonstrated strong technical knowledge."
        elif avg_score >= 6:
            overall_feedback = "Good effort! Focus on the areas marked for improvement to reach the next level."
        else:
            overall_feedback = "Keep practicing! Review the optimized answers and work on the missing concepts."
        action_items = []
        communication_feedback = ""

    return {
        "total_questions": len(evaluations),
        "average_score": round(avg_score, 1),
        "top_strengths": top_strengths[:3],
        "areas_to_improve": areas_to_improve[:3],
        "overall_feedback": overall_feedback,
        "action_items": action_items,
        "communication_feedback": communication_feedback,
        "performance_breakdown": {
            "excellent": sum(1 for s in scores if s >= 8),
            "good": sum(1 for s in scores if 6 <= s < 8),
            "needs_work": sum(1 for s in scores if s < 6),
        },
        "telemetry": {
            "pace": telemetry["words_per_minute"],
            "fillerWords": telemetry["filler_word_count"],
            "confidence": telemetry["confidence_level"],
            "word_count": telemetry["word_count"],
            "filler_detail": telemetry["filler_words_detail"],
            "avg_sentence_length": telemetry["avg_sentence_length"],
        },
    }

async def evaluate_answer_stream(question, answer, callback):
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
    
    question_text = question.get('text', 'Unknown question')
    expected_points = question.get('expected_points', [])
    category = question.get('category', 'General')
    skill = question.get('skill_tested', 'General knowledge')
    
    system_prompt = """You are an expert interview coach evaluating a candidate's response.
Be constructive but honest. If the answer is weak, explain WHY and HOW to improve.

IMPORTANT: Output ONLY valid JSON, no markdown code blocks, no extra text.

JSON Schema (follow exactly):
{
  "score": <number 0-10>,
  "score_breakdown": {
    "clarity": <number 0-10>,
    "accuracy": <number 0-10>,
    "completeness": <number 0-10>,
    "structure": <number 0-10>
  },
  "strengths": ["<specific strength 1>", "<strength 2>"],
  "missing_concepts": ["<concept they missed>", "<another>"],
  "coaching_tip": "<one specific improvement tip>",
  "optimized_answer": "<2-3 sentence ideal answer summary>",
  "feedback": "<2-3 sentence detailed feedback>"
}"""

    user_prompt = f"""QUESTION: {question_text}
CATEGORY: {category}
SKILL TESTED: {skill}
EXPECTED POINTS: {', '.join(expected_points[:5]) if expected_points else 'Clear explanation with examples'}

CANDIDATE'S ANSWER: "{answer}"

Evaluate this answer. If the answer is weak, rambling, or doesn't address the question:
- Give a low score (0-3)
- Identify what's missing
- Provide a clear coaching tip on how to improve
- Give an optimized answer example

Output valid JSON only:"""

    full_response = ""
    try:
        # Stream response
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        async for chunk in llm.astream(messages):
            content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            await callback("token", content)
            full_response += content
        
        # Parse JSON from response
        import json
        import re
        
        # Clean the response
        clean_response = full_response.strip()
        
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
                # Manual extraction as last resort
                score_match = re.search(r'"score"\s*:\s*(\d+)', clean_response)
                score = int(score_match.group(1)) if score_match else 3
                
                evaluation = {
                    "score": score,
                    "score_breakdown": {"clarity": score, "accuracy": score, "completeness": score, "structure": score},
                    "strengths": ["Attempted to answer the question"],
                    "missing_concepts": ["Many key concepts were not addressed"],
                    "coaching_tip": "Structure your answer around 2-3 key points with specific examples",
                    "optimized_answer": "A strong answer would define the concept, explain its importance, and give a practical example.",
                    "feedback": clean_response[:200] if clean_response else "Unable to parse detailed feedback."
                }
        
        # Ensure all required fields exist
        if "score_breakdown" not in evaluation:
            s = evaluation.get("score", 5)
            evaluation["score_breakdown"] = {"clarity": s, "accuracy": s, "completeness": s, "structure": s}
        
        if "optimized_answer" not in evaluation:
            evaluation["optimized_answer"] = "Focus on the core concept, explain your reasoning, and provide a concrete example."
            
        if "coaching_tip" not in evaluation:
            evaluation["coaching_tip"] = "Try to structure your answer with a clear opening, supporting details, and a conclusion."
            
        if "missing_concepts" not in evaluation:
            evaluation["missing_concepts"] = []
            
        print(f"📝 Evaluation: Score {evaluation.get('score', 0)}/10")
        return evaluation
        
    except Exception as e:
        print(f"❌ Error in evaluate_answer_stream: {e}")
        import traceback
        traceback.print_exc()
        return {
            "score": 2,
            "score_breakdown": {"clarity": 2, "accuracy": 2, "completeness": 2, "structure": 2},
            "feedback": "The answer needs significant improvement. Focus on addressing the specific question with concrete examples.",
            "strengths": ["Showed willingness to attempt the question"],
            "missing_concepts": ["Core concepts not explained", "No examples provided"],
            "coaching_tip": "Start by defining the main concept, then explain how it works with a real example.",
            "optimized_answer": "A strong answer would clearly define the concept, explain the key differences or components, and provide a practical example from your experience.",
            "improvements": ["Address the question directly", "Provide specific examples", "Structure your answer clearly"]
        }
