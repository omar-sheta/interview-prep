"""
TTS Service using Qwen3-TTS via mlx-audio.
Optimized for Apple Silicon with MLX.
"""

import asyncio
import base64
import io
from typing import Optional

import numpy as np
import warnings
import os
import logging

# Hide non-critical hardware/tokenizer warnings from libraries
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*regex pattern.*")
os.environ["TOKENIZERS_PARALLELISM"] = "false"


# ============== Global TTS Cache ==============

_tts_model = None
QWEN3_TTS_MODEL_ID = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-4bit"


def _ensure_tts_loaded():
    """
    Lazy-load the Qwen3 TTS model into unified memory.
    """
    global _tts_model
    if _tts_model is None:
        # Silence library-level logging during load
        lib_logger = logging.getLogger("transformers")
        old_level = lib_logger.level
        lib_logger.setLevel(logging.ERROR)
        
        print(f"🔄 Loading TTS model: {QWEN3_TTS_MODEL_ID}...")
        try:
            from mlx_audio.tts.utils import get_model_path, load_model
            model_path = get_model_path(QWEN3_TTS_MODEL_ID)
            _tts_model = load_model(model_path)
            print(f"✅ Qwen3 TTS READY")
        finally:
            lib_logger.setLevel(old_level)
            
    return _tts_model


# ============== TTS Service ==============

class TTSService:
    """
    Text-to-Speech service using Qwen3-TTS via mlx-audio.
    Generates natural-sounding speech for the interviewer.
    """
    
    def __init__(self):
        """
        Initialize TTS service.
        """
        self._sample_rate = None  # Will be set from model
    
    @property
    def sample_rate(self) -> int:
        """Get sample rate from model (24kHz for Qwen3 TTS)."""
        if self._sample_rate is None:
            model = _ensure_tts_loaded()
            self._sample_rate = model.sample_rate
        return self._sample_rate
    
    def speak(self, text: str, instruct: Optional[str] = None) -> bytes:
        """
        Generate speech audio from text.
        
        Args:
            text: Text to synthesize
            instruct: Optional instruction for tone (e.g. "whispering", "angry", "cheerful")
            
        Returns:
            Raw PCM audio bytes (16-bit signed, mono, 24kHz)
        """
        model = _ensure_tts_loaded()
        
        # Generate audio with Qwen3 TTS (it's a generator)
        audio_array = None
        for result in model.generate(text=text, instruct=instruct):
            audio_array = result.audio
            break  # Get first (and typically only) result
        
        if audio_array is None:
            raise RuntimeError("Failed to generate audio")
        
        # Convert to numpy if it's an MLX array
        if hasattr(audio_array, 'tolist'):
            audio_array = np.array(audio_array)
        
        # Flatten if needed
        if audio_array.ndim > 1:
            audio_array = audio_array.flatten()
        
        # Normalize and convert to 16-bit PCM
        audio_array = np.clip(audio_array, -1.0, 1.0)
        audio_int16 = (audio_array * 32767).astype(np.int16)
        
        return audio_int16.tobytes()
    
    def speak_base64(self, text: str, instruct: Optional[str] = None) -> str:
        """
        Generate speech and return as base64-encoded string.
        Useful for sending over WebSocket/Socket.IO.
        
        Args:
            text: Text to synthesize
            instruct: Optional instruction for tone
            
        Returns:
            Base64-encoded audio data
        """
        audio_bytes = self.speak(text, instruct=instruct)
        return base64.b64encode(audio_bytes).decode('utf-8')
    
    def speak_wav(self, text: str, instruct: Optional[str] = None) -> bytes:
        """
        Generate speech and return as WAV file bytes.
        
        Args:
            text: Text to synthesize
            instruct: Optional instruction for tone
            
        Returns:
            WAV file bytes
        """
        import soundfile as sf
        
        model = _ensure_tts_loaded()
        
        # Generate audio with Qwen3 TTS
        audio_array = None
        for result in model.generate(text=text, instruct=instruct):
            audio_array = result.audio
            break
        
        if audio_array is None:
            raise RuntimeError("Failed to generate audio")
        
        # Convert to numpy
        if hasattr(audio_array, 'tolist'):
            audio_array = np.array(audio_array)
        
        # Flatten if needed
        if audio_array.ndim > 1:
            audio_array = audio_array.flatten()
        
        # Write to WAV buffer
        buffer = io.BytesIO()
        sf.write(buffer, audio_array, self.sample_rate, format='WAV', subtype='PCM_16')
        buffer.seek(0)
        
        return buffer.read()
    
    def speak_wav_base64(self, text: str) -> str:
        """
        Generate speech as WAV and return base64-encoded.
        
        Args:
            text: Text to synthesize
            
        Returns:
            Base64-encoded WAV data
        """
        wav_bytes = self.speak_wav(text)
        return base64.b64encode(wav_bytes).decode('utf-8')
    
    async def speak_async(self, text: str) -> bytes:
        """
        Async version of speak.
        Runs TTS in thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.speak(text))
    
    async def speak_wav_base64_async(self, text: str) -> str:
        """
        Async version of speak_wav_base64.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.speak_wav_base64(text))


# ============== Factory Function ==============

_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """Get or create the TTS service singleton."""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service


def preload_tts():
    """Preload TTS model at startup."""
    _ensure_tts_loaded()
