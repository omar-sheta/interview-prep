# BeePrepared - Spark HTTPS Deployment

This project is configured to run behind Caddy on `https://<host>:8443` so microphone access works in browsers.

## 1. Prerequisites on DGX

- Conda env `interview` with backend deps installed.
- Node modules installed in `client/`:
  - `cd client && npm install`
- TLS cert/key in:
  - `certs/cert.pem`
  - `certs/key.pem`

If you do not have a company-trusted certificate yet, create a temporary self-signed cert (users will need to trust it manually):

```bash
openssl req -x509 -nodes -newkey rsa:4096 -days 365 \
  -keyout certs/key.pem \
  -out certs/cert.pem
```

## 2. Start the app

From repo root:

```bash
cp .env.example .env
chmod +x start.sh
PUBLIC_HOST=spark.hivehub.org PUBLIC_PORT=8443 ./start.sh
```

If frontend is already built and `npm` is unavailable in your runtime shell:

```bash
BUILD_CLIENT=0 PUBLIC_HOST=spark.hivehub.org PUBLIC_PORT=8443 ./start.sh
```

What `start.sh` does:
- Builds frontend (`client/dist`)
- Loads `.env` if present
- Checks the configured LLM endpoint
- Starts/reloads Caddy with `Caddyfile`
- Runs backend on `${HOST:-0.0.0.0}:${PORT:-8000}`

## 3. Share with company users

Share this URL:

`https://spark.hivehub.org:8443`

If your users access via IP instead, set `PUBLIC_HOST` accordingly and ensure origin is allowed:

```bash
CORS_ORIGINS="https://spark.hivehub.org:8443,https://192.168.1.48:8443" ./start.sh
```

`CORS_ORIGINS` accepts either:
- comma-separated string, or
- JSON list

## 4. Runtime Config

Use `.env` for DGX hostnames/IPs and model endpoints. `LLM_PROVIDER=lmstudio` is the correct setting for any OpenAI-compatible `/v1` server, even if you are not using the LM Studio desktop app.

Key settings:
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `CORS_ORIGINS`
- `PUBLIC_HOST`
- `PIPER_MODEL_PATH`
- `WHISPER_MODEL_ID`

## 5. Performance (DGX Spark)

DGX Spark is ARM64 + NVIDIA GB10. The Spark path here uses OpenAI-compatible LLM endpoints, faster-whisper on CUDA, and Piper by default.

Fast profile is enabled by default in `start.sh` (`SPARK_FAST_PRESET=1`), which sets:
- lower-latency LLM context/stream batching
- faster-whisper decode defaults (`beam_size=1`, `best_of=1`)
- Piper fast style for snappier question audio

Check GPU contention before testing:

```bash
nvidia-smi
```

If non-Ollama jobs (for example LM Studio/Jupyter training jobs) are using most VRAM, latency will spike.
Stop those jobs or run this app on a less-busy GPU.

Optional overrides:

```bash
SPARK_FAST_PRESET=1 \
LLM_MODEL_ID=qwen3:8b \
LLM_NUM_CTX=4096 \
WHISPER_MODEL_ID=large-v3 \
./start.sh
```

## 6. Stop services

- Stop backend with `Ctrl+C`
- Stop Caddy:
  - `./caddy stop`
