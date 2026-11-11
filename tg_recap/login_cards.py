"""Resumable sign-in by secret-request cards (the default): `login --cards <step>`.

Each card is one value, delivered as an env var. Each step runs in its own
process, reads only its own vars, and keeps what the next step needs on disk.
  save-api   TG_RECAP_API_ID + TG_RECAP_API_HASH -> credentials.json (0600)
  send-code  TG_RECAP_PHONE -> pending/ (0700): Telethon session + state.json
             (phone_code_hash, stage), files 0600
  sign-in    TG_RECAP_CODE + TG_RECAP_PHONE -> done, or 10 NEED_2FA
  password   TG_RECAP_2FA -> done
  reset      wipe pending/
On success the session moves to ~/.tg_recap/tg_recap.session (0600) and
pending/ is removed. The phone is never written to disk in any form (a hash of
it is easy to reverse): sign-in re-reads TG_RECAP_PHONE, which stays set after
its card. Telethon's entity cache is off, so your own user record (with your
number) isn't saved in the sqlite session either. Values are never printed,
logged or saved; messages name only the step, the env var or the error kind.
Exit codes: the EXIT_* constants below (9 CONSENT_REQUIRED: run `consent accept` after
reading `consent show`; 8 CONNECT_FAILED: Telegram's web endpoint
unreachable); 6 MISSING_DEPS comes from the CLI.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from datetime import datetime, timezone

from . import consent, paths
from .lock import LockHeld, SessionLock
from .login_backend import (ApiInvalid, CodeExpired, CodeInvalid, FloodWait, LoginError,
                            PasswordInvalid, PasswordNeeded, PhoneInvalid, TelegramRefused, ConnectFailed,
                            TelethonBackend, save_credentials)

ENV_API_ID = "TG_RECAP_API_ID"
ENV_API_HASH = "TG_RECAP_API_HASH"
ENV_PHONE = "TG_RECAP_PHONE"
ENV_CODE = "TG_RECAP_CODE"
ENV_2FA = "TG_RECAP_2FA"
ENV_VARS = (ENV_API_ID, ENV_API_HASH, ENV_PHONE, ENV_CODE, ENV_2FA)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_LOCK = 2
EXIT_FLOOD = 4
EXIT_CONNECT = 8
EXIT_NOT_SET_UP = 5
EXIT_NEED_2FA = 10
EXIT_CODE_INVALID = 11
EXIT_PASSWORD_INVALID = 12
EXIT_CODE_EXPIRED = 13
EXIT_PHONE_INVALID = 14
EXIT_API_INVALID = 15
EXIT_MISSING_ENV = 16
EXIT_NO_PENDING = 17

STEPS = ("save-api", "send-code", "sign-in", "password", "reset")

USAGE = (
    "Sign in with secret-request cards (one value each), then run each step:\n"
    f"  login --cards save-api    reads {ENV_API_ID}, {ENV_API_HASH}\n"
    f"  login --cards send-code   reads {ENV_PHONE}\n"
    f"  login --cards sign-in     reads {ENV_CODE} and {ENV_PHONE} (exit 10 = send the {ENV_2FA} card)\n"
    f"  login --cards password    reads {ENV_2FA}\n"
    "  login --cards reset       wipes an unfinished sign-in\n"
    "Fallbacks: login --terminal (type in a terminal) or login --web (127.0.0.1 page).\n"
    "Never type these values into a chat."
)


class _Exit(Exception):
    def __init__(self, code: int, message: str = ""):
        super().__init__()
        self.code, self.message = code, message


def _env(env, name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise _Exit(EXIT_MISSING_ENV, f"MISSING_ENV: {name} isn't set. Send the {name} secret card, then run "
                                      "this step again.")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clear_pending() -> None:
    shutil.rmtree(paths.pending_dir(), ignore_errors=True)


def _tighten_tree(root) -> None:
    if not root.exists():
        return
    os.chmod(root, paths.DIR_MODE)
    for p in root.rglob("*"):
        os.chmod(p, paths.DIR_MODE if p.is_dir() else paths.FILE_MODE)


def _creds():
    creds = paths.read_json(paths.credentials_file()) or {}
    if not creds.get("api_id") or not creds.get("api_hash"):
        raise _Exit(EXIT_NOT_SET_UP, "NOT_SET_UP: no saved API ID / API hash yet. Run `login --cards save-api` "
                                     "first.")
    return int(creds["api_id"]), creds["api_hash"]


def _pending():
    state = paths.read_json(paths.pending_state_file())
    if not state or not state.get("phone_code_hash") or not \
            (paths.pending_dir() / (paths.pending_session_base().name + ".session")).exists():
        raise _Exit(EXIT_NO_PENDING, "NO_PENDING: no sign-in in progress. Run `login --cards send-code` first.")
    return state


class CardLogin:
    def __init__(self, env=None, client_factory=None, out=None, err=None):
        self.env = os.environ if env is None else env
        self.factory = client_factory
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self._loop = None

    def say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def _backend(self):
        return TelethonBackend(client_factory=self.factory, session_base=paths.pending_session_base())

    def _close(self, backend) -> None:
        try:
            self._run(backend.abort())  # disconnect only; keeps pending files
        except BaseException:  # noqa: BLE001
            pass
        _tighten_tree(paths.pending_dir())

    def _finish(self, backend) -> None:
        self._run(backend.finish())
        pending_session = paths.pending_dir() / (paths.pending_session_base().name + ".session")
        final = paths.session_file()
        for stale in (final.with_name(final.name + "-journal"),):
            if stale.exists():
                stale.unlink()
        os.replace(pending_session, final)
        paths.tighten(final)
        clear_pending()

    # --- steps --------------------------------------------------------------
    def save_api(self) -> int:
        api_id = _env(self.env, ENV_API_ID)
        api_hash = _env(self.env, ENV_API_HASH)
        if not api_id.isdigit() or int(api_id) <= 0 or len(api_hash) < 16:
            raise _Exit(EXIT_API_INVALID, f"API_INVALID: {ENV_API_ID} must be a whole number and {ENV_API_HASH} "
                                          "the hash from my.telegram.org. Re-send those cards.")
        clear_pending()  # a pending sign-in belongs to the old API values
        save_credentials(int(api_id), api_hash)
        self.say("Saved the API ID and API hash (owner-only). Next: the phone card, then "
                 "`login --cards send-code`.")
        return EXIT_OK

    def send_code(self) -> int:
        api_id, api_hash = _creds()
        phone = _env(self.env, ENV_PHONE)
        clear_pending()
        paths.ensure_dir(paths.pending_dir())
        backend = self._backend()
        try:
            self._run(backend.start(api_id, api_hash))
            self._run(backend.send_code(phone))
            paths.write_json(paths.pending_state_file(),
                             {"phone_code_hash": backend.phone_code_hash, "stage": "code", "created_at": _now()})
        except BaseException:
            self._close(backend)
            clear_pending()
            raise
        self._close(backend)
        self.say("Telegram sent a login code to your Telegram app. Next: the code card, then "
                 "`login --cards sign-in`.")
        return EXIT_OK

    def sign_in(self) -> int:
        state = _pending()
        code = _env(self.env, ENV_CODE)
        phone = _env(self.env, ENV_PHONE)
        api_id, api_hash = _creds()
        backend = self._backend()
        try:
            self._run(backend.start(api_id, api_hash))
            backend.restore(phone, state["phone_code_hash"])
            self._run(backend.sign_in_code(code))
        except PasswordNeeded:
            self._close(backend)
            state["stage"] = "password"
            paths.write_json(paths.pending_state_file(), state)
            _tighten_tree(paths.pending_dir())
            raise _Exit(EXIT_NEED_2FA, f"NEED_2FA: your account has a two-step password. Next: the {ENV_2FA} "
                                       "card, then `login --cards password`.") from None
        except CodeInvalid:
            self._close(backend)
            raise _Exit(EXIT_CODE_INVALID, f"CODE_INVALID: Telegram didn't accept that code. Re-send the "
                                           f"{ENV_CODE} card, then run sign-in again.") from None
        except CodeExpired:
            self._close(backend)
            clear_pending()
            raise _Exit(EXIT_CODE_EXPIRED, "CODE_EXPIRED: that code expired; the unfinished sign-in was cleared. "
                                           f"Start again at `login --cards send-code`, then a new {ENV_CODE} "
                                           "card.") from None
        except BaseException:
            self._close(backend)
            raise
        self._finish(backend)
        return self._signed_in()

    def password(self) -> int:
        state = _pending()
        if state.get("stage") != "password":
            raise _Exit(EXIT_NO_PENDING, "NO_PENDING: no two-step password is pending. Run "
                                         "`login --cards sign-in` first.")
        password = _env(self.env, ENV_2FA)
        api_id, api_hash = _creds()
        backend = self._backend()
        try:
            self._run(backend.start(api_id, api_hash))
            self._run(backend.sign_in_password(password))
        except PasswordInvalid:
            self._close(backend)
            raise _Exit(EXIT_PASSWORD_INVALID, f"PASSWORD_INVALID: Telegram didn't accept that two-step password. "
                                               f"Re-send the {ENV_2FA} card, then run password again.") from None
        except BaseException:
            self._close(backend)
            raise
        finally:
            password = None
        self._finish(backend)
        return self._signed_in()

    def reset(self) -> int:
        clear_pending()
        self.say("Cleared any unfinished sign-in. Saved API values and an existing session were kept.")
        return EXIT_OK

    def _signed_in(self) -> int:
        self.say("Signed in. Session saved under ~/.tg_recap (owner-only). End it any time in Telegram "
                 "Settings > Devices.")
        return EXIT_OK

    # --- entry --------------------------------------------------------------
    def run(self, step: str) -> int:
        if step not in STEPS:
            print(USAGE, file=self.err)
            return EXIT_FAILED
        os.umask(0o077)
        paths.ensure_dir()
        try:
            lock = SessionLock().acquire()
        except LockHeld:
            print("LOCK_HELD: a recap run is using the session right now. Try this step again in a minute.",
                  file=self.err, flush=True)
            return EXIT_LOCK
        self._loop = asyncio.new_event_loop()
        try:
            fn = {"save-api": self.save_api, "send-code": self.send_code, "sign-in": self.sign_in,
                  "password": self.password, "reset": self.reset}[step]
            return fn()
        except _Exit as ex:
            print(ex.message, file=self.err, flush=True)
            return ex.code
        except PhoneInvalid:
            print(f"PHONE_INVALID: Telegram didn't accept that phone number. Re-send the {ENV_PHONE} card "
                  "(international format, like +1 then the number), then run send-code again.",
                  file=self.err, flush=True)
            return EXIT_PHONE_INVALID
        except ApiInvalid:
            print(f"API_INVALID: Telegram didn't accept the API ID / API hash. Re-send the {ENV_API_ID} and "
                  f"{ENV_API_HASH} cards, then run save-api again.", file=self.err, flush=True)
            return EXIT_API_INVALID
        except FloodWait as fw:
            clear_pending()
            print(f"FLOOD_STOP: Telegram asked to wait {fw.seconds}s. The unfinished sign-in was cleared; "
                  "start again at send-code later.", file=self.err, flush=True)
            return EXIT_FLOOD
        except ConnectFailed as cf:
            print(f"CONNECT_FAILED: couldn't reach Telegram's web endpoint ({cf.kind}). Nothing was saved by "
                  f"this step; tell the user and stop. Run {step} again later.", file=self.err, flush=True)
            return EXIT_CONNECT
        except TelegramRefused as tr:
            print(f"FAILED: Telegram didn't accept the {step} step ({tr.kind}).", file=self.err, flush=True)
            return EXIT_FAILED
        except LoginError as le:
            print(f"FAILED: {step} didn't finish ({type(le).__name__}).", file=self.err, flush=True)
            return EXIT_FAILED
        except (KeyboardInterrupt, EOFError):
            print(f"FAILED: {step} was cancelled.", file=self.err, flush=True)
            return EXIT_FAILED
        except Exception as exc:  # noqa: BLE001 - kind only, never values or a traceback
            print(f"FAILED: {step} stopped ({type(exc).__name__}).", file=self.err, flush=True)
            return EXIT_FAILED
        finally:
            lock.release()
            self._loop.close()
            _tighten_tree(paths.pending_dir())
            paths.tighten(paths.session_file())


def login(step: str, env=None, client_factory=None, out=None, err=None) -> int:
    """Every step except `reset` needs the API-terms consent first (exit 9 without it)."""
    logging.getLogger("telethon").setLevel(logging.CRITICAL)
    if step != "reset":
        refused = consent.require(err or sys.stderr)
        if refused is not None:
            return refused
    return CardLogin(env, client_factory, out, err).run(step)
