"""
Session state and in-memory registries for active socket users.
"""

import asyncio
from collections import defaultdict
from typing import Optional

from server.config import settings


class SessionState:
    """Per-session state for audio streaming and conversation."""

    # Buffer constants
    MAX_BUFFER_SIZE = 4_800_000  # ~150 seconds at 16kHz mono 16-bit
    NEW_AUDIO_THRESHOLD = int(32000 * (settings.STT_PARTIAL_CHUNK_MS / 1000.0))
    TRANSCRIBE_COOLDOWN = max(0.1, settings.STT_PARTIAL_COOLDOWN_MS / 1000.0)
    FINALIZE_SILENCE_SECONDS = max(0.3, settings.STT_FINALIZE_SILENCE_MS / 1000.0)

    def __init__(
        self,
        user_id: str = "anonymous",
        is_authenticated: bool = False,
        session_token: Optional[str] = None,
    ):
        self.user_id = user_id
        self.is_authenticated = is_authenticated
        self.session_token = session_token

        # Audio buffer - circular with max size
        self.audio_buffer = bytearray()

        # Transcription tracking
        self.last_transcribed_position: int = 0
        self.last_finalized_position: int = 0
        self.current_utterance_start_position: int = 0
        self.last_transcribe_time: float = 0
        self.recent_transcripts: list[str] = []  # Last 3 for deduplication
        self.current_partial_transcript: str = ""
        self.finalized_answer_transcript: str = ""

        # Legacy (for compatibility)
        self.transcript_chunks: list[str] = []
        self.messages: list = []
        self.status: str = "warmup"
        self.is_processing: bool = False

        # Interview practice fields
        self.interview_active: bool = False
        self.interview_questions: list[dict] = []
        self.current_question_index: int = 0
        self.interview_mode: str = "practice"
        self.interview_feedback_timing: str = "end_only"
        self.live_scoring_enabled: bool = False
        self.interviewer_persona: str = "friendly"
        self.tts_style: str = "interviewer"
        self.tts_provider: str = "piper"
        self.coaching_enabled: bool = False
        self.answer_start_time: float = None
        self.current_answer_transcript: str = ""
        self.evaluations: list[dict] = []
        self.job_title: str = ""
        self.last_hint_time: float = 0
        self.hints_given: list[str] = []
        self.db_session_id: str = None  # UUID for database persistence
        self.answer_submission_in_flight: bool = False
        self.accept_audio_chunks: bool = False
        self.end_requested: bool = False
        self.question_tts_task: Optional[asyncio.Task] = None
        self.tts_prefetch_cache: dict = {}  # question_index -> audio_b64
        self.tts_prefetch_tasks: dict = {}  # question_index -> asyncio.Task
        self.finalize_lock: asyncio.Lock = asyncio.Lock()

        # Speaking state tracking
        self.was_speaking: bool = False
        self.silence_start_time: float = None

    def append_audio(self, audio_bytes: bytes) -> int:
        """Append audio with circular buffer management. Returns bytes trimmed."""
        self.audio_buffer.extend(audio_bytes)
        trimmed = 0

        if len(self.audio_buffer) > self.MAX_BUFFER_SIZE:
            overflow = len(self.audio_buffer) - self.MAX_BUFFER_SIZE
            self.audio_buffer = self.audio_buffer[overflow:]
            # Adjust position tracker
            self.last_transcribed_position = max(0, self.last_transcribed_position - overflow)
            self.last_finalized_position = max(0, self.last_finalized_position - overflow)
            self.current_utterance_start_position = max(0, self.current_utterance_start_position - overflow)
            trimmed = overflow

        return trimmed

    def should_transcribe(self, current_time: float) -> bool:
        """Check if we have enough new audio and cooldown has passed."""
        bytes_new = len(self.audio_buffer) - self.last_transcribed_position
        time_since = current_time - self.last_transcribe_time
        min_new_audio = max(3200, self.NEW_AUDIO_THRESHOLD)
        return bytes_new >= min_new_audio and time_since >= self.TRANSCRIBE_COOLDOWN

    def clear_for_new_question(self):
        """Reset buffer state for a new question."""
        self.audio_buffer.clear()
        self.last_transcribed_position = 0
        self.last_finalized_position = 0
        self.current_utterance_start_position = 0
        self.last_transcribe_time = 0
        self.recent_transcripts = []
        self.current_partial_transcript = ""
        self.finalized_answer_transcript = ""
        self.current_answer_transcript = ""
        self.hints_given = []
        self.was_speaking = False
        self.silence_start_time = None


# Global session storage
sessions: dict[str, SessionState] = {}

# Maps Socket ID -> User ID for quick lookup on disconnect
sid_to_user: dict[str, str] = {}

# Maps User ID -> count of active socket connections
user_connection_count: dict[str, int] = defaultdict(int)

# Maps User ID -> Active asyncio Task (for cancellation on disconnect or restart)
active_tasks: dict[str, asyncio.Task] = {}

# Maps User ID -> delayed cancellation task (disconnect grace window)
pending_disconnect_cancels: dict[str, asyncio.Task] = {}
