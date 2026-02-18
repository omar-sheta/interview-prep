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
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TypedDict

try:
    import mlx.core as mx
except ImportError:
    mx = None  # MLX not available (non-Apple Silicon)
import socketio
import tempfile
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.graph import END, START, StateGraph

from server.config import settings
from server.services.database import check_qdrant_status, init_vectors
from server.services.audio_service import get_audio_processor, get_vad
from server.services.tts_service import get_tts_service
from server.services.llm_factory import get_chat_model, preload_model
from server.services.user_database import get_user_db


# ============== Session State Management ==============

class SessionState:
    """Per-session state for audio streaming and conversation."""
    
    # Buffer constants
    MAX_BUFFER_SIZE = 960000  # 30 seconds at 16kHz mono 16-bit
    NEW_AUDIO_THRESHOLD = 32000  # 2 seconds of new audio before transcribing
    TRANSCRIBE_COOLDOWN = 2.0  # Minimum seconds between transcriptions
    
    def __init__(self, user_id: str = "anonymous"):
        self.user_id = user_id
        
        # Audio buffer - circular with max size
        self.audio_buffer = bytearray()
        
        # Transcription tracking
        self.last_transcribed_position: int = 0
        self.last_transcribe_time: float = 0
        self.recent_transcripts: list[str] = []  # Last 3 for deduplication
        
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
        self.coaching_enabled: bool = True
        self.answer_start_time: float = None
        self.current_answer_transcript: str = ""
        self.evaluations: list[dict] = []
        self.job_title: str = ""
        self.last_hint_time: float = 0
        self.hints_given: list[str] = []
        self.db_session_id: str = None  # UUID for database persistence
        
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
            trimmed = overflow
        
        return trimmed
    
    def should_transcribe(self, current_time: float) -> bool:
        """Check if we have enough new audio and cooldown has passed."""
        bytes_new = len(self.audio_buffer) - self.last_transcribed_position
        time_since = current_time - self.last_transcribe_time
        return bytes_new >= self.NEW_AUDIO_THRESHOLD and time_since >= self.TRANSCRIBE_COOLDOWN
    
    def clear_for_new_question(self):
        """Reset buffer state for a new question."""
        self.audio_buffer.clear()
        self.last_transcribed_position = 0
        self.last_transcribe_time = 0
        self.recent_transcripts = []
        self.current_answer_transcript = ""
        self.hints_given = []
        self.was_speaking = False
        self.silence_start_time = None

# Global session storage
sessions: dict[str, SessionState] = defaultdict(SessionState)

# Maps Socket ID -> User ID for quick lookup on disconnect
sid_to_user: dict[str, str] = {}

# Maps User ID -> count of active socket connections
user_connection_count: dict[str, int] = defaultdict(int)

# Maps User ID -> Active asyncio Task (for cancellation on disconnect or restart)
active_tasks: dict[str, asyncio.Task] = {}


def transcript_similarity(a: str, b: str) -> float:
    """Return similarity ratio 0.0-1.0 between two transcripts."""
    if not a or not b:
        return 0.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def merge_transcript(existing: str, new_chunk: str) -> str:
    """Intelligently merge new transcript chunk with existing, avoiding duplicates."""
    if not existing:
        return new_chunk.strip()
    if not new_chunk:
        return existing
    
    existing_words = existing.split()
    new_words = new_chunk.strip().split()
    
    # Find overlap: check if end of existing matches start of new
    max_overlap = min(len(existing_words), len(new_words), 10)  # Max 10 word overlap
    
    for overlap in range(max_overlap, 0, -1):
        if existing_words[-overlap:] == new_words[:overlap]:
            # Found overlap - merge without duplication
            merged = existing + " " + " ".join(new_words[overlap:])
            return merged.strip()
    
    # No overlap found - just append
    return (existing + " " + new_chunk).strip()


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
    print(f"🤖 LLM Model: {settings.LLM_MODEL_ID}")
    print(f"💾 Qdrant path: {settings.QDRANT_PATH}")
    
    # Initialize vector database
    init_vectors()
    
    # Check MLX Metal availability
    metal_available = mx.metal.is_available() if mx else False
    print(f"🍎 MLX Metal GPU: {metal_available}")
    
    if not metal_available:
        print("⚠️  Warning: Metal acceleration is not available!")
    
    # Verify LangGraph installation
    try:
        graph = build_sanity_check_graph()
        result = graph.invoke({"value": "test"})
        print(f"✅ LangGraph sanity check passed: {result['value']}")
    except Exception as e:
        print(f"❌ LangGraph sanity check failed: {e}")
    
    # Note: Models are lazily loaded on first use to speed up startup
    print("ℹ️  Models will be loaded on first use (lazy loading)")
    
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
    cors_allowed_origins=settings.CORS_ORIGINS
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
async def get_user_progress_api(user_id: str):
    """Get user's overall progress and statistics."""
    user_db = get_user_db()
    progress = user_db.get_user_progress(user_id)
    user = user_db.get_user(user_id)
    
    return {
        "user": user,
        "progress": progress
    }


@fast_app.get("/api/user/{user_id}/sessions")
async def get_user_sessions_api(user_id: str, limit: int = 10):
    """Get user's interview session history."""
    user_db = get_user_db()
    sessions_list = user_db.get_session_history(user_id, limit)
    return {"sessions": sessions_list}


@fast_app.get("/api/session/{session_id}")
async def get_session_details_api(session_id: str):
    """Get full details of a specific interview session."""
    user_db = get_user_db()
    session_details = user_db.get_session_details(session_id)
    
    if not session_details:
        return {"error": "Session not found"}
    
    return session_details


@fast_app.get("/api/user/{user_id}/career_analyses")
async def get_career_analyses_api(user_id: str, limit: int = 5):
    """Get user's career analysis history."""
    user_db = get_user_db()
    analyses = user_db.get_career_analyses(user_id, limit)
    return {"analyses": analyses}


# ============== Socket.IO Events ==============

@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    print(f"🔌 Client connected: {sid}")
    
    # Extract user_email or user_id from query params
    query_string = environ.get("QUERY_STRING", "")
    print(f"🔍 Handshake Query: {query_string}")
    
    user_email = None
    user_id = "anonymous"
    
    try:
        import urllib.parse
        params = urllib.parse.parse_qs(query_string)
        print(f"🔍 Handshake Params: {params}")
        
        # Check for user_id first (returning user)
        if "user_id" in params:
            provided_id = params["user_id"][0]
            if provided_id and provided_id not in ("null", "undefined", "anonymous"):
                user_db = get_user_db()
                existing_user = user_db.get_user(provided_id)
                if existing_user:
                    user_id = provided_id
                    print(f"✅ Recognized returning user: {user_id}")

        # Check for user_email (auto-login/signup via magic link or similar)
        if "user_email" in params and user_id == "anonymous":
            user_email = params["user_email"][0]
    except Exception:
        pass
    
    # Create or get user from database if email provided
    if user_email and user_id == "anonymous":
        user_db = get_user_db()
        user = user_db.get_user_by_email(user_email)
        if not user:
            user_id = user_db.create_user(user_email, user_email.split("@")[0])
        else:
            user_id = user["user_id"]
            user_db.update_last_login(user_id)
    
    sessions[sid] = SessionState(user_id=user_id)
    
    # User Room Pattern: Join private room and register mapping
    await sio.enter_room(sid, str(user_id))
    sid_to_user[sid] = user_id
    user_connection_count[user_id] += 1  # Track connection count
    
    await sio.emit("connected", {"sid": sid, "status": "ready", "user_id": user_id}, room=str(user_id))


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
            task = active_tasks.pop(user_id, None)
            if task and not task.done():
                task.cancel()
                print(f"🛑 All connections closed: Cancelled task for user {user_id}")
        else:
            print(f"📡 User {user_id} still has {remaining} connection(s) - task continues")
    
    if sid in sessions:
        del sessions[sid]


# ============== Authentication Events ==============

@sio.event
async def signup(sid, data):
    """Handle user signup."""
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
        user = user_db.get_user(user_id)
        
        # Update session and room membership
        if sid in sessions:
            sessions[sid].user_id = user_id
        
        # Leave old room, join new user room
        old_user = sid_to_user.get(sid)
        if old_user and old_user != user_id:
            await sio.leave_room(sid, str(old_user))
        await sio.enter_room(sid, str(user_id))
        sid_to_user[sid] = user_id
        user_connection_count[user_id] += 1
        
        await sio.emit("auth_success", {
            "user": {
                "user_id": user_id,
                "email": email,
                "username": username
            },
            "user_id": user_id
        }, room=str(user_id))
        print(f"✅ New user signed up: {email}")
    except Exception as e:
        await sio.emit("auth_error", {"error": str(e), "user_id": "anonymous"}, room=sid)


@sio.event
async def login(sid, data):
    """Handle user login."""
    import hashlib
    
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
    
    # Update session and room membership
    user_id = user["user_id"]
    if sid in sessions:
        sessions[sid].user_id = user_id
    
    # Leave old room, join new user room
    old_user = sid_to_user.get(sid)
    if old_user and old_user != user_id:
        await sio.leave_room(sid, str(old_user))
    await sio.enter_room(sid, str(user_id))
    sid_to_user[sid] = user_id
    user_connection_count[user_id] += 1
    
    user_db.update_last_login(user_id)
    
    # Get user preferences (to check onboarding status)
    prefs = user_db.get_user_preferences(user_id)
    
    await sio.emit("auth_success", {
        "user": {
            "user_id": user_id,
            "email": user["email"],
            "username": user["username"]
        },
        "preferences": prefs or {},
        "user_id": user_id
    }, room=str(user_id))
    print(f"✅ User logged in: {email}")

    # Automatically load latest analysis
    try:
        recent = user_db.get_career_analyses(user_id, limit=1)
        if recent:
            saved_analysis = recent[0]
            mapped_analysis = {
                "job_title": saved_analysis.get("job_title"),
                "company": saved_analysis.get("company"),
                "readiness_score": saved_analysis.get("readiness_score"),
                "skill_gaps": saved_analysis.get("skill_gaps", []),
                "bridge_roles": saved_analysis.get("bridge_roles", []),
                "suggested_sessions": saved_analysis.get("analysis", {}).get("suggested_sessions", []),
                "analysis_data": saved_analysis.get("analysis", {})
            }
            await sio.emit("career_analysis", {"analysis": mapped_analysis, "user_id": user_id}, room=str(user_id))
    except Exception as e:
        print(f"⚠️ Failed to load analysis on login: {e}")


@sio.event
async def restore_session(sid, data):
    """
    Restore a session using a stored user_id (for page refreshes).
    Trusts the client-side user_id (in a real app, use a session token).
    """
    user_id = data.get("user_id")
    if not user_id:
        return
    
    user_db = get_user_db()
    user = user_db.get_user(user_id)
    
    if not user:
        # Invalid user_id
        return
    
    # Associate current SID with this user and update room
    if sid in sessions:
        sessions[sid].user_id = user_id
    
    # Leave old room, join new user room
    old_user = sid_to_user.get(sid)
    if old_user and old_user != user_id:
        await sio.leave_room(sid, str(old_user))
    await sio.enter_room(sid, str(user_id))
    sid_to_user[sid] = user_id
    user_connection_count[user_id] += 1
        
    print(f"🔄 Restored session for user: {user_id}")
    
    # Send ack with preferences to ensure client is in sync
    prefs = user_db.get_user_preferences(user_id)
    await sio.emit("session_restored", {
        "user": user,
        "preferences": prefs or {},
        "user_id": user_id
    }, room=str(user_id))

    # Automatically load latest analysis
    try:
        recent = user_db.get_career_analyses(user_id, limit=1)
        if recent:
            saved_analysis = recent[0]
            mapped_analysis = {
                "job_title": saved_analysis.get("job_title"),
                "company": saved_analysis.get("company"),
                "readiness_score": saved_analysis.get("readiness_score"),
                "skill_gaps": saved_analysis.get("skill_gaps", []),
                "bridge_roles": saved_analysis.get("bridge_roles", []),
                "suggested_sessions": saved_analysis.get("analysis", {}).get("suggested_sessions", []),
                "analysis_data": saved_analysis.get("analysis", {})
            }
            await sio.emit("career_analysis", {"analysis": mapped_analysis, "user_id": user_id}, room=str(user_id))
    except Exception as e:
        print(f"⚠️ Failed to load analysis on restore: {e}")


# ============== User Identification Helper ==============

def _get_uid(sid, data=None):
    """Robust helper to get user_id from session or data fallback."""
    session = sessions.get(sid)
    uid = session.user_id if session else "anonymous"
    
    # Check if data contains a valid user_id override
    if uid == "anonymous" and data and isinstance(data, dict):
        provided = data.get("user_id")
        if provided and provided not in ("anonymous", "null", "undefined"):
            uid = provided
            # Update session for consistency
            if session:
                session.user_id = provided
            print(f"💡 Identification: Using fallback user_id from data: {uid}")
            
    return uid


# ============== User Preferences & History Events ==============

@sio.event
async def save_preferences(sid, data):
    """Save user preferences (resume, target role, focus areas)."""
    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    
    preferences = {
        "resume_text": data.get("resume_text"),
        "resume_filename": data.get("resume_filename"),
        "target_role": data.get("target_role"),
        "target_company": data.get("target_company"),
        "focus_areas": data.get("focus_areas", []),
        "onboarding_complete": data.get("onboarding_complete", False),
        "mic_permission_granted": data.get("mic_permission_granted", False)
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
    user_id = _get_uid(sid, data)
    print(f"🚀 Starting career analysis for {user_id}")

    # Resource Guard: Cancel any existing task for this user
    existing_task = active_tasks.get(user_id)
    if existing_task and not existing_task.done():
        existing_task.cancel()
        print(f"🛑 Cancelled previous task for {user_id} (double-click prevention)")

    user_db = get_user_db()

    # Check if new resume/role provided in request
    if data and data.get("resume") and data.get("job_title"):
        print(f"📝 New resume provided, saving preferences first...")

        # Extract resume text from base64 PDF
        resume_text = ""
        try:
            from server.tools.resume_tool import extract_text_from_pdf_bytes
            import base64
            pdf_bytes = base64.b64decode(data["resume"].split(",")[-1])
            resume_text = extract_text_from_pdf_bytes(pdf_bytes)
        except Exception as e:
            print(f"❌ Resume extraction failed: {e}")
            await sio.emit("analysis_error", {"error": f"Failed to extract resume text: {e}", "user_id": user_id}, room=str(user_id))
            return

        # Save new preferences
        preferences = {
            "resume_text": resume_text,
            "resume_filename": f"resume_{user_id}.pdf",
            "target_role": data["job_title"],
            "target_company": data.get("company", "Tech Company"),
            "focus_areas": []
        }
        user_db.save_user_preferences(user_id, preferences)
        print(f"✅ Saved new preferences for {user_id}")

    # Load preferences (either just saved or existing)
    prefs = user_db.get_user_preferences(user_id)

    if not prefs or not prefs.get("resume_text") or not prefs.get("target_role"):
        print(f"❌ Analysis failed: Missing prefs for {user_id}. Prefs: {prefs}")
        await sio.emit("analysis_error", {"error": "Missing resume or target role. Please complete onboarding first.", "user_id": user_id}, room=str(user_id))
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
            from server.agents.nodes import analyze_career_path
            import json

            # Run analysis
            result = await analyze_career_path(
                resume_text=prefs["resume_text"],
                target_role=prefs["target_role"],
                target_company=prefs.get("target_company", "Tech Company"),
                emit_progress=emit_progress
            )

            if result.get("error"):
                await sio.emit("analysis_error", {"error": result["error"], "user_id": user_id}, room=str(user_id))
                return

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
                result
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
                trigger_background_generation(user_id, result)

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
    user_id = _get_uid(sid, data)
    limit = (data or {}).get("limit", 20)
    
    user_db = get_user_db()
    history = user_db.get_interview_history(user_id, limit)
    
    await sio.emit("interview_history", {
        "history": history,
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def get_user_stats(sid, data=None):
    """Get user progress statistics."""
    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    stats = user_db.get_user_stats(user_id)
    
    await sio.emit("user_stats", {
        "stats": stats,
        "user_id": user_id
    }, room=str(user_id))


@sio.event
async def get_latest_analysis(sid, data=None):
    """Get the most recent career analysis for the user."""
    user_id = _get_uid(sid, data)
    user_db = get_user_db()
    # reuse get_career_analyses but limit 1
    recent = user_db.get_career_analyses(user_id, limit=1)
    
    if recent:
        # Transform DB format to Frontend format
        saved_analysis = recent[0]
        mapped_analysis = {
            "job_title": saved_analysis.get("job_title"),
            "company": saved_analysis.get("company"),
            "readiness_score": saved_analysis.get("readiness_score"),
            "skill_gaps": saved_analysis.get("skill_gaps", []),
            "bridge_roles": saved_analysis.get("bridge_roles", []),
            "suggested_sessions": saved_analysis.get("suggested_sessions", []) or saved_analysis.get("analysis", {}).get("suggested_sessions", []),
            "practice_plan": saved_analysis.get("practice_plan") or saved_analysis.get("analysis", {}).get("practice_plan"),
            "analysis_data": saved_analysis.get("analysis", {})
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
        "suggested_sessions": latest.get("suggested_sessions", [])
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
            new_state
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
    Handle incoming audio chunks with improved buffer management.
    - Circular buffer (max 30s)
    - Smart transcription timing (every 2s of new audio)
    - Deduplication
    - Proper interview mode handling
    """
    session = sessions.get(sid)
    if session is None:
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
            print(f"📦 Buffer trimmed {trimmed} bytes (circular)")

    except Exception as e:
        print(f"❌ Error decoding audio chunk: {e}")
        return

    if session.is_processing:
        return  # Audio is saved, skip processing
    
    try:
        import time
        current_time = time.time()
        audio_processor = get_audio_processor()
        
        # Check volume of recent audio
        recent_chunk = bytes(session.audio_buffer[-len(audio_bytes):]) if len(audio_bytes) > 0 else b''
        rms = audio_processor.calculate_rms(recent_chunk) if recent_chunk else 0
        is_speaking = rms > 0.012  # Noise gate
        
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
        
        # Determine if we should transcribe
        should_transcribe = (
            session.should_transcribe(current_time) and (is_speaking or is_extended_silence)
        ) or (
            # Also transcribe if user just stopped speaking
            not is_speaking and session.was_speaking and silence_duration > 0.8
        )
        
        if not should_transcribe:
            return
        
        # Skip transcription if too quiet overall
        buffer_rms = audio_processor.calculate_rms(bytes(session.audio_buffer[-32000:])) if len(session.audio_buffer) > 32000 else rms
        if buffer_rms < 0.01:
            print(f"🔇 Skipping quiet buffer (RMS: {buffer_rms:.4f})")
            session.last_transcribe_time = current_time
            return
        
        session.is_processing = True
        
        try:
            if session.interview_active:
                # Interview Mode - Transcribe with overlap for context
                OVERLAP = 16000  # 1 second overlap for context
                start_pos = max(0, session.last_transcribed_position - OVERLAP)
                audio_to_transcribe = bytes(session.audio_buffer[start_pos:])
                
                print(f"🎙️ Transcribing {len(audio_to_transcribe)} bytes (pos {start_pos} to {len(session.audio_buffer)})")
                
                transcript = await audio_processor.transcribe_buffer_async(audio_to_transcribe)
                
                # Update position
                session.last_transcribed_position = len(session.audio_buffer)
                session.last_transcribe_time = current_time
                
                if transcript.strip():
                    # Deduplication check
                    is_duplicate = False
                    if session.recent_transcripts:
                        for recent in session.recent_transcripts[-2:]:
                            if transcript_similarity(transcript, recent) > 0.85:
                                print(f"🔄 Skipping duplicate transcript")
                                is_duplicate = True
                                break
                    
                    if not is_duplicate:
                        # Merge with existing transcript
                        session.current_answer_transcript = merge_transcript(
                            session.current_answer_transcript,
                            transcript
                        )
                        
                        # Track for dedup
                        session.recent_transcripts.append(transcript)
                        session.recent_transcripts = session.recent_transcripts[-3:]
                        
                        # Emit full accumulated transcript
                        await sio.emit("transcript", {
                            "text": session.current_answer_transcript,
                            "full": session.current_answer_transcript,
                            "user_id": session.user_id
                        }, room=str(session.user_id))
                        
                        print(f"📝 Transcript: {session.current_answer_transcript[:80]}...")
                        
                        # Coaching hints logic
                        if session.answer_start_time:
                            answer_duration = current_time - session.answer_start_time
                        else:
                            answer_duration = 0
                        
                        words = session.current_answer_transcript.lower().split()
                        filler_words = ['uh', 'uhm', 'um', 'hmm', 'err', 'like,', '...']
                        last_words = words[-5:] if len(words) >= 5 else words
                        has_fillers = any(fw in ' '.join(last_words) for fw in filler_words)
                        
                        hint_count = len(session.hints_given)
                        hint_cooldown = 5 if hint_count == 0 else 10
                        
                        should_hint = (
                            session.coaching_enabled and
                            (current_time - session.last_hint_time) > hint_cooldown and
                            is_extended_silence and
                            (
                                (answer_duration > 5 and len(words) < 10) or
                                (has_fillers and len(words) < 20) or
                                (answer_duration > 20)
                            )
                        )
                        
                        if should_hint:
                            session.last_hint_time = current_time
                            hint_level = hint_count + 1
                            print(f"🤔 Generating hint level {hint_level}")
                            
                            async def send_hint():
                                try:
                                    from server.services.coaching_service import generate_coaching_hint
                                    current_q = session.interview_questions[session.current_question_index] if session.interview_questions else {}
                                    hint = await generate_coaching_hint(
                                        session.current_answer_transcript,
                                        current_q,
                                        previous_hints=session.hints_given,
                                        hint_level=hint_level
                                    )
                                    if hint:
                                        print(f"💡 Hint L{hint_level}: {hint}")
                                        session.hints_given.append(hint)
                                        await sio.emit("coaching_hint", {"message": hint, "level": hint_level, "user_id": session.user_id}, room=str(session.user_id))
                                except Exception as e:
                                    print(f"⚠️ Hint error: {e}")
                            
                            asyncio.create_task(send_hint())
            else:
                # Normal Chat Mode
                if is_extended_silence:
                    await process_audio_and_respond(sid, session)
        finally:
            session.is_processing = False
            # Reset speaking state after extended silence
            if is_extended_silence:
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
            await process_audio_and_respond(sid, session)
        finally:
            session.is_processing = False
            session.audio_buffer.clear()


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
            print(f"🗣️ Transcribed: {text[:50]}...")
            # Emit transcript back to user
            await sio.emit("transcript", {"text": text, "user_id": session.user_id}, room=str(session.user_id))
            
            # Process as Answer
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
    
    # Step 2: Generate TTS audio
    await sio.emit("status", {"stage": "speaking", "user_id": session.user_id}, room=str(session.user_id))
    
    tts_service = get_tts_service()
    audio_base64 = await tts_service.speak_wav_base64_async(full_response)
    
    # Send audio to client
    await sio.emit("tts_audio", {
        "audio": audio_base64,
        "format": "wav",
        "sample_rate": 24000,
        "user_id": session.user_id
    }, room=str(session.user_id))
    
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
                print(f"💡 Manual Hint L{hint_level}: {hint}")
                session.hints_given.append(hint)
                await sio.emit("coaching_hint", {"message": hint, "level": hint_level, "user_id": session.user_id}, room=str(session.user_id))
            else:
                await sio.emit("coaching_hint", {"message": "Try to break down the problem into smaller steps.", "level": 1, "user_id": session.user_id}, room=str(session.user_id))
        except Exception as e:
            print(f"⚠️ Manual hint generation error: {e}")
    
    asyncio.create_task(send_hint())


# ============== Interview Practice Events ==============

@sio.event
async def start_interview(sid, data):
    """
    Start personalized interview practice session.
    
    Expected data:
    {
        "job_title": "from analysis",
        "skill_gaps": ["Python", "System Design"],
        "readiness_score": 0.65,
        "mode": "practice" | "coaching"
    }
    """
    session = sessions.get(sid)
    if not session:
        return
    
    await sio.emit("status", {"stage": "generating_questions", "user_id": session.user_id}, room=str(session.user_id))
    
    try:
        from server.agents.interview_nodes import generate_interview_questions
        from server.services.user_database import get_user_db
        
        # CRITICAL FIX: Generate unique DB ID for every interview attempt
        db_session_id = str(uuid.uuid4())
        plan_node_id = data.get("suggestion_id")  # e.g. "s1" - keep as metadata
        
        # Generate personalized questions
        interview_state = {
            "job_title": data.get("job_title", "Software Engineer"),
            "skill_gaps": data.get("skill_gaps", []),
            "readiness_score": data.get("readiness_score", 0.5),
            "mode": data.get("mode", "practice")
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
        
        if suggestion_id or session_id:
            job_title = data.get("job_title", "generic")
            safe_title = re.sub(r'[^a-zA-Z0-9]', '_', job_title).lower()
            
            # Try multiple cache key formats (pre-gen may use different IDs)
            possible_keys = [
                f"{session.user_id}_{safe_title}_{suggestion_id}",  # Standard: user_job_s1
                f"{session.user_id}_{safe_title}_{session_id}",     # With session_id
                f"{session.user_id}_{suggestion_id}",               # Short: user_s1
                f"{session.user_id}_{session_id}",                  # Short with session_id
            ]
            
            for key in possible_keys:
                if key:
                    cached_questions = cache.get(key)
                    if cached_questions:
                        cache_key = key
                        break
            
            # If no cache_key was set but we found questions, use first format
            if not cache_key and suggestion_id:
                cache_key = f"{session.user_id}_{safe_title}_{suggestion_id}"
            
        if cached_questions:
            print(f"⚡ Using cached questions for {suggestion_id} (key: {cache_key})")
            await sio.emit("status", {"stage": "questions_ready", "user_id": session.user_id}, room=str(session.user_id))
            result = {"questions": cached_questions}
        else:
            # Fallback: Check DB (Persistent Store)
            db_questions = None
            if suggestion_id:
                try:
                    from server.services.user_database import get_user_db
                    user_db = get_user_db()
                    db_questions = user_db.get_analysis_session_questions(session.user_id, suggestion_id)
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

        
        # Store in session
        session.interview_active = True
        session.interview_questions = result["questions"]
        session.current_question_index = 0
        session.interview_mode = data.get("mode", "practice")
        session.coaching_enabled = True  # Always enable coaching hints
        session.evaluations = []
        session.hints_given = []  # Clear hint history
        session.job_title = data.get("job_title", "Software Engineer")
        
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
            "user_id": session.user_id
        }, room=str(session.user_id))
        
        await sio.emit("interview_question", {
            "question": first_q,
            "question_number": 1,
            "total_questions": len(session.interview_questions),
            "user_id": session.user_id
        }, room=str(session.user_id))
        
        # Generate initial coaching tip for the question (non-blocking)
        async def send_initial_tip():
            try:
                from server.services.llm_factory import get_fast_chat_model
                from langchain_core.messages import SystemMessage
                
                category = first_q.get("category", "General")
                difficulty = first_q.get("difficulty", "medium")
                
                prompt = f"""Generate a brief, encouraging coaching tip for someone about to answer this interview question.
Question: {first_q.get('text', '')[:200]}
Category: {category}
Difficulty: {difficulty}

Give ONE actionable tip in 10-15 words. Be encouraging. No quotes or prefixes."""
                
                chat_model = get_fast_chat_model()
                response = await chat_model.ainvoke([SystemMessage(content=prompt)])
                tip = response.content.strip().replace('"', '').replace("'", "")
                
                # Clean up common prefixes
                for prefix in ["Tip:", "Hint:", "Remember:", "Try:"]:
                    if tip.startswith(prefix):
                        tip = tip[len(prefix):].strip()
                
                await sio.emit("coaching_hint", {
                    "message": tip,
                    "level": 0,  # Initial tip
                    "user_id": session.user_id
                }, room=str(session.user_id))
                print(f"💡 Initial tip: {tip}")
            except Exception as e:
                print(f"⚠️ Initial tip generation skipped: {e}")
        
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
    Triggers evaluation and shows next question.
    
    Expected data:
    {
        "answer": "text answer",
        "duration_seconds": 45.3
    }
    """
    session = sessions.get(sid)
    if not session or not session.interview_active:
        return
    
    try:
        from server.agents.interview_nodes import evaluate_answer_stream
        from server.services.audio_service import get_audio_processor
        
        # Get current question
        current_q = session.interview_questions[session.current_question_index]
        user_answer = data.get("answer", "")
        
        # Prefer accumulated transcript over full retranscription
        if not user_answer.strip():
            # Use the incrementally accumulated transcript (already deduped and merged)
            user_answer = session.current_answer_transcript.strip()
            print(f"📝 Using accumulated transcript ({len(user_answer)} chars)")
            
            # Only retranscribe full buffer if accumulated is too short (< 10 words)
            if len(user_answer.split()) < 10 and len(session.audio_buffer) > 32000:
                print(f"📝 Accumulated too short, retranscribing {len(session.audio_buffer)} bytes...")
                audio_processor = get_audio_processor()
                full_transcript = await audio_processor.transcribe_buffer_async(bytes(session.audio_buffer))
                if len(full_transcript.split()) > len(user_answer.split()):
                    user_answer = full_transcript.strip()
        
        if not user_answer.strip():
            await sio.emit("interview_error", {"error": "No answer detected. Please speak your answer.", "user_id": session.user_id}, room=str(session.user_id))
            return
        
        # Evaluation callback for streaming
        async def eval_callback(msg_type, content):
            if msg_type == "token":
                await sio.emit("evaluation_token", {"token": content, "user_id": session.user_id}, room=str(session.user_id))
            elif msg_type == "status":
                await sio.emit("status", {"stage": content, "user_id": session.user_id}, room=str(session.user_id))
        
        await sio.emit("status", {"stage": "evaluating", "user_id": session.user_id}, room=str(session.user_id))
        
        # Evaluate answer
        evaluation = await evaluate_answer_stream(
            current_q,
            user_answer,
            eval_callback
        )
        
        # Store evaluation
        session.evaluations.append({
            "question": current_q,
            "answer": user_answer,
            "evaluation": evaluation,
            "duration": data.get("duration_seconds", 0)
        })
        
        # Save answer to database using the proper DB session ID (not socket ID)
        user_db = get_user_db()
        db_sid = getattr(session, 'db_session_id', None)
        if db_sid:
            user_db.save_answer(
                session_id=db_sid,
                question_number=session.current_question_index + 1,
                question_text=current_q.get("text", ""),
                question_category=current_q.get("category", "Technical"),
                question_difficulty=current_q.get("difficulty", "intermediate"),
                user_answer=user_answer,
                evaluation=evaluation,
                duration_seconds=data.get("duration_seconds", 0),
                skipped=False
            )
        else:
            print(f"⚠️ No db_session_id found for session {sid}, answer not saved to DB")
        
        # Send complete evaluation
        await sio.emit("answer_evaluated", {
            "question_number": session.current_question_index + 1,
            "evaluation": evaluation,
            "user_id": session.user_id
        }, room=str(session.user_id))
        
        # Move to next question or finish
        session.current_question_index += 1
        
        if session.current_question_index < len(session.interview_questions):
            # Next question - clear buffer state properly
            next_q = session.interview_questions[session.current_question_index]
            session.clear_for_new_question()  # Use proper method
            session.answer_start_time = time.time()
            
            await sio.emit("interview_question", {
                "question": next_q,
                "question_number": session.current_question_index + 1,
                "total_questions": len(session.interview_questions),
                "user_id": session.user_id
            }, room=str(session.user_id))
        else:
            # Interview complete
            await finish_interview(sid, session)
            
    except Exception as e:
        print(f"❌ Error evaluating answer: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit("interview_error", {"error": str(e), "user_id": session.user_id}, room=str(session.user_id))


async def finish_interview(sid: str, session: SessionState):
    """Complete interview and generate summary report."""
    from server.agents.interview_nodes import generate_interview_summary
    
    summary = await generate_interview_summary(session.evaluations)
    
    # Save session summary to database using the proper DB session ID
    user_db = get_user_db()
    db_sid = getattr(session, 'db_session_id', None)
    if db_sid:
        user_db.complete_session(db_sid, summary)
    else:
        print(f"⚠️ No db_session_id found, session summary not saved to DB")
    
    session.interview_active = False
    
    await sio.emit("interview_complete", {
        "summary": summary,
        "evaluations": session.evaluations,
        "message": f"Interview complete! Average score: {summary['average_score']}/10",
        "user_id": session.user_id
    }, room=str(session.user_id))


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
    
    # Record skip
    current_q = session.interview_questions[session.current_question_index]
    skip_eval = {"score": 0, "score_breakdown": {"clarity": 0, "accuracy": 0, "completeness": 0}}
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
    else:
        await finish_interview(sid, session)


@sio.event
async def end_interview_early(sid, data):
    """End interview before all questions are answered."""
    session = sessions.get(sid)
    if not session or not session.interview_active:
        return
    
    await finish_interview(sid, session)



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

