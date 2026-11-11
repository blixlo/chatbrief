"""Owner-only storage under ~/.tg_recap (override with TG_RECAP_HOME).

Directories are created 0700 and files are written 0600. Nothing here ever
stores a phone number, login code or two-step password.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DIR_MODE = 0o700
FILE_MODE = 0o600


def home() -> Path:
    return Path(os.environ.get("TG_RECAP_HOME", str(Path.home() / ".tg_recap")))


def ensure_dir(path: Path | None = None) -> Path:
    path = Path(path) if path else home()
    path.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    os.chmod(path, DIR_MODE)
    return path


def credentials_file() -> Path:
    return home() / "credentials.json"  # api_id + api_hash only


def session_base() -> Path:
    return home() / "tg_recap"  # Telethon appends ".session"


def session_file() -> Path:
    return home() / "tg_recap.session"


def pending_dir() -> Path:
    return home() / "pending"  # in-progress card sign-in (login --cards)


def pending_session_base() -> Path:
    return pending_dir() / "login"  # Telethon appends ".session"


def pending_state_file() -> Path:
    return pending_dir() / "state.json"  # phone_code_hash + stage; never the phone


def settings_file() -> Path:
    return home() / "settings.json"  # user settings (config.SCHEMA)


def config_file() -> Path:
    return home() / "config.json"  # legacy (v0.1.0-v0.1.4); read once if settings.json is missing


def state_file() -> Path:
    return home() / "state.json"


def lock_file() -> Path:
    return home() / "session.lock"


def raw_dir() -> Path:
    return home() / "cache" / "raw"


def recaps_dir() -> Path:
    return home() / "cache" / "recaps"


def write_private(path: Path, data: str) -> None:
    """Atomically write text with 0600 perms inside a 0700 dir."""
    path = Path(path)
    ensure_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
    finally:
        if tmp.exists():
            os.chmod(tmp, FILE_MODE)
    os.replace(tmp, path)
    os.chmod(path, FILE_MODE)


def write_json(path: Path, obj) -> None:
    write_private(path, json.dumps(obj, indent=2, sort_keys=True))


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def tighten(path: Path) -> None:
    """Force 0600 on an existing file (e.g. Telethon's session file)."""
    if Path(path).exists():
        os.chmod(path, FILE_MODE)
