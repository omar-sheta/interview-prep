import unittest
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from server.routes.rest import register_rest_routes


class _FakeTask:
    def __init__(self, done=False):
        self._done = done
        self._cancelled = False

    def done(self):
        return self._done

    def cancelled(self):
        return self._cancelled

    def cancel(self):
        self._cancelled = True
        self._done = True


class _FakeUserDb:
    def count_users(self):
        return 7

    def get_user(self, user_id):
        users = {
            "admin-user": {"user_id": "admin-user", "email": "admin@example.com", "username": "Admin"},
            "user-1": {"user_id": "user-1", "email": "omar@example.com", "username": "Omar"},
        }
        return users.get(user_id)

    def get_user_progress(self, _user_id):
        return {}

    def get_session_history(self, _user_id, _limit=10):
        return []

    def get_session_details(self, _session_id):
        return None

    def get_career_analyses(self, _user_id, limit=5):
        return []


def _build_client(allow_admin=True):
    app = FastAPI()
    user_db = _FakeUserDb()
    active_task = _FakeTask(done=False)

    async def require_admin_rest_user():
        if not allow_admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        return user_db.get_user("admin-user")

    async def get_authenticated_rest_user_id():
        return "admin-user"

    register_rest_routes(
        app,
        SimpleNamespace(
            mx=None,
            build_sanity_check_graph=lambda: SimpleNamespace(invoke=lambda payload: {"value": payload["value"] + " processed by Node A"}),
            check_qdrant_status=lambda: {"status": "disabled"},
            get_authenticated_rest_user_id=get_authenticated_rest_user_id,
            require_admin_rest_user=require_admin_rest_user,
            get_user_db=lambda: user_db,
            safe_user_payload=lambda user: user,
            sessions={
                "sid-1": SimpleNamespace(user_id="user-1", is_authenticated=True, interview_active=True, current_question_index=1),
                "sid-2": SimpleNamespace(user_id="user-1", is_authenticated=True, interview_active=False, current_question_index=0),
                "sid-3": SimpleNamespace(user_id="anon_sid", is_authenticated=False, interview_active=False, current_question_index=0),
            },
            user_connection_count={"user-1": 2, "anon_sid": 1},
            active_tasks={"user-1": active_task},
            feedback_metrics={"avg_v2": 0.82, "low_stt_ratio": 0.15},
        ),
    )

    return TestClient(app), active_task


class AdminRestRoutesTests(unittest.TestCase):
    def test_admin_overview_requires_allowlisted_user(self):
        client, _ = _build_client(allow_admin=False)
        response = client.get("/api/admin/overview")
        self.assertEqual(response.status_code, 403)

    def test_admin_overview_returns_counts_and_safe_headers(self):
        client, _ = _build_client(allow_admin=True)
        response = client.get("/api/admin/overview")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["counts"]["registered_users"], 7)
        self.assertEqual(payload["counts"]["live_users"], 1)
        self.assertEqual(payload["counts"]["live_connections"], 3)
        self.assertEqual(payload["counts"]["active_analysis_tasks"], 1)
        self.assertEqual(payload["live_users"][0]["email"], "omar@example.com")
        self.assertEqual(response.headers["cache-control"], "no-store, private")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_cancel_admin_task_marks_task_cancelled(self):
        client, task = _build_client(allow_admin=True)
        response = client.post("/api/admin/tasks/user-1/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["cancelled"])
        self.assertTrue(task.cancelled())


if __name__ == "__main__":
    unittest.main()
