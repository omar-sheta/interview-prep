"""
Helpers for TTS startup warmup and timeout budgeting.
"""

import asyncio
import os
from typing import Optional

from server.services.tts_service import get_tts_service, preload_tts

TTS_RESPONSE_TIMEOUT_SEC = float(os.getenv("TTS_RESPONSE_TIMEOUT_SEC", "90"))
TTS_TIMEOUT_PER_CHAR_SEC = float(os.getenv("TTS_TIMEOUT_PER_CHAR_SEC", "0.08"))
TTS_MAX_TIMEOUT_SEC = float(os.getenv("TTS_MAX_TIMEOUT_SEC", "180"))
TTS_PRELOAD_ON_STARTUP = os.getenv("TTS_PRELOAD_ON_STARTUP", "1").lower() in {"1", "true", "yes", "on"}
TTS_STARTUP_WARMUP_TEXT = os.getenv(
    "TTS_STARTUP_WARMUP_TEXT",
    "Calibration.",
).strip()
TTS_WARMUP_AWAIT_ON_FIRST_TTS = os.getenv("TTS_WARMUP_AWAIT_ON_FIRST_TTS", "1").lower() in {"1", "true", "yes", "on"}
TTS_WARMUP_WAIT_SEC = float(os.getenv("TTS_WARMUP_WAIT_SEC", "180"))

_tts_warmup_task: Optional[asyncio.Task] = None


def compute_tts_timeout(text: str) -> float:
    """Compute TTS timeout from base + text-length budget, clamped by max."""
    text_len = len((text or "").strip())
    timeout = TTS_RESPONSE_TIMEOUT_SEC + (text_len * TTS_TIMEOUT_PER_CHAR_SEC)
    return max(1.0, min(TTS_MAX_TIMEOUT_SEC, timeout))


async def warmup_tts_backend():
    """Preload and warm TTS once so first live question does not time out."""
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, preload_tts)
        if TTS_STARTUP_WARMUP_TEXT:
            tts_service = get_tts_service()
            warmup_timeout = compute_tts_timeout(TTS_STARTUP_WARMUP_TEXT)
            await asyncio.wait_for(
                tts_service.speak_wav_base64_async(TTS_STARTUP_WARMUP_TEXT),
                timeout=warmup_timeout,
            )
        print("✅ TTS warmup complete")
    except Exception as e:
        print(f"⚠️ TTS warmup skipped: {e}")


def schedule_tts_warmup() -> Optional[asyncio.Task]:
    """Start the startup warmup task once and return it when enabled."""
    global _tts_warmup_task
    if not TTS_PRELOAD_ON_STARTUP:
        return None
    _tts_warmup_task = asyncio.create_task(warmup_tts_backend())
    return _tts_warmup_task


async def await_tts_warmup_if_needed():
    """Await startup warmup if it is still running (avoids first-question timeout drops)."""
    if not TTS_WARMUP_AWAIT_ON_FIRST_TTS:
        return
    task = _tts_warmup_task
    if not task or task.done():
        return
    if asyncio.current_task() is task:
        return
    try:
        print("⏳ Waiting for TTS warmup to finish before synthesis...")
        await asyncio.wait_for(task, timeout=max(1.0, TTS_WARMUP_WAIT_SEC))
    except asyncio.TimeoutError:
        print(f"⚠️ TTS warmup wait timed out after {TTS_WARMUP_WAIT_SEC:.1f}s; continuing.")
    except Exception as e:
        print(f"⚠️ TTS warmup wait failed: {e}")
