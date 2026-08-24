"""Shared photo helpers: acquire bytes, normalize, stage uploads, attach to Paprika.

Paprika's photo upload uses the recipe-sync endpoint with a multipart form that
has TWO file parts: `data` (gzipped recipe JSON) and `photo_upload` (the binary
JPEG). The recipe's `photo` field must be a generated "<UUID>.jpg" filename, NOT
base64 — the server stores the binary and populates `photo_url` (the S3-hosted URL
the app uses to render thumbnails).

Because a photo the user pastes into a Claude conversation cannot be re-emitted as
tool-argument bytes, the remote HTTP server also exposes a browser upload endpoint
(see server_http.py) that stages normalized JPEG bytes here under a short code. A
tool then references that code to attach the staged photo to a recipe.
"""

import base64
import binascii
import hashlib
import io
import re
import secrets
import time
import uuid as uuid_lib
from typing import Any

import requests

MAX_DIMENSION = 1200
JPEG_QUALITY = 85
DOWNLOAD_TIMEOUT = 30
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MB safety cap on the source download

# --- Staging store for browser-uploaded photos --------------------------------
# Module-level, in-process. Fine for this project's single-instance Render
# deployment; NOT safe across multiple uvicorn workers or instances.
STAGE_TTL_SECONDS = 30 * 60  # codes expire after 30 minutes
STAGE_MAX_ENTRIES = 20  # bound memory; oldest is evicted past this
_staged: dict[str, tuple[float, bytes]] = {}  # code -> (expiry_epoch, jpeg_bytes)

_heif_registered = False


def _ensure_heif_support() -> None:
    """Register the HEIF/HEIC opener with Pillow once, if pillow-heif is present.

    iPhone photos are commonly HEIC; Safari usually converts to JPEG on upload,
    but not always. Registering the opener lets Pillow read HEIC directly.
    """
    global _heif_registered
    if _heif_registered:
        return
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except ImportError:
        pass
    _heif_registered = True


def _download_image(url: str) -> bytes:
    """Download image bytes from URL with a size cap."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT, stream=True)
    resp.raise_for_status()

    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_DOWNLOAD_BYTES:
            raise ValueError(
                f"Image at {url} exceeds {MAX_DOWNLOAD_BYTES // 1024 // 1024} MB cap"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def normalize_to_jpeg(raw: bytes) -> bytes:
    """Open with Pillow, convert to RGB JPEG, downscale if needed.

    Raises ImportError if Pillow is unavailable (callers surface a hint).
    """
    from PIL import Image  # imported lazily so server still starts without Pillow

    _ensure_heif_support()

    with Image.open(io.BytesIO(raw)) as img:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue()


def _prune(now: float) -> None:
    for code in [c for c, (exp, _) in _staged.items() if exp <= now]:
        _staged.pop(code, None)


def stage_photo(jpeg_bytes: bytes) -> str:
    """Store normalized JPEG bytes under a short code; return the code."""
    now = time.time()
    _prune(now)
    if len(_staged) >= STAGE_MAX_ENTRIES:
        oldest = min(_staged, key=lambda c: _staged[c][0])
        _staged.pop(oldest, None)
    code = secrets.token_hex(3).upper()  # 6 hex chars, e.g. "K7QX9F"
    _staged[code] = (now + STAGE_TTL_SECONDS, jpeg_bytes)
    return code


def pop_staged(code: str) -> bytes:
    """Return and remove the staged JPEG for `code`. Raises KeyError if missing."""
    now = time.time()
    _prune(now)
    entry = _staged.pop(code, None)
    if entry is None:
        raise KeyError(code)
    return entry[1]


def pop_latest() -> tuple[str, bytes]:
    """Return and remove the most recently staged photo. Raises KeyError if none.

    Lets the user attach a just-uploaded photo without copying its code back —
    they upload, then say "attach it". All entries share the same TTL, so the
    greatest expiry is the newest upload.
    """
    now = time.time()
    _prune(now)
    if not _staged:
        raise KeyError("no staged uploads")
    code = max(_staged, key=lambda c: _staged[c][0])
    return code, _staged.pop(code)[1]


_DATA_URI_RE = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,", re.IGNORECASE)


def decode_image_base64(value: str) -> bytes:
    """Decode base64 image data, tolerating a data: URI prefix and whitespace.

    Image-generation MCPs sometimes hand back base64 instead of a hosted URL;
    this lets such a result be attached without a round-trip through a host.
    """
    payload = _DATA_URI_RE.sub("", value.strip())
    payload = "".join(payload.split())  # strip newlines from wrapped base64
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"'image_base64' is not valid base64 data: {e}") from None
    if not raw:
        raise ValueError("'image_base64' decoded to zero bytes.")
    if len(raw) > MAX_DOWNLOAD_BYTES:
        cap = MAX_DOWNLOAD_BYTES // 1024 // 1024
        raise ValueError(f"Decoded image exceeds the {cap} MB cap.")
    return raw


def resolve_image_bytes(args: dict[str, Any]) -> tuple[bytes, str]:
    """Acquire source image bytes from whichever input was provided.

    Returns (raw_bytes, source_label). Callers normalize the bytes to JPEG.
    Resolution order:
      1. `upload_code` — a specific browser-staged photo.
      2. `image_url` — a public image URL.
      3. `image_base64` — raw/base64 image data (e.g. from an image-generation
         MCP that returns data rather than a hosted URL).
      4. None given — the most recently staged upload (the common "I just
         uploaded a photo, attach it" case, so no code needs copying back).
    """
    upload_code = args.get("upload_code")
    image_url = args.get("image_url")
    image_base64 = args.get("image_base64")

    if upload_code:
        code = str(upload_code).strip().upper()
        try:
            return pop_staged(code), f"upload:{code}"
        except KeyError:
            raise ValueError(
                f"Upload code '{code}' was not found or has expired. Re-upload the "
                "photo at the /upload URL and use the fresh code."
            ) from None

    if image_url:
        return _download_image(image_url), image_url

    if image_base64:
        return decode_image_base64(str(image_base64)), "generated:base64"

    try:
        code, data = pop_latest()
        return data, f"upload:{code}"
    except KeyError:
        raise ValueError(
            "No photo to attach. Upload one at the /upload URL first (ask for the "
            "upload link), or pass an 'image_url' or 'image_base64'."
        ) from None


def attach_photo_bytes(remote, recipe, jpeg_bytes: bytes, source_label: str) -> dict:
    """Set the recipe's photo fields and POST the two-part multipart upload.

    Reuses Remote's authenticated session via the protected `_request` helper so
    we keep the bearer token, retries, and configured user-agent.
    """
    photo_filename = f"{str(uuid_lib.uuid4()).upper()}.jpg"
    recipe.photo = photo_filename
    recipe.photo_hash = hashlib.sha256(jpeg_bytes).hexdigest().upper()
    recipe.image_url = source_label
    # photo_url is server-managed; clear any stale value so the server resets it
    if hasattr(recipe, "photo_url"):
        recipe.photo_url = None
    if hasattr(recipe, "update_hash"):
        recipe.update_hash()

    files = {
        "data": ("data", recipe.as_paprikarecipe()),
        "photo_upload": (photo_filename, jpeg_bytes, "image/jpeg"),
    }
    remote._request("post", f"/api/v2/sync/recipe/{recipe.uid}/", files=files)

    return {
        "photo_filename": photo_filename,
        "photo_hash": recipe.photo_hash,
        "size_kb": len(jpeg_bytes) // 1024,
    }
