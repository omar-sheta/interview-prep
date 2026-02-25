"""
Persistent cache for pre-generated interview questions.
Uses SQLite database as primary storage, with in-memory cache for hot reads.
"""
import json
from typing import Any, Optional


class QuestionCache:
    """
    Question cache with SQLite persistence.
    Falls back to in-memory cache for current session.
    """
    _instance = None
    _cache: dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QuestionCache, cls).__new__(cls)
            cls._cache = {}
            print("🔧 QuestionCache initialized (DB-backed)")
        return cls._instance
    
    def _get_db(self):
        """Get UserDatabase instance."""
        from server.services.user_database import get_user_db
        return get_user_db()
    
    def set(self, key: str, value: Any, user_id: str = None, job_title: str = None, session_id: str = None):
        """
        Set a value in the cache and persist to database.
        
        Args:
            key: Cache key (e.g., user_id_job_title_session_id)
            value: Questions list to cache
            user_id: Optional user ID for database storage
            job_title: Optional job title for database storage
            session_id: Optional session ID for database storage
        """
        # Update in-memory cache
        self._cache[key] = value
        
        # Parse key for user_id if not provided
        if not user_id and "_" in key:
            parts = key.split("_")
            user_id = parts[0] if len(parts) >= 1 else "unknown"
            session_id = parts[-1] if len(parts) >= 2 else "s1"
        
        # Persist to database
        try:
            db = self._get_db()
            db.save_cached_questions(
                cache_key=key,
                user_id=user_id or "unknown",
                job_title=job_title or "",
                session_id=session_id or "",
                questions=value
            )
        except Exception as e:
            print(f"⚠️ Failed to persist cache to DB: {e}")
        
    def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        Checks in-memory first, then database.
        """
        # Check in-memory cache first (hot path)
        if key in self._cache:
            print(f"✅ Memory cache hit for {key}")
            return self._cache[key]
        
        # Check database
        try:
            db = self._get_db()
            result = db.get_cached_questions(key)
            if result:
                # Populate in-memory cache for future reads
                self._cache[key] = result
                return result
        except Exception as e:
            print(f"⚠️ DB cache lookup failed: {e}")
        
        print(f"❌ Cache miss for {key}")
        return None
    
    def delete(self, key: str):
        """Remove a value from the cache."""
        if key in self._cache:
            del self._cache[key]
        
        try:
            db = self._get_db()
            db.delete_cached_questions(key)
        except Exception as e:
            print(f"⚠️ Failed to delete from DB cache: {e}")

    def delete_user_keys(self, user_id: str):
        """Remove all cache entries for a user from memory and DB."""
        prefix = f"{user_id}_"
        keys_to_delete = [k for k in self._cache.keys() if k.startswith(prefix)]
        for key in keys_to_delete:
            del self._cache[key]

        try:
            db = self._get_db()
            db.delete_cached_questions_for_user(user_id)
        except Exception as e:
            print(f"⚠️ Failed to clear user cache from DB: {e}")

    def clear(self):
        """Clear in-memory cache only (DB persists)."""
        self._cache = {}
        print("🧹 In-memory cache cleared")


def get_question_cache() -> QuestionCache:
    return QuestionCache()
