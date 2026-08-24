"""Paprika MCP Server"""

import logging
import os
from pathlib import Path

__version__ = "0.7.0"

logger = logging.getLogger(__name__)


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from a local .env into the environment.

    Deliberately dependency-free and forgiving. Real environment variables
    always win, so a hosted deployment (Render, Docker) is never overridden by
    a stray file. Without this, a key placed in .env is silently ignored during
    local runs while working fine in production — a confusing mismatch.
    """
    env_path = path or Path(__file__).resolve().parents[2] / ".env"
    try:
        if not env_path.is_file():
            return
        raw = env_path.read_text(encoding="utf-8-sig")
    except OSError as e:
        logger.debug(f"Could not read {env_path}: {e}")
        return

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        # setdefault: never clobber a real environment variable.
        if key and value:
            os.environ.setdefault(key, value)


load_dotenv()
