"""Socket.IO preference, history, and career-analysis event registration."""

import asyncio
from datetime import datetime
from types import SimpleNamespace


def register_preferences_events(sio, deps):
    """Register user preference, history, and career-analysis Socket.IO events."""

    def extract_resume_text_from_payload(resume_payload):
        """Decode a base64 PDF payload into extracted resume text."""
        import base64
        from server.tools.resume_tool import extract_text_from_pdf_bytes

        payload = str(resume_payload or "").strip()
        if not payload:
            return ""

        pdf_bytes = base64.b64decode(payload.split(",")[-1])
        return extract_text_from_pdf_bytes(pdf_bytes)

    async def save_preferences(sid, data):
        """Save user preferences (resume, target role, focus areas)."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        data = data or {}
        user_id = deps.get_uid(sid, data)
        user_db = deps.get_user_db()

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
        normalized_thresholds = deps.normalize_feedback_thresholds(incoming_thresholds)
        incoming_recording_thresholds = data.get("recording_thresholds", existing.get("recording_thresholds", {}))
        normalized_recording_thresholds = deps.normalize_recording_thresholds(incoming_recording_thresholds)

        incoming_persona = str(data.get("interviewer_persona", existing.get("interviewer_persona", "friendly")) or "friendly").strip().lower()
        if incoming_persona not in {"friendly", "strict"}:
            incoming_persona = str(existing.get("interviewer_persona") or "friendly").strip().lower() or "friendly"

        incoming_piper_style = deps.normalize_piper_style(
            data.get("piper_style", existing.get("piper_style", "interviewer")),
            fallback=existing.get("piper_style", "interviewer"),
        )
        incoming_tts_provider = deps.normalize_tts_provider(
            data.get("tts_provider", existing.get("tts_provider", "piper")),
            fallback=existing.get("tts_provider", "piper"),
        )
        incoming_target_role = deps.first_present(
            data,
            ("target_role", "job_title", "targetRole", "jobTitle"),
            existing.get("target_role"),
        )
        incoming_target_company = deps.first_present(
            data,
            ("target_company", "company", "targetCompany"),
            existing.get("target_company"),
        )
        incoming_job_description = deps.first_present(
            data,
            ("job_description", "jobDescription"),
            existing.get("job_description"),
        )
        incoming_job_description = str(incoming_job_description or "").strip()
        if not incoming_job_description and str(existing.get("job_description") or "").strip():
            incoming_job_description = str(existing.get("job_description") or "")

        incoming_resume = deps.first_present(data, ("resume", "resume_base64", "resumeBase64"), "")
        resume_text = data.get("resume_text", existing.get("resume_text"))
        resume_filename = data.get("resume_filename", existing.get("resume_filename"))
        if incoming_resume:
            try:
                resume_text = extract_resume_text_from_payload(incoming_resume)
                if not resume_filename:
                    resume_filename = f"resume_{user_id}.pdf"
            except Exception as exc:
                error_message = f"Failed to save resume: {exc}"
                print(f"❌ Save preferences failed for {user_id}: {error_message}")
                await sio.emit(
                    "preferences_saved",
                    {"success": False, "error": error_message, "user_id": user_id},
                    room=str(user_id),
                )
                return

        preferences = {
            "resume_text": resume_text,
            "resume_filename": resume_filename,
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
            "mic_permission_granted": data.get("mic_permission_granted", existing.get("mic_permission_granted", False)),
            "has_seen_tour": data.get("has_seen_tour", existing.get("has_seen_tour", False)),
        }

        user_db.save_user_preferences(user_id, preferences)
        await sio.emit(
            "preferences_saved",
            {
                "success": True,
                "user_id": user_id,
                "has_resume": bool(str(preferences.get("resume_text") or "").strip()),
                "resume_filename": preferences.get("resume_filename"),
            },
            room=str(user_id),
        )
        print(f"✅ Saved preferences for {user_id}")

    async def start_career_analysis(sid, data=None):
        """
        Start the full career analysis process.
        Can use saved preferences OR accept new resume/job_title in data.
        Implements Resource Guard pattern for cancellation.
        """
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        data = data or {}
        user_id = deps.get_uid(sid, data)
        force_refresh = bool(data.get("force_refresh", False))
        print(f"🚀 Starting career analysis for {user_id}")
        if force_refresh:
            print(f"🔁 Force refresh enabled for {user_id}")

        existing_task = deps.active_tasks.get(user_id)
        if existing_task and not existing_task.done():
            existing_task.cancel()
            print(f"🛑 Cancelled previous task for {user_id} (double-click prevention)")

        user_db = deps.get_user_db()
        existing_prefs = user_db.get_user_preferences(user_id) or {}
        incoming_resume = deps.first_present(data, ("resume", "resume_base64", "resumeBase64"), "")
        incoming_job_title = deps.first_present(
            data,
            ("job_title", "target_role", "jobTitle", "targetRole"),
            existing_prefs.get("target_role"),
        )
        incoming_company = deps.first_present(
            data,
            ("company", "target_company", "targetCompany"),
            existing_prefs.get("target_company", "Tech Company"),
        )
        incoming_job_description = deps.first_present(
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
            except Exception as exc:
                print(f"⚠️ Failed to clear cache for force refresh: {exc}")

        if data and incoming_resume and incoming_job_title:
            print("📝 New resume provided, saving preferences first...")
            resume_text = ""
            try:
                resume_text = extract_resume_text_from_payload(incoming_resume)
            except Exception as exc:
                print(f"❌ Resume extraction failed: {exc}")
                await sio.emit(
                    "analysis_error",
                    {"error": f"Failed to extract resume text: {exc}", "user_id": user_id},
                    room=str(user_id),
                )
                return

            preferences = {
                "resume_text": resume_text,
                "resume_filename": data.get("resume_filename") or existing_prefs.get("resume_filename") or f"resume_{user_id}.pdf",
                "target_role": incoming_job_title,
                "target_company": incoming_company,
                "job_description": incoming_job_description,
                "question_count_override": existing_prefs.get("question_count_override"),
                "interviewer_persona": existing_prefs.get("interviewer_persona", "friendly"),
                "piper_style": existing_prefs.get("piper_style", "interviewer"),
                "tts_provider": existing_prefs.get("tts_provider", "piper"),
                "evaluation_thresholds": existing_prefs.get("evaluation_thresholds", {}),
                "recording_thresholds": existing_prefs.get("recording_thresholds", {}),
                "focus_areas": [],
            }
            user_db.save_user_preferences(user_id, preferences)
            print(f"✅ Saved new preferences for {user_id}")
        elif data and any(
            key in data
            for key in (
                "job_title",
                "company",
                "job_description",
                "target_role",
                "target_company",
                "jobDescription",
                "jobTitle",
                "targetRole",
                "targetCompany",
            )
        ):
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

        prefs = user_db.get_user_preferences(user_id)
        print(
            "📌 Loaded preferences for analysis: "
            f"target_role='{prefs.get('target_role') if prefs else ''}', "
            f"jd_len={len(str((prefs or {}).get('job_description') or ''))}"
        )

        if not prefs or not prefs.get("resume_text") or not prefs.get("target_role"):
            print(f"❌ Analysis failed: Missing prefs for {user_id}. Prefs: {prefs}")
            missing_parts = []
            if not prefs or not str(prefs.get("resume_text") or "").strip():
                missing_parts.append("resume")
            if not prefs or not str(prefs.get("target_role") or "").strip():
                missing_parts.append("target role")
            missing_summary = " and ".join(missing_parts) if missing_parts else "required profile data"
            await sio.emit(
                "analysis_error",
                {"error": f"Missing {missing_summary}. Upload or save a resume, then try again.", "user_id": user_id},
                room=str(user_id),
            )
            return

        if not str(prefs.get("job_description", "")).strip():
            await sio.emit(
                "analysis_error",
                {"error": "Job description is required before running analysis.", "user_id": user_id},
                room=str(user_id),
            )
            return

        async def emit_progress(event_type: str, message: str):
            await sio.emit(
                "analysis_progress",
                {
                    "stage": event_type,
                    "message": message,
                    "timestamp": datetime.now().isoformat(),
                    "user_id": user_id,
                },
                room=str(user_id),
            )

        async def run_analysis():
            try:
                import json
                from server.agents.nodes import (
                    analyze_career_path,
                    normalize_practice_plan_titles,
                    trigger_background_generation,
                )

                result = await analyze_career_path(
                    resume_text=prefs["resume_text"],
                    target_role=prefs["target_role"],
                    target_company=prefs.get("target_company", "Tech Company"),
                    job_description=prefs.get("job_description", ""),
                    emit_progress=emit_progress,
                )

                if result.get("error"):
                    await sio.emit("analysis_error", {"error": result["error"], "user_id": user_id}, room=str(user_id))
                    return

                result["job_description"] = prefs.get("job_description", "")
                if isinstance(result.get("practice_plan"), dict):
                    result["practice_plan"] = normalize_practice_plan_titles(result["practice_plan"])

                try:
                    json.dumps(result)
                except (TypeError, ValueError) as exc:
                    print(f"⚠️ Result contains non-serializable data: {exc}")
                    result = json.loads(json.dumps(result, default=str))

                user_db.save_career_analysis(
                    user_id,
                    prefs["target_role"],
                    prefs.get("target_company", "Tech Company"),
                    result,
                    job_description=prefs.get("job_description", ""),
                )

                try:
                    safe_result = {
                        "job_title": prefs["target_role"],
                        "company": prefs.get("target_company"),
                        "readiness_score": result.get("readiness_score"),
                        "skill_gaps": result.get("skill_gaps"),
                        "bridge_roles": result.get("bridge_roles"),
                        "suggested_sessions": result.get("suggested_sessions", []),
                        "practice_plan": result.get("practice_plan"),
                        "analysis_data": result,
                    }
                    json.dumps(safe_result)
                    await sio.emit("career_analysis", {"analysis": safe_result, "user_id": user_id}, room=str(user_id))
                    print(f"✅ Career analysis completed for {user_id}")
                    trigger_background_generation(user_id, result, force_refresh=force_refresh)
                except (TypeError, ValueError) as json_err:
                    print(f"⚠️ JSON serialization error in career_analysis result: {json_err}")
                    safe_fallback = {
                        "job_title": prefs["target_role"],
                        "company": prefs.get("target_company"),
                        "readiness_score": result.get("readiness_score", 0.5),
                        "skill_gaps": result.get("skill_gaps", []),
                        "bridge_roles": result.get("bridge_roles", []),
                        "analysis_data": {"mindmap": "[Mindmap rendering error - see console]"},
                        "suggested_sessions": result.get("suggested_sessions", []),
                    }
                    await sio.emit("career_analysis", {"analysis": safe_fallback, "user_id": user_id}, room=str(user_id))
                    print(f"⚠️ Career analysis completed with fallback for {user_id}")
            except asyncio.CancelledError:
                print(f"🛑 Analysis task cancelled for {user_id}")
                raise
            except Exception as exc:
                import traceback

                print(f"❌ Analysis failed: {exc}")
                traceback.print_exc()
                await sio.emit("analysis_error", {"error": str(exc), "user_id": user_id}, room=str(user_id))
            finally:
                if deps.active_tasks.get(user_id) is asyncio.current_task():
                    deps.active_tasks.pop(user_id, None)

        task = asyncio.create_task(run_analysis())
        deps.active_tasks[user_id] = task

    async def get_preferences(sid, data=None):
        """Get user preferences."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        preferences = deps.get_user_db().get_user_preferences(user_id)
        await sio.emit("user_preferences", {"preferences": preferences or {}, "user_id": user_id}, room=str(user_id))

    async def get_interview_history(sid, data=None):
        """Get user's interview session history."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        limit = (data or {}).get("limit", 20)
        history = deps.get_user_db().get_session_history(user_id, limit)
        await sio.emit("interview_history", {"history": history, "user_id": user_id}, room=str(user_id))

    async def get_session_details(sid, data=None):
        """Get full details of a specific interview session including all answers."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        session_id = (data or {}).get("session_id")
        if not session_id:
            await sio.emit("session_details_error", {"error": "session_id required", "user_id": user_id}, room=str(user_id))
            return

        details = deps.get_user_db().get_session_details(session_id)
        if not details:
            await sio.emit("session_details_error", {"error": "Session not found", "user_id": user_id}, room=str(user_id))
            return
        if details.get("user_id") != user_id:
            await sio.emit("session_details_error", {"error": "Access denied", "user_id": user_id}, room=str(user_id))
            return

        await sio.emit("session_details", {"session": details, "user_id": user_id}, room=str(user_id))

    async def get_retry_attempts(sid, data=None):
        """Get retry attempts for a specific question in a completed session."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        payload = data or {}
        user_id = deps.get_uid(sid, payload)
        session_id = str(payload.get("session_id") or "").strip()
        question_number = payload.get("question_number")
        try:
            question_number = int(question_number)
        except Exception:
            question_number = None

        if not session_id or not question_number or question_number < 1:
            await sio.emit(
                "retry_error",
                {
                    "error": "session_id and valid question_number are required",
                    "session_id": session_id or None,
                    "question_number": question_number,
                    "user_id": user_id,
                },
                room=str(user_id),
            )
            return

        user_db = deps.get_user_db()
        owner_id = user_db.get_session_owner(session_id)
        if owner_id != user_id:
            await sio.emit(
                "retry_error",
                {
                    "error": "Access denied",
                    "session_id": session_id,
                    "question_number": question_number,
                    "user_id": user_id,
                },
                room=str(user_id),
            )
            return

        attempts = user_db.get_retry_attempts(session_id, question_number)
        await sio.emit(
            "retry_attempts",
            {
                "session_id": session_id,
                "question_number": question_number,
                "attempts": attempts,
                "user_id": user_id,
            },
            room=str(user_id),
        )

    async def submit_retry_answer(sid, data=None):
        """Evaluate and save a report-stage retry attempt for one question."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        payload = data or {}
        user_id = deps.get_uid(sid, payload)
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
            await sio.emit(
                "retry_error",
                {
                    "error": "session_id, question_number, and answer are required",
                    "session_id": session_id or None,
                    "question_number": question_number,
                    "user_id": user_id,
                },
                room=str(user_id),
            )
            return

        user_db = deps.get_user_db()
        owner_id = user_db.get_session_owner(session_id)
        if owner_id != user_id:
            await sio.emit(
                "retry_error",
                {
                    "error": "Access denied",
                    "session_id": session_id,
                    "question_number": question_number,
                    "user_id": user_id,
                },
                room=str(user_id),
            )
            return

        original = user_db.get_answer_record(session_id, question_number)
        if not original:
            await sio.emit(
                "retry_error",
                {
                    "error": "Original answer record not found",
                    "session_id": session_id,
                    "question_number": question_number,
                    "user_id": user_id,
                },
                room=str(user_id),
            )
            return

        user_db.ensure_original_retry_snapshot(session_id, question_number)

        original_eval = original.get("evaluation") or {}
        expected_points = original_eval.get("expected_points_used") or []
        if not isinstance(expected_points, list) or not expected_points:
            expected_points = (
                (original_eval.get("strengths") or [])
                + (original_eval.get("gaps") or original_eval.get("rubric_misses") or [])
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

        user_thresholds = deps.get_user_feedback_thresholds(user_id)

        async def retry_callback(msg_type, content):
            if msg_type == "status":
                await sio.emit("status", {"stage": f"retry_{content}", "user_id": user_id}, room=str(user_id))

        await sio.emit("status", {"stage": "retry_evaluating", "user_id": user_id}, room=str(user_id))
        evaluation = await evaluate_answer_stream(question_payload, answer, retry_callback, thresholds=user_thresholds)
        deps.record_evaluation_metrics(evaluation)

        baseline_score = float((original_eval or {}).get("score") or 0)
        attempt = user_db.save_retry_attempt(
            session_id=session_id,
            question_number=question_number,
            answer_text=answer,
            input_mode=input_mode,
            duration_seconds=duration_seconds,
            evaluation=evaluation,
            baseline_score=baseline_score,
        )
        promotion = user_db.promote_retry_if_higher(session_id, question_number, attempt)
        deps.record_retry_metrics(attempt.get("delta_score", 0))

        await sio.emit(
            "retry_evaluated",
            {
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
                "user_id": user_id,
            },
            room=str(user_id),
        )

    async def get_user_stats(sid, data=None):
        """Get user progress statistics."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        stats = deps.get_user_db().get_user_stats(user_id)
        await sio.emit("user_stats", {"stats": stats, "user_id": user_id}, room=str(user_id))

    async def get_action_queue(sid, data=None):
        """Get persisted dashboard action queue."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        queue = deps.get_user_db().get_action_queue(user_id)
        await sio.emit("action_queue", {"actions": queue, "user_id": user_id}, room=str(user_id))

    async def reset_analysis_workspace(sid, data=None):
        """Reset analysis workspace artifacts and clear resume/JD inputs."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        user_db = deps.get_user_db()
        user_db.reset_analysis_workspace(user_id)
        try:
            from server.services.cache import get_question_cache

            get_question_cache().delete_user_keys(user_id)
        except Exception as exc:
            print(f"⚠️ Failed to clear in-memory cache on workspace reset: {exc}")

        await sio.emit("career_analysis", {"analysis": None, "user_id": user_id}, room=str(user_id))
        await sio.emit("action_queue", {"actions": [], "user_id": user_id}, room=str(user_id))
        prefs = user_db.get_user_preferences(user_id) or {}
        await sio.emit("user_preferences", {"preferences": prefs, "user_id": user_id}, room=str(user_id))
        await sio.emit("workspace_reset", {"success": True, "user_id": user_id}, room=str(user_id))

    async def clear_configuration(sid, data=None):
        """Clear saved configuration fields (resume/role/company/JD/default persona/count)."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        user_db = deps.get_user_db()
        user_db.clear_user_configuration(user_id)
        try:
            from server.services.cache import get_question_cache

            get_question_cache().delete_user_keys(user_id)
        except Exception as exc:
            print(f"⚠️ Failed to clear question cache on configuration clear: {exc}")

        await sio.emit("career_analysis", {"analysis": None, "user_id": user_id}, room=str(user_id))
        await sio.emit("action_queue", {"actions": [], "user_id": user_id}, room=str(user_id))
        prefs = user_db.get_user_preferences(user_id) or {}
        await sio.emit("user_preferences", {"preferences": prefs, "user_id": user_id}, room=str(user_id))
        await sio.emit("configuration_cleared", {"success": True, "user_id": user_id}, room=str(user_id))

    async def delete_interview_history(sid, data=None):
        """Delete all interview history (sessions + answers + retries) for the authenticated user."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        deps.get_user_db().delete_interview_history(user_id)
        await sio.emit("interview_history", {"history": [], "user_id": user_id}, room=str(user_id))
        await sio.emit("history_deleted", {"success": True, "user_id": user_id}, room=str(user_id))

    async def delete_interview_session(sid, data=None):
        """Delete a single interview session for the authenticated user."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        session_id = str((data or {}).get("session_id") or "").strip()
        if not session_id:
            await sio.emit("session_delete_error", {"error": "session_id required", "user_id": user_id}, room=str(user_id))
            return

        user_db = deps.get_user_db()
        deleted = user_db.delete_interview_session(user_id, session_id)
        if not deleted:
            await sio.emit(
                "session_delete_error",
                {"error": "Session not found", "session_id": session_id, "user_id": user_id},
                room=str(user_id),
            )
            return

        history = user_db.get_session_history(user_id, 30)
        await sio.emit("interview_history", {"history": history, "user_id": user_id}, room=str(user_id))
        await sio.emit("session_deleted", {"success": True, "session_id": session_id, "user_id": user_id}, room=str(user_id))

    async def reset_all_data(sid, data=None):
        """Full reset: clear interview history, configuration, and analysis workspace artifacts."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        user_db = deps.get_user_db()
        user_db.reset_all_user_data(user_id)
        try:
            from server.services.cache import get_question_cache

            get_question_cache().delete_user_keys(user_id)
        except Exception as exc:
            print(f"⚠️ Failed to clear cache on full reset: {exc}")

        await sio.emit("career_analysis", {"analysis": None, "user_id": user_id}, room=str(user_id))
        await sio.emit("interview_history", {"history": [], "user_id": user_id}, room=str(user_id))
        await sio.emit("action_queue", {"actions": [], "user_id": user_id}, room=str(user_id))
        prefs = user_db.get_user_preferences(user_id) or {}
        await sio.emit("user_preferences", {"preferences": prefs, "user_id": user_id}, room=str(user_id))
        await sio.emit("all_data_reset", {"success": True, "user_id": user_id}, room=str(user_id))

    async def save_action_queue(sid, data=None):
        """Persist dashboard action queue updates."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        payload = data or {}
        actions = payload.get("actions", [])
        if not isinstance(actions, list):
            actions = []

        user_id = deps.get_uid(sid, payload)
        deps.get_user_db().save_action_queue(user_id, actions)
        await sio.emit("action_queue", {"actions": actions, "user_id": user_id}, room=str(user_id))

    async def get_latest_analysis(sid, data=None):
        """Get the most recent career analysis for the user."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        user_id = deps.get_uid(sid, data)
        recent = deps.get_user_db().get_career_analyses(user_id, limit=1)
        if recent:
            saved_analysis = recent[0]
            analysis_data = deps.normalize_latest_analysis_payload(user_id, saved_analysis)
            mapped_analysis = {
                "job_title": saved_analysis.get("job_title"),
                "company": saved_analysis.get("company"),
                "job_description": saved_analysis.get("job_description") or analysis_data.get("job_description", ""),
                "readiness_score": saved_analysis.get("readiness_score"),
                "skill_gaps": saved_analysis.get("skill_gaps", []),
                "bridge_roles": saved_analysis.get("bridge_roles", []),
                "suggested_sessions": saved_analysis.get("suggested_sessions", []) or analysis_data.get("suggested_sessions", []),
                "practice_plan": analysis_data.get("practice_plan"),
                "analysis_data": analysis_data,
            }
            await sio.emit("career_analysis", {"analysis": mapped_analysis, "user_id": user_id}, room=str(user_id))
        else:
            await sio.emit("career_analysis", {"analysis": None, "user_id": user_id}, room=str(user_id))

    async def regenerate_suggestions(sid, data):
        """Regenerate suggested sessions based on user prompt."""
        session = await deps.require_socket_auth(sid)
        if not session:
            return

        data = data or {}
        user_id = deps.get_uid(sid, data)
        user_prompt = data.get("prompt", "")
        if not user_prompt:
            return

        print(f"🔄 Regenerating suggestions for {user_id}: '{user_prompt}'")
        await sio.emit("status", {"stage": "regenerating_suggestions", "user_id": user_id}, room=str(user_id))

        user_db = deps.get_user_db()
        recent = user_db.get_career_analyses(user_id, limit=1)
        if not recent:
            await sio.emit("error", {"message": "No analysis found", "user_id": user_id}, room=str(user_id))
            return

        latest = recent[0]
        full_analysis = latest.get("analysis", {})
        state = {
            "resume_data": full_analysis.get("resume_data", {}),
            "job_requirements": full_analysis.get("job_requirements", {}),
            "skill_mapping": full_analysis.get("skill_mapping", {}),
            "readiness_score": latest.get("readiness_score", 0.5),
            "suggested_sessions": latest.get("suggested_sessions", []),
            "job_description": latest.get("job_description", ""),
        }

        try:
            import traceback
            from server.agents.nodes import regenerate_suggestions as regenerate_suggestions_impl
            from server.agents.nodes import trigger_background_generation

            new_suggestions = await regenerate_suggestions_impl(state, user_prompt)
            new_state = {**state, "suggested_sessions": new_suggestions}
            user_db.save_career_analysis(
                user_id,
                latest["job_title"],
                latest["company"],
                new_state,
                job_description=latest.get("job_description", ""),
            )
            await sio.emit("suggestions_updated", {"suggestions": new_suggestions, "user_id": user_id}, room=str(user_id))
            trigger_background_generation(user_id, new_state)
        except Exception as exc:
            print(f"❌ Error regenerating: {exc}")
            traceback.print_exc()
            await sio.emit("error", {"message": "Failed to regenerate suggestions", "user_id": user_id}, room=str(user_id))

    sio.on("save_preferences", handler=save_preferences)
    sio.on("start_career_analysis", handler=start_career_analysis)
    sio.on("get_preferences", handler=get_preferences)
    sio.on("get_interview_history", handler=get_interview_history)
    sio.on("get_session_details", handler=get_session_details)
    sio.on("get_retry_attempts", handler=get_retry_attempts)
    sio.on("submit_retry_answer", handler=submit_retry_answer)
    sio.on("get_user_stats", handler=get_user_stats)
    sio.on("get_action_queue", handler=get_action_queue)
    sio.on("reset_analysis_workspace", handler=reset_analysis_workspace)
    sio.on("clear_configuration", handler=clear_configuration)
    sio.on("delete_interview_history", handler=delete_interview_history)
    sio.on("delete_interview_session", handler=delete_interview_session)
    sio.on("reset_all_data", handler=reset_all_data)
    sio.on("save_action_queue", handler=save_action_queue)
    sio.on("get_latest_analysis", handler=get_latest_analysis)
    sio.on("regenerate_suggestions", handler=regenerate_suggestions)

    return SimpleNamespace(
        save_preferences=save_preferences,
        start_career_analysis=start_career_analysis,
        get_preferences=get_preferences,
        get_interview_history=get_interview_history,
        get_session_details=get_session_details,
        get_retry_attempts=get_retry_attempts,
        submit_retry_answer=submit_retry_answer,
        get_user_stats=get_user_stats,
        get_action_queue=get_action_queue,
        reset_analysis_workspace=reset_analysis_workspace,
        clear_configuration=clear_configuration,
        delete_interview_history=delete_interview_history,
        delete_interview_session=delete_interview_session,
        reset_all_data=reset_all_data,
        save_action_queue=save_action_queue,
        get_latest_analysis=get_latest_analysis,
        regenerate_suggestions=regenerate_suggestions,
    )
