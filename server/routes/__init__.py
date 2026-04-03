"""Route registration helpers for REST and Socket.IO handlers."""

from server.routes.audio_events import register_audio_events
from server.routes.auth_events import register_auth_events
from server.routes.interview_events import register_interview_events
from server.routes.preferences_events import register_preferences_events
from server.routes.rest import register_rest_routes

__all__ = [
    "register_audio_events",
    "register_auth_events",
    "register_interview_events",
    "register_preferences_events",
    "register_rest_routes",
]
