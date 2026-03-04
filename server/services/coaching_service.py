"""
Coaching Service
Provides realtime hints and guidance during interviews with progressive clarity.
Uses fast lightweight model (gemma3:4b) for quick responses.
"""

import json
import re

from server.services.llm_factory import get_fast_chat_model
from langchain_core.messages import SystemMessage, HumanMessage


async def generate_coaching_hint(
    transcript: str, 
    question: dict, 
    previous_hints: list[str] = None,
    hint_level: int = 1
) -> dict | None:
    """
    Generate a coaching hint with progressive clarity based on hint_level.
    
    hint_level:
        1 = Gentle nudge (subtle)
        2 = Clearer direction (more direct)
        3+ = Very direct guidance (without giving the full answer)
    """
    question_text = question.get("text", "")
    points = question.get("expected_points", [])
    skill = question.get("skill_tested", "")
    category = question.get("category", "General")
    
    # Handle case where user hasn't started speaking
    has_transcript = transcript and len(transcript.split()) >= 3
    
    # Progressive hint prompts based on level
    if hint_level <= 0:
        directiveness = """Give a short "starting tip" before the candidate speaks.
Keep it encouraging and tactical."""
    elif hint_level == 1:
        directiveness = """Candidate needs a gentle but specific nudge.
Suggest the next concept they should mention."""
    elif hint_level == 2:
        directiveness = """Candidate needs clearer direction.
Point to an interview framework and one concrete move."""
    else:  # 3+
        directiveness = f"""This is hint #{hint_level}. Candidate is still struggling.
Be very explicit with a mini-plan, while avoiding giving a full final answer."""
    
    # Context about previous hints
    prev_context = ""
    if previous_hints and len(previous_hints) > 0:
        prev_context = f"\nPrevious hints: {previous_hints[-2:]}\nProvide something NEW and more specific."
    
    # Context about what they've said
    transcript_context = f'What they\'ve said so far: "{transcript[:300]}..."' if has_transcript else "They haven't started answering yet."
    
    system_prompt = """You are an expert Interview Coach helping in real-time.
Return STRICT JSON ONLY with this exact schema:
{
  "message": "single actionable sentence (max 22 words)",
  "next_step": "single concrete action to do now",
  "framework": "short framework name (e.g. STAR, Problem-Approach-Tradeoff-Result)",
  "starter": "first sentence stem candidate can say next",
  "must_mention": ["point 1", "point 2", "point 3"],
  "avoid": "one common mistake to avoid"
}

Rules:
- Do not provide the full answer.
- Keep must_mention to 2-3 short items.
- No markdown, no preface, no extra keys."""

    human_prompt = f"""QUESTION: "{question_text}"
CATEGORY: {category}
SKILL TESTED: {skill or "General"}
KEY POINTS TO COVER: {', '.join(points[:4]) if points else "Clear explanation with examples"}

{transcript_context}
{prev_context}

INSTRUCTION: {directiveness}"""

    chat_model = get_fast_chat_model()
    try:
        response = await chat_model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        content = response.content.strip()

        # Extract JSON block safely, even if model adds wrappers.
        if content.startswith("```"):
            content = re.sub(r"^```[a-zA-Z]*\n?", "", content).strip()
            content = re.sub(r"\n?```$", "", content).strip()
        if not content.startswith("{"):
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                content = match.group(0)

        data = json.loads(content)

        message = str(data.get("message", "")).strip()
        next_step = str(data.get("next_step", "")).strip()
        framework = str(data.get("framework", "")).strip()
        starter = str(data.get("starter", "")).strip()
        avoid = str(data.get("avoid", "")).strip()
        must_mention = data.get("must_mention", [])
        if not isinstance(must_mention, list):
            must_mention = []
        must_mention = [str(x).strip() for x in must_mention if str(x).strip()][:3]

        if not message:
            message = next_step or "Start with the core challenge, then explain your decision and measurable outcome."

        return {
            "message": message,
            "next_step": next_step or message,
            "framework": framework or ("STAR" if category.lower() == "behavioral" else "Problem-Approach-Tradeoff-Result"),
            "starter": starter or "I’d approach this by first clarifying the core problem, then outlining my actions and impact.",
            "must_mention": must_mention,
            "avoid": avoid or "Avoid staying too abstract without a concrete example or result.",
        }
    except Exception as e:
        print(f"❌ Coaching generation failed: {e}")
        fallback_framework = "STAR" if category.lower() == "behavioral" else "Problem-Approach-Tradeoff-Result"
        fallback_points = points[:3] if points else ["Core challenge", "Your specific action", "Measurable result"]
        return {
            "message": "Use a clear structure: challenge, your action, and outcome with a metric.",
            "next_step": "State the situation in one line, then move to what you did.",
            "framework": fallback_framework,
            "starter": "In that scenario, the key challenge was __, so I focused on __.",
            "must_mention": fallback_points,
            "avoid": "Avoid listing tasks without explaining your decisions and impact.",
        }


async def generate_quick_encouragement() -> str:
    """Generate a quick encouraging phrase for moments of silence."""
    encouragements = [
        "Take your time, you're doing great!",
        "Think about the core concept first...",
        "What's the main idea here?",
        "Break it down step by step...",
        "Start with what you know best.",
    ]
    import random
    return random.choice(encouragements)
