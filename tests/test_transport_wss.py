"""WebSocket-over-TLS transport, fully offline (fake WebSocket, no network at all)."""
import asyncio
import collections
import io
import logging
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

import pytest

pytest.importorskip("telethon")
pytest.importorskip("websockets")

from telethon.crypto import AESModeCTR  # noqa: E402
from telethon.crypto.authkey import AuthKey  # noqa: E402
from telethon.network.connection.tcpobfuscated import ConnectionTcpObfuscated  # noqa: E402
from telethon.sessions import SQLiteSession  # noqa: E402

from tg_recap import login_cards, paths, runner, transport_wss as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["pluto", "venus", "aurora", "vesta", "flora"]
LOGGERS = collections.defaultdict(lambda: logging.getLogger("test.wss"))
API_ID, API_HASH = 7654321, "sentinel-wss-api-hash-00001"


@pytest.mark.parametrize("dc", [1, 2, 3, 4, 5])
def test_url_host_port_path_per_dc(dc):
    u = urlparse(W.url_for(dc))
    assert (u.scheme, u.hostname, u.port, u.path) == ("wss", f"{NAMES[dc - 1]}.web.telegram.org", 443, "/apiws")
    assert W.web_host(dc) == u.hostname


@pytest.mark.parametrize("bad", [0, 6, 99, None, "x"])
def test_unknown_dc_never_falls_back(bad):
    with pytest.raises(W.UnknownDc):
        W.url_for(bad)


def test_open_websocket_uses_binary_subprotocol_and_no_proxy(monkeypatch):
    import websockets.asyncio.client as wsc
    seen = {}

    async def fake_connect(url, **kw):
        seen["url"], seen["kw"] = url, kw
        return "ws"
    monkeypatch.setattr(wsc, "connect", fake_connect)
    assert asyncio.run(W._open_websocket(W.url_for(2), 3)) == "ws"
    assert seen["url"] == "wss://venus.web.telegram.org:443/apiws"
    assert seen["kw"]["subprotocols"] == ["binary"]
    assert seen["kw"]["proxy"] is None and seen["kw"]["compression"] is None


class FakeWs:
    """Server side of obfuscated2: derives keys from the client's 64-byte init."""

    def __init__(self):
        self.sent = []
        self.inbox = asyncio.Queue()
        self.closed = False
        self.dec = self.enc = None

    async def send(self, data):
        assert isinstance(data, bytes)
        self.sent.append(data)
        if self.dec is None:
            head = data[:64]
            self.dec = AESModeCTR(bytes(head[8:40]), bytes(head[40:56]))
            rev = head[55:7:-1]
            self.enc = AESModeCTR(bytes(rev[:32]), bytes(rev[32:48]))
            self.plain_head = self.dec.encrypt(bytes(head))

    async def recv(self):
        item = await self.inbox.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self):
        self.closed = True

    def reply(self, payload: bytes):
        self.inbox.put_nowait(self.enc.encrypt(bytes([len(payload) >> 2]) + payload))


def _conn(ip="149.154.167.51", dc=2):
    return W.ConnectionWss(ip, 443, dc, loggers=LOGGERS)


def test_obfuscated_handshake_and_round_trip():
    async def go():
        ws, urls = FakeWs(), []

        async def fake_open(url, timeout):
            urls.append(url)
            return ws
        conn = _conn(ip="149.154.167.91", dc=4)
        conn.open_websocket = fake_open
        await conn.connect(timeout=1)
        assert urls == ["wss://vesta.web.telegram.org:443/apiws"]  # by DC id; the IP is never dialed
        head = ws.sent[0]
        assert len(head) == 64 and head[0] != 0xEF
        assert head[:4] not in (b"PVrG", b"GET ", b"POST", b"\xee\xee\xee\xee") and head[4:8] != b"\0\0\0\0"
        assert ws.plain_head[56:60] == b"\xef\xef\xef\xef"  # the 0xefefefef obfuscated (abridged) tag in place
        payload = bytes(range(16)) * 2
        await conn.send(payload)
        for _ in range(50):
            if len(ws.sent) > 1:
                break
            await asyncio.sleep(0.01)
        body = ws.dec.encrypt(ws.sent[1])
        assert body[0] == len(payload) >> 2 and body[1:] == payload
        ws.reply(b"\xaa" * 24)
        assert await asyncio.wait_for(conn.recv(), 2) == b"\xaa" * 24
        await conn.disconnect()
        assert ws.closed
    asyncio.run(go())


def test_reuses_telethon_obfuscated_framing():
    assert issubclass(W.ConnectionWss, ConnectionTcpObfuscated)
    assert W.ConnectionWss.packet_codec is ConnectionTcpObfuscated.packet_codec
    assert W.ConnectionWss.obfuscated_io is ConnectionTcpObfuscated.obfuscated_io


def test_connect_errors_become_typed_connection_errors():
    async def boom(url, timeout):
        raise socket.gaierror("resolver said secret-detail")
    conn = _conn()
    conn.open_websocket = boom
    with pytest.raises(W.WssConnectError) as e:
        asyncio.run(conn.connect(timeout=1))
    assert e.value.kind == "gaierror" and isinstance(e.value, ConnectionError)
    assert "secret-detail" not in str(e.value) and e.value.__cause__ is None
    assert W.last_connect_error() == "gaierror"


def _client(tg_home, dc=None, addr=None, key=None):
    paths.ensure_dir()
    if dc is not None:
        s = SQLiteSession(str(paths.session_base()))
        s.set_dc(dc, addr, 443)
        if key:
            s.auth_key = AuthKey(key)
        s.save()
        s.close()
    return W.WebTelegramClient(str(paths.session_base()), API_ID, API_HASH, receive_updates=False)


def test_new_session_starts_on_venus(tg_home):
    c = _client(tg_home)
    assert (c.session.dc_id, c.session.server_address, c.session.port) == (2, "venus.web.telegram.org", 443)
    assert c._connection is W.ConnectionWss and c._proxy is None
    c.session.close()


def test_existing_ip_session_keeps_auth_key_and_dc(tg_home):
    key = bytes(range(256))
    c = _client(tg_home, dc=4, addr="149.154.167.91", key=key)
    assert (c.session.dc_id, c.session.server_address) == (4, "vesta.web.telegram.org")
    assert c.session.auth_key.key == key
    c.session.close()
    again = SQLiteSession(str(paths.session_base()))  # persisted, still loadable by plain Telethon
    assert (again.dc_id, again.server_address, again.port, again.auth_key.key) == (4, "vesta.web.telegram.org",
                                                                                   443, key)
    again.close()


def test_migration_uses_web_host_by_dc_id_never_an_ip(tg_home, monkeypatch):
    c = _client(tg_home)

    async def must_not_call(*a, **k):
        raise AssertionError("help.getConfig (or any request) must not be sent")
    monkeypatch.setattr(type(c), "__call__", must_not_call)
    dc = asyncio.run(c._get_dc(5))
    assert (dc.id, dc.ip_address, dc.port) == (5, "flora.web.telegram.org", 443)

    async def noop(*a, **k):
        return None
    monkeypatch.setattr(c, "_disconnect", noop)
    monkeypatch.setattr(c, "connect", noop)
    asyncio.run(c._switch_dc(3))  # Telethon's own migrate path
    assert (c.session.dc_id, c.session.server_address, c.session.port) == (3, "aurora.web.telegram.org", 443)
    assert not re.search(r"\d+\.\d+\.\d+\.\d+", c.session.server_address)
    with pytest.raises(W.UnknownDc):
        asyncio.run(c._get_dc(2, cdn=True))
    c.session.close()


def test_client_refuses_proxy_or_other_transport(tg_home):
    for kw in ({"proxy": ("socks5", "127.0.0.1", 1080)}, {"connection": object}, {"use_ipv6": True}):
        with pytest.raises(ValueError):
            W.WebTelegramClient(str(tg_home / "x"), API_ID, API_HASH, **kw)


def test_no_proxy_anywhere_in_code_or_requirements():
    banned = re.compile(r"socks|TG_RECAP_PROXY|ConnectionHttp|MTProxy|tcpmtproxy", re.I)
    for f in sorted((ROOT / "tg_recap").glob("*.py")) + [ROOT / "requirements.txt", ROOT / "pyproject.toml"]:
        text = f.read_text()
        assert not banned.search(text), f.name
        for line in text.splitlines():
            if "proxy" in line.lower():
                assert f.name == "transport_wss.py", f"{f.name}: {line.strip()}"
                assert re.search(r"proxy=None|No proxy|\"proxy\"", line), line


def _fail_connect(monkeypatch):
    attempts = []

    async def boom(url, timeout):
        attempts.append(url)
        raise socket.gaierror(f"lookup failed for {API_HASH}")  # a would-be leak in the message
    monkeypatch.setattr(W.ConnectionWss, "open_websocket", staticmethod(boom))
    monkeypatch.setattr(W, "RETRY_DELAY", 0)
    return attempts


def test_run_connect_failure_exits_8_cleanly(tg_home, monkeypatch, capsys):
    attempts = _fail_connect(monkeypatch)
    paths.write_json(paths.credentials_file(), {"api_id": API_ID, "api_hash": API_HASH})
    _client(tg_home, dc=2, addr="149.154.167.51", key=bytes(256)).session.close()
    out, err = io.StringIO(), io.StringIO()
    rc = runner.run(now=None, out=out, err=err)
    assert rc == runner.EXIT_CONNECT == 8
    lines = err.getvalue().strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("CONNECT_FAILED:") and "(gaierror)" in lines[0]
    cap = capsys.readouterr()
    blob = err.getvalue() + out.getvalue() + cap.out + cap.err
    assert "Traceback" not in blob and API_HASH not in blob and out.getvalue() == ""
    assert 1 <= len(attempts) <= 2 and set(attempts) == {"wss://venus.web.telegram.org:443/apiws"}


def test_card_send_code_connect_failure_exits_8(tg_home, monkeypatch, capsys):
    _fail_connect(monkeypatch)
    env = {"TG_RECAP_API_ID": str(API_ID), "TG_RECAP_API_HASH": API_HASH, "TG_RECAP_PHONE": "+15550007777"}
    assert login_cards.login("save-api", env=env) == 0
    assert login_cards.login("send-code", env=env) == login_cards.EXIT_CONNECT == 8
    assert not paths.pending_dir().exists()
    cap = capsys.readouterr()
    assert "CONNECT_FAILED" in cap.err and "Traceback" not in cap.err
    for secret in (API_HASH, "15550007777"):
        assert secret not in cap.out + cap.err


def test_unknown_dc_session_exits_3(tg_home, capsys):
    paths.write_json(paths.credentials_file(), {"api_id": API_ID, "api_hash": API_HASH})
    s = SQLiteSession(str(paths.session_base()))
    s.set_dc(9, "149.154.1.1", 443)
    s.save()
    s.close()
    err = io.StringIO()
    assert runner.run(out=io.StringIO(), err=err) == runner.EXIT_REVOKED
    assert err.getvalue().startswith("SESSION_REVOKED") and "data center" in err.getvalue()


def test_auth_key_not_found_exits_3(tg_home):
    from telethon.errors.common import AuthKeyNotFound

    class Dead:
        async def connect(self):
            raise AuthKeyNotFound()

        async def disconnect(self):
            return None
    err = io.StringIO()
    assert runner.run(lambda: Dead(), out=io.StringIO(), err=err) == runner.EXIT_REVOKED
    assert err.getvalue().startswith("SESSION_REVOKED")
