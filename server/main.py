"""
Main application entry point for BeePrepared.
Combines FastAPI with Socket.IO and LangGraph agent architecture.
Implements real-time audio streaming pipeline: STT -> LLM -> TTS.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Optional, TypedDict

try:
    import mlx.core as mx
except ImportError:
    mx = None  # MLX not available (non-Apple Silicon)
import socketio
import os
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from langgraph.graph import END, START, StateGraph

from server.config import settings
from server.metrics import (
    feedback_metrics,
    record_evaluation_metrics as _record_evaluation_metrics,
    record_retry_metrics as _record_retry_metrics,
)
from server.session import (
    SessionState,
    active_tasks,
    pending_disconnect_cancels,
    sessions,
    sid_to_user,
    user_connection_count,
)
from server.transcript import (
    combine_final_and_partial as _combine_final_and_partial,
    merge_transcript,
    should_drop_false_start as _should_drop_false_start,
    transcript_similarity,
)
from server.tts_warmup import (
    TTS_PRELOAD_ON_STARTUP,
    await_tts_warmup_if_needed as _await_tts_warmup_if_needed,
    compute_tts_timeout as _compute_tts_timeout,
    schedule_tts_warmup,
)
from server.routes import (
    register_audio_events,
    register_auth_events,
    register_interview_events,
    register_preferences_events,
    register_rest_routes,
)
from server.services.database import check_qdrant_status, init_vectors
from server.services.audio_service import (
    get_audio_processor,
    get_streaming_audio_processor,
)
from server.services.tts_service import get_tts_service
from server.services.llm_factory import get_chat_model
from server.services.user_database import get_user_db
DISCONNECT_TASK_CANCEL_GRACE_SEC = float(os.getenv("DISCONNECT_TASK_CANCEL_GRACE_SEC", "90"))


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

        prev_final = (session.finalized_answer_transcript or "").strip()
        prev_partial = (session.current_partial_transcript or "").strip()
        prev_display = (
            (session.current_answer_transcript or "").strip()
            or _combine_final_and_partial(prev_final, prev_partial).strip()
        )

        audio_processor = get_audio_processor()
        finalized_chunk = await audio_processor.transcribe_buffer_async(bytes(session.audio_buffer[start_pos:end_pos]))
        finalized_chunk = (finalized_chunk or "").strip()

        # If final pass is empty, keep best-effort partial text so user doesn't lose words.
        if not finalized_chunk:
            finalized_chunk = prev_partial

        merged = prev_final
        if finalized_chunk:
            merged = merge_transcript(prev_final, finalized_chunk)
        session.finalized_answer_transcript = merged

        session.current_partial_transcript = ""
        session.current_answer_transcript = session.finalized_answer_transcript
        changed = bool(session.current_answer_transcript.strip()) and session.current_answer_transcript.strip() != prev_display

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
    print("🚀 Starting BeePrepared...")
    print(f"📁 Model path: {settings.MODEL_PATH}")
    print(f"🧠 LLM Provider: {getattr(settings, 'LLM_PROVIDER', 'ollama')}")
    print(f"🤖 LLM Model: {settings.LLM_MODEL_ID}")
    print(f"🧩 LLM Single Instance: {getattr(settings, 'LLM_SINGLE_INSTANCE', True)}")
    print(f"🌐 LLM Base URL: {settings.LLM_BASE_URL}")
    if getattr(settings, "QDRANT_ENABLED", False):
        print(f"💾 Qdrant path: {settings.QDRANT_PATH}")
    else:
        print("💾 Qdrant: disabled")

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
        schedule_tts_warmup()
        print("ℹ️  TTS preload/warmup scheduled")
    
    yield
    
    # Shutdown
    print("👋 Shutting down BeePrepared...")
    sessions.clear()


# ============== FastAPI Application ==============

fast_app = FastAPI(
    title="BeePrepared API",
    description="BeePrepared - LangGraph backend with multi-modal interview coaching",
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


# ============== Registered REST/Auth Routes ==============

_rest_routes = register_rest_routes(
    fast_app,
    SimpleNamespace(
        mx=mx,
        build_sanity_check_graph=lambda: build_sanity_check_graph(),
        check_qdrant_status=lambda: check_qdrant_status(),
        get_authenticated_rest_user_id=_get_authenticated_rest_user_id,
        get_user_db=lambda: get_user_db(),
        safe_user_payload=lambda user: _safe_user_payload(user),
    ),
)
health_check = _rest_routes.health_check
root = _rest_routes.root
get_user_progress_api = _rest_routes.get_user_progress_api
get_user_sessions_api = _rest_routes.get_user_sessions_api
get_session_details_api = _rest_routes.get_session_details_api
export_session_pdf = _rest_routes.export_session_pdf
get_career_analyses_api = _rest_routes.get_career_analyses_api

_auth_events = register_auth_events(
    sio,
    SimpleNamespace(
        settings=settings,
        SessionState=SessionState,
        sessions=sessions,
        sid_to_user=sid_to_user,
        user_connection_count=user_connection_count,
        get_user_db=lambda: get_user_db(),
        public_user_id=lambda session: _public_user_id(session),
        safe_user_payload=lambda user: _safe_user_payload(user),
        normalize_latest_analysis_payload=lambda user_id, saved_analysis: _normalize_latest_analysis_payload(user_id, saved_analysis),
        bind_sid_identity=lambda **kwargs: _bind_sid_identity(**kwargs),
        cancel_user_task_if_idle=lambda user_id: _cancel_user_task_if_idle(user_id),
    ),
)
connect = _auth_events.connect
disconnect = _auth_events.disconnect
signup = _auth_events.signup
login = _auth_events.login
restore_session = _auth_events.restore_session
logout = _auth_events.logout


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
ALLOWED_TTS_PROVIDERS = {"piper", "neutts", "kokoro", "qwen3_tts"}


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
    if normalized_fallback == "qwen3_tts_mlx":
        normalized_fallback = "qwen3_tts"
    if normalized_fallback not in ALLOWED_TTS_PROVIDERS:
        normalized_fallback = "piper"
    normalized_value = str(provider_value or "").strip().lower()
    if normalized_value == "qwen3_tts_mlx":
        normalized_value = "qwen3_tts"
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

_preferences_events = register_preferences_events(
    sio,
    SimpleNamespace(
        active_tasks=active_tasks,
        get_user_db=lambda: get_user_db(),
        require_socket_auth=lambda sid: _require_socket_auth(sid),
        get_uid=lambda sid, data=None: _get_uid(sid, data),
        normalize_feedback_thresholds=lambda overrides: _normalize_feedback_thresholds(overrides),
        normalize_recording_thresholds=lambda overrides: _normalize_recording_thresholds(overrides),
        normalize_piper_style=lambda style_value, fallback="interviewer": _normalize_piper_style(style_value, fallback=fallback),
        normalize_tts_provider=lambda provider_value, fallback="piper": _normalize_tts_provider(provider_value, fallback=fallback),
        first_present=lambda data, keys, default=None: _first_present(data, keys, default),
        normalize_latest_analysis_payload=lambda user_id, saved_analysis: _normalize_latest_analysis_payload(user_id, saved_analysis),
        get_user_feedback_thresholds=lambda user_id: _get_user_feedback_thresholds(user_id),
        record_evaluation_metrics=lambda evaluation: _record_evaluation_metrics(evaluation),
        record_retry_metrics=lambda delta: _record_retry_metrics(delta),
    ),
)
save_preferences = _preferences_events.save_preferences
start_career_analysis = _preferences_events.start_career_analysis
get_preferences = _preferences_events.get_preferences
get_interview_history = _preferences_events.get_interview_history
get_session_details = _preferences_events.get_session_details
get_retry_attempts = _preferences_events.get_retry_attempts
submit_retry_answer = _preferences_events.submit_retry_answer
get_user_stats = _preferences_events.get_user_stats
get_action_queue = _preferences_events.get_action_queue
reset_analysis_workspace = _preferences_events.reset_analysis_workspace
clear_configuration = _preferences_events.clear_configuration
delete_interview_history = _preferences_events.delete_interview_history
delete_interview_session = _preferences_events.delete_interview_session
reset_all_data = _preferences_events.reset_all_data
save_action_queue = _preferences_events.save_action_queue
get_latest_analysis = _preferences_events.get_latest_analysis
regenerate_suggestions = _preferences_events.regenerate_suggestions

_audio_events = register_audio_events(
    sio,
    SimpleNamespace(
        sessions=sessions,
        get_audio_processor=lambda: get_audio_processor(),
        get_streaming_audio_processor=lambda: get_streaming_audio_processor(),
        get_chat_model=lambda: get_chat_model(),
        get_tts_service=lambda: get_tts_service(),
        emit_transcript_update=lambda session, is_final=False: _emit_transcript_update(session, is_final=is_final),
        maybe_emit_coaching_hint=lambda session, current_time, is_extended_silence: _maybe_emit_coaching_hint(session, current_time, is_extended_silence),
        finalize_current_utterance=lambda session, reason="silence": _finalize_current_utterance(session, reason=reason),
        should_drop_false_start=lambda existing, new_chunk: _should_drop_false_start(existing, new_chunk),
        combine_final_and_partial=lambda finalized, partial: _combine_final_and_partial(finalized, partial),
        merge_transcript=lambda existing, new_chunk: merge_transcript(existing, new_chunk),
        transcript_similarity=lambda a, b: transcript_similarity(a, b),
        await_tts_warmup_if_needed=lambda: _await_tts_warmup_if_needed(),
        compute_tts_timeout=lambda text: _compute_tts_timeout(text),
    ),
)
user_audio_chunk = _audio_events.user_audio_chunk
force_transcribe = _audio_events.force_transcribe
set_recording_state = _audio_events.set_recording_state
text_message = _audio_events.text_message
set_phase = _audio_events.set_phase
submit_audio = _audio_events.submit_audio
process_audio_and_respond = _audio_events.process_audio_and_respond
process_text_and_respond = _audio_events.process_text_and_respond


_interview_events = register_interview_events(
    sio,
    SimpleNamespace(
        sessions=sessions,
        settings=settings,
        feedback_metrics=feedback_metrics,
        allowed_piper_styles=ALLOWED_PIPER_STYLES,
        allowed_tts_providers=ALLOWED_TTS_PROVIDERS,
        get_user_db=lambda: get_user_db(),
        get_tts_service=lambda: get_tts_service(),
        await_tts_warmup_if_needed=lambda: _await_tts_warmup_if_needed(),
        compute_tts_timeout=lambda text: _compute_tts_timeout(text),
        require_socket_auth=lambda sid: _require_socket_auth(sid),
        normalize_piper_style=lambda style_value, fallback="interviewer": _normalize_piper_style(style_value, fallback=fallback),
        normalize_tts_provider=lambda provider_value, fallback="piper": _normalize_tts_provider(provider_value, fallback=fallback),
        finalize_current_utterance=lambda session, reason="silence": _finalize_current_utterance(session, reason=reason),
        get_user_feedback_thresholds=lambda user_id: _get_user_feedback_thresholds(user_id),
        record_evaluation_metrics=lambda evaluation: _record_evaluation_metrics(evaluation),
        send_status_ready=lambda user_id: sio.emit("status", {"stage": "ready", "user_id": user_id}, room=str(user_id)),
    ),
)
request_hint = _interview_events.request_hint
send_question_tts = _interview_events.send_question_tts
_cancel_question_tts = _interview_events.cancel_question_tts
start_interview = _interview_events.start_interview
submit_interview_answer = _interview_events.submit_interview_answer
finish_interview = _interview_events.finish_interview
check_struggle = _interview_events.check_struggle
toggle_coaching = _interview_events.toggle_coaching
skip_question = _interview_events.skip_question
end_interview_early = _interview_events.end_interview_early



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
