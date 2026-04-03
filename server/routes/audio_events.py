"""Socket.IO audio ingestion and chat pipeline registration."""

import asyncio
import base64
import os
import tempfile
from types import SimpleNamespace


def register_audio_events(sio, deps):
    """Register audio and chat-related Socket.IO events."""

    async def user_audio_chunk(sid, data):
        """
        Handle incoming audio chunks with low-latency partial STT and utterance finalization.
        """
        session = deps.sessions.get(sid)
        if session is None:
            return
        if not session.accept_audio_chunks:
            return

        try:
            audio_bytes = base64.b64decode(data.get("audio", ""))
            sample_rate = data.get("sample_rate", 16000)

            if sample_rate != 16000:
                audio_bytes = deps.get_audio_processor().resample_pcm(audio_bytes, sample_rate, 16000)

            trimmed = session.append_audio(audio_bytes)
            if trimmed > 0:
                import time as _time

                now = _time.time()
                last = getattr(session, "_last_trim_log", 0)
                if now - last > 5.0:
                    session._last_trim_log = now
                    print(
                        f"📦 Buffer trimmed {trimmed} bytes (circular) — "
                        f"buffer full at {session.MAX_BUFFER_SIZE} bytes"
                    )
        except Exception as exc:
            print(f"❌ Error decoding audio chunk: {exc}")
            return

        if session.is_processing:
            return

        try:
            import time

            current_time = time.time()
            audio_processor = deps.get_audio_processor()
            streaming_audio_processor = deps.get_streaming_audio_processor()

            recent_chunk = bytes(session.audio_buffer[-len(audio_bytes):]) if len(audio_bytes) > 0 else b""
            rms = audio_processor.calculate_rms(recent_chunk) if recent_chunk else 0
            is_speaking = rms > 0.012

            if is_speaking and not session.was_speaking:
                session.current_utterance_start_position = max(
                    session.last_finalized_position,
                    len(session.audio_buffer) - len(audio_bytes),
                )
                session.current_partial_transcript = ""

            if is_speaking:
                session.was_speaking = True
                session.silence_start_time = None
            elif session.was_speaking and session.silence_start_time is None:
                session.silence_start_time = current_time

            silence_duration = 0
            if session.silence_start_time:
                silence_duration = current_time - session.silence_start_time
            is_extended_silence = silence_duration > 1.5

            should_partial_transcribe = (
                session.interview_active and is_speaking and session.should_transcribe(current_time)
            )
            should_finalize_utterance = (
                session.interview_active
                and not is_speaking
                and session.was_speaking
                and silence_duration >= session.FINALIZE_SILENCE_SECONDS
            )

            max_utterance_bytes = 480_000
            unfinalized_bytes = len(session.audio_buffer) - session.last_finalized_position
            if (
                session.interview_active
                and session.was_speaking
                and unfinalized_bytes > max_utterance_bytes
                and not should_finalize_utterance
            ):
                should_finalize_utterance = True

            should_process_chat = (not session.interview_active) and is_extended_silence

            if not (should_partial_transcribe or should_finalize_utterance or should_process_chat):
                return

            buffer_rms = (
                audio_processor.calculate_rms(bytes(session.audio_buffer[-32000:]))
                if len(session.audio_buffer) > 32000
                else rms
            )
            if buffer_rms < 0.01 and not (should_finalize_utterance or should_process_chat):
                print(f"🔇 Skipping quiet buffer (RMS: {buffer_rms:.4f})")
                session.last_transcribe_time = current_time
                return

            session.is_processing = True

            try:
                if session.interview_active:
                    if should_partial_transcribe:
                        start_pos = max(0, min(session.current_utterance_start_position, len(session.audio_buffer)))
                        max_partial_bytes = 480_000
                        if (len(session.audio_buffer) - start_pos) > max_partial_bytes:
                            start_pos = len(session.audio_buffer) - max_partial_bytes
                        audio_to_transcribe = bytes(session.audio_buffer[start_pos:])
                        if len(audio_to_transcribe) >= 6400:
                            transcript = await streaming_audio_processor.transcribe_buffer_async(audio_to_transcribe)
                            transcript = (transcript or "").strip()
                            session.last_transcribed_position = len(session.audio_buffer)
                            session.last_transcribe_time = current_time

                            if transcript and not deps.should_drop_false_start(session.finalized_answer_transcript, transcript):
                                if deps.transcript_similarity(transcript, session.current_partial_transcript) < 0.98:
                                    session.current_partial_transcript = transcript
                                    composed = deps.combine_final_and_partial(
                                        session.finalized_answer_transcript,
                                        session.current_partial_transcript,
                                    )
                                    if composed != session.current_answer_transcript:
                                        session.current_answer_transcript = composed
                                        await deps.emit_transcript_update(session, is_final=False)
                                        print(f"📝 Partial: {session.current_answer_transcript[:80]}...")

                    if should_finalize_utterance:
                        await deps.finalize_current_utterance(session, reason="silence")

                    await deps.maybe_emit_coaching_hint(session, current_time, is_extended_silence)
                else:
                    if should_process_chat:
                        await process_audio_and_respond(sid, session)
            finally:
                session.is_processing = False
                if is_extended_silence and not session.interview_active:
                    session.was_speaking = False
        except Exception as exc:
            print(f"❌ Error processing audio: {exc}")
            import traceback

            traceback.print_exc()

    async def force_transcribe(sid):
        """
        Force transcription of current audio buffer.
        Useful when user clicks a button to submit.
        """
        session = deps.sessions.get(sid)
        if session is None or session.is_processing:
            return

        if len(session.audio_buffer) > 0:
            session.is_processing = True
            try:
                if session.interview_active:
                    await deps.finalize_current_utterance(session, reason="force")
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

    async def set_recording_state(sid, data):
        """Client toggles recording lifecycle; backend uses this to gate audio chunks."""
        session = deps.sessions.get(sid)
        if session is None:
            return

        data = data or {}
        recording = bool(data.get("recording", False))
        session.accept_audio_chunks = recording and session.interview_active
        if not session.accept_audio_chunks:
            session.was_speaking = False
            session.silence_start_time = None

    async def text_message(sid, data):
        """Handle text message (for testing without audio)."""
        session = deps.sessions.get(sid)
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

    async def set_phase(sid, data):
        """Set the interview phase for the session."""
        session = deps.sessions.get(sid)
        if session:
            session.status = data.get("phase", "technical")
            await sio.emit(
                "phase_changed",
                {"phase": session.status, "user_id": session.user_id},
                room=str(session.user_id),
            )

    async def submit_audio(sid, data):
        """
        Handle complete audio submission (blob) from the client.
        Saves to temp file to handle WebM format correctly, then transcribes.
        """
        session = deps.sessions.get(sid)
        if session is None:
            return

        audio_b64 = data.get("audio", "")
        if not audio_b64:
            return

        try:
            audio_bytes = base64.b64decode(audio_b64)
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as temp:
                temp.write(audio_bytes)
                temp_path = temp.name

            processor = deps.get_audio_processor()
            text = (
                await processor.transcribe_file_async(temp_path)
                if hasattr(processor, "transcribe_file_async")
                else processor.transcribe_file(temp_path)
            )

            os.remove(temp_path)

            if text.strip():
                if session.interview_active and deps.should_drop_false_start(session.current_answer_transcript, text):
                    print(f"🔇 Dropping false-start transcript: {text!r}")
                    return

                print(f"🗣️ Transcribed: {text[:50]}...")

                if session.interview_active:
                    merged = deps.merge_transcript(session.finalized_answer_transcript, text)
                    if merged != session.finalized_answer_transcript:
                        session.finalized_answer_transcript = merged
                        session.current_partial_transcript = ""
                        session.current_answer_transcript = merged
                        await deps.emit_transcript_update(session, is_final=True)
                else:
                    await sio.emit("transcript", {"text": text, "user_id": session.user_id}, room=str(session.user_id))
                    session.is_processing = True
                    await sio.emit("status", {"stage": "analyzing", "user_id": session.user_id}, room=str(session.user_id))
                    try:
                        await process_text_and_respond(sid, session, text)
                    finally:
                        session.is_processing = False
            else:
                print("⚠️ Transcription empty")
        except Exception as exc:
            print(f"❌ Error in submit_audio: {exc}")
            await sio.emit("error", {"message": "Audio processing failed", "user_id": session.user_id}, room=str(session.user_id))

    async def process_audio_and_respond(sid: str, session):
        """Process audio buffer: STT -> LLM -> TTS -> Send response."""
        await sio.emit("status", {"stage": "transcribing", "user_id": session.user_id}, room=str(session.user_id))

        audio_processor = deps.get_audio_processor()
        transcript = await audio_processor.transcribe_buffer_async(bytes(session.audio_buffer))

        if not transcript.strip():
            await sio.emit("status", {"stage": "no_speech"}, room=str(session.user_id))
            return

        await sio.emit("transcript", {"text": transcript, "user_id": session.user_id}, room=str(session.user_id))
        session.transcript_chunks.append(transcript)
        await process_text_and_respond(sid, session, transcript)

    async def process_text_and_respond(sid: str, session, text: str):
        """Process text input: LLM -> TTS -> Send response."""
        from langchain_core.messages import AIMessage, HumanMessage

        session.messages.append(HumanMessage(content=text))
        await sio.emit("status", {"stage": "thinking", "user_id": session.user_id}, room=str(session.user_id))

        chat_model = deps.get_chat_model()
        full_response = ""

        async for token in chat_model.generate_response_stream(session.messages, phase=session.status):
            full_response += token
            await sio.emit("llm_token", {"token": token, "user_id": session.user_id}, room=str(session.user_id))

        session.messages.append(AIMessage(content=full_response))
        await sio.emit("llm_complete", {"text": full_response, "user_id": session.user_id}, room=str(session.user_id))
        await sio.emit("status", {"stage": "speaking", "user_id": session.user_id}, room=str(session.user_id))

        try:
            await deps.await_tts_warmup_if_needed()
            tts_service = deps.get_tts_service()
            tts_timeout = deps.compute_tts_timeout(full_response)
            audio_base64 = await asyncio.wait_for(
                tts_service.speak_wav_base64_async(
                    full_response,
                    style=getattr(session, "tts_style", "interviewer"),
                    provider=getattr(session, "tts_provider", "piper"),
                ),
                timeout=tts_timeout,
            )

            await sio.emit(
                "tts_audio",
                {
                    "audio": audio_base64,
                    "format": "wav",
                    "sample_rate": tts_service.sample_rate_for_provider(getattr(session, "tts_provider", "piper")),
                    "user_id": session.user_id,
                },
                room=str(session.user_id),
            )
        except asyncio.TimeoutError:
            print(f"⚠️ TTS timed out after {tts_timeout:.1f}s (continuing without audio)")
            await sio.emit(
                "tts_error",
                {"error": "TTS timed out; continuing without audio.", "user_id": session.user_id},
                room=str(session.user_id),
            )
        except Exception as exc:
            print(f"⚠️ TTS failed in process_text_and_respond (continuing): {exc}")
            await sio.emit(
                "tts_error",
                {"error": "TTS unavailable; continuing without audio.", "user_id": session.user_id},
                room=str(session.user_id),
            )
        finally:
            await sio.emit("status", {"stage": "ready", "user_id": session.user_id}, room=str(session.user_id))

    sio.on("user_audio_chunk", handler=user_audio_chunk)
    sio.on("force_transcribe", handler=force_transcribe)
    sio.on("set_recording_state", handler=set_recording_state)
    sio.on("text_message", handler=text_message)
    sio.on("set_phase", handler=set_phase)
    sio.on("submit_audio", handler=submit_audio)

    return SimpleNamespace(
        user_audio_chunk=user_audio_chunk,
        force_transcribe=force_transcribe,
        set_recording_state=set_recording_state,
        text_message=text_message,
        set_phase=set_phase,
        submit_audio=submit_audio,
        process_audio_and_respond=process_audio_and_respond,
        process_text_and_respond=process_text_and_respond,
    )
