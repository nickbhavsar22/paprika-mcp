"""Streamable HTTP transport for Paprika MCP.

Exposes the same `Server("paprika")` instance defined in `server.py`, but
over Streamable HTTP so it can be reached by claude.ai web/mobile via a
Custom Connector.

Auth model: the value of MCP_BEARER_TOKEN is embedded in the URL path
(`/mcp/<TOKEN>/`). claude.ai's connector UI does not support pasting a
static Bearer header (only OAuth client_id/secret), so a path-segment
secret is the simplest viable scheme. All other paths return 404 so
claude.ai's OAuth discovery probes fail cleanly and it falls back to
no-auth mode.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

from .server import app as mcp_app


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


BEARER_TOKEN = _required_env("MCP_BEARER_TOKEN")


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
        Mount(f"/mcp/{BEARER_TOKEN}", app=session_manager.handle_request),
    ],
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
