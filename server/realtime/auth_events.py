"""Socket.IO auth and connection event registration."""

import asyncio
import hashlib
import time
from types import SimpleNamespace
from typing import Optional

import socketio


def register_auth_events(sio, deps):
    """Register connection and auth-related Socket.IO events."""

    def _cancel_preserved_interview_cleanup(session_token: Optional[str]) -> None:
        if not session_token:
            return
        task = deps.disconnected_interview_cleanup_tasks.pop(session_token, None)
        if task and not task.done():
            task.cancel()

    def _stash_disconnected_interview(session) -> None:
        session_token = getattr(session, "session_token", None)
        if not session_token or not getattr(session, "interview_active", False):
            return

        _cancel_preserved_interview_cleanup(session_token)
        if getattr(session, "question_tts_task", None) and not session.question_tts_task.done():
            session.question_tts_task.cancel()
        session.question_tts_task = None
        deps.disconnected_interview_sessions[session_token] = session

        grace = max(5.0, float(getattr(deps, "reconnect_grace_sec", 90.0)))

        async def _drop_after_grace():
            try:
                await asyncio.sleep(grace)
                preserved = deps.disconnected_interview_sessions.get(session_token)
                if preserved is session:
                    deps.disconnected_interview_sessions.pop(session_token, None)
                    print(f"⌛ Dropped preserved interview session after {grace:.0f}s grace window")
            except asyncio.CancelledError:
                return
            finally:
                deps.disconnected_interview_cleanup_tasks.pop(session_token, None)

        deps.disconnected_interview_cleanup_tasks[session_token] = asyncio.create_task(_drop_after_grace())

    async def _resume_preserved_interview_if_available(sid: str, user_id: str, session_token: str):
        preserved = deps.disconnected_interview_sessions.pop(session_token, None)
        _cancel_preserved_interview_cleanup(session_token)
        if not preserved:
            return None

        preserved.sid = sid
        preserved.user_id = user_id
        preserved.is_authenticated = True
        preserved.session_token = session_token
        preserved.answer_submission_in_flight = False
        preserved.accept_audio_chunks = False
        preserved.end_requested = False
        preserved.clear_for_new_question()
        preserved.answer_start_time = time.time()
        deps.sessions[sid] = preserved
        print(
            f"🔁 Reattached active interview for {user_id} at question "
            f"{getattr(preserved, 'current_question_index', 0) + 1}"
        )
        return preserved

    async def _emit_resumed_interview_state(session) -> None:
        if not session or not getattr(session, "interview_active", False):
            return
        if not getattr(session, "interview_questions", None):
            return

        question_index = max(0, min(
            int(getattr(session, "current_question_index", 0) or 0),
            len(session.interview_questions) - 1,
        ))
        current_q = session.interview_questions[question_index]
        await sio.emit(
            "interview_started",
            {
                "session_id": getattr(session, "db_session_id", None),
                "total_questions": len(session.interview_questions),
                "mode": getattr(session, "interview_mode", "practice"),
                "coaching_enabled": bool(getattr(session, "coaching_enabled", False)),
                "interviewer_persona": getattr(session, "interviewer_persona", "friendly"),
                "piper_style": getattr(session, "tts_style", "interviewer"),
                "tts_provider": getattr(session, "tts_provider", "piper"),
                "feedback_timing": getattr(session, "interview_feedback_timing", "end_only"),
                "live_scoring": bool(getattr(session, "live_scoring_enabled", False)),
                "user_id": getattr(session, "user_id", "anonymous"),
            },
            room=session.sid,
        )
        await sio.emit(
            "interview_question",
            {
                "question": current_q,
                "question_number": question_index + 1,
                "total_questions": len(session.interview_questions),
                "user_id": getattr(session, "user_id", "anonymous"),
            },
            room=session.sid,
        )

    def _log_auth_session_event(
        user_id: str,
        session_token: str,
        sid: str,
        event_type: str,
        details: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Persist auth/login lifecycle events for debugging."""
        if not user_id or not session_token:
            return
        try:
            user_db = deps.get_user_db()
            user_db.log_session_event(
                user_id=user_id,
                session_id=session_id,
                auth_session_fingerprint=user_db.get_session_token_fingerprint(session_token),
                sid=sid,
                event_type=event_type,
                event_source="auth",
                details=details or {},
            )
        except Exception as exc:
            print(f"⚠️ Failed logging auth session event {event_type}: {exc}")

    async def _emit_latest_analysis(user_id: str):
        try:
            recent = deps.get_user_db().get_career_analyses(user_id, limit=1)
            if not recent:
                return

            saved_analysis = recent[0]
            analysis_data = deps.normalize_latest_analysis_payload(user_id, saved_analysis)
            mapped_analysis = {
                "job_title": saved_analysis.get("job_title"),
                "company": saved_analysis.get("company"),
                "readiness_score": saved_analysis.get("readiness_score"),
                "skill_gaps": saved_analysis.get("skill_gaps", []),
                "bridge_roles": saved_analysis.get("bridge_roles", []),
                "suggested_sessions": analysis_data.get("suggested_sessions", []),
                "practice_plan": analysis_data.get("practice_plan"),
                "analysis_data": analysis_data,
            }
            await sio.emit(
                "career_analysis",
                {"analysis": mapped_analysis, "user_id": user_id},
                room=str(user_id),
            )
        except Exception as exc:
            print(f"⚠️ Failed to load analysis for {user_id}: {exc}")

    async def connect(sid, environ, auth=None):
        """Handle client connection with origin validation."""
        print(f"🔌 Client connected: {sid}")

        origin = (environ.get("HTTP_ORIGIN", "") or "").strip()
        trusted_origins = set(deps.settings.CORS_ORIGINS or [])
        local_dev_prefixes = (
            "http://localhost",
            "http://127.0.0.1",
            "https://localhost",
            "https://127.0.0.1",
        )
        is_local_dev_origin = origin.startswith(local_dev_prefixes)

        if origin and "*" not in trusted_origins and origin not in trusted_origins and not is_local_dev_origin:
            print(f"🛡️ Rejected connection from untrusted origin: {origin}")
            raise socketio.exceptions.ConnectionRefusedError("Origin not allowed")

        user_id = f"anon_{sid}"
        is_authenticated = False
        session_token = None

        try:
            if isinstance(auth, dict):
                session_token = auth.get("session_token")
            if session_token:
                token_user_id = deps.get_user_db().validate_session_token(session_token)
                if token_user_id:
                    user_id = token_user_id
                    is_authenticated = True
                    print(f"✅ Authenticated socket via session token: {user_id}")
        except Exception:
            pass

        deps.sessions[sid] = deps.SessionState(
            user_id=user_id,
            is_authenticated=is_authenticated,
            session_token=session_token if is_authenticated else None,
            sid=sid,
        )
        await deps.bind_sid_identity(
            sid=sid,
            new_user_id=user_id,
            is_authenticated=is_authenticated,
            session_token=session_token if is_authenticated else None,
        )

        session = deps.sessions[sid]
        if session.is_authenticated and session.session_token:
            _log_auth_session_event(
                user_id=session.user_id,
                session_token=session.session_token,
                sid=sid,
                event_type="socket_connected",
                details={
                    "authenticated": True,
                    "origin": origin or None,
                },
            )
        await sio.emit(
            "connected",
            {
                "sid": sid,
                "status": "ready",
                "user_id": deps.public_user_id(session),
                "authenticated": session.is_authenticated,
            },
            room=str(session.user_id),
        )

    async def disconnect(sid):
        """Handle client disconnection with task cancellation."""
        session = deps.sessions.get(sid)
        user_id = deps.sid_to_user.pop(sid, None)
        print(f"🔌 Client disconnected: {sid} (user: {user_id})")

        if session and session.is_authenticated and session.session_token:
            _log_auth_session_event(
                user_id=session.user_id,
                session_token=session.session_token,
                sid=sid,
                event_type="socket_disconnected",
                session_id=getattr(session, "db_session_id", None),
                details={
                    "interview_active": bool(getattr(session, "interview_active", False)),
                },
            )

        if user_id:
            await sio.leave_room(sid, str(user_id))
            deps.user_connection_count[user_id] = max(0, deps.user_connection_count[user_id] - 1)
            remaining = deps.user_connection_count[user_id]
            if remaining == 0:
                if session and session.is_authenticated and session.session_token and session.interview_active:
                    _stash_disconnected_interview(session)
                deps.cancel_user_task_if_idle(user_id)
            else:
                print(f"📡 User {user_id} still has {remaining} connection(s) - task continues")

        if sid in deps.sessions:
            del deps.sessions[sid]

    async def signup(sid, data):
        """Handle user signup."""
        data = data or {}
        email = data.get("email", "").strip().lower()
        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not email or not username or not password:
            await sio.emit("auth_error", {"error": "All fields are required", "user_id": "anonymous"}, room=sid)
            return

        user_db = deps.get_user_db()
        existing = user_db.get_user_by_email(email)
        if existing:
            await sio.emit("auth_error", {"error": "Email already registered", "user_id": "anonymous"}, room=sid)
            return

        try:
            user_id = user_db.create_user(email, username, password)
            session_token = user_db.create_session_token(user_id)
            is_admin = email in set(deps.settings.ADMIN_EMAILS or [])
            await deps.bind_sid_identity(
                sid=sid,
                new_user_id=user_id,
                is_authenticated=True,
                session_token=session_token,
            )
            _log_auth_session_event(
                user_id=user_id,
                session_token=session_token,
                sid=sid,
                event_type="signup_success",
                details={"email": email},
            )

            await sio.emit(
                "auth_success",
                {
                    "user": {
                        "user_id": user_id,
                        "email": email,
                        "username": username,
                        "is_admin": is_admin,
                    },
                    "session_token": session_token,
                    "user_id": user_id,
                },
                room=str(user_id),
            )
            print(f"✅ New user signed up: {email}")
        except Exception as exc:
            await sio.emit("auth_error", {"error": str(exc), "user_id": "anonymous"}, room=sid)

    async def login(sid, data):
        """Handle user login."""
        data = data or {}
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email or not password:
            await sio.emit(
                "auth_error",
                {"error": "Email and password are required", "user_id": "anonymous"},
                room=sid,
            )
            return

        user_db = deps.get_user_db()
        user = user_db.get_user_by_email(email)
        if not user:
            await sio.emit("auth_error", {"error": "Invalid email or password", "user_id": "anonymous"}, room=sid)
            return

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        if user.get("password_hash") and user["password_hash"] != password_hash:
            await sio.emit("auth_error", {"error": "Invalid email or password", "user_id": "anonymous"}, room=sid)
            return

        user_id = user["user_id"]
        session_token = user_db.create_session_token(user_id)
        is_admin = str(user.get("email") or email).strip().lower() in set(deps.settings.ADMIN_EMAILS or [])
        await deps.bind_sid_identity(
            sid=sid,
            new_user_id=user_id,
            is_authenticated=True,
            session_token=session_token,
        )
        _log_auth_session_event(
            user_id=user_id,
            session_token=session_token,
            sid=sid,
            event_type="login_success",
            details={"email": user["email"]},
        )

        user_db.update_last_login(user_id)
        prefs = user_db.get_user_preferences(user_id)

        await sio.emit(
            "auth_success",
            {
                "user": {
                    "user_id": user_id,
                    "email": user["email"],
                    "username": user["username"],
                    "is_admin": is_admin,
                },
                "session_token": session_token,
                "preferences": prefs or {},
                "user_id": user_id,
            },
            room=str(user_id),
        )
        print(f"✅ User logged in: {email}")
        await _emit_latest_analysis(user_id)

    async def restore_session(sid, data):
        """Restore a session using a server-issued session token."""
        data = data or {}
        session_token = data.get("session_token")
        if not session_token:
            await sio.emit("auth_error", {"error": "Session token required", "user_id": "anonymous"}, room=sid)
            return

        user_db = deps.get_user_db()
        user_id = user_db.validate_session_token(session_token)
        if not user_id:
            await sio.emit("auth_error", {"error": "Invalid or expired session token", "user_id": "anonymous"}, room=sid)
            return

        user = user_db.get_user(user_id)
        if not user:
            await sio.emit("auth_error", {"error": "Session user not found", "user_id": "anonymous"}, room=sid)
            return

        await deps.bind_sid_identity(
            sid=sid,
            new_user_id=user_id,
            is_authenticated=True,
            session_token=session_token,
        )
        resumed_session = await _resume_preserved_interview_if_available(sid, user_id, session_token)

        print(f"🔄 Restored session for user: {user_id}")
        _log_auth_session_event(
            user_id=user_id,
            session_token=session_token,
            sid=sid,
            event_type="session_restored",
            details={},
        )
        prefs = user_db.get_user_preferences(user_id)
        await sio.emit(
            "session_restored",
            {
                "user": deps.safe_user_payload(user),
                "session_token": session_token,
                "preferences": prefs or {},
                "user_id": user_id,
            },
            room=str(user_id),
        )
        await _emit_latest_analysis(user_id)
        if resumed_session:
            await _emit_resumed_interview_state(resumed_session)

    async def logout(sid, data=None):
        """Revoke auth token and drop socket back to anonymous identity."""
        data = data or {}
        session = deps.sessions.get(sid)
        token = data.get("session_token") or (session.session_token if session else None)

        try:
            if token:
                if session and session.is_authenticated:
                    _log_auth_session_event(
                        user_id=session.user_id,
                        session_token=token,
                        sid=sid,
                        event_type="logout",
                        session_id=getattr(session, "db_session_id", None),
                        details={},
                    )
                deps.get_user_db().revoke_session_token(token)
        except Exception as exc:
            print(f"⚠️ Token revoke failed on logout: {exc}")

        if session:
            await deps.bind_sid_identity(
                sid=sid,
                new_user_id=f"anon_{sid}",
                is_authenticated=False,
                session_token=None,
            )

        await sio.emit("logged_out", {"success": True, "user_id": "anonymous"}, room=sid)

    sio.on("connect", handler=connect)
    sio.on("disconnect", handler=disconnect)
    sio.on("signup", handler=signup)
    sio.on("login", handler=login)
    sio.on("restore_session", handler=restore_session)
    sio.on("logout", handler=logout)

    return SimpleNamespace(
        connect=connect,
        disconnect=disconnect,
        signup=signup,
        login=login,
        restore_session=restore_session,
        logout=logout,
    )
