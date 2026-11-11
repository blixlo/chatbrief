"""Runtime dependency checks: fail with one line, not a traceback."""
from __future__ import annotations

import sys

TELETHON_VERSION = "1.45.0"
WEBSOCKETS_VERSION = "17.4"
EXIT_MISSING_DEPS = 6


def missing_telethon_message(executable: str | None = None) -> str:
    exe = executable or sys.executable
    return (
        f"Telethon {TELETHON_VERSION} isn't installed for this Python ({exe}). "
        f"Run: {exe} -m pip install -r requirements.txt"
    )


def missing_websockets_message(executable: str | None = None) -> str:
    exe = executable or sys.executable
    return (
        f"websockets {WEBSOCKETS_VERSION} isn't installed for this Python ({exe}). "
        f"Run: {exe} -m pip install -r requirements.txt"
    )


def require_telethon() -> int | None:
    """Return exit code 6 if Telethon or websockets is missing, otherwise None."""
    try:
        import telethon  # noqa: F401
    except ImportError:
        print(missing_telethon_message(), file=sys.stderr)
        return EXIT_MISSING_DEPS
    try:
        import websockets.asyncio.client  # noqa: F401
    except ImportError:
        print(missing_websockets_message(), file=sys.stderr)
        return EXIT_MISSING_DEPS
    return None


require_deps = require_telethon
