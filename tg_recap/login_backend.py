"""Shared Telethon sign-in steps for the terminal login (default) and the web fallback.

Only these client methods are ever used here: LOGIN_METHODS. They are the
login calls themselves; nothing else is sent to Telegram. After sign-in, every
scheduled run goes through readonly.ReadOnlyClient, which denies sign_in and
send_code_request (and every write) outright.

Telethon errors are translated into the small exceptions below, raised
``from None`` and carrying no message, so a phone number, login code or
two-step password can never ride along in an exception, a traceback or a log.
"""
from __future__ import annotations

import logging

from . import paths
from .readonly import _flood_seconds

LOGIN_METHODS = frozenset({"connect", "send_code_request", "sign_in", "disconnect"})

# Keep Telethon quiet during sign-in; our own messages never include values.
logging.getLogger("telethon").setLevel(logging.WARNING)


class LoginError(Exception):
    """Base for sign-in outcomes. Never carries user-typed values."""

    def __init__(self):
        super().__init__()


class PasswordNeeded(LoginError):
    """The account has a two-step password."""


class CodeInvalid(LoginError):
    """Telegram rejected the login code."""


class CodeExpired(LoginError):
    """The login code expired; a new one has to be requested."""


class PasswordInvalid(LoginError):
    """Telegram rejected the two-step password."""


class PhoneInvalid(LoginError):
    """Telegram rejected the phone number format."""


class ApiInvalid(LoginError):
    """Telegram rejected the API ID / API hash pair."""


class FloodWait(LoginError):
    """Telegram asked to wait before trying again."""

    def __init__(self, seconds: int):
        super().__init__()
        self.seconds = int(seconds)


class ConnectFailed(LoginError):
    """Couldn't reach Telegram's web endpoint (DNS, TLS, WebSocket, timeout)."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind


class TelegramRefused(LoginError):
    """Any other Telegram error. Only the error type name is kept."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind


_BY_NAME = {
    "SessionPasswordNeededError": PasswordNeeded,
    "PhoneCodeInvalidError": CodeInvalid,
    "PhoneCodeEmptyError": CodeInvalid,
    "PhoneCodeExpiredError": CodeExpired,
    "PasswordHashInvalidError": PasswordInvalid,
    "PhoneNumberInvalidError": PhoneInvalid,
    "ApiIdInvalidError": ApiInvalid,
    "ApiIdPublishedFloodError": ApiInvalid,
}


def translate(exc: BaseException) -> LoginError:
    """Map a Telethon (or other) error to a value-free LoginError."""
    if isinstance(exc, LoginError):
        return exc
    secs = _flood_seconds(exc)
    if secs is not None:
        return FloodWait(secs)
    cls = _BY_NAME.get(type(exc).__name__)
    if cls is not None:
        return cls()
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        from .transport_wss import last_connect_error  # noqa: WPS433 - lazy: needs telethon
        return ConnectFailed(getattr(exc, "kind", None) or last_connect_error() or type(exc).__name__)
    return TelegramRefused(type(exc).__name__)


def _default_client_factory(session: str, api_id: int, api_hash: str):
    from .transport_wss import WebTelegramClient, quiet_telethon_logs
    quiet_telethon_logs()
    client = WebTelegramClient(session, api_id, api_hash, receive_updates=False, flood_sleep_threshold=0)
    no_entity_cache(client)
    return client


def no_entity_cache(client):
    """Stop Telethon caching users/chats (names, usernames, phone numbers) in the
    session sqlite file. Sign-in returns your own user (with your phone number),
    so without this the number would land on disk."""
    session = getattr(client, "session", None)
    if session is not None and hasattr(session, "save_entities"):
        session.save_entities = False
    return client


class TelethonBackend:
    """Real sign-in through Telethon. Offline tests inject a fake ``client_factory``."""

    def __init__(self, client_factory=None, session_base=None):
        self._factory = client_factory or _default_client_factory
        self._session_base = session_base  # default: paths.session_base()
        self.client = None
        self._phone = None
        self._hash = None

    @property
    def phone_code_hash(self):
        return self._hash

    def restore(self, phone: str, phone_code_hash: str) -> None:
        """Resume in a new process: phone from the caller, hash from pending state."""
        self._phone, self._hash = phone, phone_code_hash

    def _session_file(self):
        base = self._session_base or paths.session_base()
        return base.with_name(base.name + ".session")

    async def _call(self, name: str, *args, **kwargs):
        if name not in LOGIN_METHODS:  # defensive: login touches nothing else
            raise TelegramRefused("NotALoginCall")
        try:
            return await getattr(self.client, name)(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - translated, values dropped
            err = translate(exc)
        raise err from None

    async def start(self, api_id: int, api_hash: str):
        base = self._session_base or paths.session_base()
        paths.ensure_dir(base.parent)
        self.client = self._factory(str(base), int(api_id), api_hash)
        await self._call("connect")
        paths.tighten(self._session_file())

    async def send_code(self, phone: str):
        sent = await self._call("send_code_request", phone)
        self._phone, self._hash = phone, sent.phone_code_hash

    async def resend_code(self):
        """Ask for a fresh code after CodeExpired (same login call, same phone)."""
        sent = await self._call("send_code_request", self._phone)
        self._hash = sent.phone_code_hash

    async def sign_in_code(self, code: str):
        await self._call("sign_in", phone=self._phone, code=code, phone_code_hash=self._hash)

    async def sign_in_password(self, password: str):
        await self._call("sign_in", password=password)

    async def finish(self):
        self._phone = self._hash = None
        if self.client is not None:
            await self._call("disconnect")
        paths.tighten(self._session_file())

    async def abort(self):
        self._phone = self._hash = None
        if self.client is not None:
            try:
                await self._call("disconnect")
            finally:
                paths.tighten(self._session_file())


def save_credentials(api_id: int, api_hash: str) -> None:
    """Persist only api_id + api_hash (0600) and force the session file to 0600."""
    paths.ensure_dir()
    paths.write_json(paths.credentials_file(), {"api_id": int(api_id), "api_hash": api_hash})
    paths.tighten(paths.session_file())
