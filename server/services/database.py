"""
Database service for Qdrant vector database operations.
"""

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from server.config import settings


# Initialize Qdrant client with local persistence
qdrant_client = QdrantClient(path=settings.QDRANT_PATH)


def init_vectors() -> None:
    """
    Initialize vector collections on application startup.
    Creates the 'interview_questions' collection if it doesn't exist.
    """
    collection_name = "interview_questions"
    
    # Check if collection already exists
    collections = qdrant_client.get_collections().collections
    collection_names = [c.name for c in collections]
    
    if collection_name not in collection_names:
        # Create the collection with cosine similarity
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=settings.EMBEDDING_DIM,  # 768 for nomic-embed-text
                distance=Distance.COSINE
            )
        )
        print(f"✅ Created collection: {collection_name}")
    else:
        print(f"ℹ️  Collection '{collection_name}' already exists")


def check_qdrant_status() -> str:
    """
    Quick health check for Qdrant.
    Returns 'active' if the client can communicate, 'error' otherwise.
    """
    try:
        qdrant_client.get_collections()
        return "active"
    except Exception as e:
        print(f"⚠️ Qdrant health check failed: {e}")
        return "error"
