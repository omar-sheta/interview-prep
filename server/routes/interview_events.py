"""Socket.IO interview-practice event registration."""

import asyncio
import hashlib
import re
import time
import uuid
from types import SimpleNamespace
from typing import Optional


def register_interview_events(sio, deps):
    """Register interview and coaching Socket.IO events."""

    def _question_log_details(question: Optional[dict]) -> dict:
        """Return compact question metadata for timeline events."""
        question = question or {}
        question_text = str(question.get("text", "") or "").strip()
        preview = question_text[:220] + ("..." if len(question_text) > 220 else "")
        return {
            "question_preview": preview,
            "category": question.get("category", "Technical"),
            "difficulty": question.get("difficulty", "intermediate"),
        }

    def _log_session_event(
        session,
        event_type: str,
        *,
        event_source: str = "interview",
        question_number: Optional[int] = None,
        details: Optional[dict] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Persist interview/auth timeline data without breaking the live flow."""
        if not session or not getattr(session, "user_id", None):
            return
        try:
            user_db = deps.get_user_db()
            user_db.log_session_event(
                user_id=session.user_id,
                session_id=str(session_id or getattr(session, "db_session_id", None) or "").strip() or None,
                auth_session_fingerprint=user_db.get_session_token_fingerprint(getattr(session, "session_token", None)),
                sid=getattr(session, "sid", None),
                event_type=event_type,
                event_source=event_source,
                question_number=question_number,
                details=details or {},
            )
        except Exception as exc:
            print(f"⚠️ Failed logging session event {event_type}: {exc}")

    async def request_hint(sid):
        """Manually generate a hint for the current context."""
        session = deps.sessions.get(sid)
        if not session or not session.interview_active:
            return

        print(f"🤔 Manual hint requested by {sid}")
        _log_session_event(
            session,
            "hint_requested",
            event_source="coaching",
            question_number=session.current_question_index + 1,
            details={"hint_origin": "manual"},
        )

        async def send_hint():
            try:
                from server.services.coaching_service import generate_coaching_hint

                current_q = (
                    session.interview_questions[session.current_question_index]
                    if session.interview_questions
                    else {}
                )
                transcript = session.current_answer_transcript
                hint_level = len(session.hints_given) + 1
                hint = await generate_coaching_hint(
                    transcript,
                    current_q,
                    previous_hints=session.hints_given,
                    hint_level=hint_level,
                )

                if hint:
                    hint_message = hint["message"] if isinstance(hint, dict) else str(hint)
                    print(f"💡 Manual Hint L{hint_level}: {hint_message}")
                    session.hints_given.append(hint_message)
                    payload = {"message": hint_message, "level": hint_level, "user_id": session.user_id}
                    if isinstance(hint, dict):
                        payload.update({k: v for k, v in hint.items() if k != "message"})
                    await sio.emit("coaching_hint", payload, room=session.sid)
                    _log_session_event(
                        session,
                        "hint_sent",
                        event_source="coaching",
                        question_number=session.current_question_index + 1,
                        details={
                            "hint_origin": "manual",
                            "hint_level": hint_level,
                            "message": hint_message,
                        },
                    )
                else:
                    fallback_message = "Try to break down the problem into smaller steps."
                    await sio.emit(
                        "coaching_hint",
                        {
                            "message": fallback_message,
                            "level": 1,
                            "user_id": session.user_id,
                        },
                        room=session.sid,
                    )
                    _log_session_event(
                        session,
                        "hint_sent",
                        event_source="coaching",
                        question_number=session.current_question_index + 1,
                        details={
                            "hint_origin": "manual",
                            "hint_level": 1,
                            "message": fallback_message,
                            "fallback": True,
                        },
                    )
            except Exception as exc:
                print(f"⚠️ Manual hint generation error: {exc}")
                _log_session_event(
                    session,
                    "hint_error",
                    event_source="coaching",
                    question_number=session.current_question_index + 1,
                    details={"hint_origin": "manual", "error": str(exc)},
                )

        asyncio.create_task(send_hint())

    async def _prefetch_question_tts(session, question_index: int):
        """Pre-generate TTS for a question and cache it without sending."""
        if question_index < 0 or question_index >= len(session.interview_questions):
            return
        if question_index in session.tts_prefetch_cache:
            return
        question_text = session.interview_questions[question_index].get("text", "")
        if not question_text:
            return
        # Yield to let active question TTS from other sessions acquire the lock first.
        await asyncio.sleep(1.0)
        if not session.interview_active:
            return
        try:
            await deps.await_tts_warmup_if_needed()
            tts_service = deps.get_tts_service()
            tts_style = getattr(session, "tts_style", "interviewer")
            tts_provider = getattr(session, "tts_provider", "piper")
            print(f"🔄 Pre-fetching question TTS (q_index={question_index}, chars={len(question_text)})")
            tts_timeout = deps.compute_tts_timeout(question_text)
            audio_b64 = await asyncio.wait_for(
                tts_service.speak_wav_base64_async(question_text, style=tts_style, provider=tts_provider),
                timeout=tts_timeout,
            )
            if session.interview_active:
                session.tts_prefetch_cache[question_index] = audio_b64
                print(f"✅ Pre-fetched question TTS cached (q_index={question_index})")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"⚠️ TTS pre-fetch failed (q_index={question_index}): {exc}")
        finally:
            session.tts_prefetch_tasks.pop(question_index, None)

    async def send_question_tts(session, question_text: str, question_index: Optional[int] = None):
        """Generate TTS audio for an interview question and send to client asynchronously."""
        tts_timeout = deps.compute_tts_timeout(question_text)
        try:
            await deps.await_tts_warmup_if_needed()
            tts_service = deps.get_tts_service()
            tts_style = getattr(session, "tts_style", "interviewer")
            tts_provider = getattr(session, "tts_provider", "piper")

            # Check prefetch cache first to avoid re-generating
            cached = session.tts_prefetch_cache.pop(question_index, None) if question_index is not None else None
            if cached:
                print(f"⚡ TTS cache hit (q_index={question_index}, chars={len(question_text or '')})")
                audio_b64 = cached
            else:
                if tts_service.supports_streaming(tts_provider):
                    print(
                        f"🔈 Streaming question TTS (q_index={question_index}, chars={len(question_text or '')}, "
                        f"provider={tts_provider}, style={tts_style})"
                    )
                    async with asyncio.timeout(tts_timeout):
                        async for chunk in tts_service.stream_pcm_base64_chunks_async(
                            question_text,
                            style=tts_style,
                            provider=tts_provider,
                        ):
                            if not session.interview_active:
                                return
                            if question_index is not None and session.current_question_index != question_index:
                                return
                            await sio.emit(
                                "tts_audio_chunk",
                                {
                                    "audio": chunk["audio"],
                                    "format": "pcm16",
                                    "sample_rate": chunk["sample_rate"],
                                    "question_index": question_index,
                                    "chunk_index": chunk["chunk_index"],
                                    "is_final": chunk["is_final"],
                                    "user_id": session.user_id,
                                },
                                room=session.sid,
                            )
                    print(f"🔊 Streamed TTS sent for question ({len(question_text)} chars)")
                    audio_b64 = None
                else:
                    print(
                        f"🔈 Generating question TTS (q_index={question_index}, chars={len(question_text or '')}, "
                        f"provider={tts_provider}, style={tts_style})"
                    )
                    audio_b64 = await asyncio.wait_for(
                        tts_service.speak_wav_base64_async(question_text, style=tts_style, provider=tts_provider),
                        timeout=tts_timeout,
                    )

            if not session.interview_active:
                return
            if question_index is not None and session.current_question_index != question_index:
                return
            if audio_b64:
                await sio.emit(
                    "tts_audio",
                    {
                        "audio": audio_b64,
                        "format": "wav",
                        "sample_rate": tts_service.sample_rate_for_provider(tts_provider),
                        "question_index": question_index,
                        "user_id": session.user_id,
                    },
                    room=session.sid,
                )
                print(f"🔊 TTS sent for question ({len(question_text)} chars)")
                _log_session_event(
                    session,
                    "question_audio_ready",
                    event_source="tts",
                    question_number=(question_index + 1) if question_index is not None else None,
                    details={
                        "provider": tts_provider,
                        "style": tts_style,
                        "streaming": False,
                        "cached": bool(cached),
                    },
                )
            elif question_index is not None:
                _log_session_event(
                    session,
                    "question_audio_ready",
                    event_source="tts",
                    question_number=question_index + 1,
                    details={
                        "provider": tts_provider,
                        "style": tts_style,
                        "streaming": True,
                        "cached": False,
                    },
                )

            # Pre-fetch next question TTS in the background
            if question_index is not None:
                next_index = question_index + 1
                if (
                    next_index < len(session.interview_questions)
                    and next_index not in session.tts_prefetch_cache
                    and next_index not in session.tts_prefetch_tasks
                ):
                    task = asyncio.create_task(_prefetch_question_tts(session, next_index))
                    session.tts_prefetch_tasks[next_index] = task

        except asyncio.TimeoutError:
            print(f"⚠️ Question TTS timed out after {tts_timeout:.1f}s")
            _log_session_event(
                session,
                "question_audio_error",
                event_source="tts",
                question_number=(question_index + 1) if question_index is not None else None,
                details={"error": "timeout", "timeout_seconds": round(tts_timeout, 2)},
            )
            await sio.emit(
                "tts_error",
                {"error": "Question audio timed out; continuing without audio.", "user_id": session.user_id},
                room=session.sid,
            )
        except asyncio.CancelledError:
            print(f"ℹ️ Question TTS task cancelled (q_index={question_index})")
            return
        except Exception as exc:
            print(f"⚠️ TTS failed (non-blocking): {exc}")
            _log_session_event(
                session,
                "question_audio_error",
                event_source="tts",
                question_number=(question_index + 1) if question_index is not None else None,
                details={"error": str(exc)},
            )
            await sio.emit(
                "tts_error",
                {"error": "Question audio generation failed; continuing without audio.", "user_id": session.user_id},
                room=session.sid,
            )

    def cancel_question_tts(session):
        """Cancel in-flight per-question TTS task and any pre-fetch tasks."""
        task = getattr(session, "question_tts_task", None)
        if task and not task.done():
            task.cancel()
        session.question_tts_task = None
        for t in session.tts_prefetch_tasks.values():
            if not t.done():
                t.cancel()
        session.tts_prefetch_tasks.clear()
        session.tts_prefetch_cache.clear()

    async def start_interview(sid, data):
        """
        Start personalized interview practice session.
        """
        session = await deps.require_socket_auth(sid)
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

        await sio.emit("status", {"stage": "generating_questions", "user_id": session.user_id}, room=session.sid)

        try:
            from server.agents.interview_nodes import generate_interview_questions
            from server.services.cache import get_question_cache

            if requested_question_count is None:
                try:
                    prefs = deps.get_user_db().get_user_preferences(session.user_id) or {}
                    pref_count = prefs.get("question_count_override")
                    if pref_count not in (None, ""):
                        requested_question_count = max(1, min(12, int(pref_count)))
                except Exception:
                    requested_question_count = None

            if requested_persona not in {"friendly", "strict"}:
                try:
                    prefs_for_persona = deps.get_user_db().get_user_preferences(session.user_id) or {}
                    requested_persona = str(prefs_for_persona.get("interviewer_persona") or "friendly").strip().lower()
                except Exception:
                    requested_persona = "friendly"
            if requested_persona not in {"friendly", "strict"}:
                requested_persona = "friendly"

            if requested_tts_style not in deps.allowed_piper_styles:
                try:
                    prefs_for_tts = deps.get_user_db().get_user_preferences(session.user_id) or {}
                    requested_tts_style = deps.normalize_piper_style(
                        prefs_for_tts.get("piper_style"),
                        fallback="interviewer",
                    )
                except Exception:
                    requested_tts_style = "interviewer"
            requested_tts_style = deps.normalize_piper_style(requested_tts_style, fallback="interviewer")

            if requested_tts_provider not in deps.allowed_tts_providers:
                try:
                    prefs_for_tts_provider = deps.get_user_db().get_user_preferences(session.user_id) or {}
                    requested_tts_provider = deps.normalize_tts_provider(
                        prefs_for_tts_provider.get("tts_provider"),
                        fallback="piper",
                    )
                except Exception:
                    requested_tts_provider = "piper"
            requested_tts_provider = deps.normalize_tts_provider(requested_tts_provider, fallback="piper")

            db_session_id = str(uuid.uuid4())
            plan_node_id = data.get("suggestion_id")

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

            async def progress_cb(stage, msg):
                await sio.emit("status", {"stage": msg, "user_id": session.user_id}, room=session.sid)

            cache = get_question_cache()
            suggestion_id = data.get("suggestion_id")
            session_id = data.get("session_id", suggestion_id)
            cached_questions = None
            cache_key = None
            job_title = data.get("job_title", "generic")
            safe_title = re.sub(r"[^a-zA-Z0-9]", "_", job_title).lower()
            question_suffix = f"_q{requested_question_count}" if requested_question_count else ""
            persona_suffix = f"_p{requested_persona}"

            if suggestion_id or session_id:
                base_keys = [
                    f"{session.user_id}_{safe_title}_{suggestion_id}",
                    f"{session.user_id}_{safe_title}_{session_id}",
                    f"{session.user_id}_{suggestion_id}",
                    f"{session.user_id}_{session_id}",
                ]
                persona_keys = [f"{key}{question_suffix}{persona_suffix}" for key in base_keys]
                persona_no_q_keys = [f"{key}{persona_suffix}" for key in base_keys] if question_suffix else []
                legacy_keys = []
                if requested_persona == "friendly":
                    legacy_keys = [f"{key}{question_suffix}" for key in base_keys] if question_suffix else []
                    legacy_keys += list(base_keys)
                possible_keys = persona_keys + persona_no_q_keys + legacy_keys

                for key in possible_keys:
                    if key:
                        cached_questions = cache.get(key)
                        if cached_questions:
                            cache_key = key
                            break

                if not cache_key and suggestion_id:
                    cache_key = f"{session.user_id}_{safe_title}_{suggestion_id}{question_suffix}{persona_suffix}"
            else:
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

                normalized_title = re.sub(r"\s+", " ", str(data.get("job_title", "") or "").strip().lower())
                normalized_jd = re.sub(r"\s+", " ", str(data.get("job_description", "") or "").strip().lower())
                fingerprint_source = "|".join(
                    [
                        "quick_cache_v2",
                        str(session.user_id or ""),
                        normalized_title,
                        str(data.get("interview_type", "mixed") or "mixed").strip().lower(),
                        str(requested_persona),
                        str(requested_mode),
                        str(requested_feedback_timing),
                        str(bool(coaching_enabled)),
                        str(requested_question_count or ""),
                        ",".join(skill_values),
                        normalized_jd,
                    ]
                )
                auto_hash = hashlib.sha1(fingerprint_source.encode("utf-8")).hexdigest()[:16]
                cache_key = f"{session.user_id}_{safe_title}_auto_v2_{auto_hash}{question_suffix}{persona_suffix}"
                cached_questions = cache.get(cache_key)

            if cached_questions:
                cache_label = suggestion_id if suggestion_id else "direct_start"
                print(f"⚡ Using cached questions for {cache_label} (key: {cache_key})")
                await sio.emit("status", {"stage": "questions_ready", "user_id": session.user_id}, room=session.sid)
                result = {"questions": cached_questions}
            else:
                db_questions = None
                if suggestion_id:
                    try:
                        db_questions = deps.get_user_db().get_analysis_session_questions(
                            session.user_id,
                            suggestion_id,
                            interviewer_persona=requested_persona,
                        )
                    except Exception as exc:
                        print(f"⚠️ DB Fallback failed: {exc}")

                if db_questions:
                    print(f"💾 Using DB persisted questions for {suggestion_id}")
                    await sio.emit("status", {"stage": "questions_ready", "user_id": session.user_id}, room=session.sid)
                    result = {"questions": db_questions}
                    if cache_key:
                        cache.set(cache_key, db_questions)
                else:
                    result = await generate_interview_questions(interview_state, progress_cb)
                    if cache_key and result.get("questions"):
                        cache.set(cache_key, result["questions"])

            if requested_question_count and result.get("questions"):
                result["questions"] = result["questions"][:requested_question_count]

            if suggestion_id and result.get("questions"):
                try:
                    deps.get_user_db().set_latest_analysis_session_questions(
                        user_id=session.user_id,
                        session_id=suggestion_id,
                        questions=result["questions"],
                        interviewer_persona=requested_persona,
                    )
                except Exception as exc:
                    print(f"⚠️ Failed to persist persona questions for {suggestion_id}: {exc}")

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
            session.hints_given = []
            session.answer_submission_in_flight = False
            session.accept_audio_chunks = False
            session.end_requested = False
            session.job_title = data.get("job_title", "Software Engineer")
            session.clear_for_new_question()
            session.db_session_id = db_session_id

            user_db = deps.get_user_db()
            user_db.create_session(
                user_id=session.user_id,
                session_id=db_session_id,
                job_title=session.job_title,
                mode=session.interview_mode,
                total_questions=len(session.interview_questions),
                plan_node_id=plan_node_id,
            )
            _log_session_event(
                session,
                "interview_started",
                details={
                    "job_title": session.job_title,
                    "mode": session.interview_mode,
                    "feedback_timing": session.interview_feedback_timing,
                    "coaching_enabled": session.coaching_enabled,
                    "live_scoring": session.live_scoring_enabled,
                    "interviewer_persona": session.interviewer_persona,
                    "tts_style": session.tts_style,
                    "tts_provider": session.tts_provider,
                    "total_questions": len(session.interview_questions),
                    "suggestion_id": suggestion_id,
                    "used_cached_questions": bool(cached_questions),
                },
            )

            first_q = session.interview_questions[0]
            session.answer_start_time = time.time()

            await sio.emit(
                "interview_started",
                {
                    "session_id": db_session_id,
                    "total_questions": len(session.interview_questions),
                    "mode": session.interview_mode,
                    "coaching_enabled": session.coaching_enabled,
                    "interviewer_persona": session.interviewer_persona,
                    "piper_style": session.tts_style,
                    "tts_provider": session.tts_provider,
                    "feedback_timing": session.interview_feedback_timing,
                    "live_scoring": session.live_scoring_enabled,
                    "user_id": session.user_id,
                },
                room=session.sid,
            )

            await sio.emit(
                "interview_question",
                {
                    "question": first_q,
                    "question_number": 1,
                    "total_questions": len(session.interview_questions),
                    "user_id": session.user_id,
                },
                room=session.sid,
            )
            _log_session_event(
                session,
                "question_presented",
                question_number=1,
                details={**_question_log_details(first_q), "trigger": "session_start"},
            )

            cancel_question_tts(session)
            session.question_tts_task = asyncio.create_task(send_question_tts(session, first_q["text"], question_index=0))

            async def send_initial_tip():
                try:
                    from server.services.coaching_service import generate_coaching_hint

                    hint = await generate_coaching_hint(
                        transcript="",
                        question=first_q,
                        previous_hints=[],
                        hint_level=0,
                    )

                    if hint:
                        hint_message = hint["message"] if isinstance(hint, dict) else str(hint)
                        payload = {"message": hint_message, "level": 0, "user_id": session.user_id}
                        if isinstance(hint, dict):
                            payload.update({k: v for k, v in hint.items() if k != "message"})
                        await sio.emit("coaching_hint", payload, room=session.sid)
                        print(f"💡 Initial tip: {hint_message}")
                        _log_session_event(
                            session,
                            "hint_sent",
                            event_source="coaching",
                            question_number=1,
                            details={
                                "hint_origin": "initial_tip",
                                "hint_level": 0,
                                "message": hint_message,
                            },
                        )
                except Exception as exc:
                    print(f"⚠️ Initial tip generation skipped: {exc}")
                    _log_session_event(
                        session,
                        "hint_error",
                        event_source="coaching",
                        question_number=1,
                        details={"hint_origin": "initial_tip", "error": str(exc)},
                    )

            if session.coaching_enabled:
                asyncio.create_task(send_initial_tip())
        except Exception as exc:
            print(f"❌ Error starting interview: {exc}")
            import traceback

            traceback.print_exc()
            _log_session_event(
                session,
                "interview_start_error",
                details={"error": str(exc)},
            )
            await sio.emit("interview_error", {"error": str(exc), "user_id": session.user_id}, room=session.sid)

    async def submit_interview_answer(sid, data):
        """
        Submit answer to current interview question.
        Immediately advances to the next question; evaluation runs in the background.
        """
        session = deps.sessions.get(sid)
        if not session or not session.interview_active:
            return
        data = data or {}
        session.accept_audio_chunks = False
        if session.answer_submission_in_flight:
            await sio.emit("status", {"stage": "answer_already_submitting", "user_id": session.user_id}, room=session.sid)
            return

        session.answer_submission_in_flight = True
        try:
            current_q = session.interview_questions[session.current_question_index]
            q_index = session.current_question_index
            await deps.finalize_current_utterance(session, reason="force")
            user_answer = data.get("answer", "")
            used_transcript = False

            if not user_answer.strip():
                used_transcript = True
                user_answer = session.finalized_answer_transcript.strip() or session.current_answer_transcript.strip()
                print(f"📝 Using finalized transcript ({len(user_answer)} chars)")

            if not user_answer.strip():
                _log_session_event(
                    session,
                    "answer_rejected",
                    question_number=q_index + 1,
                    details={"reason": "no_answer_detected", "used_transcript": used_transcript},
                )
                await sio.emit(
                    "interview_error",
                    {"error": "No answer detected. Please speak your answer.", "user_id": session.user_id},
                    room=session.sid,
                )
                return

            if used_transcript:
                is_valid_submission, rejection_reason = deps.assess_submitted_transcript(
                    user_answer,
                    question_text=current_q.get("text", ""),
                )
                if not is_valid_submission:
                    print(f"🔇 Rejected low-confidence transcript submission: {user_answer!r}")
                    _log_session_event(
                        session,
                        "answer_rejected",
                        question_number=q_index + 1,
                        details={
                            "reason": rejection_reason,
                            "used_transcript": True,
                            "answer_length": len(user_answer),
                        },
                    )
                    await sio.emit(
                        "interview_error",
                        {"error": rejection_reason, "user_id": session.user_id},
                        room=session.sid,
                    )
                    return

            duration = data.get("duration_seconds", 0)
            eval_entry = {
                "question": current_q,
                "answer": user_answer,
                "evaluation": None,
                "duration": duration,
            }
            session.evaluations.append(eval_entry)
            _log_session_event(
                session,
                "answer_submitted",
                question_number=q_index + 1,
                details={
                    "answer_length": len(user_answer),
                    "duration_seconds": duration,
                    "answer_source": ("transcript" if used_transcript else "payload"),
                },
            )

            if not hasattr(session, "_pending_eval_tasks"):
                session._pending_eval_tasks = []

            async def _bg_evaluate(entry, q_idx):
                from server.agents.interview_nodes import evaluate_answer_stream

                try:
                    user_thresholds = deps.get_user_feedback_thresholds(session.user_id)

                    async def eval_callback(msg_type, content):
                        return None

                    evaluation = await evaluate_answer_stream(
                        entry["question"],
                        entry["answer"],
                        eval_callback,
                        thresholds=user_thresholds,
                    )
                    deps.record_evaluation_metrics(evaluation)
                    entry["evaluation"] = evaluation
                    print(f"📝 Evaluation: Score {evaluation.get('score', '?')}/10 (Q{q_idx + 1}, background)")

                    db_sid = getattr(session, "db_session_id", None)
                    if db_sid:
                        deps.get_user_db().save_answer(
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
                    _log_session_event(
                        session,
                        "answer_evaluated",
                        question_number=q_idx + 1,
                        details={
                            "score": evaluation.get("score"),
                            "quality_flags": evaluation.get("quality_flags", []),
                        },
                    )
                except Exception as exc:
                    print(f"⚠️ Background evaluation failed (Q{q_idx + 1}): {exc}")
                    entry["evaluation"] = {"score": 0, "feedback": "Evaluation failed.", "error": True}
                    _log_session_event(
                        session,
                        "answer_evaluation_failed",
                        question_number=q_idx + 1,
                        details={"error": str(exc)},
                    )

            task = asyncio.create_task(_bg_evaluate(eval_entry, q_index))
            session._pending_eval_tasks.append(task)

            if session.end_requested:
                await finish_interview(sid, session)
                return

            session.current_question_index += 1

            if session.current_question_index < len(session.interview_questions):
                next_q = session.interview_questions[session.current_question_index]
                session.clear_for_new_question()
                session.answer_start_time = time.time()

                await sio.emit(
                    "interview_question",
                    {
                        "question": next_q,
                        "question_number": session.current_question_index + 1,
                        "total_questions": len(session.interview_questions),
                        "user_id": session.user_id,
                    },
                    room=session.sid,
                )
                _log_session_event(
                    session,
                    "question_presented",
                    question_number=session.current_question_index + 1,
                    details={**_question_log_details(next_q), "trigger": "answer_advanced"},
                )

                # Re-check: user may have requested end while we yielded on the emit.
                if session.end_requested:
                    cancel_question_tts(session)
                    await finish_interview(sid, session)
                    return

                cancel_question_tts(session)
                session.question_tts_task = asyncio.create_task(
                    send_question_tts(session, next_q["text"], question_index=session.current_question_index)
                )
            else:
                await finish_interview(sid, session)
        except Exception as exc:
            print(f"❌ Error submitting answer: {exc}")
            import traceback

            traceback.print_exc()
            _log_session_event(
                session,
                "answer_submit_error",
                question_number=(getattr(session, "current_question_index", 0) + 1),
                details={"error": str(exc)},
            )
            await sio.emit("interview_error", {"error": str(exc), "user_id": session.user_id}, room=session.sid)
        finally:
            session.answer_submission_in_flight = False

    async def finish_interview(sid: str, session):
        """Complete interview and generate summary report."""
        from server.agents.interview_nodes import generate_interview_summary

        session.accept_audio_chunks = False
        session.end_requested = False
        cancel_question_tts(session)

        await sio.emit("generating_report", {"user_id": session.user_id}, room=session.sid)

        pending_tasks = getattr(session, "_pending_eval_tasks", [])
        if pending_tasks:
            n_pending = sum(1 for task in pending_tasks if not task.done())
            if n_pending:
                print(f"⏳ Waiting for {n_pending} pending evaluation(s)…")
            await asyncio.gather(*pending_tasks, return_exceptions=True)
            session._pending_eval_tasks = []

        for entry in session.evaluations:
            if entry.get("evaluation") is None:
                entry["evaluation"] = {"score": 0, "feedback": "Evaluation unavailable.", "error": True}

        try:
            summary = await generate_interview_summary(session.evaluations)
        except Exception as exc:
            print(f"⚠️ Summary generation failed in finish_interview: {exc}")
            _log_session_event(
                session,
                "interview_summary_failed",
                details={"error": str(exc)},
            )
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

        try:
            db_sid = getattr(session, "db_session_id", None)
            if db_sid:
                user_db = deps.get_user_db()
                user_db.complete_session(db_sid, summary)
                updated_queue = user_db.append_report_actions(session.user_id, summary, session_id=db_sid)
                await sio.emit("action_queue", {"actions": updated_queue, "user_id": session.user_id}, room=session.sid)
            else:
                print("⚠️ No db_session_id found, session summary not saved to DB")
        except Exception as exc:
            print(f"⚠️ Failed persisting completed interview {getattr(session, 'db_session_id', 'unknown')}: {exc}")

        session.interview_active = False
        _log_session_event(
            session,
            "interview_completed",
            details={
                "total_questions": summary.get("total_questions"),
                "answered_questions": summary.get("answered_questions"),
                "skipped_questions": summary.get("skipped_questions"),
                "average_score": summary.get("average_score"),
                "evaluation_status": summary.get("evaluation_status"),
            },
        )

        await sio.emit(
            "interview_complete",
            {
                "session_id": getattr(session, "db_session_id", None),
                "summary": summary,
                "evaluations": session.evaluations,
                "message": f"Interview complete! Average score: {summary.get('average_score', 0)}/10",
                "user_id": session.user_id,
            },
            room=session.sid,
        )

        if deps.settings.FEEDBACK_LOOP_V2:
            retries = deps.feedback_metrics["retries_total"]
            avg_delta = (deps.feedback_metrics["retry_delta_sum"] / retries) if retries else 0.0
            eval_total = max(1, deps.feedback_metrics["evaluations_total"])
            low_quality_rate = deps.feedback_metrics["low_transcript_quality"] / eval_total
            retry_usage_rate = retries / eval_total
            retry_success_rate = (deps.feedback_metrics["retry_improved_count"] / retries) if retries else 0.0
            avg_score_v1 = (
                deps.feedback_metrics["score_sum_v1"] / deps.feedback_metrics["score_count_v1"]
                if deps.feedback_metrics["score_count_v1"]
                else 0.0
            )
            avg_score_v2 = (
                deps.feedback_metrics["score_sum_v2"] / deps.feedback_metrics["score_count_v2"]
                if deps.feedback_metrics["score_count_v2"]
                else 0.0
            )
            print(
                "📊 Feedback v2 metrics: eval=%s v2=%s low_stt=%s (%.2f) retries=%s retry_usage=%.2f retry_success=%.2f avg_delta=%.2f avg_v1=%.2f avg_v2=%.2f"
                % (
                    deps.feedback_metrics["evaluations_total"],
                    deps.feedback_metrics["evaluations_v2"],
                    deps.feedback_metrics["low_transcript_quality"],
                    low_quality_rate,
                    retries,
                    retry_usage_rate,
                    retry_success_rate,
                    avg_delta,
                    avg_score_v1,
                    avg_score_v2,
                )
            )

    async def check_struggle(sid, data):
        """Check if candidate is struggling (called periodically by client)."""
        session = deps.sessions.get(sid)
        if not session or not session.coaching_enabled or not session.interview_active:
            return

        try:
            from server.agents.interview_nodes import detect_struggle_and_coach

            current_q = session.interview_questions[session.current_question_index]
            hint = await detect_struggle_and_coach(
                data.get("transcript", ""),
                data.get("silence_duration", 0),
                current_q,
            )
            if hint:
                await sio.emit("coaching_hint", {**hint, "user_id": session.user_id}, room=session.sid)
                _log_session_event(
                    session,
                    "hint_sent",
                    event_source="coaching",
                    question_number=session.current_question_index + 1,
                    details={
                        "hint_origin": "struggle_check",
                        "message": hint.get("message"),
                        "silence_duration": data.get("silence_duration", 0),
                    },
                )
        except Exception as exc:
            print(f"⚠️ Struggle detection error: {exc}")
            _log_session_event(
                session,
                "hint_error",
                event_source="coaching",
                question_number=session.current_question_index + 1,
                details={"hint_origin": "struggle_check", "error": str(exc)},
            )

    async def toggle_coaching(sid, data):
        """Enable/disable real-time coaching hints."""
        session = deps.sessions.get(sid)
        if session:
            session.coaching_enabled = data.get("enabled", False)
            _log_session_event(
                session,
                "coaching_toggled",
                event_source="coaching",
                question_number=(session.current_question_index + 1) if session.interview_active else None,
                details={"enabled": session.coaching_enabled},
            )
            await sio.emit(
                "coaching_toggled",
                {"enabled": session.coaching_enabled, "user_id": session.user_id},
                room=session.sid,
            )

    async def skip_question(sid, data):
        """Skip current question and move to next."""
        session = deps.sessions.get(sid)
        if not session or not session.interview_active:
            return
        if session.answer_submission_in_flight:
            return
        if session.current_question_index >= len(session.interview_questions):
            return
        session.answer_submission_in_flight = True
        session.accept_audio_chunks = False

        try:
            cancel_question_tts(session)
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
            session.evaluations.append(
                {
                    "question": current_q,
                    "answer": "(Skipped)",
                    "evaluation": skip_eval,
                    "duration": 0,
                    "skipped": True,
                }
            )

            db_sid = getattr(session, "db_session_id", None)
            if db_sid:
                deps.get_user_db().save_answer(
                    session_id=db_sid,
                    question_number=session.current_question_index + 1,
                    question_text=current_q.get("text", ""),
                    question_category=current_q.get("category", "Technical"),
                    question_difficulty=current_q.get("difficulty", "intermediate"),
                    user_answer="(Skipped)",
                    evaluation=skip_eval,
                    duration_seconds=0,
                    skipped=True,
                )
            _log_session_event(
                session,
                "question_skipped",
                question_number=session.current_question_index + 1,
                details=_question_log_details(current_q),
            )

            session.current_question_index += 1

            if session.current_question_index < len(session.interview_questions):
                next_q = session.interview_questions[session.current_question_index]
                session.clear_for_new_question()
                session.answer_start_time = time.time()

                await sio.emit(
                    "interview_question",
                    {
                        "question": next_q,
                        "question_number": session.current_question_index + 1,
                        "total_questions": len(session.interview_questions),
                        "user_id": session.user_id,
                    },
                    room=session.sid,
                )
                _log_session_event(
                    session,
                    "question_presented",
                    question_number=session.current_question_index + 1,
                    details={**_question_log_details(next_q), "trigger": "question_skipped"},
                )

                cancel_question_tts(session)
                session.question_tts_task = asyncio.create_task(
                    send_question_tts(session, next_q["text"], question_index=session.current_question_index)
                )
            else:
                await finish_interview(sid, session)
        finally:
            session.answer_submission_in_flight = False

    async def end_interview_early(sid, data=None):
        """End interview before all questions are answered."""
        session = deps.sessions.get(sid)
        if not session or not session.interview_active:
            return
        session.accept_audio_chunks = False
        session.end_requested = True
        cancel_question_tts(session)
        _log_session_event(
            session,
            "interview_end_requested",
            details={
                "current_question_number": session.current_question_index + 1,
                "answer_submission_in_flight": bool(session.answer_submission_in_flight),
            },
        )

        if session.answer_submission_in_flight:
            await sio.emit(
                "status",
                {"stage": "ending_after_current_evaluation", "user_id": session.user_id},
                room=session.sid,
            )
            return

        try:
            await deps.finalize_current_utterance(session, reason="force")
            current_q = session.interview_questions[session.current_question_index]
        except Exception:
            current_q = None

        if current_q:
            raw_answer = session.finalized_answer_transcript.strip() or session.current_answer_transcript.strip()
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

                session.evaluations.append(
                    {
                        "question": current_q,
                        "answer": raw_answer,
                        "evaluation": partial_eval,
                        "duration": duration,
                        "skipped": True,
                    }
                )

                db_sid = getattr(session, "db_session_id", None)
                if db_sid:
                    try:
                        deps.get_user_db().save_answer(
                            session_id=db_sid,
                            question_number=session.current_question_index + 1,
                            question_text=current_q.get("text", ""),
                            question_category=current_q.get("category", "Technical"),
                            question_difficulty=current_q.get("difficulty", "intermediate"),
                            user_answer=raw_answer,
                            evaluation=partial_eval,
                            duration_seconds=duration,
                            skipped=True,
                        )
                    except Exception as exc:
                        print(f"⚠️ Failed saving partial end-interview answer: {exc}")
                _log_session_event(
                    session,
                    "partial_answer_saved",
                    question_number=session.current_question_index + 1,
                    details={
                        "answer_length": len(raw_answer),
                        "duration_seconds": duration,
                    },
                )

        try:
            await finish_interview(sid, session)
        except Exception as exc:
            print(f"❌ end_interview_early fallback path: {exc}")
            _log_session_event(
                session,
                "interview_end_error",
                details={"error": str(exc)},
            )
            session.interview_active = False
            await sio.emit(
                "interview_complete",
                {
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
                    "user_id": session.user_id,
                },
                room=session.sid,
            )

    sio.on("request_hint", handler=request_hint)
    sio.on("start_interview", handler=start_interview)
    sio.on("submit_interview_answer", handler=submit_interview_answer)
    sio.on("check_struggle", handler=check_struggle)
    sio.on("toggle_coaching", handler=toggle_coaching)
    sio.on("skip_question", handler=skip_question)
    sio.on("end_interview_early", handler=end_interview_early)

    return SimpleNamespace(
        request_hint=request_hint,
        send_question_tts=send_question_tts,
        cancel_question_tts=cancel_question_tts,
        start_interview=start_interview,
        submit_interview_answer=submit_interview_answer,
        finish_interview=finish_interview,
        check_struggle=check_struggle,
        toggle_coaching=toggle_coaching,
        skip_question=skip_question,
        end_interview_early=end_interview_early,
    )
