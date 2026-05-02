# Spark Deployment Notes

The production Spark service is designed to run from the working deployment
checkout, not from cleanup branches.

## Runtime Shape

- Public site: `https://beeprepared.cyber-hive.org`
- Origin listener: `http://0.0.0.0:8443`
- Backend: Uvicorn importing `server.main:app`
- Frontend: built static assets served by the backend/Caddy setup
- Service environment: conda env `interview`

## Manual Startup

```bash
ORIGIN_SCHEME=http \
ORIGIN_PORT=8443 \
PUBLIC_SCHEME=https \
PUBLIC_HOST=beeprepared.cyber-hive.org \
PUBLIC_PORT=443 \
./start.sh
```

If the frontend is already built:

```bash
BUILD_CLIENT=0 \
ORIGIN_SCHEME=http \
ORIGIN_PORT=8443 \
PUBLIC_SCHEME=https \
PUBLIC_HOST=beeprepared.cyber-hive.org \
PUBLIC_PORT=443 \
./start.sh
```

## Systemd

The Spark deployment uses a user systemd service. Cleanup branches must not
restart it. Validate cleanup work with tests/builds inside the cleanup clone
instead.

## Important Environment Variables

- `BACKEND_ENV`
- `BUILD_CLIENT`
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_MODEL_ID`
- `FAST_LLM_MODEL_ID`
- `TTS_PROVIDER`
- `TTS_BACKEND`
- `PUBLIC_HOST`
- `PUBLIC_PORT`
- `ORIGIN_SCHEME`
- `ORIGIN_PORT`
- `CORS_ORIGINS`

## Health Check

```bash
curl -fsS http://127.0.0.1:8000/health
```
