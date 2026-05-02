"""
Lightweight in-memory semantic skill matcher.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None


_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_EMBED_MODEL: SentenceTransformer | None = None


def _normalize_skill_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("/", " ").replace("-", " ").split())


def _token_overlap_score(left: str, right: str) -> float:
    left_tokens = set(_normalize_skill_text(left).split())
    right_tokens = set(_normalize_skill_text(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    jaccard = intersection / union if union else 0.0
    seq = SequenceMatcher(None, _normalize_skill_text(left), _normalize_skill_text(right)).ratio()
    return round(max(jaccard, seq), 4)


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def _get_embedder() -> SentenceTransformer | None:
    global _EMBED_MODEL
    if SentenceTransformer is None:
        return None
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer(_MODEL_NAME)
    return _EMBED_MODEL


@lru_cache(maxsize=512)
def _embed_text(text: str) -> np.ndarray | None:
    embedder = _get_embedder()
    if embedder is None:
        return None
    vector = embedder.encode(text, normalize_embeddings=True)
    return np.array(vector, dtype=float)


def match_skills_semantically(
    candidate_skills: list[str],
    required_skills: list[str],
    threshold: float = 0.75
) -> dict[str, dict[str, Any]]:
    """
    Match required skills to the closest candidate skills.

    Returns:
        {
            "required skill": {
                "candidate_skill": "closest candidate skill",
                "score": 0.84
            }
        }
    """
    matches: dict[str, dict[str, Any]] = {}
    normalized_candidates = [str(skill or "").strip() for skill in candidate_skills if str(skill or "").strip()]
    normalized_required = [str(skill or "").strip() for skill in required_skills if str(skill or "").strip()]
    if not normalized_candidates or not normalized_required:
        return matches

    embedded_required = {}
    embedded_candidates = {}
    try:
        for skill in normalized_required:
            embedded_required[skill] = _embed_text(skill)
        for skill in normalized_candidates:
            embedded_candidates[skill] = _embed_text(skill)
    except Exception:
        embedded_required = {}
        embedded_candidates = {}

    use_embeddings = bool(embedded_required) and all(vec is not None for vec in embedded_required.values()) and all(
        vec is not None for vec in embedded_candidates.values()
    )

    for required_skill in normalized_required:
        best_skill = ""
        best_score = 0.0
        for candidate_skill in normalized_candidates:
            if use_embeddings:
                score = _cosine_similarity(embedded_required[required_skill], embedded_candidates[candidate_skill])
            else:
                score = _token_overlap_score(required_skill, candidate_skill)
            if score > best_score:
                best_score = score
                best_skill = candidate_skill
        if best_skill and best_score >= threshold:
            matches[required_skill] = {
                "candidate_skill": best_skill,
                "score": round(best_score, 4),
            }

    return matches
