import tempfile
import unittest
import uuid
from pathlib import Path

from server.services.user_database import UserDatabase


class UserDatabaseRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_interview.db")
        self.db = UserDatabase(db_path=self.db_path)

        self.user_id = self.db.create_user(
            email="retry-test@example.com",
            username="retry-user",
            password="password123",
        )
        self.session_id = uuid.uuid4().hex
        self.db.create_session(
            user_id=self.user_id,
            session_id=self.session_id,
            job_title="Software Engineer",
            mode="practice",
            total_questions=3,
        )
        self.db.save_answer(
            session_id=self.session_id,
            question_number=1,
            question_text="How do you design high availability?",
            question_category="Technical",
            question_difficulty="medium",
            user_answer="I mentioned redundancy at a high level.",
            evaluation={
                "score": 4.0,
                "score_breakdown": {"clarity": 4, "accuracy": 4, "completeness": 4, "structure": 4},
            },
            duration_seconds=30,
            skipped=False,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_retry_insert_and_read_ordering(self):
        eval_one = {"score": 4.0, "score_breakdown": {"clarity": 4, "accuracy": 4, "completeness": 4, "structure": 4}}
        eval_two = {"score": 6.5, "score_breakdown": {"clarity": 6, "accuracy": 7, "completeness": 6, "structure": 7}}

        attempt1 = self.db.save_retry_attempt(
            session_id=self.session_id,
            question_number=1,
            answer_text="first retry answer",
            input_mode="text",
            duration_seconds=20,
            evaluation=eval_one,
            baseline_score=3.0,
        )
        attempt2 = self.db.save_retry_attempt(
            session_id=self.session_id,
            question_number=1,
            answer_text="second retry answer",
            input_mode="text",
            duration_seconds=25,
            evaluation=eval_two,
            baseline_score=3.0,
        )

        attempts = self.db.get_retry_attempts(self.session_id, 1)

        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["attempt_number"], 1)
        self.assertEqual(attempts[1]["attempt_number"], 2)
        self.assertEqual(attempts[0]["retry_id"], attempt1["retry_id"])
        self.assertEqual(attempts[1]["retry_id"], attempt2["retry_id"])

    def test_latest_delta_uses_last_attempt(self):
        self.db.save_retry_attempt(
            session_id=self.session_id,
            question_number=2,
            answer_text="retry one",
            input_mode="text",
            duration_seconds=15,
            evaluation={"score": 5.0},
            baseline_score=3.0,
        )
        self.db.save_retry_attempt(
            session_id=self.session_id,
            question_number=2,
            answer_text="retry two",
            input_mode="text",
            duration_seconds=22,
            evaluation={"score": 6.5},
            baseline_score=3.0,
        )

        latest_delta = self.db.get_latest_retry_delta(self.session_id, 2)
        self.assertAlmostEqual(latest_delta, 3.5)

    def test_promote_retry_if_higher_updates_primary_and_keeps_original_snapshot(self):
        snapshot = self.db.ensure_original_retry_snapshot(self.session_id, 1)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["attempt_number"], 0)

        attempt = self.db.save_retry_attempt(
            session_id=self.session_id,
            question_number=1,
            answer_text="I implemented redundancy, failover, and health checks with clear RTO targets.",
            input_mode="text",
            duration_seconds=35,
            evaluation={"score": 7.5, "score_breakdown": {"clarity": 7, "accuracy": 8, "completeness": 7, "structure": 8}},
            baseline_score=4.0,
        )
        promotion = self.db.promote_retry_if_higher(self.session_id, 1, attempt)
        self.assertTrue(promotion["promoted"])
        self.assertAlmostEqual(promotion["primary_score"], 7.5)

        updated = self.db.get_answer_record(self.session_id, 1)
        self.assertIsNotNone(updated)
        self.assertAlmostEqual(float(updated["evaluation"]["score"]), 7.5)
        self.assertIn("failover", updated["user_answer"].lower())

        attempts = self.db.get_retry_attempts(self.session_id, 1)
        attempt_numbers = [a["attempt_number"] for a in attempts]
        self.assertIn(0, attempt_numbers)
        self.assertIn(1, attempt_numbers)

    def test_delete_interview_session_removes_only_target_session(self):
        other_session_id = uuid.uuid4().hex
        self.db.create_session(
            user_id=self.user_id,
            session_id=other_session_id,
            job_title="ML Engineer",
            mode="practice",
            total_questions=2,
        )

        self.db.save_retry_attempt(
            session_id=self.session_id,
            question_number=1,
            answer_text="retry answer to be deleted",
            input_mode="text",
            duration_seconds=15,
            evaluation={"score": 5.5},
            baseline_score=4.0,
        )

        deleted = self.db.delete_interview_session(self.user_id, self.session_id)
        self.assertTrue(deleted)

        self.assertIsNone(self.db.get_session_details(self.session_id))
        self.assertIsNone(self.db.get_answer_record(self.session_id, 1))
        self.assertEqual(self.db.get_retry_attempts(self.session_id, 1), [])

        remaining = [s["session_id"] for s in self.db.get_session_history(self.user_id, 10)]
        self.assertIn(other_session_id, remaining)
        self.assertNotIn(self.session_id, remaining)

    def test_delete_interview_session_denies_non_owner(self):
        other_user_id = self.db.create_user(
            email="another-user@example.com",
            username="another-user",
            password="password123",
        )

        deleted = self.db.delete_interview_session(other_user_id, self.session_id)
        self.assertFalse(deleted)
        self.assertIsNotNone(self.db.get_session_details(self.session_id))


if __name__ == "__main__":
    unittest.main()
