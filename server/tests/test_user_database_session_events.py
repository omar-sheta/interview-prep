import tempfile
import unittest
import uuid
from pathlib import Path

from server.services.user_database import UserDatabase


class UserDatabaseSessionEventTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_session_events.db")
        self.db = UserDatabase(db_path=self.db_path)
        self.user_id = self.db.create_user(
            email="session-events@example.com",
            username="session-events",
            password="password123",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_login_session_history_and_details_include_events(self):
        token = self.db.create_session_token(self.user_id)
        login_sessions = self.db.get_login_session_history(self.user_id, limit=10)

        self.assertEqual(len(login_sessions), 1)
        login_session = login_sessions[0]
        self.assertTrue(login_session["session_fingerprint"])
        self.assertTrue(login_session["created_at"])
        self.assertTrue(login_session["last_used_at"])
        self.assertTrue(login_session["expires_at"])
        self.assertTrue(login_session["active"])

        session_id = uuid.uuid4().hex
        self.db.create_session(
            user_id=self.user_id,
            session_id=session_id,
            job_title="Software Engineer",
            mode="practice",
            total_questions=2,
        )

        auth_fingerprint = self.db.get_session_token_fingerprint(token)
        self.db.log_session_event(
            user_id=self.user_id,
            auth_session_fingerprint=auth_fingerprint,
            sid="sid-login",
            event_type="login_success",
            event_source="auth",
            details={"email": "session-events@example.com"},
        )
        self.db.log_session_event(
            user_id=self.user_id,
            session_id=session_id,
            auth_session_fingerprint=auth_fingerprint,
            sid="sid-login",
            event_type="interview_started",
            event_source="interview",
            details={"job_title": "Software Engineer"},
        )

        details = self.db.get_login_session_details(self.user_id, auth_fingerprint)
        self.assertIsNotNone(details)
        self.assertEqual(details["session_fingerprint"], auth_fingerprint)
        self.assertIn(session_id, details["interview_session_ids"])
        self.assertEqual([event["event_type"] for event in details["events"]], ["login_success", "interview_started"])
        self.assertEqual(details["events"][0]["created_at"] <= details["events"][1]["created_at"], True)

    def test_revoke_session_token_preserves_history_and_marks_session_inactive(self):
        token = self.db.create_session_token(self.user_id)
        auth_fingerprint = self.db.get_session_token_fingerprint(token)
        self.db.log_session_event(
            user_id=self.user_id,
            auth_session_fingerprint=auth_fingerprint,
            sid="sid-1",
            event_type="login_success",
            event_source="auth",
            details={},
        )

        self.db.revoke_session_token(token)

        self.assertIsNone(self.db.validate_session_token(token))

        login_sessions = self.db.get_login_session_history(self.user_id, limit=10)
        self.assertEqual(len(login_sessions), 1)
        self.assertFalse(login_sessions[0]["active"])
        self.assertTrue(login_sessions[0]["revoked_at"])

        details = self.db.get_login_session_details(self.user_id, auth_fingerprint)
        self.assertIsNotNone(details)
        self.assertFalse(details["active"])
        self.assertTrue(details["revoked_at"])
        self.assertEqual([event["event_type"] for event in details["events"]], ["login_success"])

    def test_session_details_include_events_and_delete_cleans_up_session_rows(self):
        session_id = uuid.uuid4().hex
        token = self.db.create_session_token(self.user_id)
        auth_fingerprint = self.db.get_session_token_fingerprint(token)

        self.db.create_session(
            user_id=self.user_id,
            session_id=session_id,
            job_title="AI Engineer",
            mode="coaching",
            total_questions=1,
        )
        self.db.log_session_event(
            user_id=self.user_id,
            session_id=session_id,
            auth_session_fingerprint=auth_fingerprint,
            sid="sid-xyz",
            event_type="interview_started",
            event_source="interview",
            details={"job_title": "AI Engineer"},
        )

        details = self.db.get_session_details(session_id)
        self.assertIsNotNone(details)
        self.assertEqual(details["auth_session_fingerprint"], auth_fingerprint)
        self.assertEqual([event["event_type"] for event in details["events"]], ["interview_started"])

        deleted = self.db.delete_interview_session(self.user_id, session_id)
        self.assertTrue(deleted)
        self.assertIsNone(self.db.get_session_details(session_id))
        self.assertEqual(self.db.get_session_events(session_id), [])


if __name__ == "__main__":
    unittest.main()
