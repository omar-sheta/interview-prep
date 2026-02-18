"""
LLM Factory - OLLAMA EDITION.
Uses the stable Ollama API instead of raw MLX.
Updated for Universal Role Support (Tech, Healthcare, Business, etc.)
"""

import asyncio
from typing import AsyncIterator, List

# Try importing standard langchain_ollama, fall back if needed
try:
    from langchain_ollama import ChatOllama
except ImportError:
    from langchain_community.chat_models import ChatOllama

from langchain_core.messages import BaseMessage, SystemMessage
from server.config import settings

# ============== Universal Interviewer Persona ==============

# CHANGED: Removed "technical" to support all industries (Nursing, Sales, etc.)
INTERVIEWER_SYSTEM_PROMPT = """You are an expert professional interviewer.
Current interview phase: {phase}

Your role:
- Adopt the persona appropriate for the candidate's target role (e.g. Clinical for Nursing, Strategic for Business).
- Ask clear, focused questions one at a time.
- Listen carefully to responses.
- Be encouraging but maintain professional standards.
- Be concise (2-3 sentences max).
"""

# ============== Ollama Wrapper ==============

class OllamaWrapper(ChatOllama):
    """
    Wrapper around ChatOllama to support the custom streaming method
    expected by the SOTA backend.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def generate_response_stream(
        self,
        messages: List[BaseMessage],
        phase: str = "general" # Renamed default from 'technical' to 'general'
    ) -> AsyncIterator[str]:
        """
        Custom streaming wrapper for main.py compatibility.
        Injects the system prompt dynamically.
        """
        # 1. Inject Persona
        system_content = INTERVIEWER_SYSTEM_PROMPT.format(phase=phase)
        
        # Check if system prompt exists, if not prepend it
        if not messages or not isinstance(messages[0], SystemMessage):
            messages.insert(0, SystemMessage(content=system_content))
        else:
            # Update existing system prompt to ensure phase is correct
            # We preserve the original context if it was specific, 
            # but usually we want to enforce the interviewer persona.
            messages[0] = SystemMessage(content=system_content)

        # 2. Stream from Ollama
        try:
            async for chunk in self.astream(messages):
                if chunk.content:
                    yield chunk.content
        except Exception as e:
            yield f"\n\n[System Error: Could not connect to Ollama at {self.base_url}. Is 'ollama serve' running?]"
            print(f"❌ Ollama Error: {e}")


def get_chat_model() -> OllamaWrapper:
    """Factory function to get the Ollama model."""
    return OllamaWrapper(
        model=settings.LLM_MODEL_ID,
        temperature=0.7,
        base_url="http://localhost:11434",
        # Disable thinking/reasoning mode (qwen3 thinks by default — adds 10-30s per call)
        reasoning=False,
        # Smaller context window — our prompts are short, no need for 32k tokens
        num_ctx=8192,
    )


def preload_model():
    """Dummy function for compatibility - Ollama handles model loading."""
    print(f"🔄 Using Ollama model: {settings.LLM_MODEL_ID}")
    print("✅ Ollama backend wrapper ready")


def get_fast_chat_model() -> OllamaWrapper:
    """
    Get lightweight model for quick coaching tips.
    Uses FAST_LLM_MODEL env var, or falls back to the main model for stability.
    """
    fast_model = getattr(settings, 'FAST_LLM_MODEL_ID', None) or settings.LLM_MODEL_ID
    return OllamaWrapper(
        model=fast_model,
        temperature=0.5,
        base_url="http://localhost:11434",
        reasoning=False,
        num_ctx=8192,
    )