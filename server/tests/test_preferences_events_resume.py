import asyncio
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from server.routes.preferences_events import register_preferences_events


class _FakeSio:
    def __init__(self):
        self.handlers = {}
        self.emits = []

    def on(self, event, handler=None):
        if handler is not None:
            self.handlers[event] = handler
        return handler

    async def emit(self, event, payload, room=None):
        self.emits.append((event, payload, room))


class _FakeUserDb:
    def __init__(self):
        self.saved_preferences = None
        self.current_preferences = {}

    def get_user_preferences(self, _user_id):
        return self.current_preferences

    def save_user_preferences(self, _user_id, preferences):
        self.saved_preferences = preferences
        self.current_preferences = preferences


def _first_present(data, keys, default=None):
    payload = data or {}
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return default


class PreferencesEventsResumeTests(unittest.TestCase):
    def test_save_preferences_persists_resume_from_base64_payload(self):
        sio = _FakeSio()
        user_db = _FakeUserDb()
        deps = SimpleNamespace(
            require_socket_auth=lambda _sid: asyncio.sleep(0, result={"user_id": "user-1"}),
            get_uid=lambda _sid, _data: "user-1",
            get_user_db=lambda: user_db,
            normalize_feedback_thresholds=lambda value: value or {},
            normalize_recording_thresholds=lambda value: value or {},
            normalize_piper_style=lambda value, fallback=None: value or fallback or "interviewer",
            normalize_tts_provider=lambda value, fallback=None: value or fallback or "piper",
            first_present=_first_present,
        )
        events = register_preferences_events(sio, deps)

        fake_resume_tool = types.ModuleType("server.tools.resume_tool")
        fake_resume_tool.extract_text_from_pdf_bytes = lambda _bytes: "parsed resume text"

        with patch.dict(sys.modules, {"server.tools.resume_tool": fake_resume_tool}):
            asyncio.run(
                events.save_preferences(
                    "sid-1",
                    {
                        "resume": "data:application/pdf;base64,ZmFrZQ==",
                        "resume_filename": "dad_resume.pdf",
                        "target_role": "Software Engineer",
                        "job_description": "Build software",
                    },
                )
            )

        self.assertIsNotNone(user_db.saved_preferences)
        self.assertEqual(user_db.saved_preferences["resume_text"], "parsed resume text")
        self.assertEqual(user_db.saved_preferences["resume_filename"], "dad_resume.pdf")
        self.assertEqual(user_db.saved_preferences["target_role"], "Software Engineer")
        self.assertEqual(sio.emits[0][0], "preferences_saved")
        self.assertTrue(sio.emits[0][1]["success"])
        self.assertTrue(sio.emits[0][1]["has_resume"])


if __name__ == "__main__":
    unittest.main()
