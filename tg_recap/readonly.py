"""Read-only wrapper around a Telethon client.

Only the methods in ALLOWED_METHODS can be used, and only the raw TL requests
in ALLOWED_RAW_REQUESTS can be sent with ``client(request)``. Everything else
(send, edit, delete, join, leave, react, mark-read / send_read_acknowledge /
ReadHistoryRequest, ...) raises ReadOnlyViolation before reaching Telegram.
Nothing here marks a chat as read, so chats stay unread in your own apps.

Rate limiting: at most one call every ``min_interval`` seconds.
FLOOD_WAIT: the first one is slept once (if it is not longer than
``max_flood_sleep``); a second one, or an over-long one, stops the run with
FloodStop.
"""
from __future__ import annotations

import asyncio
import time

ALLOWED_METHODS = frozenset({
    "connect",
    "disconnect",
    "is_user_authorized",
    "get_me",
    "get_entity",
    "iter_dialogs",
    "get_dialogs",
    "iter_messages",
    "get_messages",
})

# Raw requests (client(request)) that are allowed, by TL class name. All read-only.
ALLOWED_RAW_REQUESTS = frozenset({
    "GetFullUserRequest",
    "GetFullChatRequest",
    "GetFullChannelRequest",
})

# Never allowed, listed explicitly so the intent is obvious and tested.
DENIED_ALWAYS = frozenset({
    "send_message", "send_file", "forward_messages", "edit_message",
    "delete_messages", "delete_dialog", "send_read_acknowledge", "pin_message",
    "unpin_message", "edit_permissions", "kick_participant", "edit_admin",
    "__call__", "sign_in", "sign_up", "send_code_request", "log_out",
})

_ITER_METHODS = frozenset({"iter_dialogs", "iter_messages"})


class ReadOnlyViolation(PermissionError):
    """A non-allowlisted Telegram call was attempted."""


class FloodStop(RuntimeError):
    """Telegram asked us to slow down twice (or for too long); the run stops."""


def _flood_seconds(exc: BaseException) -> int | None:
    try:
        from telethon.errors import FloodWaitError  # type: ignore
        if isinstance(exc, FloodWaitError):
            return int(exc.seconds)
    except ImportError:  # pragma: no cover - telethon always installed in practice
        pass
    if type(exc).__name__ == "FloodWaitError" and hasattr(exc, "seconds"):
        return int(exc.seconds)
    return None


class ReadOnlyClient:
    def __init__(self, client, *, min_interval: float = 0.5, max_flood_sleep: int = 600,
                 sleep=asyncio.sleep, clock=time.monotonic):
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_min_interval", min_interval)
        object.__setattr__(self, "_max_flood_sleep", max_flood_sleep)
        object.__setattr__(self, "_sleep", sleep)
        object.__setattr__(self, "_clock", clock)
        object.__setattr__(self, "_last_call", None)
        object.__setattr__(self, "_flood_waited", False)

    # --- guards -----------------------------------------------------------
    def __setattr__(self, name, value):
        raise ReadOnlyViolation("ReadOnlyClient attributes are fixed")

    def __getattr__(self, name):
        if name in DENIED_ALWAYS or name not in ALLOWED_METHODS:
            raise ReadOnlyViolation(f"Telegram method '{name}' is not on the read-only allowlist")
        target = getattr(self._client, name)
        if name in _ITER_METHODS:
            return self._wrap_iter(name, target)
        return self._wrap_call(name, target)

    async def __call__(self, request, *args, **kwargs):
        rname = type(request).__name__
        if rname not in ALLOWED_RAW_REQUESTS:
            raise ReadOnlyViolation(f"Raw request '{rname}' is not on the read-only allowlist")
        return await self._guarded(lambda: self._client(request, *args, **kwargs))

    # --- rate limit + flood handling --------------------------------------
    async def _throttle(self):
        now = self._clock()
        last = self._last_call
        if last is not None:
            wait = self._min_interval - (now - last)
            if wait > 0:
                await self._sleep(wait)
        object.__setattr__(self, "_last_call", self._clock())

    async def _handle_flood(self, seconds: int):
        if self._flood_waited:
            raise FloodStop(
                f"Telegram asked to wait again ({seconds}s) after one wait already. "
                "This run stopped to protect your account; the next scheduled run will try again.")
        if seconds > self._max_flood_sleep:
            raise FloodStop(
                f"Telegram asked to wait {seconds}s, longer than the {self._max_flood_sleep}s limit. "
                "This run stopped; the next scheduled run will try again.")
        object.__setattr__(self, "_flood_waited", True)
        await self._sleep(seconds)

    async def _guarded(self, make_call):
        while True:
            await self._throttle()
            try:
                result = make_call()
                if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                    result = await result
                return result
            except Exception as exc:  # noqa: BLE001
                secs = _flood_seconds(exc)
                if secs is None:
                    raise
                await self._handle_flood(secs)

    def _wrap_call(self, name, target):
        async def call(*args, **kwargs):
            return await self._guarded(lambda: target(*args, **kwargs))
        call.__name__ = name
        return call

    def _wrap_iter(self, name, target):
        """Buffer the whole iteration so a FLOOD_WAIT retry restarts cleanly."""
        ro = self

        async def collect_all(args, kwargs):
            async def run():
                return [item async for item in target(*args, **kwargs)]
            return await ro._guarded(run)

        def iterator(*args, **kwargs):
            async def gen():
                for item in await collect_all(args, kwargs):
                    yield item
            return gen()
        iterator.__name__ = name
        return iterator
