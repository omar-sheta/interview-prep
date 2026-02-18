"""
Configuration settings for the Interview Agent Server.
Uses pydantic-settings for environment-based configuration.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Model paths
    MODEL_PATH: str = str(Path.home() / ".cache" / "huggingface")
    
    # Qdrant configuration
    QDRANT_PATH: str = "./qdrant_data"
    
    # Embedding dimensions (optimized for nomic-embed-text)
    EMBEDDING_DIM: int = 768
    
    # LLM Model (Ollama Tag)
    # Available: qwen2.5:7b (FAST), qwen3:14b (slow), deepseek-r1:14b
    LLM_MODEL_ID: str = "qwen3:8b"

    # Fast LLM for coaching hints (defaults to same as main model for stability)
    FAST_LLM_MODEL_ID: str = "qwen3:8b"
    
    # CORS configuration
    # Set CORS_ORIGINS env var to restrict in production (comma-separated)
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
    
    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # User database path
    USER_DB_PATH: str = "./user_data/interview_app.db"


# Global settings instance
settings = Settings()
