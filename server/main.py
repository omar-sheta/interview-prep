"""
Compatibility entry point for BeePrepared.

Runtime tools still import ``server.main:app``. The application wiring now
lives in ``server.app.bootstrap`` so feature code can grow around clearer
agent, adapter, API, and realtime boundaries.
"""

import sys

from server.app import bootstrap as _bootstrap

# Preserve the historical ``server.main`` module contract for tests, uvicorn,
# and any operational scripts while keeping implementation in server.app.
sys.modules[__name__] = _bootstrap


if __name__ == "__main__":
    import uvicorn

    from server.config import settings

    uvicorn.run(
        "server.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
