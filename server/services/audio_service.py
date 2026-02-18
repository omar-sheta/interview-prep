"""
Audio Service for Speech-to-Text (STT) using MLX-Whisper.
Optimized for Apple Silicon with the large-v3-turbo model.
"""

import asyncio
import io
from typing import Optional

import numpy as np
import soundfile as sf
import mlx_whisper

from server.config import settings


# ============== Global Model Cache ==============

_whisper_model: Optional[str] = None
WHISPER_MODEL_ID = "mlx-community/whisper-large-v3-turbo"


def _ensure_whisper_loaded():
    """
    Ensure Whisper model is loaded.
    The mlx_whisper library handles caching internally.
    """
    global _whisper_model
    if _whisper_model is None:
        print(f"🔄 Loading Whisper model: {WHISPER_MODEL_ID}")
        # Trigger model download/cache by doing a dummy transcription
        # The model will be cached for subsequent calls
        _whisper_model = WHISPER_MODEL_ID
        print(f"✅ Whisper model ready")


# ============== Audio Processor ==============

class AudioProcessor:
    """
    Audio processing service using MLX-Whisper for transcription.
    Uses the large-v3-turbo model for optimal M4 performance.
    """
    
    def __init__(self):
        self.model_id = WHISPER_MODEL_ID
        self.sample_rate = 16000  # Whisper expects 16kHz audio
    
    def transcribe_buffer(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribe raw PCM audio bytes to text.
        
        Args:
            audio_data: Raw PCM audio bytes (16-bit signed, mono)
            sample_rate: Sample rate of the audio (default 16kHz)
            
        Returns:
            Transcribed text string
        """
        _ensure_whisper_loaded()
        
        # Convert bytes to numpy array
        # Assuming 16-bit signed PCM, mono
        audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
        
        # Normalize to [-1, 1] range
        audio_array = audio_array / 32768.0
        
        # Resample if needed
        if sample_rate != 16000:
            # Simple resampling using linear interpolation
            duration = len(audio_array) / sample_rate
            target_length = int(duration * 16000)
            indices = np.linspace(0, len(audio_array) - 1, target_length)
            audio_array = np.interp(indices, np.arange(len(audio_array)), audio_array)
        
        # Transcribe using mlx_whisper
        result = mlx_whisper.transcribe(
            audio_array,
            path_or_hf_repo=self.model_id,
            language="en",
            task="transcribe",
            temperature=0.0,
            condition_on_previous_text=False,
            verbose=False,
        )
        
        return result.get("text", "").strip()
    
    def transcribe_file(self, file_path: str) -> str:
        """
        Transcribe an audio file to text.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Transcribed text string
        """
        _ensure_whisper_loaded()
        
        result = mlx_whisper.transcribe(
            file_path,
            path_or_hf_repo=self.model_id,
            language="en",
            temperature=0.0,
            condition_on_previous_text=False,
        )
        
        return result.get("text", "").strip()
    
    async def transcribe_buffer_async(
        self,
        audio_data: bytes,
        sample_rate: int = 16000
    ) -> str:
        """
        Async version of transcribe_buffer.
        Runs transcription in thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.transcribe_buffer(audio_data, sample_rate)
        )

    async def transcribe_file_async(self, file_path: str) -> str:
        """
        Async version of transcribe_file.
        Runs transcription in thread pool to avoid blocking.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.transcribe_file(file_path)
        )

    @staticmethod
    def resample_pcm(audio_bytes: bytes, from_rate: int, to_rate: int = 16000) -> bytes:
        """
        Resample PCM audio bytes to target rate.
        Input/Output: 16-bit signed PCM, Mono.
        """
        if from_rate == to_rate:
            return audio_bytes
            
        # Bytes -> Int16 -> Float32
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        
        # Resample
        duration = len(audio_array) / from_rate
        target_length = int(duration * to_rate)
        indices = np.linspace(0, len(audio_array) - 1, target_length)
        resampled = np.interp(indices, np.arange(len(audio_array)), audio_array)
        
        # Float32 -> Int16 -> Bytes
        return resampled.astype(np.int16).tobytes()

    @staticmethod
    def calculate_rms(audio_bytes: bytes) -> float:
        """
        Calculate Root Mean Square (RMS) amplitude of audio bytes.
        Returns value between 0.0 and 1.0 (approximated for normalized Int16).
        """
        if not audio_bytes:
            return 0.0
        
        # Bytes -> Int16 -> Float32
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        
        # Calculate RMS
        rms = np.sqrt(np.mean(audio_array**2))
        
        # Normalize by max possible amplitude (32768)
        return float(rms / 32768.0)


# ============== VAD (Voice Activity Detection) ==============

class VoiceActivityDetector:
    """
    Simple Voice Activity Detection using webrtcvad.
    Detects speech/silence to trigger transcription.
    """
    
    def __init__(self, sample_rate: int = 16000, aggressiveness: int = 2):
        """
        Initialize VAD.
        
        Args:
            sample_rate: Audio sample rate (must be 8000, 16000, 32000, or 48000)
            aggressiveness: VAD aggressiveness from 0-3 (3 = most aggressive)
        """
        import webrtcvad
        
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_duration_ms = 30  # WebRTC VAD supports 10, 20, or 30 ms
        self.frame_size = int(sample_rate * self.frame_duration_ms / 1000)
    
    def is_speech(self, audio_frame: bytes) -> bool:
        """
        Check if an audio frame contains speech.
        
        Args:
            audio_frame: Raw PCM audio bytes (16-bit signed, mono)
            
        Returns:
            True if speech is detected, False otherwise
        """
        # Frame must be exactly the right size for webrtcvad
        expected_size = self.frame_size * 2  # 2 bytes per sample (16-bit)
        if len(audio_frame) != expected_size:
            return False
        
        try:
            return self.vad.is_speech(audio_frame, self.sample_rate)
        except Exception:
            return False
    
    def detect_silence_duration(
        self, 
        audio_buffer: bytes, 
        threshold_ms: int = 600  # Reduced from 1500 for snappy, conversational feel
    ) -> bool:
        """
        Check if the end of audio buffer has silence for threshold duration.
        
        Args:
            audio_buffer: Full audio buffer
            threshold_ms: Silence threshold in milliseconds
            
        Returns:
            True if silence detected for threshold duration
        """
        frame_bytes = self.frame_size * 2
        num_frames_threshold = int(threshold_ms / self.frame_duration_ms)
        
        if len(audio_buffer) < frame_bytes * num_frames_threshold:
            return False
        
        # Check last N frames
        silence_frames = 0
        for i in range(num_frames_threshold):
            start = len(audio_buffer) - (i + 1) * frame_bytes
            end = start + frame_bytes
            frame = audio_buffer[start:end]
            
            if not self.is_speech(frame):
                silence_frames += 1
            else:
                break
        
        return silence_frames >= num_frames_threshold


# ============== Factory Functions ==============

_audio_processor: Optional[AudioProcessor] = None
_vad: Optional[VoiceActivityDetector] = None


def get_audio_processor() -> AudioProcessor:
    """Get or create the audio processor singleton."""
    global _audio_processor
    if _audio_processor is None:
        _audio_processor = AudioProcessor()
    return _audio_processor


def get_vad() -> VoiceActivityDetector:
    """Get or create the VAD singleton."""
    global _vad
    if _vad is None:
        _vad = VoiceActivityDetector()
    return _vad
