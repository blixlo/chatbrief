"""Interactive terminal sign-in (the default): `python -m tg_recap login`.

The user runs this in a terminal on the machine that will hold the session and
types their own details. Prompts, in order:
  API ID (shown as typed) and API hash (hidden), unless saved ones are reused,
  phone number (input), login code (input), and the two-step password
  (hidden, getpass) only when Telegram says the account has one.

Uses the same Telethon send_code_request / sign_in steps as the web fallback
(login_backend.TelethonBackend). Nothing else is sent to Telegram.

Saved (dir 0700, files 0600): credentials.json (api_id + api_hash) and
Telethon's session file tg_recap.session. Never printed, logged or saved: the
phone number, login code, two-step password, or session contents. Errors are
reported by kind only, never with the values, and never as a traceback.

Exit codes: 0 signed in, 1 not finished (cancelled, too many wrong tries, or
Telegram refused), 2 LOCK_HELD (a recap run is using the session),
4 FLOOD_STOP (Telegram asked to wait), 8 CONNECT_FAILED (Telegram's web endpoint
unreachable), 9 CONSENT_REQUIRED (run `consent accept` after reading `consent show`).
"""
from __future__ import annotations

import asyncio
import getpass
import logging
import os
import sys

from . import consent, paths
from .branding import PRODUCT_NAME
from .lock import LockHeld, SessionLock
from .login_backend import (ApiInvalid, CodeExpired, CodeInvalid, FloodWait, LoginError,
                            PasswordInvalid, PasswordNeeded, PhoneInvalid, TelegramRefused, ConnectFailed,
                            TelethonBackend, save_credentials)

EXIT_OK, EXIT_NOT_FINISHED, EXIT_LOCK, EXIT_FLOOD, EXIT_CONNECT = 0, 1, 2, 4, 8
MAX_TRIES = 3      # per prompt: API values, phone, code, password
MAX_RESENDS = 1    # fresh codes requested after an expired one

INTRO = (
    f"{PRODUCT_NAME}: sign in\n"
    f"{consent.DISCLOSURE}\n"
    "This signs in as you with Telethon, on this computer only. It only reads your chats.\n"
    "Type your details here yourself, never in a chat. Hidden fields don't show what you type.\n"
    "Your phone number, login code and two-step password are used once and are never saved,\n"
    "shown back or logged. Kept on this computer, readable only by you: your API ID, API hash\n"
    "and Telegram's session file (~/.tg_recap). End the session any time in Telegram under\n"
    "Settings > Devices. Ctrl+C cancels.\n"
)
API_HELP = ("Get your own API ID and API hash at https://my.telegram.org (API development tools).\n"
            "Telegram's steps: https://core.telegram.org/api/obtaining_api_id\n")
NOT_SAVED = "Nothing about your phone, code or password was saved."


class _Stop(Exception):
    def __init__(self, code: int, message: str):
        super().__init__()
        self.code, self.message = code, message


def _valid_api(api_id: str, api_hash: str) -> bool:
    return api_id.isdigit() and len(api_hash) >= 16


class TerminalLogin:
    def __init__(self, backend=None, input_fn=input, getpass_fn=getpass.getpass, out=None, err=None):
        self.backend = backend or TelethonBackend()
        self.input = input_fn
        self.getpass = getpass_fn
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self._loop = asyncio.new_event_loop()

    # --- helpers ------------------------------------------------------------
    def say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def warn(self, text: str) -> None:
        print(text, file=self.err, flush=True)

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    # --- steps --------------------------------------------------------------
    def _api_values(self):
        saved = paths.read_json(paths.credentials_file()) or {}
        if saved.get("api_id") and saved.get("api_hash"):
            answer = self.input("Use the API ID and API hash already saved on this computer? [Y/n]: ")
            if answer.strip().lower() in ("", "y", "yes"):
                return int(saved["api_id"]), saved["api_hash"]
        self.say(API_HELP)
        for left in range(MAX_TRIES - 1, -1, -1):
            api_id = self.input("API ID: ").strip()
            api_hash = self.getpass("API hash (hidden): ").strip()
            if _valid_api(api_id, api_hash):
                return int(api_id), api_hash
            api_id = api_hash = None
            self.warn("That API ID or API hash doesn't look right. Copy both from my.telegram.org."
                      + (f" {left} tries left." if left else ""))
        raise _Stop(EXIT_NOT_FINISHED, "Too many tries for the API ID / API hash.")

    def _phone(self):
        for left in range(MAX_TRIES - 1, -1, -1):
            phone = self.input("Phone number, international format (for example +1 then your number): ").strip()
            try:
                if not phone:
                    raise PhoneInvalid()
                self._run(self.backend.send_code(phone))
                self.say("Telegram sent a login code to your Telegram app.")
                return
            except PhoneInvalid:
                self.warn("Telegram didn't accept that phone number. Use international format."
                          + (f" {left} tries left." if left else ""))
            finally:
                phone = None
        raise _Stop(EXIT_NOT_FINISHED, "Too many tries for the phone number.")

    def _code(self) -> bool:
        """Return True when a two-step password is needed next."""
        wrong = resends = 0
        while True:
            code = self.input("Login code: ").strip()
            try:
                self._run(self.backend.sign_in_code(code))
                return False
            except PasswordNeeded:
                return True
            except CodeInvalid:
                wrong += 1
                if wrong >= MAX_TRIES:
                    raise _Stop(EXIT_NOT_FINISHED, "Too many wrong login codes.") from None
                self.warn(f"That code didn't work. {MAX_TRIES - wrong} tries left.")
            except CodeExpired:
                if resends >= MAX_RESENDS:
                    raise _Stop(EXIT_NOT_FINISHED, "The login code expired again.") from None
                resends += 1
                self._run(self.backend.resend_code())
                self.warn("That code expired. Telegram sent a new one; type the new code.")
            finally:
                code = None

    def _password(self):
        for left in range(MAX_TRIES - 1, -1, -1):
            password = self.getpass("Two-step password (hidden): ")
            try:
                self._run(self.backend.sign_in_password(password))
                return
            except PasswordInvalid:
                self.warn("That two-step password didn't work." + (f" {left} tries left." if left else ""))
            finally:
                password = None
        raise _Stop(EXIT_NOT_FINISHED, "Too many wrong two-step passwords.")

    def _flow(self) -> int:
        self.say(INTRO)
        api_id, api_hash = self._api_values()
        self._run(self.backend.start(api_id, api_hash))
        try:
            self._phone()
        except ApiInvalid:
            raise _Stop(EXIT_NOT_FINISHED, "Telegram didn't accept that API ID / API hash. "
                                           "Check both on my.telegram.org.") from None
        if self._code():
            self.say("Your account has a two-step password.")
            self._password()
        self._run(self.backend.finish())
        save_credentials(api_id, api_hash)
        api_hash = None
        return EXIT_OK

    def run(self) -> int:
        os.umask(0o077)
        paths.ensure_dir()
        try:
            lock = SessionLock().acquire()
        except LockHeld:
            self.warn("LOCK_HELD: A recap run is using the session right now. Try again in a minute.")
            self._loop.close()
            return EXIT_LOCK
        code, ok = EXIT_NOT_FINISHED, False
        try:
            code = self._flow()
            ok = code == EXIT_OK
        except _Stop as stop:
            self.warn(f"Sign-in not finished: {stop.message} {NOT_SAVED}")
            code = stop.code
        except FloodWait as fw:
            self.warn(f"FLOOD_STOP: Telegram asked to wait {fw.seconds}s before another sign-in try. "
                      f"{NOT_SAVED} Try again later.")
            code = EXIT_FLOOD
        except (KeyboardInterrupt, EOFError):
            self.warn(f"Sign-in cancelled. {NOT_SAVED}")
            code = EXIT_NOT_FINISHED
        except ConnectFailed as cf:
            self.warn(f"CONNECT_FAILED: couldn't reach Telegram's web endpoint ({cf.kind}). {NOT_SAVED}")
            code = EXIT_CONNECT
        except TelegramRefused as tr:
            self.warn(f"Telegram didn't accept the sign-in ({tr.kind}). {NOT_SAVED}")
            code = EXIT_NOT_FINISHED
        except LoginError as le:
            self.warn(f"Sign-in not finished ({type(le).__name__}). {NOT_SAVED}")
            code = EXIT_NOT_FINISHED
        except Exception as exc:  # noqa: BLE001 - kind only, never values or a traceback
            self.warn(f"Sign-in stopped ({type(exc).__name__}). {NOT_SAVED}")
            code = EXIT_NOT_FINISHED
        finally:
            if not ok:
                try:
                    self._run(self.backend.abort())
                except BaseException:  # noqa: BLE001
                    pass
            lock.release()
            self._loop.close()
            paths.tighten(paths.session_file())
        if ok:
            self.say("Signed in. Session saved under ~/.tg_recap (owner-only). "
                     "End it any time in Telegram Settings > Devices.")
        return code


def login(backend=None, input_fn=input, getpass_fn=getpass.getpass, out=None, err=None) -> int:
    logging.getLogger("telethon").setLevel(logging.CRITICAL)
    refused = consent.require(err or sys.stderr)
    if refused is not None:
        return refused  # 9: accept the API-terms warning first (`consent accept`)
    return TerminalLogin(backend, input_fn, getpass_fn, out, err).run()
