"""Streamable HTTP transport for Paprika MCP, with bearer-token auth.

Exposes the same `Server("paprika")` instance defined in `server.py`, but
over Streamable HTTP so it can be reached by claude.ai web/mobile via a
Custom Connector.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route

from .server import app as mcp_app


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


BEARER_TOKEN = _required_env("MCP_BEARER_TOKEN")


class BearerAuth(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Allow unauthenticated health checks
        if request.url.path == "/healthz":
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if auth != f"Bearer {BEARER_TOKEN}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


# Stateless mode: every request is self-contained — no in-memory session
# state — which is essential when running on a free tier that may spin
# down between calls.
session_manager = StreamableHTTPSessionManager(
    app=mcp_app,
    json_response=False,
    stateless=True,
)


@asynccontextmanager
async def lifespan(_app):
    async with session_manager.run():
        yield


async def healthz(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


asgi_app = Starlette(
    routes=[
        Route("/healthz", healthz),
        Mount("/mcp", app=session_manager.handle_request),
    ],
    middleware=[Middleware(BearerAuth)],
    lifespan=lifespan,
)


def run() -> None:
    """CLI entry point — launches uvicorn directly."""
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "paprika_mcp.server_http:asgi_app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    run()
