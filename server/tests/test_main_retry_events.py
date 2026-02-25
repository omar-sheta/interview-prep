import unittest
import importlib.util
from unittest.mock import ANY, AsyncMock, patch

HAS_MAIN_DEPS = all(
    importlib.util.find_spec(module_name) is not None
    for module_name in ("socketio", "fastapi", "langgraph")
)

if HAS_MAIN_DEPS:
    import server.main as main
else:
    main = None


class _FakeDb:
    def __init__(self):
        self.saved_retry = None
        self.owner = "user_123"

    def get_session_owner(self, session_id):
        return self.owner if session_id == "sess_1" else None

    def get_answer_record(self, session_id, question_number):
        if session_id != "sess_1" or question_number != 1:
            return None
        return {
            "question_text": "How do you design high availability systems?",
            "question_category": "Technical",
            "question_difficulty": "hard",
            "evaluation": {
                "score": 4.0,
                "expected_points_used": [
                    "redundancy",
                    "load balancing",
                    "failover",
                ],
            },
        }

    def save_retry_attempt(
        self,
        session_id,
        question_number,
        answer_text,
        input_mode,
        duration_seconds,
        evaluation,
        baseline_score,
    ):
        self.saved_retry = {
            "session_id": session_id,
            "question_number": question_number,
            "answer_text": answer_text,
            "input_mode": input_mode,
            "duration_seconds": duration_seconds,
            "evaluation": evaluation,
            "baseline_score": baseline_score,
        }
        return {
            "retry_id": "retry_1",
            "session_id": session_id,
            "question_number": question_number,
            "attempt_number": 1,
            "answer_text": answer_text,
            "input_mode": input_mode,
            "duration_seconds": duration_seconds,
            "evaluation": evaluation,
            "baseline_score": baseline_score,
            "delta_score": round(float(evaluation.get("score", 0)) - float(baseline_score or 0), 2),
            "created_at": "2026-02-21T00:00:00",
        }

    def ensure_original_retry_snapshot(self, session_id, question_number):
        return {
            "retry_id": "orig_0",
            "attempt_number": 0,
            "answer_text": "original answer",
            "input_mode": "original",
            "duration_seconds": 10,
            "evaluation": {"score": 4.0},
            "baseline_score": 4.0,
            "delta_score": 0.0,
            "created_at": "2026-02-21T00:00:00",
        }

    def promote_retry_if_higher(self, session_id, question_number, attempt):
        return {
            "promoted": True,
            "previous_score": 4.0,
            "primary_score": float((attempt or {}).get("evaluation", {}).get("score", 0)),
            "session_average_score": 6.5,
        }

    def get_retry_attempts(self, session_id, question_number):
        return [
            {
                "retry_id": "retry_1",
                "attempt_number": 1,
                "answer_text": "Retry answer",
                "input_mode": "text",
                "duration_seconds": 12,
                "evaluation": {"score": 6.0},
                "baseline_score": 4.0,
                "delta_score": 2.0,
                "created_at": "2026-02-21T00:00:00",
            }
        ]


@unittest.skipUnless(HAS_MAIN_DEPS, "requires socketio/fastapi/langgraph dependencies")
class MainRetrySocketEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_retry_answer_evaluates_persists_and_emits(self):
        fake_db = _FakeDb()
        fake_session = main.SessionState(user_id="user_123", is_authenticated=True)
        evaluated_payload = {
            "score": 6.5,
            "score_breakdown": {
                "clarity": 6,
                "accuracy": 7,
                "completeness": 6,
                "structure": 6,
            },
            "evaluation_version": "v2",
            "quality_flags": [],
            "confidence": 0.8,
            "rubric_hits": ["redundancy"],
            "rubric_misses": ["failover"],
            "evidence_quotes": ["I used redundancy and health checks."],
            "improvement_plan": {
                "focus": "failover",
                "steps": ["add active-passive failover"],
                "success_criteria": ["explains failover"],
            },
            "retry_drill": {
                "prompt": "Retry with failover details",
                "target_points": ["failover"],
            },
            "strengths": ["clear explanation"],
            "missing_concepts": ["failover"],
            "coaching_tip": "",
            "optimized_answer": "",
            "feedback": "",
        }

        with (
            patch.object(main, "_require_socket_auth", new=AsyncMock(return_value=fake_session)),
            patch.object(main, "_get_uid", return_value="user_123"),
            patch.object(main, "get_user_db", return_value=fake_db),
            patch.object(main.sio, "emit", new=AsyncMock()) as emit_mock,
            patch("server.agents.interview_nodes.evaluate_answer_stream", new=AsyncMock(return_value=evaluated_payload)),
        ):
            await main.submit_retry_answer(
                "sid_1",
                {
                    "session_id": "sess_1",
                    "question_number": 1,
                    "answer": "I would use redundancy and load balancing with failover drills.",
                    "duration_seconds": 18,
                    "input_mode": "text",
                },
            )

        self.assertIsNotNone(fake_db.saved_retry)
        self.assertEqual(fake_db.saved_retry["session_id"], "sess_1")
        self.assertEqual(fake_db.saved_retry["question_number"], 1)
        self.assertEqual(fake_db.saved_retry["baseline_score"], 4.0)

        emit_mock.assert_any_call(
            "retry_evaluated",
            ANY,
            room="user_123",
        )

    async def test_get_retry_attempts_returns_timeline(self):
        fake_db = _FakeDb()
        fake_session = main.SessionState(user_id="user_123", is_authenticated=True)

        with (
            patch.object(main, "_require_socket_auth", new=AsyncMock(return_value=fake_session)),
            patch.object(main, "_get_uid", return_value="user_123"),
            patch.object(main, "get_user_db", return_value=fake_db),
            patch.object(main.sio, "emit", new=AsyncMock()) as emit_mock,
        ):
            await main.get_retry_attempts(
                "sid_1",
                {
                    "session_id": "sess_1",
                    "question_number": 1,
                },
            )

        emit_mock.assert_any_call(
            "retry_attempts",
            {
                "session_id": "sess_1",
                "question_number": 1,
                "attempts": fake_db.get_retry_attempts("sess_1", 1),
                "user_id": "user_123",
            },
            room="user_123",
        )


if __name__ == "__main__":
    unittest.main()
