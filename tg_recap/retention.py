"""Retention for this code's own cache (not Telegram, not your apps).

- Raw fetched data (the digest input JSON) is deleted as soon as the recap
  is rendered.
- Rendered recap text is kept for at most 72 hours (the spec proposes
  24-72 h; we use the upper bound), then deleted on the next run.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import paths

RECAP_TTL = timedelta(hours=72)


def _stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_raw(digest: dict, now: datetime) -> Path:
    path = paths.raw_dir() / f"{_stamp(now)}.json"
    paths.ensure_dir(paths.home() / "cache")
    paths.write_private(path, json.dumps(digest))
    return path


def delete_raw() -> int:
    n = 0
    d = paths.raw_dir()
    if d.exists():
        for f in d.iterdir():
            if f.is_file():
                f.unlink()
                n += 1
    return n


def save_recap(text: str, now: datetime) -> Path | None:
    if not text:
        return None
    paths.ensure_dir(paths.home() / "cache")
    path = paths.recaps_dir() / f"{_stamp(now)}.txt"
    paths.write_private(path, text)
    return path


def purge_recaps(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    d = paths.recaps_dir()
    n = 0
    if not d.exists():
        return 0
    for f in d.glob("*.txt"):
        try:
            made = datetime.strptime(f.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if now - made > RECAP_TTL:
            f.unlink()
            n += 1
    return n
