# Backend Architecture

The backend is structured so new features have obvious homes and future MCP
support can plug in as an adapter instead of becoming the core design.

## Layers

- `server/app`: application composition, lifecycle, Socket.IO/FastAPI setup, and compatibility entrypoints.
- `server/api`: REST transport layer. It should validate/authenticate requests and delegate work.
- `server/realtime`: Socket.IO transport layer. It should manage event payloads, rooms, and emissions.
- `server/agents`: agent orchestration for adaptive interview coaching, career analysis, feedback, and coaching hints.
- `server/domain`: pure business logic with minimal framework/runtime dependencies.
- `server/adapters`: concrete runtime integrations such as LLM providers, TTS, STT/audio, cache, and vector search.
- `server/persistence`: durable data storage and query/update operations.
- `server/tools`: internal tool contracts and registry. MCP can be added later by implementing an adapter that registers remote tools here.
- `server/observability`: metrics and operational counters.

## Adding Features

- Start in `server/agents` when the feature changes coaching/interview intelligence.
- Start in `server/api` or `server/realtime` when the feature is primarily a new endpoint or socket event.
- Add pure scoring/parsing/normalization helpers to `server/domain`.
- Add provider-specific code to `server/adapters`.
- Add database schema/query changes to `server/persistence`.
- Add reusable agent-callable capabilities to `server/tools/registry.py`.

## Boundaries

- Transport modules should not contain provider-specific LLM/TTS/STT code.
- Agent modules should depend on domain rules and adapter interfaces, not FastAPI request objects.
- Domain modules should be safe to test without network, model, GPU, or database setup.
- `server.main` should remain a compatibility shim for `server.main:app`.

## MCP Direction

MCP is intentionally deferred. The current tool registry creates the seam:
internal tools and future MCP tools can share a common registration pattern,
while the app remains stable without requiring MCP at runtime.
