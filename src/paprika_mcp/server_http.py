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
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Mount, Route

from .photo import MAX_DOWNLOAD_BYTES, normalize_to_jpeg, stage_photo
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


UPLOAD_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paprika photo upload</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 32rem;
         margin: 0 auto; padding: 1.5rem; line-height: 1.5; }
  h1 { font-size: 1.3rem; }
  input[type=file] { display: block; margin: 1rem 0; width: 100%; }
  button { font-size: 1rem; padding: .6rem 1.2rem; border-radius: .5rem;
           border: none; background: #b3341f; color: #fff; }
  button:disabled { opacity: .5; }
  #out { margin-top: 1.25rem; }
  .code { font-size: 1.6rem; font-weight: 700; letter-spacing: .1em;
          font-family: ui-monospace, monospace; padding: .4rem .8rem;
          background: #f3f3f3; border-radius: .5rem; display: inline-block; }
  .err { color: #b3341f; }
</style>
</head>
<body>
<h1>Attach a photo to a recipe</h1>
<p>Pick a photo, upload it, then tell Claude:
   <em>"Attach upload &lt;code&gt; to my &lt;recipe&gt;."</em></p>
<input type="file" accept="image/*" id="f">
<button id="b" onclick="up()">Upload photo</button>
<div id="out"></div>
<script>
async function up() {
  var out = document.getElementById('out');
  var btn = document.getElementById('b');
  var f = document.getElementById('f').files[0];
  if (!f) { out.innerHTML = '<span class="err">Pick a photo first.</span>'; return; }
  btn.disabled = true;
  out.textContent = 'Uploading…';
  try {
    var r = await fetch(location.pathname, { method: 'POST', body: f });
    var t = await r.text();
    if (r.ok) {
      out.innerHTML = 'Upload code: <span class="code">' + t + '</span>' +
        '<p>Tell Claude to attach this code to a recipe. It expires in 30 minutes.</p>';
    } else {
      out.innerHTML = '<span class="err">' + t + '</span>';
    }
  } catch (e) {
    out.innerHTML = '<span class="err">Upload failed: ' + e + '</span>';
  }
  btn.disabled = false;
}
</script>
</body>
</html>"""


async def upload_get(_request: Request) -> HTMLResponse:
    return HTMLResponse(UPLOAD_PAGE)


async def upload_post(request: Request) -> PlainTextResponse:
    raw = await request.body()
    if not raw:
        return PlainTextResponse("No image data received.", status_code=400)
    if len(raw) > MAX_DOWNLOAD_BYTES:
        cap = MAX_DOWNLOAD_BYTES // 1024 // 1024
        return PlainTextResponse(f"Image exceeds {cap} MB cap.", status_code=413)
    try:
        jpeg_bytes = normalize_to_jpeg(raw)
    except ImportError:
        return PlainTextResponse(
            "Server is missing Pillow; cannot process images.", status_code=500
        )
    except Exception:
        return PlainTextResponse(
            "Could not read that file as an image (HEIC may need converting to JPEG).",
            status_code=400,
        )
    code = stage_photo(jpeg_bytes)
    return PlainTextResponse(code)


asgi_app = Starlette(
    routes=[
        Route("/healthz", healthz),
        Route(f"/upload/{BEARER_TOKEN}", upload_get, methods=["GET"]),
        Route(f"/upload/{BEARER_TOKEN}", upload_post, methods=["POST"]),
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
