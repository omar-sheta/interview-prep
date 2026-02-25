"""
Audio Service for Speech-to-Text (STT) using MLX-Whisper.
Optimized for Apple Silicon with the large-v3-turbo model.
"""

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import threading
from typing import Optional

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel

from server.config import settings


# ============== Global Model Cache ==============

_whisper_model_instance = None
# large-v3-turbo is extremely fast and accurate on modern GPUs
WHISPER_MODEL_ID = "large-v3-turbo"


def _pcm16_bytes_to_float32(audio_data: bytes) -> np.ndarray:
    """Convert raw 16-bit PCM mono bytes into float32 waveform in [-1, 1]."""
    if not audio_data:
        return np.array([], dtype=np.float32)
    return np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0


def _resample_audio(audio_array: np.ndarray, from_rate: int, to_rate: int = 16000) -> np.ndarray:
    """Resample float32 mono audio using linear interpolation."""
    if from_rate == to_rate or len(audio_array) == 0:
        return audio_array
    duration = len(audio_array) / max(1, from_rate)
    target_length = int(duration * to_rate)
    if target_length <= 0:
        return np.array([], dtype=np.float32)
    indices = np.linspace(0, len(audio_array) - 1, target_length)
    return np.interp(indices, np.arange(len(audio_array)), audio_array).astype(np.float32)


def _normalize_transcript_text(text: str) -> str:
    """Clean transcript text from tool artifacts and normalize whitespace."""
    if not text:
        return ""
    cleaned = re.sub(r"\[[^\]]+\]", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _ensure_whisper_loaded():
    """
    Ensure Whisper model is loaded using faster-whisper.
    """
    global _whisper_model_instance
    if _whisper_model_instance is None:
        print(f"🔄 Loading Whisper model: {WHISPER_MODEL_ID}")
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        _whisper_model_instance = WhisperModel(WHISPER_MODEL_ID, device=device, compute_type=compute_type)
        print(f"✅ Whisper model ready on {device}")
    return _whisper_model_instance


# ============== Audio Processor ==============

class AudioProcessor:
    """
    Audio processing service using faster-whisper for transcription.
    Optimized for NVIDIA GPUs and CUDA.
    """
    
    def __init__(self):
        self.sample_rate = 16000  # Whisper expects 16kHz audio
        self._inference_lock = threading.Lock()
    
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
        
        # Convert bytes to numpy array (16-bit signed PCM, mono), normalized to [-1, 1]
        audio_array = _pcm16_bytes_to_float32(audio_data)
        
        # Resample if needed
        if sample_rate != 16000:
            audio_array = _resample_audio(audio_array, from_rate=sample_rate, to_rate=16000)
        
        # Keep final-pass calls serialized to avoid backend crashes.
        model = _ensure_whisper_loaded()
        with self._inference_lock:
            segments, info = model.transcribe(
                audio_array,
                language="en",
                task="transcribe",
                temperature=0.0,
                condition_on_previous_text=False,
                compression_ratio_threshold=2.4,
                no_speech_threshold=0.6,
            )
            text = " ".join([segment.text for segment in segments])
        
        return text.strip()
    
    def transcribe_file(self, file_path: str) -> str:
        """
        Transcribe an audio file to text.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Transcribed text string
        """
        model = _ensure_whisper_loaded()
        
        with self._inference_lock:
            segments, info = model.transcribe(
                file_path,
                language="en",
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = " ".join([segment.text for segment in segments])
        
        return text.strip()
    
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


class WhisperCppStreamingProcessor:
    """
    Low-latency streaming STT based on whisper.cpp CLI.
    Designed for partial transcript updates during live recording.
    """

    def __init__(self):
        self.enabled = bool(settings.WHISPER_CPP_ENABLED)
        self.binary = (settings.WHISPER_CPP_BIN or "whisper-cli").strip()
        self.model_path = (settings.WHISPER_CPP_MODEL_PATH or "").strip()
        self.language = (settings.WHISPER_CPP_LANGUAGE or "en").strip() or "en"
        self.threads = int(settings.WHISPER_CPP_THREADS)
        self.gpu_layers = int(settings.WHISPER_CPP_GPU_LAYERS)
        self.timeout_sec = float(settings.WHISPER_CPP_TIMEOUT_SEC)
        self._warned_unavailable = False
        self._force_cpu = self.gpu_layers <= 0
        self._logged_cpu_fallback = False

    def is_available(self) -> bool:
        """Return True when whisper.cpp is fully configured and executable."""
        if not self.enabled:
            return False
        if not self.model_path or not os.path.exists(self.model_path):
            return False
        return shutil.which(self.binary) is not None

    def _warn_unavailable_once(self):
        if self._warned_unavailable:
            return
        self._warned_unavailable = True
        print(
            "⚠️ whisper.cpp streaming unavailable; set WHISPER_CPP_MODEL_PATH and "
            "ensure WHISPER_CPP_BIN is installed."
        )

    def _looks_like_gpu_issue(self, diag: str) -> bool:
        """Detect common GPU init/runtime failures so we can stick to CPU afterwards."""
        text = (diag or "").lower()
        markers = (
            "whisper_backend_init_gpu: no gpu found",
            "ggml_metal_buffer_init: error",
            "failed to allocate buffer",
        )
        return any(marker in text for marker in markers)

    def _set_force_cpu_once(self):
        if self._force_cpu:
            return
        self._force_cpu = True
        if not self._logged_cpu_fallback:
            self._logged_cpu_fallback = True
            print("ℹ️ whisper.cpp streaming: GPU unavailable, using CPU-only mode for subsequent chunks.")

    def transcribe_buffer(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribe a chunk of PCM audio with whisper.cpp.
        Returns empty string on errors so caller can fallback.
        """
        if not audio_data:
            return ""
        if not self.is_available():
            self._warn_unavailable_once()
            return ""

        audio_array = _pcm16_bytes_to_float32(audio_data)
        if sample_rate != 16000:
            audio_array = _resample_audio(audio_array, from_rate=sample_rate, to_rate=16000)
        if len(audio_array) < 1600:  # ~100 ms at 16kHz
            return ""

        try:
            with tempfile.TemporaryDirectory(prefix="whispercpp_chunk_") as tmp_dir:
                wav_path = os.path.join(tmp_dir, "chunk.wav")
                out_prefix = os.path.join(tmp_dir, "chunk")
                sf.write(wav_path, audio_array, 16000, subtype="PCM_16")

                base_cmd = [
                    self.binary,
                    "-m",
                    self.model_path,
                    "-f",
                    wav_path,
                    "-l",
                    self.language,
                    "-of",
                    out_prefix,
                    "-otxt",
                ]
                if self.threads > 0:
                    base_cmd.extend(["-t", str(self.threads)])

                def _run_whisper(no_gpu: bool) -> tuple[int, str, str]:
                    cmd = list(base_cmd)
                    if no_gpu:
                        cmd.append("-ng")
                    completed = subprocess.run(
                        cmd,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=max(1.0, self.timeout_sec),
                    )
                    txt_path = f"{out_prefix}.txt"
                    raw_text = ""
                    if os.path.exists(txt_path):
                        with open(txt_path, "r", encoding="utf-8") as f:
                            raw_text = f.read()
                    else:
                        raw_text = completed.stdout or completed.stderr or ""
                    diag_text = (completed.stdout or "") + "\n" + (completed.stderr or "")
                    return completed.returncode, _normalize_transcript_text(raw_text), diag_text

                # Primary run: GPU unless explicitly disabled.
                primary_no_gpu = self._force_cpu or self.gpu_layers <= 0
                rc, text_out, diag = _run_whisper(primary_no_gpu)
                if text_out:
                    return text_out

                # Retry once on CPU only if GPU run failed with an actual runtime/backend error.
                if not primary_no_gpu and (rc != 0 or self._looks_like_gpu_issue(diag)):
                    self._set_force_cpu_once()
                    rc2, text_out2, _ = _run_whisper(True)
                    if text_out2:
                        return text_out2
                    rc = rc2 if rc == 0 else rc
                return "" if rc != 0 else text_out
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""
        except Exception:
            return ""

    async def transcribe_buffer_async(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        """Async wrapper to keep event loop responsive."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.transcribe_buffer(audio_data, sample_rate),
        )


# ============== VAD (Voice Activity Detection) ==============

class VoiceActivityDetector:
    """
    Simple Voice Activity Detection using webrtcvad.
    Detects speech/silence to trigger transcription.
    """
    
    def __init__(self, sample_rate: int = 16000, aggressiveness: int = 3):
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
_streaming_audio_processor: Optional[AudioProcessor | WhisperCppStreamingProcessor] = None


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


def get_streaming_audio_processor() -> AudioProcessor | WhisperCppStreamingProcessor:
    """
    Get low-latency streaming STT processor.
    Prefers whisper.cpp, falls back to MLX-Whisper when unavailable.
    """
    global _streaming_audio_processor
    if _streaming_audio_processor is None:
        whisper_cpp = WhisperCppStreamingProcessor()
        if whisper_cpp.is_available():
            print(
                "✅ Streaming STT engine: whisper.cpp "
                f"(model={os.path.basename(whisper_cpp.model_path)})"
            )
            _streaming_audio_processor = whisper_cpp
        else:
            print("ℹ️ Streaming STT engine fallback: faster-whisper")
            _streaming_audio_processor = get_audio_processor()
    return _streaming_audio_processor
