"""
Database service for optional Qdrant vector database operations.
"""

from typing import Any, Optional

from server.config import settings

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import Distance, VectorParams
except ImportError:
    QdrantClient = None
    Distance = None
    VectorParams = None


_qdrant_client: Optional[Any] = None


def qdrant_enabled() -> bool:
    """Return whether Qdrant is enabled for this process."""
    return bool(getattr(settings, "QDRANT_ENABLED", False))


def get_qdrant_client() -> Any:
    """
    Lazily initialize Qdrant client with local persistence.
    This avoids lock conflicts during module import when uvicorn reload spawns parent/child.
    """
    if not qdrant_enabled():
        raise RuntimeError("Qdrant is disabled")

    if QdrantClient is None:
        raise RuntimeError("qdrant-client is not installed")

    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(path=settings.QDRANT_PATH)
    return _qdrant_client


def init_vectors() -> None:
    """
    Initialize vector collections on application startup.
    Creates the 'interview_questions' collection if it doesn't exist.
    """
    if not qdrant_enabled():
        print("ℹ️  Qdrant disabled; skipping vector store init")
        return

    qdrant_client = get_qdrant_client()
    collection_name = "interview_questions"

    collections = qdrant_client.get_collections().collections
    collection_names = [c.name for c in collections]

    if collection_name not in collection_names:
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=settings.EMBEDDING_DIM,
                distance=Distance.COSINE
            )
        )
        print(f"✅ Created collection: {collection_name}")
    else:
        print(f"ℹ️  Collection '{collection_name}' already exists")


def check_qdrant_status() -> str:
    """
    Quick health check for Qdrant.
    Returns 'disabled', 'missing', 'active', or 'error'.
    """
    if not qdrant_enabled():
        return "disabled"

    if QdrantClient is None:
        return "missing"

    try:
        qdrant_client = get_qdrant_client()
        qdrant_client.get_collections()
        return "active"
    except Exception as e:
        print(f"⚠️ Qdrant health check failed: {e}")
        return "error"
