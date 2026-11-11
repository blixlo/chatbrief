"""One scheduled run: lock -> collect -> (JSON for the agent | fallback text) -> retention.

`run`     prints the deterministic fallback recap (or nothing).
`collect` prints one JSON object: the digest the agent writes the recap from,
          plus "fallback_text" and "nothing_to_report".
`--peek`  (either command) does the same full read-only pass but writes nothing
          under ~/.tg_recap: the window is not advanced, state.json is not written
          at all (no window, no chat-title directory, no new salt), and no recap
          copy is saved. Only the session lock is taken and released (Telethon
          itself may still update session.session). JSON output gains "peek": true.
          Use it for test or manual runs so the next scheduled run keeps its window.

Exit codes (stderr carries one short plain line, stdout stays empty):
  0  ok (stdout is the recap / JSON; recap text empty when nothing qualified)
  2  LOCK_HELD        another run is using the session
  3  SESSION_REVOKED  not signed in / session ended in Telegram Settings > Devices
  4  FLOOD_STOP       Telegram asked to slow down twice; run stopped
  5  NOT_SET_UP       no credentials yet; run setup first
  7  SETTINGS_INVALID ~/.tg_recap/settings.json didn't validate (field named)
  9  CONSENT_REQUIRED the API-terms 1.5 warning hasn't been accepted (`consent accept`)
  8  CONNECT_FAILED   couldn't reach Telegram's web endpoint (DNS, TLS, WebSocket
                      handshake or timeout); stderr names only the error type

Transport: Telegram's official web endpoints, wss://<dc>.web.telegram.org:443/apiws
(transport_wss.py). A saved session keeps its auth key and DC; if Telegram no
longer knows the key (AuthKeyNotFound / unregistered) or the session points at a
DC with no web endpoint, the run exits 3 and asks for a new sign-in; nothing
tries to repair the session.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone

from . import collect as collect_mod
from . import config, paths, retention
from .lock import LockHeld, SessionLock
from .readonly import FloodStop, ReadOnlyClient
from .render import render
from . import consent
from .branding import PRODUCT_NAME
from .memecoin import LAST_MEMECOIN_AT

EXIT_OK, EXIT_LOCK, EXIT_REVOKED, EXIT_FLOOD, EXIT_NOT_SET_UP, EXIT_SETTINGS = 0, 2, 3, 4, 5, 7
EXIT_CONNECT = 8
REVOKED_MSG = ("SESSION_REVOKED: Your Telegram session isn't active (it may have been ended in "
               "Settings > Devices). Run setup again to sign in.")
DC_MSG = ("SESSION_REVOKED: Your saved Telegram session points at a data center this version can't reach "
          "over Telegram's web endpoints. Run setup again to sign in.")
_REVOKED_ERRORS = {"AuthKeyUnregisteredError", "SessionRevokedError", "SessionExpiredError",
                   "UserDeactivatedError", "UserDeactivatedBanError", "AuthKeyDuplicatedError",
                   "AuthKeyNotFound", "AuthKeyInvalidError", "AuthKeyPermEmptyError"}


def _connect_msg(exc) -> str:
    from .transport_wss import last_connect_error
    kind = getattr(exc, "kind", None) or last_connect_error() or type(exc).__name__
    return (f"CONNECT_FAILED: Couldn't reach Telegram's web endpoint ({kind}). Nothing was read; "
            "the next scheduled run will try again.")


class NotAuthorized(RuntimeError):
    pass


def telethon_client():
    creds = paths.read_json(paths.credentials_file())
    if not creds or not paths.session_file().exists():
        return None
    from .login_backend import no_entity_cache
    from .transport_wss import WebTelegramClient, quiet_telethon_logs
    quiet_telethon_logs()
    return no_entity_cache(WebTelegramClient(str(paths.session_base()), int(creds["api_id"]), creds["api_hash"],
                                             receive_updates=False, flood_sleep_threshold=0))


async def _collect(raw_client, cfg, state, now, *, window_hours=None, state_key="last_recap_at",
                  default_hours=None):
    client = ReadOnlyClient(raw_client)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise NotAuthorized()
        return await collect_mod.collect(client, cfg, state, now, window_hours=window_hours,
                                         state_key=state_key, default_hours=default_hours)
    finally:
        await client.disconnect()
        paths.tighten(paths.session_file())


def run(client_factory=telethon_client, now: datetime | None = None, out=sys.stdout, err=sys.stderr,
        as_json: bool = False, peek: bool = False, memecoin_only: bool = False,
        window_hours: int | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    try:
        cfg = config.load()
    except config.SettingsError as exc:
        print(f"SETTINGS_INVALID: {exc}. Fix it with `settings set ...` or `settings show`.", file=err)
        return EXIT_SETTINGS
    refused = consent.require(err)
    if refused is not None:
        return refused  # 9: nothing is read until the owner accepts the terms warning
    try:
        lock = SessionLock().acquire()
    except LockHeld as exc:
        print(f"LOCK_HELD: {exc}", file=err)
        return EXIT_LOCK
    try:
        try:
            raw_client = client_factory()
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "UnknownDc":
                print(DC_MSG, file=err)
                return EXIT_REVOKED
            raise
        if raw_client is None:
            print(f"NOT_SET_UP: {PRODUCT_NAME} isn't signed in yet. Run setup first.", file=err)
            return EXIT_NOT_SET_UP
        state = collect_mod.load_state()
        state_key = LAST_MEMECOIN_AT if memecoin_only else "last_recap_at"
        default_hours = 1 if memecoin_only else None
        try:
            digest = asyncio.run(_collect(raw_client, cfg, state, now, window_hours=window_hours,
                                          state_key=state_key, default_hours=default_hours))
        except FloodStop as exc:
            print(f"FLOOD_STOP: {exc}", file=err)
            return EXIT_FLOOD
        except NotAuthorized:
            print(REVOKED_MSG, file=err)
            return EXIT_REVOKED
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ in _REVOKED_ERRORS:
                print(REVOKED_MSG, file=err)
                return EXIT_REVOKED
            if type(exc).__name__ == "UnknownDc":
                print(DC_MSG, file=err)
                return EXIT_REVOKED
            if isinstance(exc, (ConnectionError, TimeoutError)):
                print(_connect_msg(exc), file=err)
                return EXIT_CONNECT
            raise
        text = render(digest, memecoin_only=memecoin_only)
        if not peek:
            if not memecoin_only:
                retention.write_raw(digest, now)
                retention.save_recap(text, now)
                retention.delete_raw()
                retention.purge_recaps(now)
                state["last_recap_at"] = digest["window"]["end"]
            else:
                state[LAST_MEMECOIN_AT] = digest["window"]["end"]
            collect_mod.save_state(state)
        if as_json:
            extra = {"peek": True} if peek else {}
            if memecoin_only:
                extra["memecoin_only"] = True
            out.write(json.dumps({**digest, "fallback_text": text, "nothing_to_report": not text, **extra},
                                 ensure_ascii=False, indent=1) + "\n")
        elif text:
            out.write(text)
        return EXIT_OK
    finally:
        if not peek:
            retention.delete_raw()
        lock.release()
