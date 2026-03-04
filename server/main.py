"""
Main application entry point for the Interview Agent Server.
Combines FastAPI with Socket.IO and LangGraph agent architecture.
Implements real-time audio streaming pipeline: STT -> LLM -> TTS.
"""

import asyncio
import time
import base64
import re
import uuid
import hashlib
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional, TypedDict

try:
    import mlx.core as mx
except ImportError:
    mx = None  # MLX not available (non-Apple Silicon)
import socketio
import tempfile
import os
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from langgraph.graph import END, START, StateGraph

from server.config import settings
from server.services.database import check_qdrant_status, init_vectors
from server.services.audio_service import (
    get_audio_processor,
    get_streaming_audio_processor,
    get_vad,
)
from server.services.tts_service import get_tts_service, preload_tts
from server.services.llm_factory import get_chat_model, preload_model
from server.services.user_database import get_user_db

TTS_RESPONSE_TIMEOUT_SEC = float(os.getenv("TTS_RESPONSE_TIMEOUT_SEC", "90"))
TTS_TIMEOUT_PER_CHAR_SEC = float(os.getenv("TTS_TIMEOUT_PER_CHAR_SEC", "0.08"))
TTS_MAX_TIMEOUT_SEC = float(os.getenv("TTS_MAX_TIMEOUT_SEC", "180"))
TTS_PRELOAD_ON_STARTUP = os.getenv("TTS_PRELOAD_ON_STARTUP", "1").lower() in {"1", "true", "yes", "on"}
TTS_STARTUP_WARMUP_TEXT = os.getenv(
    "TTS_STARTUP_WARMUP_TEXT",
    "Calibration.",
).strip()
TTS_WARMUP_AWAIT_ON_FIRST_TTS = os.getenv("TTS_WARMUP_AWAIT_ON_FIRST_TTS", "1").lower() in {"1", "true", "yes", "on"}
TTS_WARMUP_WAIT_SEC = float(os.getenv("TTS_WARMUP_WAIT_SEC", "180"))
DISCONNECT_TASK_CANCEL_GRACE_SEC = float(os.getenv("DISCONNECT_TASK_CANCEL_GRACE_SEC", "90"))

_tts_warmup_task: Optional[asyncio.Task] = None


def _compute_tts_timeout(text: str) -> float:
    """Compute TTS timeout from base + text-length budget, clamped by max."""
    text_len = len((text or "").strip())
    timeout = TTS_RESPONSE_TIMEOUT_SEC + (text_len * TTS_TIMEOUT_PER_CHAR_SEC)
    return max(1.0, min(TTS_MAX_TIMEOUT_SEC, timeout))


async def _warmup_tts_backend():
    """Preload and warm TTS once so first live question does not time out."""
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, preload_tts)
        if TTS_STARTUP_WARMUP_TEXT:
            tts_service = get_tts_service()
            warmup_timeout = _compute_tts_timeout(TTS_STARTUP_WARMUP_TEXT)
            await asyncio.wait_for(
                tts_service.speak_wav_base64_async(TTS_STARTUP_WARMUP_TEXT),
                timeout=warmup_timeout,
            )
        print("✅ TTS warmup complete")
    except Exception as e:
        print(f"⚠️ TTS warmup skipped: {e}")


async def _await_tts_warmup_if_needed():
    """Await startup warmup if it is still running (avoids first-question timeout drops)."""
    global _tts_warmup_task
    if not TTS_WARMUP_AWAIT_ON_FIRST_TTS:
        return
    task = _tts_warmup_task
    if not task or task.done():
        return
    if asyncio.current_task() is task:
        return
    try:
        print("⏳ Waiting for TTS warmup to finish before synthesis...")
        await asyncio.wait_for(task, timeout=max(1.0, TTS_WARMUP_WAIT_SEC))
    except asyncio.TimeoutError:
        print(f"⚠️ TTS warmup wait timed out after {TTS_WARMUP_WAIT_SEC:.1f}s; continuing.")
    except Exception as e:
        print(f"⚠️ TTS warmup wait failed: {e}")


# ============== Session State Management ==============

class SessionState:
    """Per-session state for audio streaming and conversation."""
    
    # Buffer constants
    MAX_BUFFER_SIZE = 4_800_000  # ~150 seconds at 16kHz mono 16-bit
    NEW_AUDIO_THRESHOLD = int(32000 * (settings.STT_PARTIAL_CHUNK_MS / 1000.0))
    TRANSCRIBE_COOLDOWN = max(0.1, settings.STT_PARTIAL_COOLDOWN_MS / 1000.0)
    FINALIZE_SILENCE_SECONDS = max(0.3, settings.STT_FINALIZE_SILENCE_MS / 1000.0)
    
    def __init__(self, user_id: str = "anonymous", is_authenticated: bool = False, session_token: Optional[str] = None):
        self.user_id = user_id
        self.is_authenticated = is_authenticated
        self.session_token = session_token
        
        # Audio buffer - circular with max size
        self.audio_buffer = bytearray()
        
        # Transcription tracking
        self.last_transcribed_position: int = 0
        self.last_finalized_position: int = 0
        self.current_utterance_start_position: int = 0
        self.last_transcribe_time: float = 0
        self.recent_transcripts: list[str] = []  # Last 3 for deduplication
        self.current_partial_transcript: str = ""
        self.finalized_answer_transcript: str = ""
        
        # Legacy (for compatibility)
        self.transcript_chunks: list[str] = []
        self.messages: list = []
        self.status: str = "warmup"
        self.is_processing: bool = False
        
        # Interview practice fields
        self.interview_active: bool = False
        self.interview_questions: list[dict] = []
        self.current_question_index: int = 0
        self.interview_mode: str = "practice"
        self.interview_feedback_timing: str = "end_only"
        self.live_scoring_enabled: bool = False
        self.interviewer_persona: str = "friendly"
        self.tts_style: str = "interviewer"
        self.tts_provider: str = "piper"
        self.coaching_enabled: bool = False
        self.answer_start_time: float = None
        self.current_answer_transcript: str = ""
        self.evaluations: list[dict] = []
        self.job_title: str = ""
        self.last_hint_time: float = 0
        self.hints_given: list[str] = []
        self.db_session_id: str = None  # UUID for database persistence
        self.answer_submission_in_flight: bool = False
        self.accept_audio_chunks: bool = False
        self.end_requested: bool = False
        self.question_tts_task: Optional[asyncio.Task] = None
        self.finalize_lock: asyncio.Lock = asyncio.Lock()
        
        # Speaking state tracking
        self.was_speaking: bool = False
        self.silence_start_time: float = None
    
    def append_audio(self, audio_bytes: bytes) -> int:
        """Append audio with circular buffer management. Returns bytes trimmed."""
        self.audio_buffer.extend(audio_bytes)
        trimmed = 0
        
        if len(self.audio_buffer) > self.MAX_BUFFER_SIZE:
            overflow = len(self.audio_buffer) - self.MAX_BUFFER_SIZE
            self.audio_buffer = self.audio_buffer[overflow:]
            # Adjust position tracker
            self.last_transcribed_position = max(0, self.last_transcribed_position - overflow)
            self.last_finalized_position = max(0, self.last_finalized_position - overflow)
            self.current_utterance_start_position = max(0, self.current_utterance_start_position - overflow)
            trimmed = overflow
        
        return trimmed
    
    def should_transcribe(self, current_time: float) -> bool:
        """Check if we have enough new audio and cooldown has passed."""
        bytes_new = len(self.audio_buffer) - self.last_transcribed_position
        time_since = current_time - self.last_transcribe_time
        min_new_audio = max(3200, self.NEW_AUDIO_THRESHOLD)
        return bytes_new >= min_new_audio and time_since >= self.TRANSCRIBE_COOLDOWN
    
    def clear_for_new_question(self):
        """Reset buffer state for a new question."""
        self.audio_buffer.clear()
        self.last_transcribed_position = 0
        self.last_finalized_position = 0
        self.current_utterance_start_position = 0
        self.last_transcribe_time = 0
        self.recent_transcripts = []
        self.current_partial_transcript = ""
        self.finalized_answer_transcript = ""
        self.current_answer_transcript = ""
        self.hints_given = []
        self.was_speaking = False
        self.silence_start_time = None

# Global session storage
sessions: dict[str, SessionState] = {}

# Maps Socket ID -> User ID for quick lookup on disconnect
sid_to_user: dict[str, str] = {}

# Maps User ID -> count of active socket connections
user_connection_count: dict[str, int] = defaultdict(int)

# Maps User ID -> Active asyncio Task (for cancellation on disconnect or restart)
active_tasks: dict[str, asyncio.Task] = {}
# Maps User ID -> delayed cancellation task (disconnect grace window)
pending_disconnect_cancels: dict[str, asyncio.Task] = {}

# Feedback loop metrics (v2 rollout visibility)
feedback_metrics = {
    "evaluations_total": 0,
    "evaluations_v2": 0,
    "low_transcript_quality": 0,
    "retries_total": 0,
    "retry_delta_sum": 0.0,
    "retry_improved_count": 0,
    "score_sum_v1": 0.0,
    "score_count_v1": 0,
    "score_sum_v2": 0.0,
    "score_count_v2": 0,
}


def _record_evaluation_metrics(evaluation: dict):
    feedback_metrics["evaluations_total"] += 1
    score = 0.0
    try:
        score = float((evaluation or {}).get("score", 0) or 0)
    except Exception:
        score = 0.0

    if (evaluation or {}).get("evaluation_version") == "v2":
        feedback_metrics["evaluations_v2"] += 1
        feedback_metrics["score_sum_v2"] += score
        feedback_metrics["score_count_v2"] += 1
    else:
        feedback_metrics["score_sum_v1"] += score
        feedback_metrics["score_count_v1"] += 1
    if "low_transcript_quality" in ((evaluation or {}).get("quality_flags") or []):
        feedback_metrics["low_transcript_quality"] += 1


def _record_retry_metrics(delta_score: float):
    feedback_metrics["retries_total"] += 1
    try:
        delta = float(delta_score)
        feedback_metrics["retry_delta_sum"] += delta
        if delta > 0:
            feedback_metrics["retry_improved_count"] += 1
    except Exception:
        pass


def _public_user_id(session: SessionState) -> str:
    """Expose stable public user identity to the client."""
    return session.user_id if session.is_authenticated else "anonymous"


def _safe_user_payload(user: Optional[dict]) -> dict:
    """Strip sensitive user fields before sending to client."""
    if not user:
        return {}
    return {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "username": user.get("username"),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
        "profile": user.get("profile", {}),
    }


def _normalize_latest_analysis_payload(user_id: str, saved_analysis: Optional[dict]) -> dict:
    """
    Normalize latest analysis payload for UI consistency.
    If session titles were saved as full questions, generate stable display titles and persist once.
    """
    if not isinstance(saved_analysis, dict):
        return {}

    analysis_data = saved_analysis.get("analysis")
    if not isinstance(analysis_data, dict):
        analysis_data = {}

    practice_plan = analysis_data.get("practice_plan")
    if not isinstance(practice_plan, dict):
        return analysis_data

    try:
        import copy
        from server.agents.nodes import normalize_practice_plan_titles

        normalized_plan = normalize_practice_plan_titles(copy.deepcopy(practice_plan))
        if normalized_plan != practice_plan:
            analysis_data["practice_plan"] = normalized_plan
            get_user_db().update_latest_analysis_plan(user_id, normalized_plan)
    except Exception as e:
        print(f"⚠️ Failed to normalize persisted plan titles: {e}")

    return analysis_data


def _cancel_user_task_if_idle(user_id: str):
    """Cancel or schedule cancellation for active long-running task when user is idle."""
    if user_connection_count.get(user_id, 0) != 0:
        return

    # Clear any existing scheduled cancel for this user before creating a new one.
    existing = pending_disconnect_cancels.pop(user_id, None)
    if existing and not existing.done():
        existing.cancel()

    if DISCONNECT_TASK_CANCEL_GRACE_SEC <= 0:
        task = active_tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()
            print(f"🛑 No active connections: cancelled task for {user_id}")
        return

    async def _cancel_after_grace():
        try:
            await asyncio.sleep(DISCONNECT_TASK_CANCEL_GRACE_SEC)
            if user_connection_count.get(user_id, 0) != 0:
                return
            task = active_tasks.pop(user_id, None)
            if task and not task.done():
                task.cancel()
                print(
                    f"🛑 No reconnect within {DISCONNECT_TASK_CANCEL_GRACE_SEC:.0f}s: "
                    f"cancelled task for {user_id}"
                )
        except asyncio.CancelledError:
            return
        finally:
            pending_disconnect_cancels.pop(user_id, None)

    pending_disconnect_cancels[user_id] = asyncio.create_task(_cancel_after_grace())
    print(
        f"⏳ No active connections for {user_id}; waiting "
        f"{DISCONNECT_TASK_CANCEL_GRACE_SEC:.0f}s before cancelling task"
    )


async def _bind_sid_identity(
    sid: str,
    new_user_id: str,
    is_authenticated: bool,
    session_token: Optional[str] = None
):
    """
    Atomically re-bind socket identity, room, and connection counters.
    Prevents counter drift when moving from anon -> authenticated user.
    """
    session = sessions.get(sid)
    if session is None:
        return

    old_user_id = sid_to_user.get(sid)
    old_auth = session.is_authenticated

    if old_user_id == new_user_id and old_auth == is_authenticated:
        session.session_token = session_token or session.session_token
        return

    if old_user_id:
        await sio.leave_room(sid, str(old_user_id))
        user_connection_count[old_user_id] = max(0, user_connection_count[old_user_id] - 1)
        _cancel_user_task_if_idle(old_user_id)

    await sio.enter_room(sid, str(new_user_id))
    sid_to_user[sid] = new_user_id
    user_connection_count[new_user_id] += 1
    # User reconnected / switched identity; cancel any pending idle-task cancellation.
    pending = pending_disconnect_cancels.pop(new_user_id, None)
    if pending and not pending.done():
        pending.cancel()

    session.user_id = new_user_id
    session.is_authenticated = is_authenticated
    session.session_token = session_token if is_authenticated else None


async def _get_authenticated_rest_user_id(
    authorization: Optional[str] = Header(default=None),
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token")
) -> str:
    """Authenticate REST requests using Bearer token or X-Session-Token header."""
    token = None
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            token = value.strip()
    if not token and x_session_token:
        token = x_session_token.strip()

    if not token:
        raise HTTPException(status_code=401, detail="Missing session token")

    user_db = get_user_db()
    user_id = user_db.validate_session_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    return user_id


async def _require_socket_auth(sid: str) -> Optional[SessionState]:
    """Ensure socket request belongs to an authenticated session."""
    session = sessions.get(sid)
    if not session or not session.is_authenticated:
        await sio.emit("auth_error", {"error": "Authentication required", "user_id": "anonymous"}, room=sid)
        return None
    return session


def transcript_similarity(a: str, b: str) -> float:
    """Return similarity ratio 0.0-1.0 between two transcripts."""
    if not a or not b:
        return 0.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _normalized_transcript_words(text: str) -> list[str]:
    """Normalize transcript into lowercase word tokens for fuzzy overlap checks."""
    if not text:
        return []
    return re.findall(r"[a-z0-9']+", text.lower())


def _should_drop_false_start(existing: str, new_chunk: str) -> bool:
    """
    Drop common Whisper false-start hallucinations on fresh transcripts.
    Keeps legitimate content once there is already transcript context.
    """
    if (existing or "").strip():
        return False

    words = _normalized_transcript_words(new_chunk)
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
        opening_words = _normalized_transcript_words(incoming)
        if len(opening_words) >= 6 and opening_words[:2] == ["thank", "you"]:
            incoming = re.sub(r"^\s*thank you(?:\s+very\s+much)?[,\.\!\s]*", "", incoming, flags=re.IGNORECASE).strip()
            incoming = re.sub(r"^(and|so)\b[\s,]*", "", incoming, flags=re.IGNORECASE).strip()
            if not incoming:
                return existing

    if _should_drop_false_start(existing, incoming):
        return existing

    if not existing:
        return incoming

    existing_words = existing.split()
    new_words = incoming.split()

    existing_norm = _normalized_transcript_words(existing)
    new_norm = _normalized_transcript_words(incoming)

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
        existing_tail = " ".join(_normalized_transcript_words(" ".join(existing_words[-overlap:])))
        new_head = " ".join(_normalized_transcript_words(" ".join(new_words[:overlap])))
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


def _combine_final_and_partial(finalized: str, partial: str) -> str:
    """Compose live answer text from finalized transcript plus current partial utterance."""
    finalized = (finalized or "").strip()
    partial = (partial or "").strip()
    if finalized and partial:
        return f"{finalized} {partial}".strip()
    return finalized or partial


async def _emit_transcript_update(session: SessionState, is_final: bool = False):
    """Emit current transcript to the client."""
    transcript = (session.current_answer_transcript or "").strip()
    if not transcript:
        return
    await sio.emit(
        "transcript",
        {
            "text": transcript,
            "full": transcript,
            "is_final": is_final,
            "user_id": session.user_id,
        },
        room=str(session.user_id),
    )


async def _maybe_emit_coaching_hint(session: SessionState, current_time: float, is_extended_silence: bool):
    """Evaluate struggling heuristics and emit a coaching hint when appropriate."""
    if not (session.coaching_enabled and is_extended_silence):
        return

    if session.answer_start_time:
        answer_duration = current_time - session.answer_start_time
    else:
        answer_duration = 0

    words = (session.current_answer_transcript or "").lower().split()
    filler_words = ['uh', 'uhm', 'um', 'hmm', 'err', 'like,', '...']
    last_words = words[-5:] if len(words) >= 5 else words
    has_fillers = any(fw in ' '.join(last_words) for fw in filler_words)

    hint_count = len(session.hints_given)
    hint_cooldown = 5 if hint_count == 0 else 10

    should_hint = (
        (current_time - session.last_hint_time) > hint_cooldown and
        (
            (answer_duration > 5 and len(words) < 10) or
            (has_fillers and len(words) < 20) or
            (answer_duration > 20)
        )
    )
    if not should_hint:
        return

    session.last_hint_time = current_time
    hint_level = hint_count + 1
    print(f"🤔 Generating hint level {hint_level}")

    async def send_hint():
        try:
            from server.services.coaching_service import generate_coaching_hint

            current_q = (
                session.interview_questions[session.current_question_index]
                if session.interview_questions else {}
            )
            hint = await generate_coaching_hint(
                session.current_answer_transcript,
                current_q,
                previous_hints=session.hints_given,
                hint_level=hint_level
            )
            if hint:
                hint_message = hint["message"] if isinstance(hint, dict) else str(hint)
                print(f"💡 Hint L{hint_level}: {hint_message}")
                session.hints_given.append(hint_message)
                payload = {"message": hint_message, "level": hint_level, "user_id": session.user_id}
                if isinstance(hint, dict):
                    payload.update({k: v for k, v in hint.items() if k != "message"})
                await sio.emit("coaching_hint", payload, room=str(session.user_id))
        except Exception as e:
            print(f"⚠️ Hint error: {e}")

    asyncio.create_task(send_hint())


async def _finalize_current_utterance(session: SessionState, reason: str = "silence") -> bool:
    """
    Finalize current utterance with high-accuracy STT.
    Returns True when accumulated transcript changed.
    """
    async with session.finalize_lock:
        end_pos = len(session.audio_buffer)
        start_pos = max(0, min(session.last_finalized_position, end_pos))
        if end_pos <= start_pos:
            session.current_partial_transcript = ""
            session.current_utterance_start_position = end_pos
            session.last_transcribed_position = end_pos
            session.was_speaking = False
            return False

        # Require a small minimum amount of audio unless we're force-finalizing.
        min_bytes = 6400  # ~200ms at 16kHz mono 16-bit
        if (end_pos - start_pos) < min_bytes and reason != "force":
            return False

        audio_processor = get_audio_processor()
        finalized_chunk = await audio_processor.transcribe_buffer_async(bytes(session.audio_buffer[start_pos:end_pos]))
        finalized_chunk = (finalized_chunk or "").strip()

        # If final pass is empty, keep best-effort partial text so user doesn't lose words.
        if not finalized_chunk:
            finalized_chunk = (session.current_partial_transcript or "").strip()

        changed = False
        if finalized_chunk:
            merged = merge_transcript(session.finalized_answer_transcript, finalized_chunk)
            changed = merged != session.finalized_answer_transcript or bool(session.current_partial_transcript)
            session.finalized_answer_transcript = merged

        session.current_partial_transcript = ""
        session.current_answer_transcript = session.finalized_answer_transcript

        # Reclaim finalized audio from the buffer to prevent unbounded growth.
        # Keep a small tail (~0.5s) so the next utterance has context for the
        # noise-gate to avoid a hard cut at the boundary.
        keep_tail = 16000  # ~0.5s at 16kHz mono 16-bit
        discard = max(0, end_pos - keep_tail)
        if discard > 0:
            del session.audio_buffer[:discard]
            session.last_finalized_position = max(0, end_pos - discard)
            session.current_utterance_start_position = max(0, end_pos - discard)
            session.last_transcribed_position = max(0, end_pos - discard)
        else:
            session.last_finalized_position = end_pos
            session.current_utterance_start_position = end_pos
            session.last_transcribed_position = end_pos

        session.last_transcribe_time = time.time()
        session.was_speaking = False
        session.silence_start_time = None

        if changed and session.current_answer_transcript.strip():
            await _emit_transcript_update(session, is_final=True)
            print(f"🧾 Finalized ({reason}): {session.current_answer_transcript[:80]}...")

        return changed


# ============== LangGraph Sanity Check ==============

class SimpleState(TypedDict):
    """Simple state for LangGraph sanity check."""
    value: str


def node_a(state: SimpleState) -> SimpleState:
    """Sample node that transforms the state."""
    return {"value": state["value"] + " -> processed by Node A"}


def build_sanity_check_graph():
    """Build a simple 2-node LangGraph to verify installation."""
    graph = StateGraph(SimpleState)
    graph.add_node("node_a", node_a)
    graph.add_edge(START, "node_a")
    graph.add_edge("node_a", END)
    return graph.compile()


# ============== Application Lifecycle ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    # Startup
    print("🚀 Starting Interview Agent Server...")
    print(f"📁 Model path: {settings.MODEL_PATH}")
    print(f"🧠 LLM Provider: {getattr(settings, 'LLM_PROVIDER', 'ollama')}")
    print(f"🤖 LLM Model: {settings.LLM_MODEL_ID}")
    print(f"🧩 LLM Single Instance: {getattr(settings, 'LLM_SINGLE_INSTANCE', True)}")
    print(f"🌐 LLM Base URL: {settings.LLM_BASE_URL}")
    print(f"💾 Qdrant path: {settings.QDRANT_PATH}")
    
    # Initialize vector database
    init_vectors()
    
    # Check MLX Metal availability
    metal_available = mx.metal.is_available() if mx else False
    print(f"🍎 MLX Metal GPU: {metal_available}")
    
    if not metal_available:
        print("⚠️  Warning: Metal acceleration is not available!")

    try:
        streaming_stt = get_streaming_audio_processor()
        print(f"🎙️ Streaming STT: {streaming_stt.__class__.__name__}")
    except Exception as e:
        print(f"⚠️ Streaming STT init failed: {e}")
    
    # Verify LangGraph installation
    try:
        graph = build_sanity_check_graph()
        result = graph.invoke({"value": "test"})
        print(f"✅ LangGraph sanity check passed: {result['value']}")
    except Exception as e:
        print(f"❌ LangGraph sanity check failed: {e}")
    
    # Note: LLM models are lazily loaded on first use.
    print("ℹ️  LLM models will be loaded on first use (lazy loading)")
    if TTS_PRELOAD_ON_STARTUP:
        global _tts_warmup_task
        _tts_warmup_task = asyncio.create_task(_warmup_tts_backend())
        print("ℹ️  TTS preload/warmup scheduled")
    
    yield
    
    # Shutdown
    print("👋 Shutting down Interview Agent Server...")
    sessions.clear()


# ============== FastAPI Application ==============

fast_app = FastAPI(
    title="Interview Agent API",
    description="SOTA Interview Agent - LangGraph Backend with Multi-Modal Intelligence",
    version="0.2.0",
    lifespan=lifespan
)

# Add CORS middleware
fast_app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Socket.IO Server ==============

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.CORS_ORIGINS,
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=10_000_000,  # 10 MB — allow large audio payloads
)

# Wrap FastAPI with Socket.IO ASGI application
app = socketio.ASGIApp(sio, fast_app)


# ============== REST Endpoints ==============

@fast_app.get("/health")
async def health_check():
    """Health check endpoint with LangGraph sanity verification."""
    try:
        graph = build_sanity_check_graph()
        result = graph.invoke({"value": "health_check"})
        langgraph_ok = "processed by Node A" in result["value"]
    except Exception:
        langgraph_ok = False
    
    return {
        "status": "ready" if langgraph_ok else "degraded",
        "agent_engine": "langgraph",
        "mlx_gpu": mx.metal.is_available() if mx else False,
        "qdrant_status": check_qdrant_status()
    }


@fast_app.get("/")
async def root():
    """Root endpoint with basic API info."""
    return {
        "name": "Interview Agent API",
        "version": "0.2.0",
        "engine": "LangGraph",
        "features": ["STT", "TTS", "LLM Streaming"],
        "docs": "/docs"
    }


# ============== User Data API Endpoints ==============

@fast_app.get("/api/user/{user_id}/progress")
async def get_user_progress_api(
    user_id: str,
    auth_user_id: str = Depends(_get_authenticated_rest_user_id)
):
    """Get user's overall progress and statistics."""
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    user_db = get_user_db()
    progress = user_db.get_user_progress(user_id)
    user = user_db.get_user(user_id)
    
    return {
        "user": _safe_user_payload(user),
        "progress": progress
    }


@fast_app.get("/api/user/{user_id}/sessions")
async def get_user_sessions_api(
    user_id: str,
    limit: int = 10,
    auth_user_id: str = Depends(_get_authenticated_rest_user_id)
):
    """Get user's interview session history."""
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    user_db = get_user_db()
    sessions_list = user_db.get_session_history(user_id, limit)
    return {"sessions": sessions_list}


@fast_app.get("/api/session/{session_id}")
async def get_session_details_api(
    session_id: str,
    auth_user_id: str = Depends(_get_authenticated_rest_user_id)
):
    """Get full details of a specific interview session."""
    user_db = get_user_db()
    session_details = user_db.get_session_details(session_id)
    
    if not session_details:
        raise HTTPException(status_code=404, detail="Session not found")

    if session_details.get("user_id") != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    return session_details


@fast_app.get("/api/session/{session_id}/export")
async def export_session_pdf(
    session_id: str,
    auth_user_id: str = Depends(_get_authenticated_rest_user_id),
):
    """Export interview session as a downloadable PDF report using ReportLab."""
    import io
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether,
    )
    from reportlab.lib.colors import HexColor

    user_db = get_user_db()
    details = user_db.get_session_details(session_id)
    if not details:
        raise HTTPException(status_code=404, detail="Session not found")
    if details.get("user_id") != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    summary = details.get("summary") or {}
    answers = details.get("answers") or []
    job_title = details.get("job_title") or "Interview"
    avg_score = details.get("average_score") or summary.get("average_score", 0)
    started = (details.get("started_at") or "")[:19]
    total_q = details.get("total_questions")
    if total_q is None:
        total_q = len(answers)
    answered_q = details.get("answered_questions")
    if answered_q is None:
        answered_q = len(answers)

    dim_labels = {
        "relevance": "Relevance", "depth": "Depth", "structure": "Structure",
        "specificity": "Specificity", "communication": "Communication",
        "clarity": "Clarity", "accuracy": "Accuracy", "completeness": "Completeness",
    }

    # ── Colours ──
    BRAND   = HexColor("#6366F1")
    BRAND_L = HexColor("#EEF2FF")
    DARK    = HexColor("#1E293B")
    MUTED   = HexColor("#64748B")
    SUCCESS = HexColor("#22C55E")
    WARN    = HexColor("#EAB308")
    DANGER  = HexColor("#EF4444")
    BORDER  = HexColor("#E2E8F0")
    LIGHT   = HexColor("#F8FAFC")

    def _score_color(s):
        try:
            v = float(s)
        except (TypeError, ValueError):
            return MUTED
        if v >= 7: return SUCCESS
        if v >= 5: return WARN
        return DANGER

    def _esc(text):
        """Escape XML special chars for Paragraph markup."""
        if not text:
            return ""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ── Styles ──
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Title2", parent=styles["Title"], fontSize=20,
                              textColor=DARK, spaceAfter=4, leading=24))
    styles.add(ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=12,
                              textColor=BRAND, spaceAfter=12))
    styles.add(ParagraphStyle("SectionHead", parent=styles["Heading2"], fontSize=13,
                              textColor=DARK, spaceBefore=14, spaceAfter=6,
                              borderWidth=0))
    styles.add(ParagraphStyle("SubHead", parent=styles["Heading3"], fontSize=10,
                              textColor=DARK, spaceBefore=8, spaceAfter=4))
    styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=9,
                              textColor=DARK, leading=13, spaceAfter=4))
    styles.add(ParagraphStyle("BodyItalic", parent=styles["Body"], fontName="Helvetica-Oblique"))
    styles.add(ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9,
                              textColor=MUTED, leading=12))
    # Override the built-in 'Bullet' style (already exists in getSampleStyleSheet)
    _bullet = styles["Bullet"]
    _bullet.parent = styles["Body"]
    _bullet.leftIndent = 14
    _bullet.bulletIndent = 4
    _bullet.spaceBefore = 1
    _bullet.spaceAfter = 1
    styles.add(ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8,
                              textColor=MUTED, alignment=TA_CENTER, spaceBefore=20))
    styles.add(ParagraphStyle("QHeader", parent=styles["Normal"], fontSize=10,
                              fontName="Helvetica-Bold", textColor=DARK, leading=13))
    styles.add(ParagraphStyle("SmallMuted", parent=styles["Normal"], fontSize=8,
                              textColor=MUTED, leading=11))

    story = []

    # ── Title ──
    story.append(Paragraph("Interview Report", styles["Title2"]))
    story.append(Paragraph(_esc(job_title), styles["Subtitle"]))

    # ── Meta ──
    meta_lines = [
        f"<b>Date:</b> {_esc(started or 'N/A')}",
        f"<b>Questions:</b> {answered_q}/{total_q} answered",
        f"<b>Average Score:</b> {avg_score}/10",
    ]
    story.append(Paragraph("<br/>".join(meta_lines), styles["Meta"]))
    story.append(Spacer(1, 8))

    # ── Dimension Scores ──
    breakdown = summary.get("overall_breakdown") or summary.get("score_breakdown") or {}
    if breakdown:
        story.append(Paragraph("Dimension Scores", styles["SectionHead"]))
        story.append(HRFlowable(width="30%", thickness=2, color=BRAND, spaceAfter=6))

        table_data = [["Dimension", "Score"]]
        row_colors = []
        for dim, val in breakdown.items():
            label = dim_labels.get(dim, dim.title())
            table_data.append([label, f"{val}/10"])
            row_colors.append(_score_color(val))

        t = Table(table_data, colWidths=[140, 60])
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT, colors.white]),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for i, c in enumerate(row_colors):
            style_cmds.append(("TEXTCOLOR", (1, i + 1), (1, i + 1), c))
            style_cmds.append(("FONTNAME", (1, i + 1), (1, i + 1), "Helvetica-Bold"))
        t.setStyle(TableStyle(style_cmds))
        story.append(t)
        story.append(Spacer(1, 8))

    # ── Speech Analytics ──
    telemetry = summary.get("telemetry") or {}
    if telemetry:
        story.append(Paragraph("Speech Analytics", styles["SectionHead"]))
        story.append(HRFlowable(width="30%", thickness=2, color=BRAND, spaceAfter=6))
        sa_lines = [
            f"<b>Filler Words:</b> {telemetry.get('fillerWords', 0)}  ({telemetry.get('fillersPerMinute', 0)}/min)",
            f"<b>Hedge Words:</b> {telemetry.get('hedge_words', 0)}",
            f"<b>Confidence:</b> {_esc(str(telemetry.get('confidence', 'N/A')))}",
        ]
        star = telemetry.get("star_analysis") or {}
        if star:
            comps = ["Situation", "Task", "Action", "Result"]
            detected = [c for c in comps if star.get(c.lower())]
            sa_lines.append(
                f"<b>STAR Framework:</b> {star.get('score', 0)}/4"
                f" ({', '.join(detected) if detected else 'None detected'})"
            )
        story.append(Paragraph("<br/>".join(sa_lines), styles["Meta"]))
        story.append(Spacer(1, 8))

    # ── Overall Feedback ──
    overall_feedback = summary.get("overall_feedback")
    top_strengths = summary.get("top_strengths") or []
    improvements = summary.get("areas_to_improve") or []
    actions = summary.get("action_items") or []
    comm = summary.get("communication_feedback")

    if overall_feedback or top_strengths or improvements:
        story.append(Paragraph("Overall Feedback", styles["SectionHead"]))
        story.append(HRFlowable(width="30%", thickness=2, color=BRAND, spaceAfter=6))
        if overall_feedback:
            story.append(Paragraph(_esc(overall_feedback), styles["Body"]))
        if top_strengths:
            story.append(Paragraph("Strengths", styles["SubHead"]))
            for s in top_strengths:
                story.append(Paragraph(_esc(s), styles["Bullet"], bulletText="\u2022"))
        if improvements:
            story.append(Paragraph("Areas to Improve", styles["SubHead"]))
            for a in improvements:
                story.append(Paragraph(_esc(a), styles["Bullet"], bulletText="\u2022"))
        if actions:
            story.append(Paragraph("Action Items", styles["SubHead"]))
            for a in actions:
                story.append(Paragraph(_esc(a), styles["Bullet"], bulletText="\u2022"))
        if comm:
            story.append(Paragraph("Communication Feedback", styles["SubHead"]))
            story.append(Paragraph(_esc(comm), styles["Body"]))
        story.append(Spacer(1, 6))

    # ── Per-Question Breakdown ──
    if answers:
        story.append(Paragraph("Per-Question Breakdown", styles["SectionHead"]))
        story.append(HRFlowable(width="30%", thickness=2, color=BRAND, spaceAfter=8))

        for ans in answers:
            q_num = ans.get("question_number", "?")
            q_text = ans.get("question_text", "Question")
            evaluation = ans.get("evaluation") or {}
            score = evaluation.get("score", 0)
            skipped = ans.get("skipped", False)
            sc = _score_color(score)

            q_elements = []

            # Question header with score
            skip_tag = " <i>(Skipped)</i>" if skipped else ""
            score_html = f'<font color="{sc.hexval()}">{score}/10</font>'
            q_elements.append(Paragraph(
                f"Q{q_num}: {_esc(q_text)}  —  {score_html}{skip_tag}",
                styles["QHeader"],
            ))

            # Category + dimension breakdown
            cat = ans.get("category", "General")
            sb = evaluation.get("score_breakdown") or {}
            meta_parts = [f"Category: {_esc(cat)}"]
            if sb:
                dims_str = " | ".join(
                    f"{dim_labels.get(d, d.title())}: {v}" for d, v in sb.items()
                )
                meta_parts.append(dims_str)
            q_elements.append(Paragraph(" &nbsp;&nbsp; ".join(meta_parts), styles["SmallMuted"]))
            q_elements.append(Spacer(1, 4))

            # User answer
            user_answer = ans.get("user_answer") or ""
            if user_answer and user_answer != "(Skipped)":
                snippet = user_answer[:600] + ("..." if len(user_answer) > 600 else "")
                q_elements.append(Paragraph("Your Answer", styles["SubHead"]))
                q_elements.append(Paragraph(
                    f"<i>{_esc(snippet)}</i>", styles["Body"]
                ))

            # Assessment
            reasoning = evaluation.get("evaluation_reasoning") or evaluation.get("feedback") or ""
            if reasoning:
                q_elements.append(Paragraph("Assessment", styles["SubHead"]))
                q_elements.append(Paragraph(_esc(reasoning), styles["Body"]))

            # Strengths & gaps
            q_strengths = evaluation.get("strengths") or []
            gaps = (evaluation.get("gaps") or evaluation.get("rubric_misses")
                    or evaluation.get("missing_concepts") or [])
            if q_strengths:
                q_elements.append(Paragraph(
                    f'<font color="{SUCCESS.hexval()}"><b>Strengths:</b> {_esc(", ".join(q_strengths[:4]))}</font>',
                    styles["Body"],
                ))
            if gaps:
                q_elements.append(Paragraph(
                    f'<font color="{DANGER.hexval()}"><b>Gaps:</b> {_esc(", ".join(gaps[:4]))}</font>',
                    styles["Body"],
                ))

            # Coaching tip
            tip = evaluation.get("coaching_tip")
            if tip:
                q_elements.append(Paragraph(
                    f'<font color="{BRAND.hexval()}"><b>Tip:</b></font> {_esc(tip)}',
                    styles["Body"],
                ))

            # Model answer
            model = evaluation.get("model_answer") or evaluation.get("optimized_answer") or ""
            if model:
                q_elements.append(Paragraph("Model Answer", styles["SubHead"]))
                q_elements.append(Paragraph(
                    _esc(model[:800] + ("..." if len(model) > 800 else "")),
                    styles["BodyItalic"],
                ))

            q_elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER,
                                         spaceBefore=6, spaceAfter=8))

            # Keep question block together when possible
            story.append(KeepTogether(q_elements))

    # ── Footer ──
    story.append(Paragraph("Generated by HiveMind Prep", styles["Footer"]))

    # ── Build PDF to bytes ──
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"Interview Report - {job_title}",
        author="HiveMind Prep",
    )
    doc.build(story)
    pdf_bytes = buf.getvalue()

    safe_title = "".join(c for c in job_title if c.isalnum() or c in " -_")[:40].strip() or "interview"
    filename = f"HiveMindPrep_{safe_title}_{started[:10]}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@fast_app.get("/api/user/{user_id}/career_analyses")
async def get_career_analyses_api(
    user_id: str,
    limit: int = 5,
    auth_user_id: str = Depends(_get_authenticated_rest_user_id)
):
    """Get user's career analysis history."""
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    user_db = get_user_db()
    analyses = user_db.get_career_analyses(user_id, limit)
    return {"analyses": analyses}


# ============== Socket.IO Events ==============

@sio.event
async def connect(sid, environ, auth=None):
    """Handle client connection with origin validation."""
    print(f"🔌 Client connected: {sid}")

    # ── Origin validation (CSRF protection) ──
    # environ contains ASGI/WSGI headers; Origin comes as HTTP_ORIGIN
    origin = (environ.get("HTTP_ORIGIN", "") or "").strip()
    trusted_origins = set(settings.CORS_ORIGINS or [])
    local_dev_prefixes = (
        "http://localhost",
        "http://127.0.0.1",
        "https://localhost",
        "https://127.0.0.1",
    )
    is_local_dev_origin = origin.startswith(local_dev_prefixes)

    if origin and origin not in trusted_origins and not is_local_dev_origin:
        print(f"🛡️ Rejected connection from untrusted origin: {origin}")
        raise socketio.exceptions.ConnectionRefusedError("Origin not allowed")

    # Default unauthenticated identity gets a private room, never shared.
    user_id = f"anon_{sid}"
    is_authenticated = False
    session_token = None

    # Extract session_token from auth payload (sent via Socket.IO auth option,
    # NOT the URL query string — keeps tokens out of server/proxy access logs).
    try:
        if isinstance(auth, dict):
            session_token = auth.get("session_token")
        if session_token:
            token_user_id = get_user_db().validate_session_token(session_token)
            if token_user_id:
                user_id = token_user_id
                is_authenticated = True
                print(f"✅ Authenticated socket via session token: {user_id}")
    except Exception:
        pass

    sessions[sid] = SessionState(
        user_id=user_id,
        is_authenticated=is_authenticated,
        session_token=session_token if is_authenticated else None
    )
    await _bind_sid_identity(
        sid=sid,
        new_user_id=user_id,
        is_authenticated=is_authenticated,
        session_token=session_token if is_authenticated else None
    )

    session = sessions[sid]
    await sio.emit(
        "connected",
        {
            "sid": sid,
            "status": "ready",
            "user_id": _public_user_id(session),
            "authenticated": session.is_authenticated
        },
        room=str(session.user_id)
    )


@sio.event
async def disconnect(sid):
    """Handle client disconnection with task cancellation."""
    user_id = sid_to_user.pop(sid, None)
    print(f"🔌 Client disconnected: {sid} (user: {user_id})")
    
    if user_id:
        # Leave user room
        await sio.leave_room(sid, str(user_id))
        
        # Decrement connection count
        user_connection_count[user_id] = max(0, user_connection_count[user_id] - 1)
        remaining = user_connection_count[user_id]
        
        # Only cancel task if ALL connections for this user are gone
        if remaining == 0:
            _cancel_user_task_if_idle(user_id)
        else:
            print(f"📡 User {user_id} still has {remaining} connection(s) - task continues")
    
    if sid in sessions:
        del sessions[sid]


# ============== Authentication Events ==============

@sio.event
async def signup(sid, data):
    """Handle user signup."""
    data = data or {}
    email = data.get("email", "").strip().lower()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    if not email or not username or not password:
        await sio.emit("auth_error", {"error": "All fields are required", "user_id": "anonymous"}, room=sid)
        return
    
    user_db = get_user_db()
    
    # Check if user already exists
    existing = user_db.get_user_by_email(email)
    if existing:
        await sio.emit("auth_error", {"error": "Email already registered", "user_id": "anonymous"}, room=sid)
        return
    
    # Create new user
    try:
        user_id = user_db.create_user(email, username, password)
        session_token = user_db.create_session_token(user_id)
        user = user_db.get_user(user_id)
        await _bind_sid_identity(
            sid=sid,
            new_user_id=user_id,
            is_authenticated=True,
            session_token=session_token
        )
        
        await sio.emit("auth_success", {
            "user": {
                "user_id": user_id,
                "email": email,
                "username": username
            },
            "session_token": session_token,
            "user_id": user_id
        }, room=str(user_id))
        print(f"✅ New user signed up: {email}")
    except Exception as e:
        await sio.emit("auth_error", {"error": str(e), "user_id": "anonymous"}, room=sid)


@sio.event
async def login(sid, data):
    """Handle user login."""
    import hashlib

    data = data or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    
    if not email or not password:
        await sio.emit("auth_error", {"error": "Email and password are required", "user_id": "anonymous"}, room=sid)
        return
    
    user_db = get_user_db()
    user = user_db.get_user_by_email(email)
    
    if not user:
        await sio.emit("auth_error", {"error": "Invalid email or password", "user_id": "anonymous"}, room=sid)
        return
    
    # Verify password
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user.get("password_hash") and user["password_hash"] != password_hash:
        await sio.emit("auth_error", {"error": "Invalid email or password", "user_id": "anonymous"}, room=sid)
        return
    
    user_id = user["user_id"]
    session_token = user_db.create_session_token(user_id)
    await _bind_sid_identity(
        sid=sid,
        new_user_id=user_id,
        is_authenticated=True,
        session_token=session_token
    )
    
    user_db.update_last_login(user_id)
    
    # Get user preferences (to check onboarding status)
    prefs = user_db.get_user_preferences(user_id)
    
    await sio.emit("auth_success", {
        "user": {
            "user_id": user_id,
            "email": user["email"],
            "username": user["username"]
        },
        "session_token": session_token,
        "preferences": prefs or {},
        "user_id": user_id
    }, room=str(user_id))
    print(f"✅ User logged in: {email}")

    # Automatically load latest analysis
    try:
        recent = user_db.get_career_analyses(user_id, limit=1)
        if recent:
            saved_analysis = recent[0]
            analysis_data = _normalize_latest_analysis_payload(user_id, saved_analysis)
            mapped_analysis = {
                "job_title": saved_analysis.get("job_title"),
                "company": saved_analysis.get("company"),
                "readiness_score": saved_analysis.get("readiness_score"),
                "skill_gaps": saved_analysis.get("skill_gaps", []),
                "bridge_roles": saved_analysis.get("bridge_roles", []),
                "suggested_sessions": analysis_data.get("suggested_sessions", []),
                "practice_plan": analysis_data.get("practice_plan"),
                "analysis_data": analysis_data
            }
            await sio.emit("career_analysis", {"analysis": mapped_analysis, "user_id": user_id}, room=str(user_id))
    except Exception as e:
        print(f"⚠️ Failed to load analysis on login: {e}")


@sio.event
async def restore_session(sid, data):
    """
    Restore a session using a server-issued session token.
    """
    data = data or {}
    session_token = data.get("session_token")
    if not session_token:
        await sio.emit("auth_error", {"error": "Session token required", "user_id": "anonymous"}, room=sid)
        return
    
    user_db = get_user_db()
    user_id = user_db.validate_session_token(session_token)
    if not user_id:
        await sio.emit("auth_error", {"error": "Invalid or expired session token", "user_id": "anonymous"}, room=sid)
        return

    user = user_db.get_user(user_id)
    
    if not user:
        await sio.emit("auth_error", {"error": "Session user not found", "user_id": "anonymous"}, room=sid)
        return
    
    await _bind_sid_identity(
        sid=sid,
        new_user_id=user_id,
        is_authenticated=True,
        session_token=session_token
    )
        
    print(f"🔄 Restored session for user: {user_id}")
    
    # Send ack with preferences to ensure client is in sync
    prefs = user_db.get_user_preferences(user_id)
    await sio.emit("session_restored", {
        "user": _safe_user_payload(user),
        "session_token": session_token,
        "preferences": prefs or {},
        "user_id": user_id
    }, room=str(user_id))

    # Automatically load latest analysis
    try:
        recent = user_db.get_career_analyses(user_id, limit=1)
        if recent:
            saved_analysis = recent[0]
            analysis_data = _normalize_latest_analysis_payload(user_id, saved_analysis)
            mapped_analysis = {
                "job_title": saved_analysis.get("job_title"),
                "company": saved_analysis.get("company"),
                "readiness_score": saved_analysis.get("readiness_score"),
                "skill_gaps": saved_analysis.get("skill_gaps", []),
                "bridge_roles": saved_analysis.get("bridge_roles", []),
                "suggested_sessions": analysis_data.get("suggested_sessions", []),
                "practice_plan": analysis_data.get("practice_plan"),
                "analysis_data": analysis_data
            }
            await sio.emit("career_analysis", {"analysis": mapped_analysis, "user_id": user_id}, room=str(user_id))
    except Exception as e:
        print(f"⚠️ Failed to load analysis on restore: {e}")


@sio.event
async def logout(sid, data=None):
    """Revoke auth token and drop socket back to anonymous identity."""
    data = data or {}
    session = sessions.get(sid)
    token = (
        data.get("session_token")
        or (session.session_token if session else None)
    )

    try:
        if token:
            get_user_db().revoke_session_token(token)
    except Exception as e:
        print(f"⚠️ Token revoke failed on logout: {e}")

    if session:
        await _bind_sid_identity(
            sid=sid,
            new_user_id=f"anon_{sid}",
            is_authenticated=False,
            session_token=None
        )

    await sio.emit("logged_out", {"success": True, "user_id": "anonymous"}, room=sid)


# ============== User Identification Helper ==============

def _get_uid(sid, data=None):
    """Get user_id from current socket session only."""
    session = sessions.get(sid)
    return session.user_id if session else "anonymous"


def _normalize_feedback_thresholds(overrides):
    """Normalize per-user strictness overrides against server defaults."""
    try:
        from server.agents.interview_nodes import resolve_feedback_thresholds
        return resolve_feedback_thresholds(overrides if isinstance(overrides, dict) else {})
    except Exception:
        return {}


def _normalize_recording_thresholds(overrides):
    """Normalize per-user recording/silence settings."""
    defaults = {
        "silence_auto_stop_seconds": 5.0,
        "silence_rms_threshold": 0.008,
    }
    src = overrides if isinstance(overrides, dict) else {}
    normalized = dict(defaults)
    try:
        if "silence_auto_stop_seconds" in src:
            normalized["silence_auto_stop_seconds"] = float(src.get("silence_auto_stop_seconds"))
    except Exception:
        pass
    try:
        if "silence_rms_threshold" in src:
            normalized["silence_rms_threshold"] = float(src.get("silence_rms_threshold"))
    except Exception:
        pass

    normalized["silence_auto_stop_seconds"] = max(1.0, min(20.0, normalized["silence_auto_stop_seconds"]))
    normalized["silence_rms_threshold"] = max(0.001, min(0.05, normalized["silence_rms_threshold"]))
    return normalized


ALLOWED_PIPER_STYLES = {"interviewer", "balanced", "fast"}
ALLOWED_TTS_PROVIDERS = {"piper", "qwen3_tts_mlx"}


def _normalize_piper_style(style_value, fallback: str = "interviewer") -> str:
    """Normalize piper style to a supported preset."""
    normalized_fallback = str(fallback or "interviewer").strip().lower()
    if normalized_fallback not in ALLOWED_PIPER_STYLES:
        normalized_fallback = "interviewer"
    normalized_value = str(style_value or "").strip().lower()
    if normalized_value in ALLOWED_PIPER_STYLES:
        return normalized_value
    return normalized_fallback


def _normalize_tts_provider(provider_value, fallback: str = "piper") -> str:
    """Normalize TTS provider to supported engines."""
    normalized_fallback = str(fallback or "piper").strip().lower()
    if normalized_fallback not in ALLOWED_TTS_PROVIDERS:
        normalized_fallback = "piper"
    normalized_value = str(provider_value or "").strip().lower()
    if normalized_value in ALLOWED_TTS_PROVIDERS:
        return normalized_value
    return normalized_fallback


def _first_present(data: dict, keys: tuple[str, ...], default=None):
    """Return the first non-None value for the provided keys."""
    if not isinstance(data, dict):
        return default
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return default


def _get_user_feedback_thresholds(user_id: str) -> dict:
    """Load normalized strictness thresholds for a user."""
    try:
        prefs = get_user_db().get_user_preferences(user_id) or {}
        return _normalize_feedback_thresholds(prefs.get("evaluation_thresholds") or {})
    except Exception:
        return _normalize_feedback_thresholds({})


# ============== User Preferences & History Events ==============

@sio.event
async def save_preferences(sid, data):
    """Save user preferences (resume, target role, focus areas)."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    data = data or {}
    user_id = _get_uid(sid, data)
    user_db = get_user_db()

    existing = user_db.get_user_preferences(user_id) or {}
    question_override = data.get("question_count_override", existing.get("question_count_override"))
    if question_override in ("", None):
        question_override = None
    else:
        try:
            question_override = int(question_override)
        except Exception:
            question_override = existing.get("question_count_override")
    incoming_thresholds = data.get("evaluation_thresholds", existing.get("evaluation_thresholds", {}))
    normalized_thresholds = _normalize_feedback_thresholds(incoming_thresholds)
    incoming_recording_thresholds = data.get("recording_thresholds", existing.get("recording_thresholds", {}))
    normalized_recording_thresholds = _normalize_recording_thresholds(incoming_recording_thresholds)
    incoming_persona = str(data.get("interviewer_persona", existing.get("interviewer_persona", "friendly")) or "friendly").strip().lower()
    if incoming_persona not in {"friendly", "strict"}:
        incoming_persona = str(existing.get("interviewer_persona") or "friendly").strip().lower() or "friendly"
    incoming_piper_style = _normalize_piper_style(
        data.get("piper_style", existing.get("piper_style", "interviewer")),
        fallback=existing.get("piper_style", "interviewer"),
    )
    incoming_tts_provider = _normalize_tts_provider(
        data.get("tts_provider", existing.get("tts_provider", "piper")),
        fallback=existing.get("tts_provider", "piper"),
    )
    incoming_target_role = _first_present(
        data,
        ("target_role", "job_title", "targetRole", "jobTitle"),
        existing.get("target_role"),
    )
    incoming_target_company = _first_present(
        data,
        ("target_company", "company", "targetCompany"),
        existing.get("target_company"),
    )
    incoming_job_description = _first_present(
        data,
        ("job_description", "jobDescription"),
        existing.get("job_description"),
    )
    incoming_job_description = str(incoming_job_description or "").strip()
    # Guard against accidental blank-overwrite from partial preference payloads.
    if not incoming_job_description and str(existing.get("job_description") or "").strip():
        incoming_job_description = str(existing.get("job_description") or "")
    
    preferences = {
        "resume_text": data.get("resume_text", existing.get("resume_text")),
        "resume_filename": data.get("resume_filename", existing.get("resume_filename")),
        "target_role": incoming_target_role,
        "target_company": incoming_target_company,
        "job_description": incoming_job_description,
        "question_count_override": question_override,
        "interviewer_persona": incoming_persona,
        "piper_style": incoming_piper_style,
        "tts_provider": incoming_tts_provider,
        "evaluation_thresholds": normalized_thresholds,
        "recording_thresholds": normalized_recording_thresholds,
        "focus_areas": data.get("focus_areas", existing.get("focus_areas", [])),
        "onboarding_complete": data.get("onboarding_complete", existing.get("onboarding_complete", False)),
        "mic_permission_granted": data.get("mic_permission_granted", existing.get("mic_permission_granted", False))
    }
    
    user_db.save_user_preferences(user_id, preferences)
    await sio.emit("preferences_saved", {"success": True, "user_id": user_id}, room=str(user_id))
    print(f"✅ Saved preferences for {user_id}")


@sio.event
async def start_career_analysis(sid, data=None):
    """
    Start the full career analysis process.
    Can use saved preferences OR accept new resume/job_title in data.
    Implements Resource Guard pattern for cancellation.
    """
    session = await _require_socket_auth(sid)
    if not session:
        return

    data = data or {}
    user_id = _get_uid(sid, data)
    force_refresh = bool(data.get("force_refresh", False))
    print(f"🚀 Starting career analysis for {user_id}")
    if force_refresh:
        print(f"🔁 Force refresh enabled for {user_id}")

    # Resource Guard: Cancel any existing task for this user
    existing_task = active_tasks.get(user_id)
    if existing_task and not existing_task.done():
        existing_task.cancel()
        print(f"🛑 Cancelled previous task for {user_id} (double-click prevention)")

    user_db = get_user_db()
    existing_prefs = user_db.get_user_preferences(user_id) or {}
    incoming_resume = _first_present(data, ("resume", "resume_base64", "resumeBase64"), "")
    incoming_job_title = _first_present(
        data,
        ("job_title", "target_role", "jobTitle", "targetRole"),
        existing_prefs.get("target_role"),
    )
    incoming_company = _first_present(
        data,
        ("company", "target_company", "targetCompany"),
        existing_prefs.get("target_company", "Tech Company"),
    )
    incoming_job_description = _first_present(
        data,
        ("job_description", "jobDescription"),
        existing_prefs.get("job_description", ""),
    )
    incoming_job_description = str(incoming_job_description or "").strip()
    if not incoming_job_description and str(existing_prefs.get("job_description") or "").strip():
        incoming_job_description = str(existing_prefs.get("job_description") or "")
    print(
        "🧾 Career analysis request context: "
        f"job_title='{incoming_job_title}', company='{incoming_company}', "
        f"jd_len={len(incoming_job_description)}"
    )
    if force_refresh:
        try:
            from server.services.cache import get_question_cache
            get_question_cache().delete_user_keys(user_id)
        except Exception as e:
            print(f"⚠️ Failed to clear cache for force refresh: {e}")

    # Check if new resume/role provided in request
    if data and incoming_resume and incoming_job_title:
        print(f"📝 New resume provided, saving preferences first...")

        # Extract resume text from base64 PDF
        resume_text = ""
        try:
            from server.tools.resume_tool import extract_text_from_pdf_bytes
            import base64
            pdf_bytes = base64.b64decode(str(incoming_resume).split(",")[-1])
            resume_text = extract_text_from_pdf_bytes(pdf_bytes)
        except Exception as e:
            print(f"❌ Resume extraction failed: {e}")
            await sio.emit("analysis_error", {"error": f"Failed to extract resume text: {e}", "user_id": user_id}, room=str(user_id))
            return

        # Save new preferences
        preferences = {
            "resume_text": resume_text,
            "resume_filename": f"resume_{user_id}.pdf",
            "target_role": incoming_job_title,
            "target_company": incoming_company,
            "job_description": incoming_job_description,
            "question_count_override": existing_prefs.get("question_count_override"),
            "interviewer_persona": existing_prefs.get("interviewer_persona", "friendly"),
            "piper_style": existing_prefs.get("piper_style", "interviewer"),
            "tts_provider": existing_prefs.get("tts_provider", "piper"),
            "evaluation_thresholds": existing_prefs.get("evaluation_thresholds", {}),
            "recording_thresholds": existing_prefs.get("recording_thresholds", {}),
            "focus_areas": []
        }
        user_db.save_user_preferences(user_id, preferences)
        print(f"✅ Saved new preferences for {user_id}")
    elif data and any(k in data for k in ("job_title", "company", "job_description", "target_role", "target_company", "jobDescription", "jobTitle", "targetRole", "targetCompany")):
        # Persist latest targets/JD even when resume is reused from existing prefs.
        preferences = {
            "resume_text": existing_prefs.get("resume_text"),
            "resume_filename": existing_prefs.get("resume_filename"),
            "target_role": incoming_job_title,
            "target_company": incoming_company,
            "job_description": incoming_job_description,
            "question_count_override": existing_prefs.get("question_count_override"),
            "interviewer_persona": existing_prefs.get("interviewer_persona", "friendly"),
            "piper_style": existing_prefs.get("piper_style", "interviewer"),
            "tts_provider": existing_prefs.get("tts_provider", "piper"),
            "evaluation_thresholds": existing_prefs.get("evaluation_thresholds", {}),
            "recording_thresholds": existing_prefs.get("recording_thresholds", {}),
            "focus_areas": existing_prefs.get("focus_areas", []),
            "onboarding_complete": existing_prefs.get("onboarding_complete", False),
            "mic_permission_granted": existing_prefs.get("mic_permission_granted", False),
        }
        user_db.save_user_preferences(user_id, preferences)

    # Load preferences (either just saved or existing)
    prefs = user_db.get_user_preferences(user_id)
    print(
        "📌 Loaded preferences for analysis: "
        f"target_role='{prefs.get('target_role') if prefs else ''}', "
        f"jd_len={len(str((prefs or {}).get('job_description') or ''))}"
    )

    if not prefs or not prefs.get("resume_text") or not prefs.get("target_role"):
        print(f"❌ Analysis failed: Missing prefs for {user_id}. Prefs: {prefs}")
        await sio.emit("analysis_error", {"error": "Missing resume or target role. Please complete onboarding first.", "user_id": user_id}, room=str(user_id))
        return

    if not str(prefs.get("job_description", "")).strip():
        await sio.emit("analysis_error", {"error": "Job description is required before running analysis.", "user_id": user_id}, room=str(user_id))
        return

    # Helper to emit progress events
    async def emit_progress(event_type: str, message: str):
        await sio.emit("analysis_progress", {
            "stage": event_type, 
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id
        }, room=str(user_id))

    # Create cancellable task
    async def run_analysis():
        try:
            from server.agents.nodes import analyze_career_path, normalize_practice_plan_titles
            import json

            # Run analysis
            result = await analyze_career_path(
                resume_text=prefs["resume_text"],
                target_role=prefs["target_role"],
                target_company=prefs.get("target_company", "Tech Company"),
                job_description=prefs.get("job_description", ""),
                emit_progress=emit_progress
            )

            if result.get("error"):
                await sio.emit("analysis_error", {"error": result["error"], "user_id": user_id}, room=str(user_id))
                return

            # Persist JD context in analysis payload for portability/history rendering.
            result["job_description"] = prefs.get("job_description", "")
            if isinstance(result.get("practice_plan"), dict):
                result["practice_plan"] = normalize_practice_plan_titles(result["practice_plan"])

            # Validate JSON-serializability before saving
            try:
                json.dumps(result)
            except (TypeError, ValueError) as e:
                print(f"⚠️ Result contains non-serializable data: {e}")
                result = json.loads(json.dumps(result, default=str))

            # Save to DB
            user_db.save_career_analysis(
                user_id,
                prefs["target_role"],
                prefs.get("target_company", "Tech Company"),
                result,
                job_description=prefs.get("job_description", "")
            )
            
            # Emit final result with safe JSON serialization
            try:
                safe_result = {
                    "job_title": prefs["target_role"],
                    "company": prefs.get("target_company"),
                    "readiness_score": result.get("readiness_score"),
                    "skill_gaps": result.get("skill_gaps"),
                    "bridge_roles": result.get("bridge_roles"),
                    "suggested_sessions": result.get("suggested_sessions", []),
                    "practice_plan": result.get("practice_plan"),  # New LLM-generated interview loop
                    "analysis_data": result
                }

                json.dumps(safe_result)

                await sio.emit("career_analysis", {"analysis": safe_result, "user_id": user_id}, room=str(user_id))
                print(f"✅ Career analysis completed for {user_id}")
                
                # Trigger background question generation for suggestions
                from server.agents.nodes import trigger_background_generation
                trigger_background_generation(user_id, result, force_refresh=force_refresh)

            except (TypeError, ValueError) as json_err:
                print(f"⚠️ JSON serialization error in career_analysis result: {json_err}")

                safe_fallback = {
                    "job_title": prefs["target_role"],
                    "company": prefs.get("target_company"),
                    "readiness_score": result.get("readiness_score", 0.5),
                    "skill_gaps": result.get("skill_gaps", []),
                    "bridge_roles": result.get("bridge_roles", []),
                    "analysis_data": {
                        "mindmap": "[Mindmap rendering error - see console]"
                    },
                    "suggested_sessions": result.get("suggested_sessions", [])
                }
                await sio.emit("career_analysis", {"analysis": safe_fallback, "user_id": user_id}, room=str(user_id))
                print(f"⚠️ Career analysis completed with fallback for {user_id}")
            
        except asyncio.CancelledError:
            print(f"🛑 Analysis task cancelled for {user_id}")
            # Don't emit error - user disconnected or restarted
            raise
        except Exception as e:
            print(f"❌ Analysis failed: {e}")
            import traceback
            traceback.print_exc()
            await sio.emit("analysis_error", {"error": str(e), "user_id": user_id}, room=str(user_id))
        finally:
            # Cleanup: Remove task only if it's still ours
            if active_tasks.get(user_id) is asyncio.current_task():
                active_tasks.pop(user_id, None)

    # Start and register the task
    task = asyncio.create_task(run_analysis())
    active_tasks[user_id] = task


@sio.event
async def get_preferences(sid, data=None):
    """Get user preferences."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    preferences = user_db.get_user_preferences(user_id)
    
    await sio.emit("user_preferences", {
        "preferences": preferences or {},
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def get_interview_history(sid, data=None):
    """Get user's interview session history."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    limit = (data or {}).get("limit", 20)

    user_db = get_user_db()
    # Use get_session_history which is the correct method name
    history = user_db.get_session_history(user_id, limit)

    await sio.emit("interview_history", {
        "history": history,
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def get_session_details(sid, data=None):
    """Get full details of a specific interview session including all answers."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    session_id = (data or {}).get("session_id")

    if not session_id:
        await sio.emit("session_details_error", {
            "error": "session_id required",
            "user_id": user_id
        }, room=str(user_id))
        return

    user_db = get_user_db()
    details = user_db.get_session_details(session_id)

    if not details:
        await sio.emit("session_details_error", {
            "error": "Session not found",
            "user_id": user_id
        }, room=str(user_id))
        return

    # Security: ensure the session belongs to this user
    if details.get("user_id") != user_id:
        await sio.emit("session_details_error", {
            "error": "Access denied",
            "user_id": user_id
        }, room=str(user_id))
        return

    await sio.emit("session_details", {
        "session": details,
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def get_retry_attempts(sid, data=None):
    """Get retry attempts for a specific question in a completed session."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    payload = data or {}
    user_id = _get_uid(sid, payload)
    session_id = str(payload.get("session_id") or "").strip()
    question_number = payload.get("question_number")

    try:
        question_number = int(question_number)
    except Exception:
        question_number = None

    if not session_id or not question_number or question_number < 1:
        await sio.emit("retry_error", {
            "error": "session_id and valid question_number are required",
            "session_id": session_id or None,
            "question_number": question_number,
            "user_id": user_id
        }, room=str(user_id))
        return

    user_db = get_user_db()
    owner_id = user_db.get_session_owner(session_id)
    if owner_id != user_id:
        await sio.emit("retry_error", {
            "error": "Access denied",
            "session_id": session_id,
            "question_number": question_number,
            "user_id": user_id
        }, room=str(user_id))
        return

    attempts = user_db.get_retry_attempts(session_id, question_number)
    await sio.emit("retry_attempts", {
        "session_id": session_id,
        "question_number": question_number,
        "attempts": attempts,
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def submit_retry_answer(sid, data=None):
    """Evaluate and save a report-stage retry attempt for one question."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    payload = data or {}
    user_id = _get_uid(sid, payload)
    session_id = str(payload.get("session_id") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    input_mode = str(payload.get("input_mode") or "text").strip().lower() or "text"
    duration_seconds = payload.get("duration_seconds", 0)
    question_number = payload.get("question_number")

    try:
        question_number = int(question_number)
    except Exception:
        question_number = None

    try:
        duration_seconds = float(duration_seconds or 0)
    except Exception:
        duration_seconds = 0.0

    if not session_id or not question_number or question_number < 1 or not answer:
        await sio.emit("retry_error", {
            "error": "session_id, question_number, and answer are required",
            "session_id": session_id or None,
            "question_number": question_number,
            "user_id": user_id
        }, room=str(user_id))
        return

    user_db = get_user_db()
    owner_id = user_db.get_session_owner(session_id)
    if owner_id != user_id:
        await sio.emit("retry_error", {
            "error": "Access denied",
            "session_id": session_id,
            "question_number": question_number,
            "user_id": user_id
        }, room=str(user_id))
        return

    original = user_db.get_answer_record(session_id, question_number)
    if not original:
        await sio.emit("retry_error", {
            "error": "Original answer record not found",
            "session_id": session_id,
            "question_number": question_number,
            "user_id": user_id
        }, room=str(user_id))
        return

    # Preserve immutable baseline record for report history on first retry.
    user_db.ensure_original_retry_snapshot(session_id, question_number)

    original_eval = original.get("evaluation") or {}
    expected_points = original_eval.get("expected_points_used") or []
    if not isinstance(expected_points, list) or not expected_points:
        expected_points = (
            (original_eval.get("strengths") or []) + (original_eval.get("gaps") or original_eval.get("rubric_misses") or [])
        )[:5]
    if not expected_points:
        expected_points = [
            "Directly answer the question",
            "Explain decision process and trade-offs",
            "Provide concrete outcome or impact",
        ]

    question_payload = {
        "text": original.get("question_text", "Question"),
        "category": original.get("question_category", "General"),
        "difficulty": original.get("question_difficulty", "medium"),
        "skill_tested": original.get("question_category", "General"),
        "expected_points": expected_points,
    }

    from server.agents.interview_nodes import evaluate_answer_stream
    user_thresholds = _get_user_feedback_thresholds(user_id)

    async def retry_callback(msg_type, content):
        if msg_type == "status":
            await sio.emit("status", {"stage": f"retry_{content}", "user_id": user_id}, room=str(user_id))

    await sio.emit("status", {"stage": "retry_evaluating", "user_id": user_id}, room=str(user_id))
    evaluation = await evaluate_answer_stream(question_payload, answer, retry_callback, thresholds=user_thresholds)
    _record_evaluation_metrics(evaluation)

    baseline_score = float((original_eval or {}).get("score") or 0)
    attempt = user_db.save_retry_attempt(
        session_id=session_id,
        question_number=question_number,
        answer_text=answer,
        input_mode=input_mode,
        duration_seconds=duration_seconds,
        evaluation=evaluation,
        baseline_score=baseline_score
    )
    promotion = user_db.promote_retry_if_higher(session_id, question_number, attempt)
    _record_retry_metrics(attempt.get("delta_score", 0))

    await sio.emit("retry_evaluated", {
        "session_id": session_id,
        "question_number": question_number,
        "attempt": attempt,
        "evaluation": evaluation,
        "delta": {
            "score": attempt.get("delta_score", 0),
            "baseline_score": attempt.get("baseline_score", baseline_score),
            "new_score": (evaluation or {}).get("score", 0),
        },
        "promoted_to_primary": bool((promotion or {}).get("promoted")),
        "primary_score": (promotion or {}).get("primary_score"),
        "previous_score": (promotion or {}).get("previous_score"),
        "session_average_score": (promotion or {}).get("session_average_score"),
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def get_user_stats(sid, data=None):
    """Get user progress statistics."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    stats = user_db.get_user_stats(user_id)
    
    await sio.emit("user_stats", {
        "stats": stats,
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def get_action_queue(sid, data=None):
    """Get persisted dashboard action queue."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    queue = user_db.get_action_queue(user_id)

    await sio.emit("action_queue", {
        "actions": queue,
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def reset_analysis_workspace(sid, data=None):
    """Reset analysis workspace artifacts and clear resume/JD inputs."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    user_db.reset_analysis_workspace(user_id)
    try:
        from server.services.cache import get_question_cache
        get_question_cache().delete_user_keys(user_id)
    except Exception as e:
        print(f"⚠️ Failed to clear in-memory cache on workspace reset: {e}")

    await sio.emit("career_analysis", {"analysis": None, "user_id": user_id}, room=str(user_id))
    await sio.emit("action_queue", {"actions": [], "user_id": user_id}, room=str(user_id))
    prefs = user_db.get_user_preferences(user_id) or {}
    await sio.emit("user_preferences", {"preferences": prefs, "user_id": user_id}, room=str(user_id))
    await sio.emit("workspace_reset", {"success": True, "user_id": user_id}, room=str(user_id))


@sio.event
async def clear_configuration(sid, data=None):
    """Clear saved configuration fields (resume/role/company/JD/default persona/count)."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    user_db.clear_user_configuration(user_id)
    try:
        from server.services.cache import get_question_cache
        get_question_cache().delete_user_keys(user_id)
    except Exception as e:
        print(f"⚠️ Failed to clear question cache on configuration clear: {e}")

    await sio.emit("career_analysis", {"analysis": None, "user_id": user_id}, room=str(user_id))
    await sio.emit("action_queue", {"actions": [], "user_id": user_id}, room=str(user_id))
    prefs = user_db.get_user_preferences(user_id) or {}
    await sio.emit("user_preferences", {"preferences": prefs, "user_id": user_id}, room=str(user_id))
    await sio.emit("configuration_cleared", {"success": True, "user_id": user_id}, room=str(user_id))


@sio.event
async def delete_interview_history(sid, data=None):
    """Delete all interview history (sessions + answers + retries) for the authenticated user."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    user_db.delete_interview_history(user_id)

    await sio.emit("interview_history", {"history": [], "user_id": user_id}, room=str(user_id))
    await sio.emit("history_deleted", {"success": True, "user_id": user_id}, room=str(user_id))


@sio.event
async def delete_interview_session(sid, data=None):
    """Delete a single interview session for the authenticated user."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    session_id = str((data or {}).get("session_id") or "").strip()
    if not session_id:
        await sio.emit("session_delete_error", {
            "error": "session_id required",
            "user_id": user_id,
        }, room=str(user_id))
        return

    user_db = get_user_db()
    deleted = user_db.delete_interview_session(user_id, session_id)
    if not deleted:
        await sio.emit("session_delete_error", {
            "error": "Session not found",
            "session_id": session_id,
            "user_id": user_id,
        }, room=str(user_id))
        return

    history = user_db.get_session_history(user_id, 30)
    await sio.emit("interview_history", {"history": history, "user_id": user_id}, room=str(user_id))
    await sio.emit("session_deleted", {
        "success": True,
        "session_id": session_id,
        "user_id": user_id,
    }, room=str(user_id))


@sio.event
async def reset_all_data(sid, data=None):
    """Full reset: clear interview history, configuration, and analysis workspace artifacts."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    user_db.reset_all_user_data(user_id)
    try:
        from server.services.cache import get_question_cache
        get_question_cache().delete_user_keys(user_id)
    except Exception as e:
        print(f"⚠️ Failed to clear cache on full reset: {e}")

    await sio.emit("career_analysis", {"analysis": None, "user_id": user_id}, room=str(user_id))
    await sio.emit("interview_history", {"history": [], "user_id": user_id}, room=str(user_id))
    await sio.emit("action_queue", {"actions": [], "user_id": user_id}, room=str(user_id))
    prefs = user_db.get_user_preferences(user_id) or {}
    await sio.emit("user_preferences", {"preferences": prefs, "user_id": user_id}, room=str(user_id))
    await sio.emit("all_data_reset", {"success": True, "user_id": user_id}, room=str(user_id))


@sio.event
async def save_action_queue(sid, data=None):
    """Persist dashboard action queue updates."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    payload = data or {}
    actions = payload.get("actions", [])
    if not isinstance(actions, list):
        actions = []

    user_id = _get_uid(sid, payload)
    user_db = get_user_db()
    user_db.save_action_queue(user_id, actions)

    await sio.emit("action_queue", {
        "actions": actions,
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def get_latest_analysis(sid, data=None):
    """Get the most recent career analysis for the user."""
    session = await _require_socket_auth(sid)
    if not session:
        return

    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    # reuse get_career_analyses but limit 1
    recent = user_db.get_career_analyses(user_id, limit=1)
    
    if recent:
        # Transform DB format to Frontend format
        saved_analysis = recent[0]
        analysis_data = _normalize_latest_analysis_payload(user_id, saved_analysis)
        mapped_analysis = {
            "job_title": saved_analysis.get("job_title"),
            "company": saved_analysis.get("company"),
            "job_description": saved_analysis.get("job_description") or analysis_data.get("job_description", ""),
            "readiness_score": saved_analysis.get("readiness_score"),
            "skill_gaps": saved_analysis.get("skill_gaps", []),
            "bridge_roles": saved_analysis.get("bridge_roles", []),
            "suggested_sessions": saved_analysis.get("suggested_sessions", []) or analysis_data.get("suggested_sessions", []),
            "practice_plan": analysis_data.get("practice_plan"),
            "analysis_data": analysis_data
        }
        
        await sio.emit("career_analysis", {"analysis": mapped_analysis, "user_id": user_id}, room=str(user_id))
        
        # NOTE: Background generation removed from here - only trigger after NEW analysis completes
    else:
        await sio.emit("career_analysis", {"analysis": None, "user_id": user_id}, room=str(user_id))


@sio.event
async def regenerate_suggestions(sid, data):
    """
    Regenerate suggested sessions based on user prompt.
    """
    session = await _require_socket_auth(sid)
    if not session:
        return

    data = data or {}
    user_id = _get_uid(sid, data)
    user_prompt = data.get("prompt", "")
    current_analysis_id = data.get("analysis_id") # Optional/Future use
    
    if not user_prompt:
        return
        
    print(f"🔄 Regenerating suggestions for {user_id}: '{user_prompt}'")
    await sio.emit("status", {"stage": "regenerating_suggestions", "user_id": user_id}, room=str(user_id))
    
    user_db = get_user_db()
    recent = user_db.get_career_analyses(user_id, limit=1)
    
    if not recent:
        await sio.emit("error", {"message": "No analysis found", "user_id": user_id}, room=str(user_id))
        return
        
    latest = recent[0]
    
    # Reconstruct state
    # We need the extensive analysis data to do a good job
    full_analysis = latest.get("analysis", {})
    
    # Needs: resume_data, job_requirements, skill_mapping
    # These are in 'analysis_data' but usually inside 'analysis' dict in DB
    # Let's hope full_analysis has them.
    # In nodes.py we return state which has them.
    # save_career_analysis saves the whole state into analysis_data.
    
    state = {
        "resume_data": full_analysis.get("resume_data", {}),
        "job_requirements": full_analysis.get("job_requirements", {}),
        "skill_mapping": full_analysis.get("skill_mapping", {}),
        "readiness_score": latest.get("readiness_score", 0.5),
        "suggested_sessions": latest.get("suggested_sessions", []),
        "job_description": latest.get("job_description", "")
    }
    
    try:
        from server.agents.nodes import regenerate_suggestions, trigger_background_generation
        
        new_suggestions = await regenerate_suggestions(state, user_prompt)
        
        # Update state and save? 
        # We need to update the DB entry or create a new ONE?
        # Ideally update the latest one.
        # But 'career_analyses' is append-only usually.
        # We can just emit them for now, but persistence requires update.
        # We didn't add an UPDATE method to DB.
        # Let's just create a NEW analysis entry to keep history?
        # Or just emit and rely on frontend state until next refresh?
        # The prompt says "Persistent".
        # I'll create a new analysis entry with the same data but new suggestions.
        # It preserves history of "I changed my mind".
        
        new_state = {**state, "suggested_sessions": new_suggestions}
        
        user_db.save_career_analysis(
            user_id,
            latest["job_title"],
            latest["company"],
            new_state,
            job_description=latest.get("job_description", "")
        )
        
        # Emit new suggestions
        await sio.emit("suggestions_updated", {
            "suggestions": new_suggestions,
            "user_id": user_id
        }, room=str(user_id))
        
        # Trigger background gen
        trigger_background_generation(user_id, new_state)
        
    except Exception as e:
        print(f"❌ Error regenerating: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit("error", {"message": "Failed to regenerate suggestions", "user_id": user_id}, room=str(user_id))



@sio.event
async def user_audio_chunk(sid, data):
    """
    Handle incoming audio chunks with low-latency partial STT and utterance finalization.
    """
    session = sessions.get(sid)
    if session is None:
        return
    if not session.accept_audio_chunks:
        return
    
    try:
        # Decode audio data
        audio_bytes = base64.b64decode(data.get("audio", ""))
        sample_rate = data.get("sample_rate", 16000)
        
        # Resample if needed
        if sample_rate != 16000:
            audio_bytes = get_audio_processor().resample_pcm(audio_bytes, sample_rate, 16000)
        
        # Append to circular buffer
        trimmed = session.append_audio(audio_bytes)
        if trimmed > 0:
            import time as _time
            _now = _time.time()
            _last = getattr(session, '_last_trim_log', 0)
            if _now - _last > 5.0:
                session._last_trim_log = _now
                print(f"📦 Buffer trimmed {trimmed} bytes (circular) — buffer full at {session.MAX_BUFFER_SIZE} bytes")

    except Exception as e:
        print(f"❌ Error decoding audio chunk: {e}")
        return

    if session.is_processing:
        return  # Audio is saved, skip processing
    
    try:
        import time
        current_time = time.time()
        audio_processor = get_audio_processor()
        streaming_audio_processor = get_streaming_audio_processor()
        
        # Check volume of recent audio
        recent_chunk = bytes(session.audio_buffer[-len(audio_bytes):]) if len(audio_bytes) > 0 else b''
        rms = audio_processor.calculate_rms(recent_chunk) if recent_chunk else 0
        is_speaking = rms > 0.012  # Noise gate

        if is_speaking and not session.was_speaking:
            # Start a fresh utterance from this chunk boundary.
            session.current_utterance_start_position = max(
                session.last_finalized_position,
                len(session.audio_buffer) - len(audio_bytes),
            )
            session.current_partial_transcript = ""

        # Track speaking state
        if is_speaking:
            session.was_speaking = True
            session.silence_start_time = None
        elif session.was_speaking and session.silence_start_time is None:
            session.silence_start_time = current_time
        
        # Silence detection
        silence_duration = 0
        if session.silence_start_time:
            silence_duration = current_time - session.silence_start_time
        is_extended_silence = silence_duration > 1.5  # 1.5s of silence

        should_partial_transcribe = session.interview_active and is_speaking and session.should_transcribe(current_time)
        should_finalize_utterance = (
            session.interview_active and
            not is_speaking and
            session.was_speaking and
            silence_duration >= session.FINALIZE_SILENCE_SECONDS
        )

        # Auto-finalize during long continuous speech to prevent buffer overflow
        # and keep partial transcriptions accurate.  The partial window is capped
        # at ~15s, so we finalize every ~15s to ensure the full-accuracy MLX
        # Whisper pass covers the audio before the partial window moves on.
        _MAX_UTTERANCE_BYTES = 480_000  # ~15s at 16kHz mono 16-bit
        unfinalized_bytes = len(session.audio_buffer) - session.last_finalized_position
        if (
            session.interview_active
            and session.was_speaking
            and unfinalized_bytes > _MAX_UTTERANCE_BYTES
            and not should_finalize_utterance
        ):
            should_finalize_utterance = True

        should_process_chat = (not session.interview_active) and is_extended_silence

        if not (should_partial_transcribe or should_finalize_utterance or should_process_chat):
            return
        
        # Skip transcription if too quiet overall
        buffer_rms = audio_processor.calculate_rms(bytes(session.audio_buffer[-32000:])) if len(session.audio_buffer) > 32000 else rms
        if buffer_rms < 0.01 and not (should_finalize_utterance or should_process_chat):
            print(f"🔇 Skipping quiet buffer (RMS: {buffer_rms:.4f})")
            session.last_transcribe_time = current_time
            return
        
        session.is_processing = True
        
        try:
            if session.interview_active:
                if should_partial_transcribe:
                    start_pos = max(0, min(session.current_utterance_start_position, len(session.audio_buffer)))
                    # Cap partial window to ~15s — streaming Whisper degrades on longer clips
                    # and re-transcribing 2+ minutes per chunk is wasteful.
                    _MAX_PARTIAL_BYTES = 480_000  # ~15s at 16kHz mono 16-bit
                    if (len(session.audio_buffer) - start_pos) > _MAX_PARTIAL_BYTES:
                        start_pos = len(session.audio_buffer) - _MAX_PARTIAL_BYTES
                    audio_to_transcribe = bytes(session.audio_buffer[start_pos:])
                    if len(audio_to_transcribe) >= 6400:  # ~200ms minimum
                        transcript = await streaming_audio_processor.transcribe_buffer_async(audio_to_transcribe)
                        transcript = (transcript or "").strip()
                        session.last_transcribed_position = len(session.audio_buffer)
                        session.last_transcribe_time = current_time

                        if transcript and not _should_drop_false_start(session.finalized_answer_transcript, transcript):
                            if transcript_similarity(transcript, session.current_partial_transcript) < 0.98:
                                session.current_partial_transcript = transcript
                                composed = _combine_final_and_partial(
                                    session.finalized_answer_transcript,
                                    session.current_partial_transcript,
                                )
                                if composed != session.current_answer_transcript:
                                    session.current_answer_transcript = composed
                                    await _emit_transcript_update(session, is_final=False)
                                    print(f"📝 Partial: {session.current_answer_transcript[:80]}...")

                if should_finalize_utterance:
                    await _finalize_current_utterance(session, reason="silence")

                await _maybe_emit_coaching_hint(session, current_time, is_extended_silence)
            else:
                # Normal Chat Mode
                if should_process_chat:
                    await process_audio_and_respond(sid, session)
        finally:
            session.is_processing = False
            # Reset speaking state after extended silence
            if is_extended_silence and not session.interview_active:
                session.was_speaking = False
    
    except Exception as e:
        print(f"❌ Error processing audio: {e}")
        import traceback
        traceback.print_exc()


@sio.event
async def force_transcribe(sid):
    """
    Force transcription of current audio buffer.
    Useful when user clicks a button to submit.
    """
    session = sessions.get(sid)
    if session is None or session.is_processing:
        return
    
    if len(session.audio_buffer) > 0:
        session.is_processing = True
        try:
            if session.interview_active:
                await _finalize_current_utterance(session, reason="force")
            else:
                await process_audio_and_respond(sid, session)
        finally:
            session.is_processing = False
            session.audio_buffer.clear()
            session.last_transcribed_position = 0
            session.last_finalized_position = 0
            session.current_utterance_start_position = 0
            session.current_partial_transcript = ""
            session.was_speaking = False
            session.silence_start_time = None


@sio.event
async def set_recording_state(sid, data):
    """Client toggles recording lifecycle; backend uses this to gate audio chunks."""
    session = sessions.get(sid)
    if session is None:
        return

    data = data or {}
    recording = bool(data.get("recording", False))
    session.accept_audio_chunks = recording and session.interview_active
    if not session.accept_audio_chunks:
        session.was_speaking = False
        session.silence_start_time = None


@sio.event
async def text_message(sid, data):
    """
    Handle text message (for testing without audio).
    """
    session = sessions.get(sid)
    if session is None:
        return
    
    text = data.get("text", "").strip()
    if not text:
        return
    
    session.is_processing = True
    try:
        await process_text_and_respond(sid, session, text)
    finally:
        session.is_processing = False


@sio.event
async def set_phase(sid, data):
    """Set the interview phase for the session."""
    session = sessions.get(sid)
    if session:
        session.status = data.get("phase", "technical")
        await sio.emit("phase_changed", {"phase": session.status, "user_id": session.user_id}, room=str(session.user_id))


@sio.event
async def submit_audio(sid, data):
    """
    Handle complete audio submission (blob) from the client.
    Saves to temp file to handle WebM format correctly, then transcribes.
    """
    session = sessions.get(sid)
    if session is None:
        return

    audio_b64 = data.get("audio", "")
    if not audio_b64:
        return
    
    # Save to temp file to handle WebM headers
    try:
        audio_bytes = base64.b64decode(audio_b64)
        
        # Create temp file with .webm extension
        # We use delete=False because we need to close it before reading in another process/thread (sometimes)
        # But here we just pass path.
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp:
            temp.write(audio_bytes)
            temp_path = temp.name
            
        # Transcribe
        processor = get_audio_processor()
        # This uses mlx_whisper.transcribe(path) which handles ffmpeg decoding
        text = await processor.transcribe_file_async(temp_path) if hasattr(processor, 'transcribe_file_async') else processor.transcribe_file(temp_path)
        
        # Cleanup
        os.remove(temp_path)
        
        if text.strip():
            if session.interview_active and _should_drop_false_start(session.current_answer_transcript, text):
                print(f"🔇 Dropping false-start transcript: {text!r}")
                return

            print(f"🗣️ Transcribed: {text[:50]}...")

            # In interview mode we only keep transcript; no live LLM/TTS feedback.
            if session.interview_active:
                merged = merge_transcript(
                    session.finalized_answer_transcript,
                    text
                )
                if merged != session.finalized_answer_transcript:
                    session.finalized_answer_transcript = merged
                    session.current_partial_transcript = ""
                    session.current_answer_transcript = merged
                    await _emit_transcript_update(session, is_final=True)
            else:
                # Emit transcript back to user
                await sio.emit("transcript", {"text": text, "user_id": session.user_id}, room=str(session.user_id))
                # Process as chat answer for non-interview mode
                session.is_processing = True
                await sio.emit("status", {"stage": "analyzing", "user_id": session.user_id}, room=str(session.user_id))
                try:
                    await process_text_and_respond(sid, session, text)
                finally:
                    session.is_processing = False
        else:
            print("⚠️ Transcription empty")
            
    except Exception as e:
        print(f"❌ Error in submit_audio: {e}")
        await sio.emit("error", {"message": "Audio processing failed", "user_id": session.user_id}, room=str(session.user_id))


# ============== Audio/LLM/TTS Pipeline ==============

async def process_audio_and_respond(sid: str, session: SessionState):
    """
    Process audio buffer: STT -> LLM -> TTS -> Send response.
    """
    # Step 1: Transcribe audio
    await sio.emit("status", {"stage": "transcribing", "user_id": session.user_id}, room=str(session.user_id))
    
    audio_processor = get_audio_processor()
    transcript = await audio_processor.transcribe_buffer_async(
        bytes(session.audio_buffer)
    )
    
    if not transcript.strip():
        await sio.emit("status", {"stage": "no_speech"}, room=str(session.user_id))
        return
    
    # Emit transcript to client
    await sio.emit("transcript", {"text": transcript, "user_id": session.user_id}, room=str(session.user_id))
    session.transcript_chunks.append(transcript)
    
    # Step 2: Process with LLM
    await process_text_and_respond(sid, session, transcript)


async def process_text_and_respond(sid: str, session: SessionState, text: str):
    """
    Process text input: LLM -> TTS -> Send response.
    Streams LLM tokens in real-time.
    """
    from langchain_core.messages import AIMessage, HumanMessage
    
    # Add user message to history
    session.messages.append(HumanMessage(content=text))
    
    # Step 1: Generate LLM response with streaming
    await sio.emit("status", {"stage": "thinking", "user_id": session.user_id}, room=str(session.user_id))
    
    chat_model = get_chat_model()
    full_response = ""
    
    async for token in chat_model.generate_response_stream(
        session.messages, 
        phase=session.status
    ):
        full_response += token
        # Stream each token to client
        await sio.emit("llm_token", {"token": token, "user_id": session.user_id}, room=str(session.user_id))
    
    # Add AI response to history
    session.messages.append(AIMessage(content=full_response))
    
    # Emit complete response
    await sio.emit("llm_complete", {"text": full_response, "user_id": session.user_id}, room=str(session.user_id))
    
    # Step 2: Generate TTS audio (non-fatal if unavailable/slow)
    await sio.emit("status", {"stage": "speaking", "user_id": session.user_id}, room=str(session.user_id))

    try:
        await _await_tts_warmup_if_needed()
        tts_service = get_tts_service()
        tts_timeout = _compute_tts_timeout(full_response)
        audio_base64 = await asyncio.wait_for(
            tts_service.speak_wav_base64_async(
                full_response,
                style=getattr(session, "tts_style", "interviewer"),
                provider=getattr(session, "tts_provider", "piper"),
            ),
            timeout=tts_timeout,
        )

        # Send audio to client
        await sio.emit("tts_audio", {
            "audio": audio_base64,
            "format": "wav",
            "sample_rate": tts_service.sample_rate_for_provider(getattr(session, "tts_provider", "piper")),
            "user_id": session.user_id
        }, room=str(session.user_id))
    except asyncio.TimeoutError:
        print(f"⚠️ TTS timed out after {tts_timeout:.1f}s (continuing without audio)")
        await sio.emit("tts_error", {
            "error": "TTS timed out; continuing without audio.",
            "user_id": session.user_id
        }, room=str(session.user_id))
    except Exception as e:
        print(f"⚠️ TTS failed in process_text_and_respond (continuing): {e}")
        await sio.emit("tts_error", {
            "error": "TTS unavailable; continuing without audio.",
            "user_id": session.user_id
        }, room=str(session.user_id))
    finally:
        await sio.emit("status", {"stage": "ready", "user_id": session.user_id}, room=str(session.user_id))


# ============== Career Analysis ==============




@sio.event
async def request_hint(sid):
    """Manually generate a hint for the current context."""
    session = sessions.get(sid)
    if not session or not session.interview_active:
        return
        
    print(f"🤔 Manual hint requested by {sid}")
    
    # Non-blocking hint generation
    async def send_hint():
        try:
            from server.services.coaching_service import generate_coaching_hint
            current_q = session.interview_questions[session.current_question_index] if session.interview_questions else {}
            
            # Use current transcript
            transcript = session.current_answer_transcript
            
            # Progressive hint level based on hints already given
            hint_level = len(session.hints_given) + 1
            
            hint = await generate_coaching_hint(
                transcript, 
                current_q, 
                previous_hints=session.hints_given,
                hint_level=hint_level
            )
            
            if hint:
                hint_message = hint["message"] if isinstance(hint, dict) else str(hint)
                print(f"💡 Manual Hint L{hint_level}: {hint_message}")
                session.hints_given.append(hint_message)
                payload = {"message": hint_message, "level": hint_level, "user_id": session.user_id}
                if isinstance(hint, dict):
                    payload.update({k: v for k, v in hint.items() if k != "message"})
                await sio.emit("coaching_hint", payload, room=str(session.user_id))
            else:
                await sio.emit("coaching_hint", {"message": "Try to break down the problem into smaller steps.", "level": 1, "user_id": session.user_id}, room=str(session.user_id))
        except Exception as e:
            print(f"⚠️ Manual hint generation error: {e}")
    
    asyncio.create_task(send_hint())


# ============== Interview Practice Events ==============


async def send_question_tts(session, question_text: str, question_index: Optional[int] = None):
    """Generate TTS audio for an interview question and send to client asynchronously."""
    try:
        await _await_tts_warmup_if_needed()
        tts_service = get_tts_service()
        tts_style = getattr(session, "tts_style", "interviewer")
        tts_provider = getattr(session, "tts_provider", "piper")
        print(
            f"🔈 Generating question TTS (q_index={question_index}, chars={len(question_text or '')}, provider={tts_provider}, style={tts_style})"
        )
        tts_timeout = _compute_tts_timeout(question_text)
        audio_b64 = await asyncio.wait_for(
            tts_service.speak_wav_base64_async(question_text, style=tts_style, provider=tts_provider),
            timeout=tts_timeout,
        )
        if not session.interview_active:
            return
        # Drop stale audio if user already advanced to another question.
        if question_index is not None and session.current_question_index != question_index:
            return
        await sio.emit("tts_audio", {
            "audio": audio_b64,
            "format": "wav",
            "sample_rate": tts_service.sample_rate_for_provider(tts_provider),
            "question_index": question_index,
            "user_id": session.user_id
        }, room=str(session.user_id))
        print(f"🔊 TTS sent for question ({len(question_text)} chars)")
    except asyncio.TimeoutError:
        print(f"⚠️ Question TTS timed out after {tts_timeout:.1f}s")
        await sio.emit("tts_error", {
            "error": "Question audio timed out; continuing without audio.",
            "user_id": session.user_id
        }, room=str(session.user_id))
    except asyncio.CancelledError:
        # Question advanced/ended before TTS finished.
        print(f"ℹ️ Question TTS task cancelled (q_index={question_index})")
        return
    except Exception as e:
        print(f"⚠️ TTS failed (non-blocking): {e}")
        await sio.emit("tts_error", {
            "error": "Question audio generation failed; continuing without audio.",
            "user_id": session.user_id
        }, room=str(session.user_id))


def _cancel_question_tts(session: SessionState):
    """Cancel in-flight per-question TTS task when question/session changes."""
    task = getattr(session, "question_tts_task", None)
    if task and not task.done():
        task.cancel()
    session.question_tts_task = None


@sio.event
async def start_interview(sid, data):
    """
    Start personalized interview practice session.
    
    Expected data:
    {
        "job_title": "from analysis",
        "skill_gaps": ["Python", "System Design"],
        "readiness_score": 0.65,
        "interview_type": "behavioral|technical|system_design|mixed",
        "interviewer_persona": "friendly|strict",
        "piper_style": "interviewer|balanced|fast",
        "tts_provider": "piper|qwen3_tts_mlx",
        "question_count": 3,  // optional debug/demo override (1-12)
        "mode": "practice" | "coaching"
    }
    """
    session = await _require_socket_auth(sid)
    if not session:
        return

    data = data or {}
    requested_mode = str(data.get("mode", "practice") or "practice").strip().lower()
    if requested_mode not in {"practice", "coaching", "evaluation"}:
        requested_mode = "practice"

    requested_feedback_timing = str(data.get("feedback_timing", "end_only") or "end_only").strip().lower()
    if requested_feedback_timing not in {"end_only", "live"}:
        requested_feedback_timing = "end_only"
    requested_persona = str(data.get("interviewer_persona", "") or "").strip().lower()
    requested_tts_style = str(data.get("piper_style", "") or "").strip().lower()
    requested_tts_provider = str(data.get("tts_provider", "") or "").strip().lower()

    explicit_coaching = data.get("coaching_enabled")
    coaching_enabled = bool(explicit_coaching) if explicit_coaching is not None else requested_mode == "coaching"
    live_scoring = bool(data.get("live_scoring", False)) or requested_feedback_timing == "live"

    requested_question_count = None
    if data.get("question_count") not in (None, ""):
        try:
            requested_question_count = int(data.get("question_count"))
            requested_question_count = max(1, min(12, requested_question_count))
        except Exception:
            requested_question_count = None
    
    await sio.emit("status", {"stage": "generating_questions", "user_id": session.user_id}, room=str(session.user_id))
    
    try:
        from server.agents.interview_nodes import generate_interview_questions
        from server.services.user_database import get_user_db

        if requested_question_count is None:
            try:
                prefs = get_user_db().get_user_preferences(session.user_id) or {}
                pref_count = prefs.get("question_count_override")
                if pref_count not in (None, ""):
                    requested_question_count = max(1, min(12, int(pref_count)))
            except Exception:
                requested_question_count = None
        if requested_persona not in {"friendly", "strict"}:
            try:
                prefs_for_persona = get_user_db().get_user_preferences(session.user_id) or {}
                requested_persona = str(prefs_for_persona.get("interviewer_persona") or "friendly").strip().lower()
            except Exception:
                requested_persona = "friendly"
        if requested_persona not in {"friendly", "strict"}:
            requested_persona = "friendly"
        if requested_tts_style not in ALLOWED_PIPER_STYLES:
            try:
                prefs_for_tts = get_user_db().get_user_preferences(session.user_id) or {}
                requested_tts_style = _normalize_piper_style(
                    prefs_for_tts.get("piper_style"),
                    fallback="interviewer",
                )
            except Exception:
                requested_tts_style = "interviewer"
        requested_tts_style = _normalize_piper_style(requested_tts_style, fallback="interviewer")
        if requested_tts_provider not in ALLOWED_TTS_PROVIDERS:
            try:
                prefs_for_tts_provider = get_user_db().get_user_preferences(session.user_id) or {}
                requested_tts_provider = _normalize_tts_provider(
                    prefs_for_tts_provider.get("tts_provider"),
                    fallback="piper",
                )
            except Exception:
                requested_tts_provider = "piper"
        requested_tts_provider = _normalize_tts_provider(requested_tts_provider, fallback="piper")
        
        # CRITICAL FIX: Generate unique DB ID for every interview attempt
        db_session_id = str(uuid.uuid4())
        plan_node_id = data.get("suggestion_id")  # e.g. "s1" - keep as metadata
        
        # Generate personalized questions
        interview_state = {
            "job_title": data.get("job_title", "Software Engineer"),
            "skill_gaps": data.get("skill_gaps", []),
            "readiness_score": data.get("readiness_score", 0.5),
            "job_description": data.get("job_description", ""),
            "interview_type": data.get("interview_type", "mixed"),
            "question_count": requested_question_count,
            "mode": requested_mode,
            "interviewer_persona": requested_persona,
        }
        
        # Progress callback
        async def progress_cb(stage, msg):
            await sio.emit("status", {"stage": msg, "user_id": session.user_id}, room=str(session.user_id))
        
        # Check cache first
        from server.services.cache import get_question_cache
        cache = get_question_cache()
        suggestion_id = data.get("suggestion_id")  # e.g., "s1" or "clinical_core"
        session_id = data.get("session_id", suggestion_id)  # Allow explicit session_id override
        cached_questions = None
        cache_key = None
        job_title = data.get("job_title", "generic")
        safe_title = re.sub(r'[^a-zA-Z0-9]', '_', job_title).lower()
        question_suffix = f"_q{requested_question_count}" if requested_question_count else ""
        persona_suffix = f"_p{requested_persona}"
        
        if suggestion_id or session_id:
            # Try multiple cache key formats (pre-gen may use different IDs)
            base_keys = [
                f"{session.user_id}_{safe_title}_{suggestion_id}",  # Standard: user_job_s1
                f"{session.user_id}_{safe_title}_{session_id}",     # With session_id
                f"{session.user_id}_{suggestion_id}",               # Short: user_s1
                f"{session.user_id}_{session_id}",                  # Short with session_id
            ]
            # Build lookup chain: most specific first, then broader fallbacks.
            # Pre-gen caches WITHOUT question_suffix, so we must try those too.
            persona_keys = [f"{k}{question_suffix}{persona_suffix}" for k in base_keys]
            # Persona-only keys (no question count) — matches pre-gen format
            persona_no_q_keys = [f"{k}{persona_suffix}" for k in base_keys] if question_suffix else []
            legacy_keys = []
            if requested_persona == "friendly":
                legacy_keys = [f"{k}{question_suffix}" for k in base_keys] if question_suffix else []
                # Plain base keys (legacy pre-gen compat)
                legacy_keys += list(base_keys)
            possible_keys = persona_keys + persona_no_q_keys + legacy_keys
            
            for key in possible_keys:
                if key:
                    cached_questions = cache.get(key)
                    if cached_questions:
                        cache_key = key
                        break
            
            # If no cache_key was set but we found questions, use first format
            if not cache_key and suggestion_id:
                cache_key = f"{session.user_id}_{safe_title}_{suggestion_id}{question_suffix}{persona_suffix}"
        else:
            # Fallback caching for direct interview starts without suggestion/session IDs.
            # This allows repeated runs from setup to reuse generated question sets.
            skill_values = []
            for item in data.get("skill_gaps", []) or []:
                if isinstance(item, dict):
                    value = str(item.get("name") or item.get("skill") or item.get("label") or "")
                else:
                    value = str(item)
                value = value.strip().lower()
                if value:
                    skill_values.append(value)
            skill_values = sorted(set(skill_values))

            normalized_jd = re.sub(r"\s+", " ", str(data.get("job_description", "") or "").strip().lower())[:240]
            fingerprint_source = "|".join([
                str(session.user_id or ""),
                safe_title,
                str(data.get("interview_type", "mixed") or "mixed").strip().lower(),
                str(requested_persona),
                str(requested_mode),
                str(requested_feedback_timing),
                str(bool(coaching_enabled)),
                str(requested_question_count or ""),
                ",".join(skill_values),
                normalized_jd,
            ])
            auto_hash = hashlib.sha1(fingerprint_source.encode("utf-8")).hexdigest()[:16]
            cache_key = f"{session.user_id}_{safe_title}_auto_{auto_hash}{question_suffix}{persona_suffix}"
            cached_questions = cache.get(cache_key)
            
        if cached_questions:
            cache_label = suggestion_id if suggestion_id else "direct_start"
            print(f"⚡ Using cached questions for {cache_label} (key: {cache_key})")
            await sio.emit("status", {"stage": "questions_ready", "user_id": session.user_id}, room=str(session.user_id))
            result = {"questions": cached_questions}
        else:
            # Fallback: Check DB (Persistent Store)
            db_questions = None
            if suggestion_id:
                try:
                    from server.services.user_database import get_user_db
                    user_db = get_user_db()
                    db_questions = user_db.get_analysis_session_questions(
                        session.user_id,
                        suggestion_id,
                        interviewer_persona=requested_persona
                    )
                except Exception as e:
                    print(f"⚠️ DB Fallback failed: {e}")
            
            if db_questions:
                 print(f"💾 Using DB persisted questions for {suggestion_id}")
                 await sio.emit("status", {"stage": "questions_ready", "user_id": session.user_id}, room=str(session.user_id))
                 result = {"questions": db_questions}
                 # Re-populate cache for next time
                 if cache_key:
                     cache.set(cache_key, db_questions)
            else:
                result = await generate_interview_questions(interview_state, progress_cb)
                # Cache newly generated questions for future use
                if cache_key and result.get("questions"):
                    cache.set(cache_key, result["questions"])

        if requested_question_count and result.get("questions"):
            result["questions"] = result["questions"][:requested_question_count]

        # Persist persona-specific question set on plan sessions.
        # This prevents non-friendly personas from falling back to generic pre-generated sets.
        if suggestion_id and result.get("questions"):
            try:
                from server.services.user_database import get_user_db
                get_user_db().set_latest_analysis_session_questions(
                    user_id=session.user_id,
                    session_id=suggestion_id,
                    questions=result["questions"],
                    interviewer_persona=requested_persona
                )
            except Exception as e:
                print(f"⚠️ Failed to persist persona questions for {suggestion_id}: {e}")

        
        # Store in session
        session.interview_active = True
        session.interview_questions = result["questions"]
        session.current_question_index = 0
        session.interview_mode = requested_mode
        session.interview_feedback_timing = requested_feedback_timing
        session.live_scoring_enabled = live_scoring
        session.interviewer_persona = requested_persona
        session.tts_style = requested_tts_style
        session.tts_provider = requested_tts_provider
        session.coaching_enabled = coaching_enabled
        session.evaluations = []
        session.hints_given = []  # Clear hint history
        session.answer_submission_in_flight = False
        session.accept_audio_chunks = False
        session.end_requested = False
        session.job_title = data.get("job_title", "Software Engineer")
        session.clear_for_new_question()
        
        # Store db_session_id in session for later DB updates
        session.db_session_id = db_session_id
        
        # Save session to database with UNIQUE UUID (not plan ID)
        user_db = get_user_db()
        user_db.create_session(
            user_id=session.user_id,
            session_id=db_session_id,  # <--- UNIQUE UUID
            job_title=session.job_title,
            mode=session.interview_mode,
            total_questions=len(session.interview_questions),
            plan_node_id=plan_node_id  # Store plan reference as metadata
        )
        
        # Send first question
        first_q = session.interview_questions[0]
        session.answer_start_time = time.time()
        
        await sio.emit("interview_started", {
            "session_id": db_session_id,  # Send back the valid unique ID
            "total_questions": len(session.interview_questions),
            "mode": session.interview_mode,
            "coaching_enabled": session.coaching_enabled,
            "interviewer_persona": session.interviewer_persona,
            "piper_style": session.tts_style,
            "tts_provider": session.tts_provider,
            "feedback_timing": session.interview_feedback_timing,
            "live_scoring": session.live_scoring_enabled,
            "user_id": session.user_id
        }, room=str(session.user_id))
        
        await sio.emit("interview_question", {
            "question": first_q,
            "question_number": 1,
            "total_questions": len(session.interview_questions),
            "user_id": session.user_id
        }, room=str(session.user_id))

        # TTS: Read the question aloud (non-blocking, one task per session)
        _cancel_question_tts(session)
        session.question_tts_task = asyncio.create_task(
            send_question_tts(session, first_q["text"], question_index=0)
        )

        # Generate initial coaching tip for the question (non-blocking)
        async def send_initial_tip():
            try:
                from server.services.coaching_service import generate_coaching_hint

                hint = await generate_coaching_hint(
                    transcript="",
                    question=first_q,
                    previous_hints=[],
                    hint_level=0
                )

                if hint:
                    hint_message = hint["message"] if isinstance(hint, dict) else str(hint)
                    payload = {"message": hint_message, "level": 0, "user_id": session.user_id}
                    if isinstance(hint, dict):
                        payload.update({k: v for k, v in hint.items() if k != "message"})
                    await sio.emit("coaching_hint", payload, room=str(session.user_id))
                    print(f"💡 Initial tip: {hint_message}")
            except Exception as e:
                print(f"⚠️ Initial tip generation skipped: {e}")
        
        if session.coaching_enabled:
            asyncio.create_task(send_initial_tip())
        
    except Exception as e:
        print(f"❌ Error starting interview: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit("interview_error", {"error": str(e), "user_id": session.user_id}, room=str(session.user_id))


@sio.event
async def submit_interview_answer(sid, data):
    """
    Submit answer to current interview question.
    Immediately advances to the next question; evaluation runs in the background.

    Expected data:
    {
        "answer": "text answer",
        "duration_seconds": 45.3
    }
    """
    session = sessions.get(sid)
    if not session or not session.interview_active:
        return
    data = data or {}
    session.accept_audio_chunks = False
    if session.answer_submission_in_flight:
        await sio.emit("status", {"stage": "answer_already_submitting", "user_id": session.user_id}, room=str(session.user_id))
        return

    session.answer_submission_in_flight = True
    try:
        # Get current question
        current_q = session.interview_questions[session.current_question_index]
        q_index = session.current_question_index
        await _finalize_current_utterance(session, reason="force")
        user_answer = data.get("answer", "")

        # Prefer finalized high-accuracy transcript over partial.
        if not user_answer.strip():
            user_answer = (
                session.finalized_answer_transcript.strip() or
                session.current_answer_transcript.strip()
            )
            print(f"📝 Using finalized transcript ({len(user_answer)} chars)")

        if not user_answer.strip():
            await sio.emit("interview_error", {"error": "No answer detected. Please speak your answer.", "user_id": session.user_id}, room=str(session.user_id))
            return

        duration = data.get("duration_seconds", 0)

        # Placeholder for the evaluation — filled asynchronously by the
        # background task.  We append immediately so the index stays stable.
        eval_entry = {
            "question": current_q,
            "answer": user_answer,
            "evaluation": None,  # will be filled by background task
            "duration": duration,
        }
        session.evaluations.append(eval_entry)

        # ---- Launch background evaluation ----
        # This runs the LLM evaluation concurrently while the user answers
        # the next question, so there's no blocking pause between questions.
        if not hasattr(session, '_pending_eval_tasks'):
            session._pending_eval_tasks = []

        async def _bg_evaluate(entry, q_idx):
            from server.agents.interview_nodes import evaluate_answer_stream
            try:
                user_thresholds = _get_user_feedback_thresholds(session.user_id)

                # Evaluation callback (silent — no streaming tokens to client
                # since the user has already moved on to the next question).
                async def eval_callback(msg_type, content):
                    pass

                evaluation = await evaluate_answer_stream(
                    entry["question"],
                    entry["answer"],
                    eval_callback,
                    thresholds=user_thresholds,
                )
                _record_evaluation_metrics(evaluation)
                entry["evaluation"] = evaluation
                print(f"📝 Evaluation: Score {evaluation.get('score', '?')}/10 (Q{q_idx + 1}, background)")

                # Persist to database
                db_sid = getattr(session, 'db_session_id', None)
                if db_sid:
                    user_db = get_user_db()
                    user_db.save_answer(
                        session_id=db_sid,
                        question_number=q_idx + 1,
                        question_text=entry["question"].get("text", ""),
                        question_category=entry["question"].get("category", "Technical"),
                        question_difficulty=entry["question"].get("difficulty", "intermediate"),
                        user_answer=entry["answer"],
                        evaluation=evaluation,
                        duration_seconds=entry["duration"],
                        skipped=False,
                    )
            except Exception as e:
                print(f"⚠️ Background evaluation failed (Q{q_idx + 1}): {e}")
                entry["evaluation"] = {"score": 0, "feedback": "Evaluation failed.", "error": True}

        task = asyncio.create_task(_bg_evaluate(eval_entry, q_index))
        session._pending_eval_tasks.append(task)

        # ---- Immediately advance to next question ----
        if session.end_requested:
            await finish_interview(sid, session)
            return

        session.current_question_index += 1

        if session.current_question_index < len(session.interview_questions):
            next_q = session.interview_questions[session.current_question_index]
            session.clear_for_new_question()
            session.answer_start_time = time.time()

            await sio.emit("interview_question", {
                "question": next_q,
                "question_number": session.current_question_index + 1,
                "total_questions": len(session.interview_questions),
                "user_id": session.user_id
            }, room=str(session.user_id))

            _cancel_question_tts(session)
            session.question_tts_task = asyncio.create_task(
                send_question_tts(
                    session,
                    next_q["text"],
                    question_index=session.current_question_index,
                )
            )
        else:
            await finish_interview(sid, session)

    except Exception as e:
        print(f"❌ Error submitting answer: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit("interview_error", {"error": str(e), "user_id": session.user_id}, room=str(session.user_id))
    finally:
        session.answer_submission_in_flight = False


async def finish_interview(sid: str, session: SessionState):
    """Complete interview and generate summary report."""
    from server.agents.interview_nodes import generate_interview_summary

    session.accept_audio_chunks = False
    session.end_requested = False
    _cancel_question_tts(session)

    # Tell the frontend to show a "generating report" loading screen.
    await sio.emit("generating_report", {"user_id": session.user_id}, room=str(session.user_id))

    # Wait for all background evaluations to complete before generating summary.
    pending_tasks = getattr(session, '_pending_eval_tasks', [])
    if pending_tasks:
        n_pending = sum(1 for t in pending_tasks if not t.done())
        if n_pending:
            print(f"⏳ Waiting for {n_pending} pending evaluation(s)…")
        await asyncio.gather(*pending_tasks, return_exceptions=True)
        session._pending_eval_tasks = []

    # Fill in any evaluations that failed / are still None with a safe fallback.
    for entry in session.evaluations:
        if entry.get("evaluation") is None:
            entry["evaluation"] = {"score": 0, "feedback": "Evaluation unavailable.", "error": True}

    try:
        summary = await generate_interview_summary(session.evaluations)
    except Exception as e:
        print(f"⚠️ Summary generation failed in finish_interview: {e}")
        total_questions = len(session.evaluations)
        skipped_questions = sum(1 for entry in session.evaluations if entry.get("skipped"))
        answered_questions = max(0, total_questions - skipped_questions)
        summary = {
            "total_questions": total_questions,
            "answered_questions": answered_questions,
            "skipped_questions": skipped_questions,
            "average_score": 0,
            "overall_breakdown": {
                "relevance": 0.0,
                "depth": 0.0,
                "structure": 0.0,
                "specificity": 0.0,
                "communication": 0.0,
            },
            "score_breakdown": {
                "relevance": 0.0,
                "depth": 0.0,
                "structure": 0.0,
                "specificity": 0.0,
                "communication": 0.0,
            },
            "top_strengths": [],
            "strengths": [],
            "areas_to_improve": [],
            "overall_feedback": "Interview ended. Summary generation failed; please retry report generation.",
            "action_items": [],
            "communication_feedback": "",
            "performance_breakdown": {"excellent": 0, "good": 0, "needs_work": answered_questions},
            "evaluation_status": ("partial" if skipped_questions > 0 else "complete"),
            "telemetry": {
                "fillerWords": 0,
                "fillersPerMinute": 0,
                "confidence": "N/A",
                "word_count": 0,
                "filler_detail": {},
                "avg_sentence_length": 0,
            },
        }

    # Save session summary to database using the proper DB session ID
    try:
        user_db = get_user_db()
        db_sid = getattr(session, 'db_session_id', None)
        if db_sid:
            user_db.complete_session(db_sid, summary)
            updated_queue = user_db.append_report_actions(session.user_id, summary, session_id=db_sid)
            await sio.emit("action_queue", {
                "actions": updated_queue,
                "user_id": session.user_id
            }, room=str(session.user_id))
        else:
            print(f"⚠️ No db_session_id found, session summary not saved to DB")
    except Exception as e:
        print(f"⚠️ Failed persisting completed interview {getattr(session, 'db_session_id', 'unknown')}: {e}")

    session.interview_active = False
    
    await sio.emit("interview_complete", {
        "session_id": getattr(session, "db_session_id", None),
        "summary": summary,
        "evaluations": session.evaluations,
        "message": f"Interview complete! Average score: {summary.get('average_score', 0)}/10",
        "user_id": session.user_id
    }, room=str(session.user_id))

    if settings.FEEDBACK_LOOP_V2:
        retries = feedback_metrics["retries_total"]
        avg_delta = (feedback_metrics["retry_delta_sum"] / retries) if retries else 0.0
        eval_total = max(1, feedback_metrics["evaluations_total"])
        low_quality_rate = feedback_metrics["low_transcript_quality"] / eval_total
        retry_usage_rate = retries / eval_total
        retry_success_rate = (feedback_metrics["retry_improved_count"] / retries) if retries else 0.0
        avg_score_v1 = (
            feedback_metrics["score_sum_v1"] / feedback_metrics["score_count_v1"]
            if feedback_metrics["score_count_v1"] else 0.0
        )
        avg_score_v2 = (
            feedback_metrics["score_sum_v2"] / feedback_metrics["score_count_v2"]
            if feedback_metrics["score_count_v2"] else 0.0
        )
        print(
            "📊 Feedback v2 metrics: eval=%s v2=%s low_stt=%s (%.2f) retries=%s retry_usage=%.2f retry_success=%.2f avg_delta=%.2f avg_v1=%.2f avg_v2=%.2f"
            % (
                feedback_metrics["evaluations_total"],
                feedback_metrics["evaluations_v2"],
                feedback_metrics["low_transcript_quality"],
                low_quality_rate,
                retries,
                retry_usage_rate,
                retry_success_rate,
                avg_delta,
                avg_score_v1,
                avg_score_v2,
            )
        )


@sio.event
async def check_struggle(sid, data):
    """
    Check if candidate is struggling (called periodically by client).
    
    Expected data:
    {
        "transcript": "current answer so far",
        "silence_duration": 5.2
    }
    """
    session = sessions.get(sid)
    if not session or not session.coaching_enabled or not session.interview_active:
        return
    
    try:
        from server.agents.interview_nodes import detect_struggle_and_coach
        
        current_q = session.interview_questions[session.current_question_index]
        
        hint = await detect_struggle_and_coach(
            data.get("transcript", ""),
            data.get("silence_duration", 0),
            current_q
        )
        
        if hint:
            await sio.emit("coaching_hint", {**hint, "user_id": session.user_id}, room=str(session.user_id))
            
    except Exception as e:
        print(f"⚠️ Struggle detection error: {e}")


@sio.event
async def toggle_coaching(sid, data):
    """Enable/disable real-time coaching hints."""
    session = sessions.get(sid)
    if session:
        session.coaching_enabled = data.get("enabled", False)
        await sio.emit("coaching_toggled", {
            "enabled": session.coaching_enabled,
            "user_id": session.user_id
        }, room=str(session.user_id))


@sio.event
async def skip_question(sid, data):
    """Skip current question and move to next."""
    session = sessions.get(sid)
    if not session or not session.interview_active:
        return
    if session.answer_submission_in_flight:
        return
    if session.current_question_index >= len(session.interview_questions):
        return
    session.answer_submission_in_flight = True
    session.accept_audio_chunks = False
    
    try:
        _cancel_question_tts(session)

        # Record skip
        current_q = session.interview_questions[session.current_question_index]
        skip_eval = {
            "score": 0,
            "score_breakdown": {"relevance": 0, "depth": 0, "structure": 0, "specificity": 0, "communication": 0},
            "strengths": [],
            "gaps": ["Question skipped"],
            "quality_flags": ["skipped"],
            "confidence": 0.0,
            "evidence_quotes": [],
            "improvement_plan": {
                "focus": "Answer the full question",
                "steps": [
                    "Give a direct response first.",
                    "Support with a specific example.",
                    "Close with measurable impact.",
                ],
                "success_criteria": [
                    "Addresses the prompt directly",
                    "Includes concrete context and action",
                    "Ends with a clear outcome",
                ],
            },
            "retry_drill": {
                "prompt": "Retry this skipped question with a structured answer.",
                "target_points": ["Direct answer", "Specific example", "Outcome"],
            },
            "coaching_tip": "Answer this question in full to unlock useful feedback.",
            "model_answer": "",
            "evaluation_reasoning": "Question was skipped.",
        }
        session.evaluations.append({
            "question": current_q,
            "answer": "(Skipped)",
            "evaluation": skip_eval,
            "duration": 0,
            "skipped": True
        })

        # Save skip to database
        db_sid = getattr(session, 'db_session_id', None)
        if db_sid:
            user_db = get_user_db()
            user_db.save_answer(
                session_id=db_sid,
                question_number=session.current_question_index + 1,
                question_text=current_q.get("text", ""),
                question_category=current_q.get("category", "Technical"),
                question_difficulty=current_q.get("difficulty", "intermediate"),
                user_answer="(Skipped)",
                evaluation=skip_eval,
                duration_seconds=0,
                skipped=True
            )

        session.current_question_index += 1
        
        if session.current_question_index < len(session.interview_questions):
            next_q = session.interview_questions[session.current_question_index]
            session.clear_for_new_question()  # Proper buffer reset
            session.answer_start_time = time.time()
            
            await sio.emit("interview_question", {
                "question": next_q,
                "question_number": session.current_question_index + 1,
                "total_questions": len(session.interview_questions),
                "user_id": session.user_id
            }, room=str(session.user_id))

            # TTS: Read next question aloud
            _cancel_question_tts(session)
            session.question_tts_task = asyncio.create_task(
                send_question_tts(
                    session,
                    next_q["text"],
                    question_index=session.current_question_index,
                )
            )
        else:
            await finish_interview(sid, session)
    finally:
        session.answer_submission_in_flight = False


@sio.event
async def end_interview_early(sid, data=None):
    """End interview before all questions are answered."""
    session = sessions.get(sid)
    if not session or not session.interview_active:
        return
    session.accept_audio_chunks = False
    session.end_requested = True
    _cancel_question_tts(session)

    if session.answer_submission_in_flight:
        await sio.emit("status", {
            "stage": "ending_after_current_evaluation",
            "user_id": session.user_id
        }, room=str(session.user_id))
        return

    # Persist partial in-progress answer if user ends mid-question.
    try:
        await _finalize_current_utterance(session, reason="force")
        current_q = session.interview_questions[session.current_question_index]
    except Exception:
        current_q = None

    if current_q:
        raw_answer = (
            (session.finalized_answer_transcript or "").strip() or
            (session.current_answer_transcript or "").strip()
        )
        already_recorded = len(session.evaluations) > session.current_question_index
        if raw_answer and not already_recorded:
            duration = 0
            if session.answer_start_time:
                duration = max(0, time.time() - session.answer_start_time)

            partial_eval = {
                "score": 0,
                "score_breakdown": {"relevance": 0, "depth": 0, "structure": 0, "specificity": 0, "communication": 0},
                "strengths": [],
                "gaps": ["Answer was incomplete"],
                "quality_flags": ["partial_answer"],
                "confidence": 0.2,
                "evidence_quotes": [],
                "improvement_plan": {
                    "focus": "Complete the answer with clear outcome",
                    "steps": [
                        "State your decision clearly.",
                        "Explain why you chose it.",
                        "Add outcome and what you learned.",
                    ],
                    "success_criteria": [
                        "Direct answer given",
                        "Reasoning and trade-off included",
                        "Outcome is concrete",
                    ],
                },
                "retry_drill": {
                    "prompt": "Retry this question and finish your full thought end-to-end.",
                    "target_points": ["Direct answer", "Reasoning", "Outcome"],
                },
                "coaching_tip": "Complete your full thought and submit before ending for a stronger evaluation.",
                "model_answer": "",
                "evaluation_reasoning": "Session ended mid-answer. Partial response saved.",
            }

            session.evaluations.append({
                "question": current_q,
                "answer": raw_answer,
                "evaluation": partial_eval,
                "duration": duration,
                "skipped": True,
            })

            db_sid = getattr(session, 'db_session_id', None)
            if db_sid:
                try:
                    user_db = get_user_db()
                    user_db.save_answer(
                        session_id=db_sid,
                        question_number=session.current_question_index + 1,
                        question_text=current_q.get("text", ""),
                        question_category=current_q.get("category", "Technical"),
                        question_difficulty=current_q.get("difficulty", "intermediate"),
                        user_answer=raw_answer,
                        evaluation=partial_eval,
                        duration_seconds=duration,
                        skipped=True
                    )
                except Exception as e:
                    print(f"⚠️ Failed saving partial end-interview answer: {e}")

    try:
        await finish_interview(sid, session)
    except Exception as e:
        print(f"❌ end_interview_early fallback path: {e}")
        session.interview_active = False
        await sio.emit("interview_complete", {
            "session_id": getattr(session, "db_session_id", None),
            "summary": {
                "total_questions": len(session.evaluations),
                "average_score": 0,
                "overall_breakdown": {
                    "clarity": 0.0,
                    "accuracy": 0.0,
                    "completeness": 0.0,
                    "structure": 0.0,
                },
                "score_breakdown": {
                    "clarity": 0.0,
                    "accuracy": 0.0,
                    "completeness": 0.0,
                    "structure": 0.0,
                },
                "top_strengths": [],
                "strengths": [],
                "areas_to_improve": [],
                "overall_feedback": "Interview ended early.",
                "action_items": [],
                "communication_feedback": "",
            },
            "evaluations": session.evaluations,
            "message": "Interview ended early.",
            "user_id": session.user_id
        }, room=str(session.user_id))



async def analyze_career_rest(
    job_title: str,
    company: str = "a top tech company"
):
    """
    REST endpoint for career analysis (for file upload via HTTP).
    Use Socket.IO start_career_analysis for real-time progress.
    """
    from fastapi import File, UploadFile
    
    return {
        "message": "Use Socket.IO 'start_career_analysis' event for real-time analysis",
        "example": {
            "event": "start_career_analysis",
            "data": {
                "resume": "base64-encoded PDF",
                "job_title": job_title,
                "company": company
            }
        }
    }


# ============== Main Entry Point ==============

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "server.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
