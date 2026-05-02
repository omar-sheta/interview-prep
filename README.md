# BeePrepared

BeePrepared is an AI interview coaching app with a Vite/React frontend and a
FastAPI + Socket.IO backend. The backend is organized around an agent core:
transport layers receive requests, agents orchestrate interview/career
workflows, domain modules hold pure rules, and adapters own concrete runtime
integrations such as LLM, TTS, STT, persistence, and vector search.

## Project Map

- `client/` - React UI, route screens, shared UI components, browser audio helpers, and Zustand state.
- `server/app/` - FastAPI/Socket.IO application bootstrap, lifecycle, session state, and runtime entrypoint wiring.
- `server/api/` - REST transport endpoints only.
- `server/realtime/` - Socket.IO transport event handlers only.
- `server/agents/` - Interview, career-analysis, and coaching orchestration.
- `server/domain/` - Pure business rules such as transcript handling and interview-domain logic.
- `server/adapters/` - Concrete integrations for LLMs, audio/STT, TTS, vector search, cache, and Qdrant.
- `server/persistence/` - SQLite/user data storage.
- `server/tools/` - Internal tools and tool registry seams for future MCP adapters.
- `docs/` - Architecture, development, and deployment guides.

`server.main:app` remains the compatibility entrypoint used by `start.sh`,
Uvicorn, and existing operational scripts.

## Common Commands

From the repo root:

```bash
make backend-test
make frontend-build
make check
```

Direct commands:

```bash
/home/omar/miniforge3/envs/interview/bin/python -m pytest server/tests
cd client && npm run build
cd client && npm run lint
```

## Feature Workflow

1. Add request/response handling in `server/api` or `server/realtime`.
2. Put orchestration in `server/agents`.
3. Put pure rules and parsing in `server/domain`.
4. Put concrete external/runtime calls in `server/adapters` or `server/persistence`.
5. Register reusable internal capabilities through `server/tools` when agents should call them as tools.
6. Preserve public REST paths, Socket.IO event names, payload shapes, env vars, and database behavior unless a feature explicitly changes them.

## Deployment

Spark/systemd/Caddy deployment notes live in
[`docs/deployment/spark.md`](docs/deployment/spark.md). Cleanup branches should
not restart or deploy the live service.
