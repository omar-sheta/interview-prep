"""
Coaching Service
Provides realtime hints and guidance during interviews with progressive clarity.
Uses fast lightweight model (gemma3:4b) for quick responses.
"""

from server.services.llm_factory import get_fast_chat_model
from langchain_core.messages import SystemMessage, HumanMessage


async def generate_coaching_hint(
    transcript: str, 
    question: dict, 
    previous_hints: list[str] = None,
    hint_level: int = 1
) -> str:
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
    if hint_level == 1:
        if has_transcript:
            directiveness = """Based on what they've said so far, give a helpful direction.
Suggest the NEXT concept or point they should cover.
Be specific and actionable. Max 20 words."""
        else:
            directiveness = """The user needs help getting started.
Suggest HOW to structure their answer or WHERE to begin.
Give a concrete first step. Max 20 words."""
    elif hint_level == 2:
        directiveness = """The user needs clearer guidance.
Mention a specific concept, framework, or example they should discuss.
Be direct and helpful. Max 25 words."""
    else:  # 3+
        directiveness = f"""This is hint #{hint_level}. Be VERY helpful.
List 2-3 specific points they should cover or give them a mini-outline.
Don't give the full answer, but guide them clearly. Max 30 words."""
    
    # Context about previous hints
    prev_context = ""
    if previous_hints and len(previous_hints) > 0:
        prev_context = f"\nPrevious hints: {previous_hints[-2:]}\nProvide something NEW and more specific."
    
    # Context about what they've said
    transcript_context = f'What they\'ve said so far: "{transcript[:300]}..."' if has_transcript else "They haven't started answering yet."
    
    prompt = f"""You are an expert Interview Coach helping in real-time.

QUESTION: "{question_text}"
CATEGORY: {category}
SKILL TESTED: {skill or "General"}
KEY POINTS TO COVER: {', '.join(points[:4]) if points else "Clear explanation with examples"}

{transcript_context}
{prev_context}

INSTRUCTION: {directiveness}

Respond with ONLY the helpful hint, no quotes or prefixes."""

    chat_model = get_fast_chat_model()
    try:
        response = await chat_model.ainvoke([SystemMessage(content=prompt)])
        hint = response.content.strip()
        # Clean up quotes and prefixes
        hint = hint.replace('"', '').replace("'", "")
        for prefix in ["Hint:", "Tip:", "Try:", "Remember:"]:
            if hint.startswith(prefix):
                hint = hint[len(prefix):].strip()
        return hint
    except Exception as e:
        print(f"❌ Coaching generation failed: {e}")
        return None


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
