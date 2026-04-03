"""
Configuration settings for BeePrepared.
Uses pydantic-settings for environment-based configuration.
"""

import json
from pathlib import Path
from typing import Annotated
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Model paths
    MODEL_PATH: str = str(Path.home() / ".cache" / "huggingface")
    
    # Optional Qdrant configuration
    QDRANT_ENABLED: bool = False
    QDRANT_PATH: str = str(PROJECT_ROOT / "qdrant_data")
    
    # Embedding dimensions (optimized for nomic-embed-text)
    EMBEDDING_DIM: int = 768
    
    # LLM provider: lmstudio (OpenAI-compatible API) or ollama.
    LLM_PROVIDER: str = "lmstudio"

    # Base URL for selected provider.
    # LM Studio default endpoint includes /v1.
    LLM_BASE_URL: str = "http://127.0.0.1:1234/v1"

    # API key used by OpenAI-compatible clients (LM Studio accepts any non-empty value).
    LLM_API_KEY: str = "lm-studio"

    # Default model for agentic flows in BeePrepared.
    # For LM Studio this must match a loaded model id, but factory includes auto-fallback.
    LLM_MODEL_ID: str = "qwen/qwen3.5-35b-a3b"

    # Fast model for short coaching calls. Set equal to main model for consistency.
    FAST_LLM_MODEL_ID: str = "qwen/qwen3.5-35b-a3b"

    # Reuse one shared model client instance for all flows (analysis/interview/coaching)
    # to avoid loading/seating multiple model sessions on constrained memory machines.
    LLM_SINGLE_INSTANCE: bool = True
    # Max concurrent LLM requests in-process. Set to 1 to avoid multi-slot contention.
    LLM_MAX_CONCURRENCY: int = 1

    # LM Studio / OpenAI-compatible generation guards.
    # Disables model "thinking" traces for Qwen chat templates when supported.
    LLM_DISABLE_THINKING: bool = True
    # Cap completion tokens to avoid very long reasoning dumps.
    LLM_MAX_TOKENS: int = 8192
    # Tighter cap for JSON-extraction style calls (resume/JD/skill extraction).
    # Increased to 2500 to allow room for "Thinking Process" traces from reasoning models.
    LLM_JSON_MAX_TOKENS: int = 6000

    # Streaming STT (partial transcripts)
    WHISPER_CPP_ENABLED: bool = True
    WHISPER_CPP_BIN: str = str(PROJECT_ROOT / "third_party" / "whisper.cpp" / "build" / "bin" / "whisper-cli")
    WHISPER_CPP_MODEL_PATH: str = str(PROJECT_ROOT / "third_party" / "whisper.cpp" / "models" / "ggml-base.en.bin")
    WHISPER_CPP_LANGUAGE: str = "en"
    WHISPER_CPP_THREADS: int = 4
    # whisper.cpp CLI auto-uses GPU when available; set <= 0 to force CPU-only fallback.
    WHISPER_CPP_GPU_LAYERS: int = 99
    WHISPER_CPP_TIMEOUT_SEC: float = 8.0

    # Audio chunk timing for low-latency partials and end-of-utterance finalization
    STT_PARTIAL_CHUNK_MS: int = 700
    STT_PARTIAL_COOLDOWN_MS: int = 450
    # Silence duration before finalizing an utterance.
    STT_FINALIZE_SILENCE_MS: int = 1800

    # CORS configuration
    # Override with CORS_ORIGINS as JSON array or comma-separated string.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "*",
        # HTTPS origins for Caddy reverse proxy
        "https://192.168.0.161", "https://192.168.1.48", "https://spark.hivehub.org",
        "https://localhost", "https://127.0.0.1",
        "https://192.168.0.161:443", "https://spark.hivehub.org:443",
        "https://192.168.0.161:8443", "https://192.168.1.48:8443", "https://spark.hivehub.org:8443",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except json.JSONDecodeError:
                    pass
            return [origin.strip() for origin in raw.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return value
    
    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # User database path
    USER_DB_PATH: str = str(PROJECT_ROOT / "user_data" / "interview_app.db")

    # Feedback loop rollout flag
    FEEDBACK_LOOP_V2: bool = True

    # ============== Interview / Feedback Thresholds ==============
    # Readiness mix thresholds
    READINESS_LOW_CUTOFF: float = 0.4
    READINESS_MID_CUTOFF: float = 0.7

    # Struggle detector thresholds
    COACH_SILENCE_SECONDS: float = 8.0
    COACH_FILLER_LIMIT: int = 8
    COACH_SHORT_ANSWER_WORDS: int = 15
    COACH_SHORT_ANSWER_SILENCE_SECONDS: float = 25.0

    # Evaluation strictness defaults
    EVAL_SHORT_ANSWER_WORDS: int = 10
    EVAL_TRANSCRIPT_LOW_WORDS: int = 8
    EVAL_REPETITION_RATIO_CAP: float = 0.42
    EVAL_QUALITY_REPETITION_RATIO_FLAG: float = 0.45
    EVAL_UNIQUE_WORD_RATIO_MIN: float = 0.40
    EVAL_QUALITY_UNIQUE_WORD_RATIO_FLAG: float = 0.35
    EVAL_GIBBERISH_RATIO_THRESHOLD: float = 0.28
    EVAL_STRUCTURE_MARKERS_MIN: int = 2
    EVAL_STRUCTURE_SENTENCE_CAP: int = 2
    EVAL_LOW_RELEVANCE_THRESHOLD: float = 0.12
    EVAL_COVERAGE_MIN: float = 0.40
    EVAL_LOW_TRANSCRIPT_PENALTY: float = 1.0
    EVAL_LOW_TRANSCRIPT_CONFIDENCE_CAP: float = 0.45

    # Score caps
    EVAL_ACCURACY_CAP_LOW_RELEVANCE: float = 3.0
    EVAL_CLARITY_CAP_REPETITION: float = 3.0
    EVAL_COMPLETENESS_CAP_LOW_COVERAGE: float = 4.0
    EVAL_STRUCTURE_CAP_WEAK: float = 4.0


# Global settings instance
settings = Settings()
