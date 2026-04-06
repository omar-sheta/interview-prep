#!/bin/bash
# BeePrepared Spark Server Startup Script

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$SCRIPT_DIR}"
BACKEND_ENV="${BACKEND_ENV-}"
BACKEND_ENV_LABEL="system"
PRESERVED_ENV_KEYS=(
  APP_DIR
  BACKEND_ENV
  BUILD_CLIENT
  ORIGIN_SCHEME
  ORIGIN_PORT
  PUBLIC_SCHEME
  UVICORN_HOST
  UVICORN_PORT
  PUBLIC_HOST
  PUBLIC_PORT
  PUBLIC_URL
  SPARK_FAST_PRESET
  LLM_PROVIDER
  LLM_BASE_URL
  LLM_MODEL_ID
  FAST_LLM_MODEL_ID
  TTS_PROVIDER
  TTS_BACKEND
  PIPER_STYLE
)
declare -A PRESERVED_ENV_SET=()
declare -A PRESERVED_ENV_VALUE=()

strip_path_entry() {
  local remove_path="$1"
  local old_path="${PATH:-}"
  local new_path=""
  local entry
  local IFS=':'
  for entry in $old_path; do
    if [ -n "$entry" ] && [ "$entry" != "$remove_path" ]; then
      if [ -n "$new_path" ]; then
        new_path="${new_path}:$entry"
      else
        new_path="$entry"
      fi
    fi
  done
  PATH="$new_path"
  export PATH
}

activate_project_venv() {
  local venv_dir="$APP_DIR/.venv"
  if [ ! -x "$venv_dir/bin/python" ]; then
    return 1
  fi
  export VIRTUAL_ENV="$venv_dir"
  export PATH="$venv_dir/bin:$PATH"
  unset PYTHONHOME || true
  BACKEND_ENV_LABEL="$venv_dir"
  return 0
}

activate_conda_env() {
  if [ ! -x "$HOME/miniforge3/bin/conda" ]; then
    return 1
  fi
  unset VIRTUAL_ENV || true
  strip_path_entry "$APP_DIR/.venv/bin"
  # Some conda activation hooks (e.g. CUDA nvcc) reference optional vars
  # that may be unset; temporarily disable nounset to avoid false failures.
  set +u
  eval "$("$HOME/miniforge3/bin/conda" shell.bash hook)"
  conda activate interview
  set -u
  BACKEND_ENV_LABEL="conda:interview"
  return 0
}

preserve_env_overrides() {
  local key
  for key in "${PRESERVED_ENV_KEYS[@]}"; do
    if [ "${!key+x}" = "x" ]; then
      PRESERVED_ENV_SET["$key"]=1
      PRESERVED_ENV_VALUE["$key"]="${!key}"
    fi
  done
}

restore_env_overrides() {
  local key
  for key in "${PRESERVED_ENV_KEYS[@]}"; do
    if [ "${PRESERVED_ENV_SET[$key]-0}" = "1" ]; then
      printf -v "$key" '%s' "${PRESERVED_ENV_VALUE[$key]}"
      export "$key"
    fi
  done
}

preserve_env_overrides
if [ -f "$APP_DIR/.env" ]; then
  set +u
  set -a
  . "$APP_DIR/.env"
  set +a
  set -u
fi
restore_env_overrides

BACKEND_ENV="${BACKEND_ENV:-auto}"

if [ "$BACKEND_ENV" = "auto" ]; then
  if [ "${CONDA_DEFAULT_ENV:-}" = "interview" ] || [ "${CONDA_PREFIX:-}" = "$HOME/miniforge3/envs/interview" ]; then
    BACKEND_ENV="conda"
  fi
fi

UVICORN_HOST="${UVICORN_HOST:-${HOST:-0.0.0.0}}"
UVICORN_PORT="${UVICORN_PORT:-${PORT:-8000}}"
ORIGIN_SCHEME="${ORIGIN_SCHEME:-${PUBLIC_SCHEME:-https}}"
ORIGIN_PORT="${ORIGIN_PORT:-${PUBLIC_PORT:-8443}}"
PUBLIC_SCHEME="${PUBLIC_SCHEME:-${ORIGIN_SCHEME}}"
PUBLIC_PORT="${PUBLIC_PORT:-${ORIGIN_PORT}}"
PUBLIC_HOST="${PUBLIC_HOST:-beeprepared.cyber-hive.org}"
if [ -z "${PUBLIC_URL:-}" ]; then
  public_port_suffix=":${PUBLIC_PORT}"
  if { [ "${PUBLIC_SCHEME}" = "http" ] && [ "${PUBLIC_PORT}" = "80" ]; } \
    || { [ "${PUBLIC_SCHEME}" = "https" ] && [ "${PUBLIC_PORT}" = "443" ]; }; then
    public_port_suffix=""
  fi
  PUBLIC_URL="${PUBLIC_SCHEME}://${PUBLIC_HOST}${public_port_suffix}"
fi
SPARK_FAST_PRESET="${SPARK_FAST_PRESET:-1}"

export APP_DIR
export ORIGIN_SCHEME
export ORIGIN_PORT
export PUBLIC_SCHEME
export PUBLIC_PORT
export UVICORN_PORT

if [ "$BACKEND_ENV" = "venv" ]; then
  if ! activate_project_venv; then
    echo "Requested BACKEND_ENV=venv but $APP_DIR/.venv was not found."
    exit 1
  fi
elif [ "$BACKEND_ENV" = "conda" ]; then
  if ! activate_conda_env; then
    echo "Requested BACKEND_ENV=conda but the 'interview' conda environment was not available."
    exit 1
  fi
elif [ -n "${VIRTUAL_ENV:-}" ]; then
  BACKEND_ENV_LABEL="$VIRTUAL_ENV"
else
  if ! activate_project_venv; then
    activate_conda_env || true
  fi
fi

cd "$APP_DIR"

echo "Starting BeePrepared on Spark..."
echo "Backend environment: ${BACKEND_ENV_LABEL}"

if ! command -v python >/dev/null 2>&1; then
  echo "python not found on PATH after environment activation."
  exit 1
fi

python - <<'PY'
import importlib.util
import os
import sys


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


llm_provider = os.getenv("LLM_PROVIDER", "lmstudio").strip().lower()
tts_provider = os.getenv("TTS_PROVIDER", os.getenv("TTS_BACKEND", "piper")).strip().lower()
required_modules = ["fastapi", "socketio", "langgraph", "numpy", "soundfile", "uvicorn"]
if llm_provider != "ollama":
    required_modules.append("langchain_openai")

missing_required = [name for name in required_modules if not has_module(name)]
if missing_required:
    joined = ", ".join(missing_required)
    print(
        f"Missing required Python packages for this configuration: {joined}.",
        file=sys.stderr,
    )
    print(
        "Install the missing packages into the active environment or choose a different "
        "environment with BACKEND_ENV=venv or BACKEND_ENV=conda.",
        file=sys.stderr,
    )
    sys.exit(1)

optional_warnings = []
if not has_module("reportlab"):
    optional_warnings.append("reportlab missing: PDF export endpoint will return 503 until installed.")
if tts_provider in {"qwen3_tts", "qwen3_tts_mlx"} and not has_module("qwen_tts"):
    optional_warnings.append("qwen-tts missing: Qwen TTS will fall back to Piper.")

for warning in optional_warnings:
    print(f"⚠️ {warning}", file=sys.stderr)
PY

# DGX/Spark-friendly defaults (all overridable via env).
if [ "$SPARK_FAST_PRESET" = "1" ]; then
  cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 8)"
  export LLM_STREAM_FLUSH_MS="${LLM_STREAM_FLUSH_MS:-35}"
  export LLM_STREAM_FLUSH_CHARS="${LLM_STREAM_FLUSH_CHARS:-24}"
  export WHISPER_BEAM_SIZE="${WHISPER_BEAM_SIZE:-1}"
  export WHISPER_BEST_OF="${WHISPER_BEST_OF:-1}"
  export WHISPER_CPU_THREADS="${WHISPER_CPU_THREADS:-$cpu_count}"
  export WHISPER_NUM_WORKERS="${WHISPER_NUM_WORKERS:-2}"
  export PIPER_STYLE="${PIPER_STYLE:-fast}"
fi

if ! python -m uvicorn --version >/dev/null 2>&1; then
  echo "uvicorn is not available in the active Python environment."
  exit 1
fi

# Verify the configured model endpoint is reachable.
llm_provider="$(printf '%s' "${LLM_PROVIDER:-lmstudio}" | tr '[:upper:]' '[:lower:]')"
llm_base_url="${LLM_BASE_URL:-http://127.0.0.1:1234/v1}"
if command -v curl >/dev/null 2>&1; then
  if [ "$llm_provider" = "ollama" ]; then
    llm_health_url="${llm_base_url%/v1}"
    llm_health_url="${llm_health_url%/}/api/tags"
  else
    llm_health_url="${llm_base_url%/}/models"
  fi
  echo "Checking ${llm_provider} availability..."
  if ! curl -sf "$llm_health_url" >/dev/null 2>&1; then
    echo "⚠️  ${llm_provider} endpoint is not reachable at ${llm_health_url}."
    echo "   The backend will still start and retry when requests arrive."
  fi
fi

if [ "${BUILD_CLIENT:-1}" = "1" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "npm not found on PATH. Install Node.js/npm or run with BUILD_CLIENT=0."
    exit 1
  fi

  if [ ! -d "$APP_DIR/client/node_modules" ]; then
    echo "client/node_modules not found. Run: cd $APP_DIR/client && npm install"
    exit 1
  fi

  echo "Building frontend..."
  (cd "$APP_DIR/client" && npm run build)
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  busy_gpu_apps="$(
    nvidia-smi --query-compute-apps=process_name,used_memory --format=csv,noheader,nounits 2>/dev/null \
      | awk -F',' '{gsub(/^[ \t]+|[ \t]+$/, "", $1); gsub(/^[ \t]+|[ \t]+$/, "", $2); if (($2+0) >= 2048) print $1 " (" $2 " MiB)"}' \
      || true
  )"
  if [ -n "$busy_gpu_apps" ]; then
    echo "⚠️ GPU contention detected (processes using >=2GB VRAM):"
    echo "$busy_gpu_apps"
    echo "   This can impact STT and TTS latency."
  fi
fi

if [ "${ORIGIN_SCHEME}" = "http" ]; then
  CADDY_CONFIG="Caddyfile.http"
  echo "Starting or reloading Caddy HTTP origin on port ${ORIGIN_PORT}..."
else
  CADDY_CONFIG="Caddyfile"
  echo "Starting or reloading Caddy HTTPS origin on port ${ORIGIN_PORT}..."
fi

./caddy validate --config "${CADDY_CONFIG}"
if ! ./caddy start --config "${CADDY_CONFIG}" >/dev/null 2>&1; then
  ./caddy reload --config "${CADDY_CONFIG}"
fi

echo ""
echo "==========================================="
echo "App is live at: ${PUBLIC_URL}"
echo "Origin listener: ${ORIGIN_SCHEME}://0.0.0.0:${ORIGIN_PORT}"
echo "==========================================="
echo "Runtime: ${llm_provider} @ ${llm_base_url}, SPARK_FAST_PRESET=${SPARK_FAST_PRESET}"
echo ""

UVICORN_RELOAD_FLAG=()
if [ "${UVICORN_RELOAD:-0}" = "1" ]; then
  UVICORN_RELOAD_FLAG=(--reload)
fi

echo "Starting Python backend on ${UVICORN_HOST}:${UVICORN_PORT}..."
python -m uvicorn server.main:app --host "$UVICORN_HOST" --port "$UVICORN_PORT" "${UVICORN_RELOAD_FLAG[@]}"
