#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WHISPER_DIR="${ROOT_DIR}/third_party/whisper.cpp"
BUILD_DIR="${WHISPER_DIR}/build"
MODELS_DIR="${WHISPER_DIR}/models"
BASE_MODEL="${MODELS_DIR}/ggml-base.en.bin"
Q8_MODEL="${MODELS_DIR}/ggml-base.en-q8_0.bin"

if [[ ! -d "${WHISPER_DIR}/.git" ]]; then
  mkdir -p "${ROOT_DIR}/third_party"
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "${WHISPER_DIR}"
else
  echo "using existing repo: ${WHISPER_DIR}"
fi

cmake -S "${WHISPER_DIR}" -B "${BUILD_DIR}" -DGGML_METAL=ON
cmake --build "${BUILD_DIR}" -j --config Release

if [[ ! -f "${BASE_MODEL}" ]]; then
  (cd "${WHISPER_DIR}" && ./models/download-ggml-model.sh base.en)
fi

if [[ ! -f "${Q8_MODEL}" ]]; then
  "${BUILD_DIR}/bin/whisper-quantize" "${BASE_MODEL}" "${Q8_MODEL}" q8_0
fi

echo "whisper.cpp setup complete"
echo "binary: ${BUILD_DIR}/bin/whisper-cli"
echo "model : ${Q8_MODEL}"
