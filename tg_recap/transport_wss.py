"""Connect to Telegram over its official web endpoints: WebSocket over TLS.

Telegram Web (and GramJS with useWSS) reach Telegram at
wss://<name>.web.telegram.org:443/apiws with WebSocket subprotocol "binary",
carrying obfuscated MTProto ("obfuscated2" with the abridged codec). That goes
over normal HTTPS egress, so it works where raw TCP to the data-center IPs
doesn't.

What this module does:
  - ConnectionWss: a Telethon Connection that reuses Telethon's own
    ConnectionTcpObfuscated framing (ObfuscatedIO + AbridgedPacketCodec) and only
    swaps the byte stream: a WebSocket instead of a TCP socket.
  - WebTelegramClient: a TelegramClient whose data centers resolve by DC id to
    the hardcoded web hostnames below. IP addresses from help.getConfig or a
    migrate error are never used (it never even calls help.getConfig). A fresh
    session starts on venus (DC2); a session saved by an older version keeps its
    DC id and auth key, and only its stored address is rewritten to the web host.
  - No proxy of any kind. The WebSocket library's environment-proxy detection is
    switched off explicitly.

Telethon internals relied on (1.45.0, pinned): Connection._connect / _reader /
_writer / _ip / _dc_id, ObfuscatedConnection, ObfuscatedIO, AbridgedPacketCodec,
TelegramClient._get_dc and session.set_dc. tests/test_transport_wss.py checks
each of them offline.
"""
from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient
from telethon.network.connection.tcpobfuscated import ConnectionTcpObfuscated

WEB_HOSTS = {
    1: "pluto.web.telegram.org",
    2: "venus.web.telegram.org",
    3: "aurora.web.telegram.org",
    4: "vesta.web.telegram.org",
    5: "flora.web.telegram.org",
}
DEFAULT_DC = 2
PORT = 443
PATH = "/apiws"
SUBPROTOCOL = "binary"
CONNECT_TIMEOUT = 15        # seconds per attempt (DNS + TLS + WebSocket handshake)
CONNECT_RETRIES = 1         # Telethon retries this many times: 2 attempts per connect, total
RETRY_DELAY = 2
MAX_MESSAGE = 16 * 1024 * 1024

_last_error: list[str] = []


class UnknownDc(ConnectionError):
    """A DC id with no web endpoint. Never falls back to an IP."""


class WssConnectError(ConnectionError):
    """DNS, TLS, WebSocket handshake or timeout. Carries only the error type name."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def web_host(dc_id) -> str:
    try:
        return WEB_HOSTS[int(dc_id)]
    except (KeyError, TypeError, ValueError):
        raise UnknownDc("no Telegram web endpoint for this data center") from None


def url_for(dc_id) -> str:
    return f"wss://{web_host(dc_id)}:{PORT}{PATH}"


def last_connect_error() -> str | None:
    return _last_error[-1] if _last_error else None


async def _open_websocket(url: str, timeout: float):
    from websockets.asyncio.client import connect
    return await connect(url, subprotocols=[SUBPROTOCOL], proxy=None, compression=None,
                         open_timeout=timeout, ping_interval=None, max_size=MAX_MESSAGE,
                         user_agent_header=None)


class _WsReader:
    """StreamReader-like: readexactly(n) over WebSocket binary messages."""

    def __init__(self, ws):
        self._ws = ws
        self._buf = bytearray()

    async def readexactly(self, n: int) -> bytes:
        while len(self._buf) < n:
            try:
                msg = await self._ws.recv()
            except Exception as exc:  # noqa: BLE001 - closed / reset: Telethon expects IOError
                partial = bytes(self._buf)
                self._buf.clear()
                raise asyncio.IncompleteReadError(partial, n) from exc
            self._buf += msg if isinstance(msg, (bytes, bytearray)) else msg.encode()
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


class _WsWriter:
    """StreamWriter-like: write() buffers, drain() sends one binary message."""

    def __init__(self, ws):
        self._ws = ws
        self._buf = bytearray()

    def write(self, data: bytes) -> None:
        self._buf += data

    async def drain(self) -> None:
        if not self._buf:
            return
        data = bytes(self._buf)
        self._buf.clear()
        try:
            await self._ws.send(data)
        except Exception as exc:  # noqa: BLE001
            raise ConnectionResetError(type(exc).__name__) from None

    def close(self) -> None:
        pass  # the WebSocket closes in wait_closed()

    async def wait_closed(self) -> None:
        try:
            await self._ws.close()
        except Exception:  # noqa: BLE001 - closing never raises
            pass


class ConnectionWss(ConnectionTcpObfuscated):
    """Obfuscated MTProto (abridged) over wss://<dc web host>:443/apiws."""

    open_websocket = staticmethod(_open_websocket)  # tests swap in a fake

    async def _connect(self, timeout=None, ssl=None):
        url = url_for(self._dc_id)  # by DC id only; self._ip is never dialed
        try:
            ws = await asyncio.wait_for(self.open_websocket(url, timeout or CONNECT_TIMEOUT),
                                        timeout=(timeout or CONNECT_TIMEOUT) + 5)
        except Exception as exc:  # noqa: BLE001 - name only, never the message
            _last_error.append(type(exc).__name__)
            del _last_error[:-5]
            raise WssConnectError(type(exc).__name__) from None
        self._reader = _WsReader(ws)
        self._writer = _WsWriter(ws)
        self._codec = self.packet_codec(self)
        self._init_conn()
        await self._writer.drain()

    def __str__(self):
        try:
            return f"{web_host(self._dc_id)}:{PORT}/Wss"
        except UnknownDc:
            return "unknown-dc/Wss"


class _WebDc:
    def __init__(self, dc_id: int):
        self.id = int(dc_id)
        self.ip_address = web_host(dc_id)
        self.port = PORT


class WebTelegramClient(TelegramClient):
    """TelegramClient that only ever talks to Telegram's web endpoints."""

    def __init__(self, session, api_id, api_hash, **kwargs):
        for banned in ("proxy", "connection", "use_ipv6", "local_addr"):
            if kwargs.pop(banned, None) not in (None, False):
                raise ValueError(f"{banned} is not configurable for the web transport")
        kwargs.setdefault("connection_retries", CONNECT_RETRIES)
        kwargs.setdefault("retry_delay", RETRY_DELAY)
        kwargs.setdefault("timeout", CONNECT_TIMEOUT)
        kwargs.setdefault("request_retries", 2)
        kwargs.setdefault("auto_reconnect", False)
        super().__init__(session, api_id, api_hash, connection=ConnectionWss, use_ipv6=False, **kwargs)
        point_session_at_web(self.session)

    async def _get_dc(self, dc_id, cdn=False):
        """Resolve a DC by id to its web host. Never calls help.getConfig and never
        uses an IP (the getDC(web=true) behaviour of Telegram Web / GramJS)."""
        if cdn:
            raise UnknownDc("CDN data centers aren't used by this read-only recap")
        return _WebDc(dc_id)


def point_session_at_web(session) -> None:
    """Store the web host for the session's DC (DC2 for a new session).
    Telethon's SQLite set_dc keeps the auth key; only the address changes."""
    dc_id = session.dc_id or DEFAULT_DC
    host = web_host(dc_id)
    if session.server_address != host or session.port != PORT or session.dc_id != dc_id:
        session.set_dc(dc_id, host, PORT)
        session.save()


def quiet_telethon_logs() -> None:
    """Telethon logs reconnect warnings with addresses and tracebacks; keep stderr to our one line."""
    logging.getLogger("telethon").setLevel(logging.CRITICAL)
