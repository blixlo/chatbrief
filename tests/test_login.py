import os
import threading
import urllib.error
import urllib.parse
import urllib.request

import pytest

from tg_recap import login_web, paths
from tg_recap.login_web import PasswordNeeded

PHONE = "+15550001234"   # fake values used only in this offline test
CODE = "24680"
PASSWORD = "fake-two-step-pw-77"
API_ID = "1234567"
API_HASH = "test-api-hash-not-real-000"


class FakeBackend:
    def __init__(self, need_password=True):
        self.need_password = need_password
        self.seen = {}

    async def start(self, api_id, api_hash):
        self.seen["api"] = (api_id, api_hash)

    async def send_code(self, phone):
        self.seen["phone"] = phone

    async def sign_in_code(self, code):
        self.seen["code"] = code
        if self.need_password:
            raise PasswordNeeded()

    async def sign_in_password(self, pw):
        self.seen["password"] = pw

    async def finish(self):
        # simulate Telethon writing its session file (contents are opaque auth data)
        p = paths.session_file()
        p.write_bytes(b"SQLite format 3\x00fake-session")
        self.seen.clear()

    async def abort(self):
        self.seen.clear()


def start(backend):
    server, flow = login_web.make_server(backend, port=0)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, flow, f"http://127.0.0.1:{port}/", t


def post(url, data):
    body = urllib.parse.urlencode(data).encode()
    return urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=10).read().decode()


def all_bytes(root):
    out = b""
    for dirpath, _, files in os.walk(root):
        for f in files:
            out += open(os.path.join(dirpath, f), "rb").read()
    return out


def test_full_login_never_persists_phone_code_password(tg_home, capsys):
    backend = FakeBackend(need_password=True)
    server, flow, url, t = start(backend)
    try:
        page = urllib.request.urlopen(url, timeout=10).read().decode()
        assert "my.telegram.org" in page and "core.telegram.org/api/obtaining_api_id" in page
        assert "Settings &gt; Devices" in page and "never saved or logged" in page
        tok = flow.token
        assert "phone number" in post(url, {"token": tok, "api_id": API_ID, "api_hash": API_HASH}).lower()
        assert "login code" in post(url, {"token": tok, "phone": PHONE}).lower()
        assert "two-step password" in post(url, {"token": tok, "code": CODE}).lower()
        assert "Signed in" in post(url, {"token": tok, "password": PASSWORD})
        t.join(timeout=5)
    finally:
        server.server_close()
        flow.close()

    files = sorted(p.name for p in tg_home.rglob("*") if p.is_file())
    assert files == ["credentials.json", "settings.json", "tg_recap.session"]  # settings: consent record only
    blob = all_bytes(tg_home)
    for secret in (PHONE, PHONE.lstrip("+"), CODE, PASSWORD):
        assert secret.encode() not in blob
    assert API_HASH.encode() in blob  # the only kept secrets: api id/hash + session
    captured = capsys.readouterr()
    for secret in (PHONE, CODE, PASSWORD, API_HASH):
        assert secret not in captured.out + captured.err
    assert flow._api is None and backend.seen == {}
    assert oct(os.stat(tg_home).st_mode & 0o777) == "0o700"
    for f in tg_home.iterdir():
        assert oct(os.stat(f).st_mode & 0o777) == "0o600"


def test_server_binds_localhost_only_and_rejects_bad_token_and_host(tg_home):
    server, flow, url, t = start(FakeBackend())
    try:
        assert server.server_address[0] == "127.0.0.1"
        with pytest.raises(urllib.error.HTTPError) as e:
            post(url, {"token": "wrong", "api_id": API_ID, "api_hash": API_HASH})
        assert e.value.code == 403
        req = urllib.request.Request(url, headers={"Host": "evil.example:80"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req, timeout=10)
        assert e.value.code == 403
        assert flow.step == "api"
    finally:
        server.shutdown()
        server.server_close()
        flow.close()
    assert not paths.credentials_file().exists()


def test_bad_api_values_rejected_without_writing(tg_home):
    server, flow, url, t = start(FakeBackend())
    try:
        page = post(url, {"token": flow.token, "api_id": "abc", "api_hash": "short"})
        assert "look right" in page
    finally:
        server.shutdown()
        server.server_close()
        flow.close()
    assert not paths.credentials_file().exists()
