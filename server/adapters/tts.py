"""
TTS Service for BeePrepared.

Supported user-selectable providers:
- Piper (CLI, ONNX voices including high-quality models)
- Qwen3-TTS CUDA (official qwen-tts or faster-qwen3-tts acceleration on NVIDIA GPUs)

Fallback backends: NeuTTS Air (Neuphonic), Kokoro-82M via PyTorch (optional)
"""

import asyncio
import base64
import io
import json
import shutil
import subprocess
import tempfile
from typing import Any, Optional
from pathlib import Path

import numpy as np
import warnings
import os
import logging
import threading

# Hide non-critical hardware/tokenizer warnings from libraries
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*regex pattern.*")
os.environ["TOKENIZERS_PARALLELISM"] = "false"


# ============== Global TTS Cache / Settings ==============

_tts_model = None
_tts_backend_kind: Optional[str] = None
_tts_sample_rate = 24000
_neutts_speaker_codes = None
_neutts_ref_audio_path = ""
_neutts_ref_text = ""
_piper_model_path = ""
_piper_config_path = ""
_piper_binary = ""
_qwen3_tts_model = None
_qwen3_tts_sample_rate = 24000
_qwen3_tts_disabled_reason = ""
_qwen3_tts_backend_variant = ""

TTS_BACKEND = os.getenv("TTS_BACKEND", "piper").strip().lower()
TTS_ALLOW_FALLBACK = os.getenv("TTS_ALLOW_FALLBACK", "1").lower() in {"1", "true", "yes", "on"}
TTS_PROVIDER = os.getenv("TTS_PROVIDER", TTS_BACKEND).strip().lower()

# Piper configuration
PIPER_BINARY = os.getenv("PIPER_BINARY", "piper").strip()
PIPER_MODEL_PATH = os.getenv("PIPER_MODEL_PATH", "").strip()
PIPER_CONFIG_PATH = os.getenv("PIPER_CONFIG_PATH", "").strip()
PIPER_SPEAKER_ID = os.getenv("PIPER_SPEAKER_ID", "").strip()
PIPER_STYLE = os.getenv("PIPER_STYLE", "interviewer").strip().lower()
PIPER_LENGTH_SCALE_RAW = os.getenv("PIPER_LENGTH_SCALE", "").strip()
PIPER_NOISE_SCALE_RAW = os.getenv("PIPER_NOISE_SCALE", "").strip()
PIPER_NOISE_W_SCALE_RAW = os.getenv("PIPER_NOISE_W_SCALE", "").strip()
PIPER_SENTENCE_SILENCE_RAW = os.getenv("PIPER_SENTENCE_SILENCE", "").strip()
PIPER_VOLUME_RAW = os.getenv("PIPER_VOLUME", "").strip()
PIPER_SAMPLE_RATE = int(os.getenv("PIPER_SAMPLE_RATE", "22050"))
PIPER_CMD_TIMEOUT_SEC = float(os.getenv("PIPER_CMD_TIMEOUT_SEC", "180"))
PIPER_AUTO_DISCOVER = os.getenv("PIPER_AUTO_DISCOVER", "1").lower() in {"1", "true", "yes", "on"}
PIPER_APPEND_TERMINAL_PUNCT = os.getenv("PIPER_APPEND_TERMINAL_PUNCT", "1").lower() in {"1", "true", "yes", "on"}
PIPER_COLLAPSE_WHITESPACE = os.getenv("PIPER_COLLAPSE_WHITESPACE", "1").lower() in {"1", "true", "yes", "on"}

# NeuTTS configuration
NEUTTS_MODEL_ID = os.getenv("NEUTTS_MODEL_ID", "neuphonic/neutts-air")
NEUTTS_DEFAULT_SPEAKER = os.getenv("NEUTTS_SPEAKER", "").strip() or None
NEUTTS_REF_AUDIO_PATH = os.getenv("NEUTTS_REF_AUDIO_PATH", "").strip()
NEUTTS_REF_TEXT = os.getenv("NEUTTS_REF_TEXT", "").strip()
NEUTTS_SAMPLE_RATE = int(os.getenv("NEUTTS_SAMPLE_RATE", "24000"))
NEUTTS_DYNAMIC_REF_TEXT = os.getenv("NEUTTS_DYNAMIC_REF_TEXT", "1").lower() in {"1", "true", "yes", "on"}

# Kokoro fallback configuration
KOKORO_MODEL_ID = os.getenv("KOKORO_MODEL_ID", "hexgrad/Kokoro-82M")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_bella")  # Warm, professional female voice
KOKORO_SPEED = float(os.getenv("KOKORO_SPEED", "0.9"))  # Slightly slower for clearer articulation
KOKORO_LANG = os.getenv("KOKORO_LANG", "a")  # "a" = American English

# Qwen3-TTS CUDA configuration
QWEN3_TTS_MODEL_ID = os.getenv("QWEN3_TTS_MODEL_ID", "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice").strip()
QWEN3_TTS_SAMPLE_RATE = int(os.getenv("QWEN3_TTS_SAMPLE_RATE", "24000"))
QWEN3_TTS_SPEAKER = os.getenv("QWEN3_TTS_SPEAKER", "Aiden").strip()
QWEN3_TTS_INSTRUCT = os.getenv(
    "QWEN3_TTS_INSTRUCT",
    "Professional and clear."
).strip()
QWEN3_TTS_ENGINE = os.getenv("QWEN3_TTS_ENGINE", "auto").strip().lower()
QWEN3_TTS_STREAMING_ENABLED = os.getenv("QWEN3_TTS_STREAMING_ENABLED", "1").lower() in {"1", "true", "yes", "on"}
QWEN3_TTS_STREAM_CHUNK_SIZE = max(1, min(16, int(os.getenv("QWEN3_TTS_STREAM_CHUNK_SIZE", "8"))))
QWEN3_TTS_ATTN_IMPLEMENTATION = os.getenv("QWEN3_TTS_ATTN_IMPLEMENTATION", "sdpa").strip() or "sdpa"
QWEN3_TTS_DTYPE = os.getenv("QWEN3_TTS_DTYPE", "bfloat16").strip() or "bfloat16"

SAVE_TTS_DEBUG_AUDIO = os.getenv("SAVE_TTS_DEBUG_AUDIO", "0").lower() in {"1", "true", "yes", "on"}
# Qwen3 TTS model is not thread-safe (shared GPU state/KV cache).
# Must serialize GPU inference. The asyncio.Lock was removed so callers
# queue here in the thread pool instead of blocking the event loop.
_tts_infer_semaphore = threading.Semaphore(1)
ALLOWED_PIPER_STYLES = {"interviewer", "balanced", "fast"}
ALLOWED_TTS_PROVIDERS = {"piper", "qwen3_tts"}


def _normalize_tts_provider(provider: Optional[str], fallback: str = "piper") -> str:
    normalized_fallback = str(fallback or "piper").strip().lower()
    # Accept legacy "qwen3_tts_mlx" as alias for "qwen3_tts"
    if normalized_fallback == "qwen3_tts_mlx":
        normalized_fallback = "qwen3_tts"
    if normalized_fallback not in ALLOWED_TTS_PROVIDERS:
        normalized_fallback = "piper"
    normalized = str(provider or "").strip().lower()
    if normalized == "qwen3_tts_mlx":
        normalized = "qwen3_tts"
    if normalized in ALLOWED_TTS_PROVIDERS:
        return normalized
    return normalized_fallback


DEFAULT_TTS_PROVIDER = _normalize_tts_provider(TTS_PROVIDER, fallback="piper")


def _normalize_qwen3_tts_model_id(model_id: Optional[str]) -> str:
    """Map legacy shorthand ids to valid Hugging Face checkpoints."""
    normalized = str(model_id or "").strip()
    alias_map = {
        "Qwen/Qwen3-TTS-1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "Qwen/Qwen3-TTS-0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
        "Qwen/Qwen3-TTS-CustomVoice-1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
        "Qwen/Qwen3-TTS-CustomVoice-0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    }
    return alias_map.get(normalized, normalized or "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice")


def _normalize_qwen3_speaker_name(speaker: Optional[str]) -> str:
    """Normalize common speaker aliases while preserving official case-sensitive names."""
    normalized = str(speaker or "").strip()
    if not normalized:
        return "Aiden"
    alias_map = {
        "aiden": "Aiden",
        "ryan": "Ryan",
        "vivian": "Vivian",
        "serena": "Serena",
        "uncle_fu": "Uncle_Fu",
        "uncle fu": "Uncle_Fu",
        "dylan": "Dylan",
        "eric": "Eric",
        "ono_anna": "Ono_Anna",
        "ono anna": "Ono_Anna",
        "sohee": "Sohee",
    }
    return alias_map.get(normalized.lower(), normalized)


def _disable_qwen3_tts(reason: str) -> None:
    """Disable qwen3 provider for this process after a hard initialization/generation failure."""
    global _qwen3_tts_model
    global _qwen3_tts_disabled_reason
    global _qwen3_tts_backend_variant
    _qwen3_tts_model = None
    _qwen3_tts_backend_variant = ""
    _qwen3_tts_disabled_reason = str(reason or "unknown_error")


def _inject_local_sox_paths() -> None:
    """Expose bundled SoX binaries/libs before importing qwen_tts-based packages."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sox_bin = os.path.join(base_dir, "sox_local/usr/bin")
    sox_lib = os.path.join(base_dir, "sox_local/usr/lib/aarch64-linux-gnu")

    if os.path.exists(sox_bin):
        os.environ["PATH"] = f"{sox_bin}:{os.environ.get('PATH', '')}"
    if os.path.exists(sox_lib):
        sox_fmt_lib = os.path.join(sox_lib, "sox")
        os.environ["LD_LIBRARY_PATH"] = f"{sox_lib}:{sox_fmt_lib}:{os.environ.get('LD_LIBRARY_PATH', '')}"


def _estimate_qwen3_max_new_tokens(text: str) -> int:
    """Bound codec-token generation to the length of the prompt instead of the package hard default."""
    text_len = len((text or "").strip())
    return min(2048, max(512, text_len * 5))


def _float_audio_to_pcm16_bytes(audio_array: np.ndarray) -> bytes:
    """Convert float audio in [-1, 1] to mono PCM16 bytes for socket streaming."""
    audio_array = np.clip(_to_float_audio(audio_array), -1.0, 1.0)
    return (audio_array * 32767).astype(np.int16).tobytes()


def _piper_style_defaults(style: str) -> dict[str, float]:
    """
    Piper tuning presets.
    - interviewer: clear, slightly slower, lower randomness for stable prompts
    - balanced: Piper defaults
    - fast: quicker for low-latency flows
    """
    key = (style or "").strip().lower()
    if key == "interviewer":
        return {
            "length_scale": 1.10,
            "noise_scale": 0.45,
            "noise_w_scale": 0.65,
            "sentence_silence": 0.14,
            "volume": 1.05,
        }
    if key == "fast":
        return {
            "length_scale": 0.95,
            "noise_scale": 0.60,
            "noise_w_scale": 0.75,
            "sentence_silence": 0.05,
            "volume": 1.00,
        }
    # balanced / unknown => use Piper-ish defaults
    return {
        "length_scale": 1.00,
        "noise_scale": 0.667,
        "noise_w_scale": 0.80,
        "sentence_silence": 0.08,
        "volume": 1.00,
    }


def _normalize_piper_style(style: Optional[str], fallback: str = "interviewer") -> str:
    normalized_fallback = str(fallback or "interviewer").strip().lower()
    if normalized_fallback not in ALLOWED_PIPER_STYLES:
        normalized_fallback = "interviewer"
    normalized = str(style or "").strip().lower()
    if normalized in ALLOWED_PIPER_STYLES:
        return normalized
    return normalized_fallback


def _float_override(raw: str, default: float) -> float:
    if not raw:
        return default
    try:
        return float(raw)
    except Exception:
        return default


_piper_defaults = _piper_style_defaults(PIPER_STYLE)
PIPER_LENGTH_SCALE = _float_override(PIPER_LENGTH_SCALE_RAW, _piper_defaults["length_scale"])
PIPER_NOISE_SCALE = _float_override(PIPER_NOISE_SCALE_RAW, _piper_defaults["noise_scale"])
PIPER_NOISE_W_SCALE = _float_override(PIPER_NOISE_W_SCALE_RAW, _piper_defaults["noise_w_scale"])
PIPER_SENTENCE_SILENCE = _float_override(PIPER_SENTENCE_SILENCE_RAW, _piper_defaults["sentence_silence"])
PIPER_VOLUME = _float_override(PIPER_VOLUME_RAW, _piper_defaults["volume"])


def _resolve_piper_tuning(style: Optional[str] = None) -> dict[str, float | str]:
    """
    Resolve effective piper parameters for the request.
    Style can be overridden per synthesis call while env overrides remain authoritative.
    """
    style_key = _normalize_piper_style(style, fallback=PIPER_STYLE)
    defaults = _piper_style_defaults(style_key)
    return {
        "style": style_key,
        "length_scale": _float_override(PIPER_LENGTH_SCALE_RAW, defaults["length_scale"]),
        "noise_scale": _float_override(PIPER_NOISE_SCALE_RAW, defaults["noise_scale"]),
        "noise_w_scale": _float_override(PIPER_NOISE_W_SCALE_RAW, defaults["noise_w_scale"]),
        "sentence_silence": _float_override(PIPER_SENTENCE_SILENCE_RAW, defaults["sentence_silence"]),
        "volume": _float_override(PIPER_VOLUME_RAW, defaults["volume"]),
    }


def _prepare_piper_text(text: str) -> str:
    """Normalize prompt text for cleaner prosody in interviewer playback."""
    t = str(text or "")
    if PIPER_COLLAPSE_WHITESPACE:
        t = " ".join(t.split())
    if PIPER_APPEND_TERMINAL_PUNCT and t and t[-1] not in ".!?":
        t = f"{t}."
    return t


def _resolve_piper_binary() -> Optional[str]:
    """Resolve Piper CLI binary path."""
    if PIPER_BINARY:
        explicit = Path(PIPER_BINARY).expanduser()
        if explicit.exists() and explicit.is_file():
            return str(explicit)
        resolved = shutil.which(PIPER_BINARY)
        if resolved:
            return resolved

    resolved = shutil.which("piper")
    if resolved:
        return resolved

    for candidate in (
        "/usr/local/bin/piper",
        "/usr/bin/piper",
    ):
        p = Path(candidate)
        if p.exists() and p.is_file():
            return str(p)
    return None


def _rank_piper_model(path: Path) -> tuple[int, str]:
    """Prefer high-quality English voices when auto-selecting models."""
    name = path.name.lower()
    score = 0
    if "high" in name:
        score += 100
    elif "medium" in name:
        score += 50
    elif "low" in name:
        score += 10
    if "en_us" in name or "en-us" in name or "english" in name:
        score += 20
    if "libritts" in name or "lessac" in name:
        score += 5
    return score, name


def _discover_piper_model_path() -> Optional[Path]:
    """Auto-discover a Piper ONNX model from common locations."""
    if not PIPER_AUTO_DISCOVER:
        return None

    project_root = Path(__file__).resolve().parent.parent.parent
    home = Path.home()
    search_roots = [
        project_root / "piper_models",
        project_root / "models" / "piper",
        project_root / "models",
        home / ".local" / "share" / "piper",
        home / ".cache" / "piper",
    ]

    candidates: list[Path] = []
    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue
        for p in root.rglob("*.onnx"):
            if p.is_file():
                candidates.append(p.resolve())

    if not candidates:
        return None

    candidates.sort(key=lambda p: _rank_piper_model(p), reverse=True)
    return candidates[0]


def _to_float_audio(audio_data) -> np.ndarray:
    """Normalize supported audio tensor formats to mono float32 [-1, 1]."""
    if isinstance(audio_data, tuple):
        # Handle `(audio, sample_rate)` return signatures.
        audio_data = audio_data[0]

    if hasattr(audio_data, "detach"):
        audio_data = audio_data.detach().cpu().numpy()
    elif hasattr(audio_data, "numpy"):
        audio_data = audio_data.numpy()

    audio_array = np.asarray(audio_data, dtype=np.float32)
    if audio_array.ndim > 1:
        audio_array = audio_array.reshape(-1)

    peak = float(np.max(np.abs(audio_array))) if audio_array.size else 0.0
    # Some backends may return int16-ish ranges; normalize if needed.
    if peak > 1.25:
        audio_array = audio_array / 32767.0

    return np.clip(audio_array, -1.0, 1.0)


def _load_piper():
    """Load Piper CLI backend and resolve model/config."""
    global _tts_model
    global _tts_backend_kind
    global _tts_sample_rate
    global _piper_model_path
    global _piper_config_path
    global _piper_binary

    binary = _resolve_piper_binary()
    if not binary:
        raise FileNotFoundError(
            "Piper CLI binary not found. Install Piper and/or set PIPER_BINARY."
        )

    model_path = None
    if PIPER_MODEL_PATH:
        candidate = Path(PIPER_MODEL_PATH).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"PIPER_MODEL_PATH not found: {candidate}")
        model_path = candidate
    else:
        discovered = _discover_piper_model_path()
        if discovered:
            model_path = discovered
            print(f"ℹ️  Auto-discovered Piper model: {model_path.name}")

    if not model_path:
        raise FileNotFoundError(
            "No Piper model found. Set PIPER_MODEL_PATH to a .onnx voice file "
            "(e.g., en_US-*-high.onnx)."
        )

    config_path: Optional[Path] = None
    if PIPER_CONFIG_PATH:
        explicit_cfg = Path(PIPER_CONFIG_PATH).expanduser().resolve()
        if not explicit_cfg.exists():
            raise FileNotFoundError(f"PIPER_CONFIG_PATH not found: {explicit_cfg}")
        config_path = explicit_cfg
    else:
        for candidate in (
            Path(str(model_path) + ".json"),
            model_path.with_suffix(".json"),
        ):
            if candidate.exists():
                config_path = candidate.resolve()
                break

    sample_rate = PIPER_SAMPLE_RATE
    if config_path:
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            sample_rate = int(cfg.get("audio", {}).get("sample_rate", sample_rate))
        except Exception as e:
            print(f"⚠️ Failed to parse Piper config for sample_rate: {e}")

    _piper_binary = binary
    _piper_model_path = str(model_path)
    _piper_config_path = str(config_path) if config_path else ""
    _tts_model = {
        "binary": _piper_binary,
        "model_path": _piper_model_path,
        "config_path": _piper_config_path,
    }
    _tts_backend_kind = "piper"
    _tts_sample_rate = sample_rate

    cfg_note = f", config={Path(_piper_config_path).name}" if _piper_config_path else ""
    default_tune = _resolve_piper_tuning(None)
    print(
        f"✅ Piper READY (model={model_path.name}{cfg_note}, sample_rate={_tts_sample_rate})"
    )
    print(
        "ℹ️  Piper tune:"
        f" style={default_tune['style']}, length={default_tune['length_scale']}, noise={default_tune['noise_scale']},"
        f" noise_w={default_tune['noise_w_scale']}, sentence_silence={default_tune['sentence_silence']},"
        f" volume={default_tune['volume']}"
    )


def _load_neutts():
    """Load NeuTTS Air and encode reference speaker codes (required for v1.1.0+)."""
    global _tts_model
    global _tts_backend_kind
    global _tts_sample_rate
    global _neutts_speaker_codes
    global _neutts_ref_audio_path
    global _neutts_ref_text

    print(f"🔄 Loading TTS backend (NeuTTS): {NEUTTS_MODEL_ID}...")
    from neutts import NeuTTS
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"🎯 NeuTTS device: {device}")
    model = NeuTTS(backbone_repo=NEUTTS_MODEL_ID, backbone_device=device, codec_device=device)

    # NeuTTS v1.1.0 API: infer(text, ref_codes, ref_text) ALWAYS requires
    # reference audio codes.  Find a reference WAV to encode.
    ref_audio_path = NEUTTS_REF_AUDIO_PATH
    if not ref_audio_path:
        # Auto-discover a default reference WAV from the project root.
        _project_root = Path(__file__).resolve().parent.parent.parent
        for candidate in ("pro.wav", "happy.wav", "whisper.wav"):
            candidate_path = _project_root / candidate
            if candidate_path.exists():
                ref_audio_path = str(candidate_path)
                print(f"ℹ️  No NEUTTS_REF_AUDIO_PATH set, using default: {candidate}")
                break

    if not ref_audio_path:
        raise FileNotFoundError(
            "NeuTTS v1.1.0 requires a reference audio file. "
            "Set NEUTTS_REF_AUDIO_PATH or place a .wav file in the project root."
        )

    ref_audio = Path(ref_audio_path).expanduser().resolve()
    if not ref_audio.exists():
        raise FileNotFoundError(f"NEUTTS_REF_AUDIO_PATH not found: {ref_audio}")

    # Encode the reference audio into speaker codes.
    _neutts_speaker_codes = model.encode_reference(str(ref_audio))

    # Reference text (for the infer call).
    ref_text = NEUTTS_REF_TEXT.strip()
    if not ref_text:
        sidecar = ref_audio.with_suffix(".txt")
        if sidecar.exists():
            ref_text = sidecar.read_text(encoding="utf-8").strip()
    if not ref_text:
        ref_text = ""
        if NEUTTS_DYNAMIC_REF_TEXT:
            print("ℹ️  No NEUTTS_REF_TEXT/pro.txt found; using dynamic ref_text from request text.")
        else:
            print("ℹ️  No NEUTTS_REF_TEXT/pro.txt found; using empty ref_text.")

    _neutts_ref_audio_path = str(ref_audio)
    _neutts_ref_text = ref_text
    print(f"✅ NeuTTS speaker reference loaded from {ref_audio.name}")

    _tts_model = model
    _tts_backend_kind = "neutts"
    _tts_sample_rate = int(getattr(model, "sample_rate", NEUTTS_SAMPLE_RATE))
    print(f"✅ NeuTTS READY (device={device}, sample_rate={_tts_sample_rate})")


def _load_kokoro():
    """Load Kokoro PyTorch as compatibility fallback."""
    global _tts_model
    global _tts_backend_kind
    global _tts_sample_rate

    # Silence library-level logging during load
    lib_logger = logging.getLogger("transformers")
    old_level = lib_logger.level
    lib_logger.setLevel(logging.ERROR)

    print(f"🔄 Loading TTS fallback (Kokoro PyTorch)...")
    try:
        from kokoro import KPipeline
        import torch

        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model = KPipeline(lang_code=KOKORO_LANG, device=device)

        # Warm up the pipeline
        for _ in model(
            "ready", voice=KOKORO_VOICE, speed=KOKORO_SPEED, split_pattern=r'\n+'
        ):
            break

        _tts_model = model
        _tts_backend_kind = "kokoro"
        _tts_sample_rate = 24000
        print(f"✅ Kokoro READY (sample_rate={_tts_sample_rate}, device={device})")
    finally:
        lib_logger.setLevel(old_level)


def _load_qwen3_tts_cuda():
    """Load Qwen3-TTS model via qwen-tts on CUDA."""
    global _qwen3_tts_model
    global _qwen3_tts_sample_rate
    global _qwen3_tts_backend_variant

    import importlib.util
    import sys
    import torch

    _inject_local_sox_paths()

    model_id = _normalize_qwen3_tts_model_id(QWEN3_TTS_MODEL_ID)
    print(f"🔄 Loading TTS backend (Qwen3-TTS CUDA): {model_id}...")
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

    faster_import_error = None
    if torch.cuda.is_available() and QWEN3_TTS_ENGINE in {"auto", "faster"}:
        try:
            from faster_qwen3_tts import FasterQwen3TTS

            fast_dtype = QWEN3_TTS_DTYPE
            model = FasterQwen3TTS.from_pretrained(
                model_id,
                device=device,
                dtype=fast_dtype,
                attn_implementation=QWEN3_TTS_ATTN_IMPLEMENTATION,
            )
            _qwen3_tts_model = model
            _qwen3_tts_sample_rate = int(getattr(model, "sample_rate", QWEN3_TTS_SAMPLE_RATE))
            _qwen3_tts_backend_variant = "faster"
            print(
                f"✅ Qwen3-TTS CUDA READY (engine=faster, device={device}, sample_rate={_qwen3_tts_sample_rate})"
            )
            return
        except Exception as err:
            faster_import_error = err
            if QWEN3_TTS_ENGINE == "faster":
                msg = str(err)
                _disable_qwen3_tts(f"fast_load_failed: {msg}")
                raise RuntimeError(
                    f"Faster Qwen3-TTS load failed ({msg}). "
                    "Ensure faster-qwen3-tts is installed and CUDA is available."
                ) from err
            print(f"⚠️ Faster Qwen3-TTS unavailable ({err}). Falling back to official qwen-tts.")

    try:
        # Suppress stderr during import to hide non-critical flash-attn warnings.
        devnull = open(os.devnull, 'w')
        old_stderr = sys.stderr
        sys.stderr = devnull
        try:
            import qwen_tts  # noqa: F401
            from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel as QwenTTS
        finally:
            sys.stderr = old_stderr
            devnull.close()
    except ImportError as import_err:
        _disable_qwen3_tts(f"qwen_tts_import_failed: {import_err}")
        raise RuntimeError(
            f"Qwen3-TTS CUDA unavailable because qwen-tts import failed ({import_err}). "
            "Install with: pip install qwen-tts"
        ) from import_err

    try:
        load_kwargs = {
            "device_map": device,
            "dtype": dtype,
        }
        if torch.cuda.is_available() and importlib.util.find_spec("flash_attn") is not None:
            load_kwargs["attn_implementation"] = "flash_attention_2"

        try:
            model = QwenTTS.from_pretrained(model_id, **load_kwargs)
        except TypeError as err:
            if "attn_implementation" not in str(err):
                raise
            load_kwargs.pop("attn_implementation", None)
            model = QwenTTS.from_pretrained(model_id, **load_kwargs)
        _qwen3_tts_model = model
        _qwen3_tts_sample_rate = QWEN3_TTS_SAMPLE_RATE
        _qwen3_tts_backend_variant = "official"
        if faster_import_error:
            print(
                f"✅ Qwen3-TTS CUDA READY (engine=official fallback, device={device}, sample_rate={_qwen3_tts_sample_rate})"
            )
        else:
            print(f"✅ Qwen3-TTS CUDA READY (engine=official, device={device}, sample_rate={_qwen3_tts_sample_rate})")
    except Exception as err:
        msg = str(err)
        _disable_qwen3_tts(f"load_failed: {msg}")
        raise RuntimeError(
            f"Qwen3-TTS CUDA load failed ({msg}). "
            "Ensure qwen-tts is installed and CUDA is available."
        ) from err


def _ensure_qwen3_tts_loaded():
    """Lazy-load Qwen3-TTS model."""
    global _qwen3_tts_model
    if _qwen3_tts_disabled_reason:
        raise RuntimeError(
            f"Qwen3-TTS disabled in this process: {_qwen3_tts_disabled_reason}"
        )
    if _qwen3_tts_model is None:
        _load_qwen3_tts_cuda()
    return _qwen3_tts_model


def _qwen3_tts_supports_streaming() -> bool:
    """True when the loaded qwen backend can emit realtime audio chunks."""
    model = _ensure_qwen3_tts_loaded()
    return (
        QWEN3_TTS_STREAMING_ENABLED
        and _qwen3_tts_backend_variant == "faster"
        and hasattr(model, "generate_custom_voice_streaming")
    )


def _ensure_piper_loaded():
    """Ensure Piper backend is loaded regardless of env default backend."""
    global _tts_model
    global _tts_backend_kind
    if _tts_backend_kind != "piper" or not isinstance(_tts_model, dict):
        _load_piper()
    return _tts_model


def _ensure_tts_loaded():
    """
    Lazy-load TTS backend.
    Default backend is Piper, with optional NeuTTS/Kokoro fallback.
    """
    global _tts_model
    if _tts_model is None:
        try:
            if TTS_BACKEND in {"piper"}:
                _load_piper()
            elif TTS_BACKEND in {"neutts", "neutts-air", "neuphonic"}:
                _load_neutts()
            elif TTS_BACKEND in {"kokoro"}:
                _load_kokoro()
            else:
                raise ValueError(f"Unsupported TTS_BACKEND='{TTS_BACKEND}'")
        except Exception as primary_err:
            if not TTS_ALLOW_FALLBACK:
                raise

            if TTS_BACKEND in {"piper"}:
                print(f"⚠️ Piper load failed ({primary_err}). Falling back to NeuTTS/Kokoro.")
                try:
                    _load_neutts()
                except Exception as neutts_err:
                    print(f"⚠️ NeuTTS fallback failed ({neutts_err}). Falling back to Kokoro.")
                    _load_kokoro()
            elif TTS_BACKEND in {"neutts", "neutts-air", "neuphonic"}:
                print(f"⚠️ NeuTTS load failed ({primary_err}). Falling back to Piper/Kokoro.")
                try:
                    _load_piper()
                except Exception as piper_err:
                    print(f"⚠️ Piper fallback failed ({piper_err}). Falling back to Kokoro.")
                    _load_kokoro()
            elif TTS_BACKEND in {"kokoro"}:
                print(f"⚠️ Kokoro load failed ({primary_err}). Falling back to Piper/NeuTTS.")
                try:
                    _load_piper()
                except Exception as piper_err:
                    print(f"⚠️ Piper fallback failed ({piper_err}). Falling back to NeuTTS.")
                    _load_neutts()
            else:
                raise

    return _tts_model


def _generate_piper_audio(text: str, voice: Optional[str] = None, style: Optional[str] = None) -> np.ndarray:
    """Generate audio with Piper CLI backend."""
    model_info = _ensure_piper_loaded()
    if not isinstance(model_info, dict):
        raise RuntimeError("Piper model metadata missing")

    binary = model_info.get("binary") or _piper_binary
    model_path = model_info.get("model_path") or _piper_model_path
    config_path = model_info.get("config_path") or _piper_config_path

    if not binary or not model_path:
        raise RuntimeError("Piper backend not initialized correctly")
    tune = _resolve_piper_tuning(style)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = Path(f.name)
    try:
        cmd = [
            str(binary),
            "--model",
            str(model_path),
            "--output_file",
            str(out_path),
            "--length_scale",
            str(tune["length_scale"]),
            "--noise_scale",
            str(tune["noise_scale"]),
            "--noise_w_scale",
            str(tune["noise_w_scale"]),
            "--sentence_silence",
            str(tune["sentence_silence"]),
            "--volume",
            str(tune["volume"]),
        ]
        if config_path:
            cmd.extend(["--config", str(config_path)])

        speaker = (voice or "").strip() or PIPER_SPEAKER_ID
        if speaker:
            cmd.extend(["--speaker", str(speaker)])

        piper_text = _prepare_piper_text(text)

        proc = subprocess.run(
            cmd,
            input=piper_text + "\n",
            text=True,
            capture_output=True,
            check=False,
            timeout=max(1.0, PIPER_CMD_TIMEOUT_SEC),
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            raise RuntimeError(
                f"Piper synthesis failed (code={proc.returncode}): {stderr or 'no stderr'}"
            )

        import soundfile as sf
        audio, _sample_rate = sf.read(str(out_path), dtype="float32")
        return _to_float_audio(audio)
    finally:
        try:
            out_path.unlink(missing_ok=True)
        except Exception:
            pass


def _generate_neutts_audio(text: str, voice: Optional[str] = None) -> np.ndarray:
    """Generate audio with NeuTTS v1.1.0 API: infer(text, ref_codes, ref_text)."""
    model = _ensure_tts_loaded()

    if _neutts_speaker_codes is None:
        raise RuntimeError("NeuTTS requires reference speaker codes but none were loaded.")

    effective_ref_text = _neutts_ref_text
    if not effective_ref_text and NEUTTS_DYNAMIC_REF_TEXT:
        effective_ref_text = text

    return _to_float_audio(model.infer(
        text=text,
        ref_codes=_neutts_speaker_codes,
        ref_text=effective_ref_text,
    ))


def _generate_kokoro_audio(text: str, voice: Optional[str] = None) -> np.ndarray:
    """Generate audio with Kokoro fallback backend."""
    model = _ensure_tts_loaded()
    audio_array = None
    for result in model(
        text=text,
        voice=voice or KOKORO_VOICE,
        speed=KOKORO_SPEED,
        split_pattern=r'\n+',
    ):
        audio_array = result.audio if hasattr(result, 'audio') else result
        break
    if audio_array is None:
        raise RuntimeError("Kokoro failed to generate audio")
    return _to_float_audio(audio_array)


def _generate_qwen3_tts_audio(text: str, voice: Optional[str] = None) -> np.ndarray:
    """Generate audio with Qwen3-TTS on CUDA via qwen-tts package."""
    import time as _time
    model = _ensure_qwen3_tts_loaded()

    speaker = _normalize_qwen3_speaker_name(voice or QWEN3_TTS_SPEAKER)
    instruct = QWEN3_TTS_INSTRUCT
    print(f"🎤 Qwen3 generating: speaker={speaker}, instruct={instruct!r}, text_len={len(text)}")

    t0 = _time.monotonic()

    # qwen-tts API: generate audio from text
    try:
        # Try the generate_custom_voice API (matches macOS mlx-audio interface)
        if hasattr(model, 'generate_custom_voice'):
            max_new_tokens = _estimate_qwen3_max_new_tokens(text)
            results = list(model.generate_custom_voice(
                text=text,
                speaker=speaker,
                language="English",
                instruct=instruct,
                max_new_tokens=max_new_tokens,
            ))
        elif hasattr(model, 'generate'):
            results = list(model.generate(
                text=text,
                speaker=speaker,
            ))
        elif hasattr(model, 'tts'):
            # Some versions use tts() method
            audio = model.tts(text=text, speaker=speaker)
            elapsed = _time.monotonic() - t0
            print(f"🎤 Qwen3 tts() returned in {elapsed:.2f}s")
            return _to_float_audio(audio)
        else:
            # Fallback: try calling the model directly
            audio = model(text, speaker=speaker)
            elapsed = _time.monotonic() - t0
            print(f"🎤 Qwen3 __call__ returned in {elapsed:.2f}s")
            return _to_float_audio(audio)
    except Exception as e:
        elapsed = _time.monotonic() - t0
        print(f"❌ Qwen3-TTS generation failed after {elapsed:.2f}s: {e}")
        raise

    elapsed = _time.monotonic() - t0
    print(f"🎤 Qwen3 generation returned in {elapsed:.2f}s, results={len(results)}")

    if not results:
        raise RuntimeError("Qwen3-TTS generation did not produce audio.")

    # Extract audio from result
    first_result = results[0]
    if hasattr(first_result, "audio"):
        audio = first_result.audio
    elif isinstance(first_result, np.ndarray):
        audio = first_result
    elif hasattr(first_result, "detach"):
        audio = first_result
    else:
        audio = first_result

    print(f"🎤 Raw audio type={type(audio).__name__}, shape={getattr(audio, 'shape', 'N/A')}")

    return _to_float_audio(audio)


def _iter_qwen3_tts_stream_chunks(text: str, voice: Optional[str] = None):
    """Yield realtime PCM16 chunks from FasterQwen3TTS when available."""
    import time as _time

    if not _qwen3_tts_supports_streaming():
        raise RuntimeError("Realtime chunked Qwen3-TTS is unavailable in this process.")

    model = _ensure_qwen3_tts_loaded()
    speaker = _normalize_qwen3_speaker_name(voice or QWEN3_TTS_SPEAKER)
    instruct = QWEN3_TTS_INSTRUCT
    max_new_tokens = _estimate_qwen3_max_new_tokens(text)

    print(
        "🎤 FasterQwen3 streaming: "
        f"speaker={speaker}, instruct={instruct!r}, text_len={len(text)}, chunk_size={QWEN3_TTS_STREAM_CHUNK_SIZE}"
    )

    started_at = _time.monotonic()
    first_chunk_at = None
    total_samples = 0
    last_chunk_index = -1

    for chunk_index, (audio_chunk, sample_rate, timing) in enumerate(
        model.generate_custom_voice_streaming(
            text=text,
            speaker=speaker,
            language="English",
            instruct=instruct,
            max_new_tokens=max_new_tokens,
            chunk_size=QWEN3_TTS_STREAM_CHUNK_SIZE,
        )
    ):
        if first_chunk_at is None:
            first_chunk_at = _time.monotonic()
            print(
                f"🎤 FasterQwen3 first chunk in {(first_chunk_at - started_at):.2f}s "
                f"(samples={len(audio_chunk)}, timing={timing})"
            )

        pcm_b64 = base64.b64encode(_float_audio_to_pcm16_bytes(audio_chunk)).decode("utf-8")
        total_samples += len(audio_chunk)
        last_chunk_index = chunk_index
        yield {
            "audio": pcm_b64,
            "sample_rate": int(sample_rate or _qwen3_tts_sample_rate or QWEN3_TTS_SAMPLE_RATE),
            "chunk_index": chunk_index,
            "is_final": bool(timing.get("is_final")),
            "timing": timing,
        }

    if last_chunk_index >= 0:
        total_time = _time.monotonic() - started_at
        total_audio_seconds = total_samples / float(_qwen3_tts_sample_rate or QWEN3_TTS_SAMPLE_RATE)
        print(
            f"🎤 FasterQwen3 stream complete in {total_time:.2f}s "
            f"(chunks={last_chunk_index + 1}, audio_s={total_audio_seconds:.2f})"
        )


def _resolve_provider_sample_rate(provider: Optional[str] = None) -> int:
    provider_key = _normalize_tts_provider(provider, fallback=DEFAULT_TTS_PROVIDER)
    if provider_key == "qwen3_tts":
        try:
            _ensure_qwen3_tts_loaded()
            return int(_qwen3_tts_sample_rate or QWEN3_TTS_SAMPLE_RATE)
        except Exception as qwen_err:
            if not TTS_ALLOW_FALLBACK:
                raise
            print(f"⚠️ Qwen3-TTS sample-rate fallback to Piper: {qwen_err}")
    _ensure_piper_loaded()
    return int(_tts_sample_rate or PIPER_SAMPLE_RATE)


def _provider_supports_streaming(provider: Optional[str] = None) -> bool:
    provider_key = _normalize_tts_provider(provider, fallback=DEFAULT_TTS_PROVIDER)
    if provider_key != "qwen3_tts":
        return False
    try:
        return _qwen3_tts_supports_streaming()
    except Exception as qwen_err:
        if not TTS_ALLOW_FALLBACK:
            raise
        print(f"⚠️ Qwen3 streaming unavailable ({qwen_err}).")
        return False


def _generate_audio(
    text: str,
    voice: Optional[str] = None,
    style: Optional[str] = None,
    provider: Optional[str] = None,
) -> np.ndarray:
    """Route synthesis to selected provider."""
    provider_key = _normalize_tts_provider(provider, fallback=DEFAULT_TTS_PROVIDER)
    if provider_key == "qwen3_tts":
        try:
            return _generate_qwen3_tts_audio(text, voice=voice)
        except Exception as qwen_err:
            if not TTS_ALLOW_FALLBACK:
                raise
            _disable_qwen3_tts(f"runtime_failed: {qwen_err}")
            print(f"⚠️ Qwen3-TTS failed ({qwen_err}). Falling back to Piper.")
            return _generate_piper_audio(text, voice=voice, style=style)
    # Default / fallback path uses Piper.
    return _generate_piper_audio(text, voice=voice, style=style)


# ============== TTS Service ==============

class TTSService:
    """
    Text-to-Speech service.
    Generates interviewer speech for realtime interview flows.
    """

    def __init__(self):
        self._sample_rate = None

    @property
    def sample_rate(self) -> int:
        """Get sample rate for the default provider."""
        return self.sample_rate_for_provider()

    def sample_rate_for_provider(self, provider: Optional[str] = None) -> int:
        """Get sample rate for a specific provider."""
        if provider is None and self._sample_rate is not None:
            return int(self._sample_rate)
        rate = _resolve_provider_sample_rate(provider=provider)
        if provider is None:
            self._sample_rate = int(rate)
        return int(rate)

    def supports_streaming(self, provider: Optional[str] = None) -> bool:
        """Whether the provider can emit chunked realtime audio instead of waiting for a full WAV."""
        return _provider_supports_streaming(provider=provider)

    def speak(
        self,
        text: str,
        voice: Optional[str] = None,
        style: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> bytes:
        """
        Generate speech audio from text.

        Args:
            text: Text to synthesize
            voice: Optional voice preset / reference audio path
            style: Piper voice style preset
            provider: TTS provider key (piper|qwen3_tts)

        Returns:
            Raw PCM audio bytes (16-bit signed, mono, 24kHz)
        """
        with _tts_infer_semaphore:
            audio_array = _generate_audio(text, voice=voice, style=style, provider=provider)

        # Normalize and convert to 16-bit PCM
        audio_array = np.clip(audio_array, -1.0, 1.0)
        audio_int16 = (audio_array * 32767).astype(np.int16)

        return audio_int16.tobytes()

    def speak_wav_base64(
        self,
        text: str,
        voice: Optional[str] = None,
        style: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> str:
        """
        Generate speech as WAV and return base64-encoded.
        This is the primary method for sending audio over Socket.IO.

        Args:
            text: Text to synthesize
            voice: Optional voice preset / reference audio path
            style: Piper voice style preset
            provider: TTS provider key (piper|qwen3_tts)

        Returns:
            Base64-encoded WAV data
        """
        provider_key = _normalize_tts_provider(provider, fallback=DEFAULT_TTS_PROVIDER)
        with _tts_infer_semaphore:
            audio_array = _generate_audio(text, voice=voice, style=style, provider=provider_key)
            sample_rate = self.sample_rate_for_provider(provider_key)

        # Write to WAV buffer
        buffer = io.BytesIO()
        import soundfile as sf
        sf.write(buffer, audio_array, sample_rate, format='WAV', subtype='PCM_16')
        buffer.seek(0)
        
        # --- DEBUG: Save to file ---
        if SAVE_TTS_DEBUG_AUDIO:
            try:
                debug_dir = "debug_audio"
                if not os.path.exists(debug_dir):
                    os.makedirs(debug_dir)

                # Create safe filename from text
                import time
                timestamp = int(time.time())
                safe_text = "".join([c for c in text if c.isalnum() or c in (' ', '_')]).strip()[:30].replace(" ", "_")
                backend_tag = provider_key
                filename = f"{debug_dir}/tts_{backend_tag}_{timestamp}_{safe_text}.wav"

                # Save using soundfile
                sf.write(filename, audio_array, sample_rate, format='WAV', subtype='PCM_16')
                print(f"🐛 Saved TTS debug audio: {filename}")
            except Exception as e:
                print(f"⚠️ Failed to save debug audio: {e}")
        # ---------------------------

        return base64.b64encode(buffer.read()).decode('utf-8')

    async def speak_wav_base64_async(
        self,
        text: str,
        voice: Optional[str] = None,
        style: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> str:
        """
        Async version of speak_wav_base64.
        Runs TTS in thread pool to avoid blocking the event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.speak_wav_base64(text, voice=voice, style=style, provider=provider)
        )

    async def stream_pcm_base64_chunks_async(
        self,
        text: str,
        voice: Optional[str] = None,
        style: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        """
        Async generator that yields PCM16/base64 chunks for low-latency browser playback.

        Currently used by the faster-qwen3-tts backend only.
        """
        loop = asyncio.get_running_loop()
        provider_key = _normalize_tts_provider(provider, fallback=DEFAULT_TTS_PROVIDER)
        if provider_key != "qwen3_tts":
            raise RuntimeError(f"Streaming audio is not implemented for provider '{provider_key}'.")

        sentinel = object()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        cancel_event = threading.Event()

        def worker():
            try:
                with _tts_infer_semaphore:
                    for chunk_payload in _iter_qwen3_tts_stream_chunks(text, voice=voice):
                        if cancel_event.is_set():
                            break
                        loop.call_soon_threadsafe(queue.put_nowait, chunk_payload)
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        thread = threading.Thread(target=worker, name="tts-stream-worker", daemon=True)
        thread.start()
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        except asyncio.CancelledError:
            cancel_event.set()
            raise
        finally:
            cancel_event.set()


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
    provider = _normalize_tts_provider(DEFAULT_TTS_PROVIDER, fallback="piper")
    if provider == "qwen3_tts":
        try:
            _ensure_qwen3_tts_loaded()
        except Exception as qwen_err:
            if not TTS_ALLOW_FALLBACK:
                raise
            print(f"⚠️ Qwen3 preload failed ({qwen_err}). Falling back to Piper preload.")
            _ensure_piper_loaded()
    else:
        _ensure_piper_loaded()
