"""Consent gate for Telegram API Terms of Service section 1.5 (AI use of data).

Sign-in, `collect` and `run` refuse (exit 9 CONSENT_REQUIRED) until the owner
has read WARNING and run `consent accept`. Accepting records exactly two keys in
~/.tg_recap/settings.json (0600): tos_1_5_accepted_at (ISO time, UTC) and
terms_version. Nothing else is stored. A new TERMS_VERSION asks again.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import paths
from .branding import DISCLOSURE, PRODUCT_NAME  # noqa: F401 - DISCLOSURE re-exported

EXIT_CONSENT = 9
TERMS_URL = "https://core.telegram.org/api/terms"
TERMS_VERSION = "tg-api-tos-1.5/2026-11-11"
KEYS = ("tos_1_5_accepted_at", "terms_version")

CLAUSE = ("you are prohibited from using, accessing or aggregating data obtained from the Telegram platform to "
          "train, fine-tune or otherwise engage in the development, enhancement or deployment of artificial "
          "intelligence, machine learning models and similar technologies.")
WARNING = (
    f"{DISCLOSURE}\n\n"
    f"Before you sign in: Telegram's API Terms of Service, section 1.5 ({TERMS_URL}), say:\n"
    f"\"{CLAUSE}\"\n\n"
    f"{PRODUCT_NAME} is an AI agent that reads your chats to write your recaps. Telegram may consider that "
    "against its API terms. Telegram's stated remedy for a breach is to notify the account responsible for the "
    "app, and if it isn't fixed within 10 days, to cut off that app's access to the Telegram API (your API ID). "
    f"{PRODUCT_NAME} never trains on your chats or uses them to build any model. Use it at your own risk.\n\n"
    "To continue, confirm that you have read this and accept the risk."
)
REQUIRED_MSG = (f"CONSENT_REQUIRED: {PRODUCT_NAME} needs your OK on Telegram's API terms (section 1.5) first. "
                "Run `consent show`, then `consent accept` only after you agree.")


def _settings() -> dict:
    data = paths.read_json(paths.settings_file(), {})
    return data if isinstance(data, dict) else {}


def accepted() -> bool:
    data = _settings()
    return isinstance(data.get("tos_1_5_accepted_at"), str) and data.get("terms_version") == TERMS_VERSION


def accept(now: datetime | None = None) -> dict:
    """Record consent: only the two KEYS are added; other settings are kept as they are."""
    now = now or datetime.now(timezone.utc)
    record = {"tos_1_5_accepted_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
              "terms_version": TERMS_VERSION}
    paths.ensure_dir()
    paths.write_json(paths.settings_file(), {**_settings(), **record})
    paths.tighten(paths.settings_file())
    return record


def preserved(existing: dict | None = None) -> dict:
    """The consent keys from settings.json, so other writers keep them."""
    data = _settings() if existing is None else existing
    return {k: data[k] for k in KEYS if k in data}


def require(err) -> int | None:
    """Print one line and return 9 when consent is missing, else None."""
    if accepted():
        return None
    print(REQUIRED_MSG, file=err, flush=True)
    return EXIT_CONSENT
