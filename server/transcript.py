"""
Transcript merge and false-start handling helpers.
"""

import re
from difflib import SequenceMatcher


def transcript_similarity(a: str, b: str) -> float:
    """Return similarity ratio 0.0-1.0 between two transcripts."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def normalized_transcript_words(text: str) -> list[str]:
    """Normalize transcript into lowercase word tokens for fuzzy overlap checks."""
    if not text:
        return []
    return re.findall(r"[a-z0-9']+", text.lower())


def should_drop_false_start(existing: str, new_chunk: str) -> bool:
    """
    Drop common Whisper false-start hallucinations on fresh transcripts.
    Keeps legitimate content once there is already transcript context.
    """
    if (existing or "").strip():
        return False

    words = normalized_transcript_words(new_chunk)
    if not words:
        return True

    joined = " ".join(words)
    common_false_starts = {
        "thank you",
        "thank you very much",
        "thanks",
        "thanks for watching",
        "thank you for watching",
        "thank you for transcription",
    }
    if joined in common_false_starts:
        return True

    # Guard short "thank you for ..." phantom opener chunks.
    if len(words) <= 5 and words[:3] == ["thank", "you", "for"]:
        return True

    return False


def merge_transcript(existing: str, new_chunk: str) -> str:
    """Intelligently merge new transcript chunk with existing, avoiding duplicates."""
    if not new_chunk:
        return existing

    incoming = new_chunk.strip()
    if not incoming:
        return existing

    # Whisper occasionally prepends "thank you" on first chunk; strip that prefix but keep real content.
    if not (existing or "").strip():
        opening_words = normalized_transcript_words(incoming)
        if len(opening_words) >= 6 and opening_words[:2] == ["thank", "you"]:
            incoming = re.sub(r"^\s*thank you(?:\s+very\s+much)?[,\.\!\s]*", "", incoming, flags=re.IGNORECASE).strip()
            incoming = re.sub(r"^(and|so)\b[\s,]*", "", incoming, flags=re.IGNORECASE).strip()
            if not incoming:
                return existing

    if should_drop_false_start(existing, incoming):
        return existing

    if not existing:
        return incoming

    existing_words = existing.split()
    new_words = incoming.split()

    existing_norm = normalized_transcript_words(existing)
    new_norm = normalized_transcript_words(incoming)

    if not new_norm:
        return existing

    # If incoming chunk is basically already present in the latest transcript tail, skip it.
    tail_len = min(len(existing_norm), max(len(new_norm) + 6, len(new_norm) * 2))
    existing_tail_norm = existing_norm[-tail_len:] if tail_len > 0 else existing_norm
    if transcript_similarity(" ".join(existing_tail_norm), " ".join(new_norm)) >= 0.9:
        return existing

    # Fuzzy overlap: compare normalized tail/start tokens to avoid duplicate append.
    max_overlap = min(len(existing_words), len(new_words), 24)
    for overlap in range(max_overlap, 2, -1):
        existing_tail = " ".join(normalized_transcript_words(" ".join(existing_words[-overlap:])))
        new_head = " ".join(normalized_transcript_words(" ".join(new_words[:overlap])))
        if existing_tail and new_head and transcript_similarity(existing_tail, new_head) >= 0.92:
            suffix = " ".join(new_words[overlap:]).strip()
            if not suffix:
                return existing
            return f"{existing} {suffix}".strip()

    # Final guard: near-identical restatement without clean overlap.
    same_window = min(len(existing_norm), len(new_norm))
    if same_window > 3:
        existing_window = " ".join(existing_norm[-same_window:])
        if transcript_similarity(existing_window, " ".join(new_norm)) >= 0.92:
            return existing

    return f"{existing} {incoming}".strip()


def combine_final_and_partial(finalized: str, partial: str) -> str:
    """Compose live answer text from finalized transcript plus current partial utterance."""
    finalized = (finalized or "").strip()
    partial = (partial or "").strip()
    if finalized and partial:
        return f"{finalized} {partial}".strip()
    return finalized or partial
