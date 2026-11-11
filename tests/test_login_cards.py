"""Card sign-in (`login --cards <step>`), fully offline.

Every step is a separate "process": a fresh CardLogin, a fresh fake client and
nothing carried in memory, so the only state between steps is what is on disk.
FakeTelegram plays the server side (it is the only thing that "knows" the code),
and it checks that each resumed client presents the auth key saved on disk.

Sentinel values are fake. The phone/code/password sentinels must appear nowhere:
not in stdout, stderr, logs (DEBUG), or any file, including pending/ and sqlite.
The API ID and hash may appear only in credentials.json.
"""
import logging
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest

from tg_recap import login_backend, login_cards, paths
from tg_recap.lock import SessionLock
from login_fakes import (FloodWaitError, PasswordHashInvalidError, PhoneCodeExpiredError,  # noqa: E402
                         PhoneCodeInvalidError, PhoneNumberInvalidError, SessionPasswordNeededError)

API_ID = "918273645"
API_HASH = "sentinel-cards-api-hash-0000"
PHONE = "+15550004321"
CODE = "86420"
PASSWORD = "sentinel-cards-2fa-pw-93"
ROOT = Path(__file__).resolve().parents[1]


class Sent:
    def __init__(self, h):
        self.phone_code_hash = h


class FakeTelegram:
    """Server side. Holds the real code; clients only hold what's on disk."""

    def __init__(self, need_password=False, fail=None):
        self.need_password = need_password
        self.fail = {k: list(v) for k, v in (fail or {}).items()}
        self.code_for = {}       # auth key -> (phone, hash)
        self.awaiting_pw = set()
        self.authorized = set()
        self.clients = []

    def _maybe_fail(self, key):
        q = self.fail.get(key) or []
        if q:
            raise q.pop(0)


class FakeClient:
    def __init__(self, session, api_id, api_hash, server):
        assert int(api_id) == int(API_ID) and api_hash == API_HASH
        self.path = Path(session + ".session")
        self.server = server
        self.key = None
        self.calls = []
        server.clients.append(self)

    async def connect(self):
        self.calls.append("connect")
        if self.path.exists():
            self.key = self.path.read_bytes().split(b"|")[0]   # resume purely from disk
        else:
            self.key = secrets.token_hex(16).encode()
            self.path.write_bytes(self.key + b"|new")
            os.chmod(self.path, 0o644)  # loose on purpose; code must tighten

    async def send_code_request(self, phone):
        self.calls.append("send_code_request")
        self.server._maybe_fail("send_code")
        h = secrets.token_hex(8)
        self.server.code_for[self.key] = (phone, h)
        return Sent(h)

    async def sign_in(self, phone=None, code=None, phone_code_hash=None, password=None):
        self.calls.append("sign_in")
        s = self.server
        if password is not None:
            assert self.key in s.awaiting_pw, "password step must resume the same session"
            s._maybe_fail("password")
            assert password == PASSWORD
        else:
            assert (phone, phone_code_hash) == s.code_for[self.key], "sign-in must resume from disk"
            s._maybe_fail("code")
            assert code == CODE
            if s.need_password:
                s.awaiting_pw.add(self.key)
                raise SessionPasswordNeededError(None)
        s.authorized.add(self.key)
        self.path.write_bytes(self.key + b"|authorized")
        return object()

    async def disconnect(self):
        self.calls.append("disconnect")


@pytest.fixture(autouse=True)
def _debug_logs(caplog):
    caplog.set_level(logging.DEBUG)


def step(name, server, **env):
    return login_cards.login(name, env=env,
                             client_factory=lambda s, a, h: FakeClient(s, a, h, server))


def save_api(server):
    return step("save-api", server, TG_RECAP_API_ID=API_ID, TG_RECAP_API_HASH=API_HASH)


def all_files(root):
    return {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} if root.exists() else {}


def check_no_leaks(capsys, caplog, tg_home):
    cap = capsys.readouterr()
    text = cap.out + cap.err + caplog.text
    for secret in (PHONE, PHONE.lstrip("+"), CODE, PASSWORD, API_HASH, API_ID):
        assert secret not in text, "value leaked to output/logs"
    assert "Traceback" not in text
    for p, data in all_files(tg_home).items():
        for secret in (PHONE, PHONE.lstrip("+"), CODE, PASSWORD):
            assert secret.encode() not in data, f"value written to {p.name}"
        if p != paths.credentials_file():
            assert API_HASH.encode() not in data and API_ID.encode() not in data, p.name
    return cap


def assert_modes(tg_home):
    assert oct(os.stat(tg_home).st_mode & 0o777) == "0o700"
    for p in tg_home.rglob("*"):
        want = "0o700" if p.is_dir() else "0o600"
        assert oct(os.stat(p).st_mode & 0o777) == want, p.name


def test_full_resume_without_2fa(tg_home, capsys, caplog):
    tg = FakeTelegram()
    assert save_api(tg) == 0
    assert paths.read_json(paths.credentials_file()) == {"api_id": int(API_ID), "api_hash": API_HASH}
    assert step("send-code", tg, TG_RECAP_PHONE=PHONE) == 0
    assert paths.pending_state_file().exists()
    assert_modes(tg_home)
    # pending state holds the hash and stage only, never the phone
    assert set(paths.read_json(paths.pending_state_file())) == {"phone_code_hash", "stage", "created_at"}
    assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == 0
    assert not paths.pending_dir().exists()
    final = paths.session_file()
    assert final.read_bytes().endswith(b"|authorized")
    assert final.read_bytes().split(b"|")[0] in tg.authorized
    assert len(tg.clients) == 2 and all(c.calls[-1] == "disconnect" for c in tg.clients)
    for c in tg.clients:
        assert set(c.calls) <= login_backend.LOGIN_METHODS
    assert_modes(tg_home)
    cap = check_no_leaks(capsys, caplog, tg_home)
    assert "Signed in" in cap.out


def test_full_resume_with_2fa(tg_home, capsys, caplog):
    tg = FakeTelegram(need_password=True)
    assert save_api(tg) == 0
    assert step("send-code", tg, TG_RECAP_PHONE=PHONE) == 0
    rc = step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE)
    assert rc == login_cards.EXIT_NEED_2FA == 10
    assert paths.read_json(paths.pending_state_file())["stage"] == "password"
    assert not paths.session_file().exists()
    assert_modes(tg_home)
    assert step("password", tg, TG_RECAP_2FA=PASSWORD) == 0
    assert not paths.pending_dir().exists()
    assert paths.session_file().read_bytes().endswith(b"|authorized")
    assert len(tg.clients) == 3
    assert_modes(tg_home)
    cap = check_no_leaks(capsys, caplog, tg_home)
    assert "NEED_2FA" in cap.err and "TG_RECAP_2FA" in cap.err


def test_wrong_code_keeps_pending_and_asks_again(tg_home, capsys, caplog):
    tg = FakeTelegram(fail={"code": [PhoneCodeInvalidError(None)]})
    save_api(tg)
    step("send-code", tg, TG_RECAP_PHONE=PHONE)
    assert step("sign-in", tg, TG_RECAP_CODE="11111", TG_RECAP_PHONE=PHONE) == login_cards.EXIT_CODE_INVALID == 11
    assert paths.pending_state_file().exists()
    assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == 0
    cap = check_no_leaks(capsys, caplog, tg_home)
    assert "CODE_INVALID" in cap.err and "11111" not in cap.err


def test_wrong_password_keeps_pending_and_asks_again(tg_home, capsys, caplog):
    tg = FakeTelegram(need_password=True, fail={"password": [PasswordHashInvalidError(None)]})
    save_api(tg)
    step("send-code", tg, TG_RECAP_PHONE=PHONE)
    assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == 10
    assert step("password", tg, TG_RECAP_2FA="wrong-sentinel-pw") == login_cards.EXIT_PASSWORD_INVALID == 12
    assert paths.read_json(paths.pending_state_file())["stage"] == "password"
    assert step("password", tg, TG_RECAP_2FA=PASSWORD) == 0
    cap = check_no_leaks(capsys, caplog, tg_home)
    assert "wrong-sentinel-pw" not in cap.err


def test_expired_code_clears_pending_and_restarts(tg_home, capsys, caplog):
    tg = FakeTelegram(fail={"code": [PhoneCodeExpiredError(None)]})
    save_api(tg)
    step("send-code", tg, TG_RECAP_PHONE=PHONE)
    assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == login_cards.EXIT_CODE_EXPIRED == 13
    assert not paths.pending_dir().exists()
    assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == login_cards.EXIT_NO_PENDING == 17
    assert step("send-code", tg, TG_RECAP_PHONE=PHONE) == 0
    assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == 0
    cap = check_no_leaks(capsys, caplog, tg_home)
    assert "CODE_EXPIRED" in cap.err and "send-code" in cap.err


@pytest.mark.parametrize("where", ["send_code", "code"])
def test_flood_exits_4_and_clears_pending(tg_home, capsys, caplog, where):
    tg = FakeTelegram(fail={where: [FloodWaitError(900)]})
    save_api(tg)
    if where == "send_code":
        assert step("send-code", tg, TG_RECAP_PHONE=PHONE) == 4
    else:
        assert step("send-code", tg, TG_RECAP_PHONE=PHONE) == 0
        assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == 4
    assert not paths.pending_dir().exists() and not paths.session_file().exists()
    cap = check_no_leaks(capsys, caplog, tg_home)
    assert "FLOOD_STOP" in cap.err and "900s" in cap.err


def test_bad_phone_exits_14(tg_home, capsys, caplog):
    tg = FakeTelegram(fail={"send_code": [PhoneNumberInvalidError(None)]})
    save_api(tg)
    assert step("send-code", tg, TG_RECAP_PHONE="12") == login_cards.EXIT_PHONE_INVALID == 14
    assert not paths.pending_dir().exists()
    assert step("send-code", tg, TG_RECAP_PHONE=PHONE) == 0
    check_no_leaks(capsys, caplog, tg_home)


@pytest.mark.parametrize("env, var", [
    ({"TG_RECAP_API_HASH": API_HASH}, "TG_RECAP_API_ID"),
    ({"TG_RECAP_API_ID": API_ID, "TG_RECAP_API_HASH": "  "}, "TG_RECAP_API_HASH"),
])
def test_missing_env_names_only_the_var(tg_home, capsys, caplog, env, var):
    tg = FakeTelegram()
    assert step("save-api", tg, **env) == login_cards.EXIT_MISSING_ENV == 16
    assert not paths.credentials_file().exists()
    cap = check_no_leaks(capsys, caplog, tg_home)
    assert f"MISSING_ENV: {var} " in cap.err


def test_missing_env_at_each_step(tg_home, capsys, caplog):
    tg = FakeTelegram(need_password=True)
    save_api(tg)
    assert step("send-code", tg) == 16
    step("send-code", tg, TG_RECAP_PHONE=PHONE)
    assert step("sign-in", tg, TG_RECAP_PHONE=PHONE) == 16
    assert step("sign-in", tg, TG_RECAP_CODE=CODE) == 16  # phone is read from its card, not disk
    assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == 10
    assert step("password", tg) == 16
    cap = check_no_leaks(capsys, caplog, tg_home)
    for var in ("TG_RECAP_PHONE", "TG_RECAP_CODE", "TG_RECAP_2FA"):
        assert f"MISSING_ENV: {var} " in cap.err


def test_bad_api_values_and_not_set_up(tg_home, capsys, caplog):
    tg = FakeTelegram()
    assert step("send-code", tg, TG_RECAP_PHONE=PHONE) == login_cards.EXIT_NOT_SET_UP == 5
    assert step("save-api", tg, TG_RECAP_API_ID="12ab", TG_RECAP_API_HASH=API_HASH) == 15
    assert step("save-api", tg, TG_RECAP_API_ID=API_ID, TG_RECAP_API_HASH="short") == 15
    assert not paths.credentials_file().exists() and not tg.clients
    check_no_leaks(capsys, caplog, tg_home)


def test_password_without_pending_2fa(tg_home, capsys, caplog):
    tg = FakeTelegram()
    save_api(tg)
    assert step("password", tg, TG_RECAP_2FA=PASSWORD) == 17
    step("send-code", tg, TG_RECAP_PHONE=PHONE)
    assert step("password", tg, TG_RECAP_2FA=PASSWORD) == 17  # stage is still "code"
    check_no_leaks(capsys, caplog, tg_home)


def test_reset_wipes_pending_only(tg_home, capsys, caplog):
    tg = FakeTelegram()
    save_api(tg)
    paths.write_private(paths.session_file(), "existing-session\n")
    step("send-code", tg, TG_RECAP_PHONE=PHONE)
    assert paths.pending_dir().exists()
    assert step("reset", tg) == 0
    assert not paths.pending_dir().exists()
    assert paths.credentials_file().exists() and paths.session_file().exists()
    assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == 17
    check_no_leaks(capsys, caplog, tg_home)


def test_lock_held_exits_2_without_touching_anything(tg_home, capsys, caplog):
    tg = FakeTelegram()
    holder = SessionLock().acquire()
    try:
        assert save_api(tg) == 2
        assert step("send-code", tg, TG_RECAP_PHONE=PHONE) == 2
        assert step("reset", tg) == 2
    finally:
        holder.release()
    assert not paths.credentials_file().exists() and not tg.clients
    assert "LOCK_HELD" in check_no_leaks(capsys, caplog, tg_home).err


def test_unexpected_error_is_kind_only(tg_home, capsys, caplog):
    class Boom(Exception):
        pass
    tg = FakeTelegram(fail={"code": [Boom(f"{PHONE} {CODE}")]})
    save_api(tg)
    step("send-code", tg, TG_RECAP_PHONE=PHONE)
    assert step("sign-in", tg, TG_RECAP_CODE=CODE, TG_RECAP_PHONE=PHONE) == 1
    assert "(Boom)" in check_no_leaks(capsys, caplog, tg_home).err


def test_cli_cards_missing_env_in_a_real_process(tg_home):
    pytest.importorskip("telethon")
    env = {k: v for k, v in os.environ.items() if not k.startswith("TG_RECAP_") or k == "TG_RECAP_HOME"}
    env["PYTHONPATH"] = str(ROOT)
    env["TG_RECAP_API_ID"] = API_ID
    res = subprocess.run([sys.executable, "-m", "tg_recap", "login", "--cards", "save-api"],
                         cwd=ROOT, env=env, capture_output=True, text=True)
    assert res.returncode == 16
    assert res.stderr.startswith("MISSING_ENV: TG_RECAP_API_HASH ") and API_ID not in res.stderr + res.stdout
    res = subprocess.run([sys.executable, "-m", "tg_recap", "login"], cwd=ROOT, env=env,
                         capture_output=True, text=True)
    assert res.returncode == 1 and "--cards send-code" in res.stdout


def stored_phones(db):
    import sqlite3
    con = sqlite3.connect(db)
    try:
        return [row[0] for row in con.execute("select phone from entities where phone is not null")]
    finally:
        con.close()


def test_real_sqlite_session_never_stores_own_phone(tg_home):
    pytest.importorskip("telethon")
    from telethon import types
    from telethon.sessions import SQLiteSession
    me = types.User(id=424242, phone=PHONE.lstrip("+"), first_name="Owner", access_hash=1)
    paths.ensure_dir()
    # Control: Telethon's default would cache the phone in the sqlite file.
    leaky = SQLiteSession(str(tg_home / "control"))
    leaky.process_entities([me])
    leaky.save()
    leaky.close()
    assert stored_phones(tg_home / "control.session") == [int(PHONE.lstrip("+"))]
    (tg_home / "control.session").unlink()
    # Our factory turns the cache off.
    paths.ensure_dir(paths.pending_dir())
    client = login_backend._default_client_factory(str(paths.pending_session_base()), int(API_ID), API_HASH)
    assert client.session.save_entities is False
    client.session.process_entities([me])
    client.session.save()
    client.session.close()
    pending = paths.pending_session_base().with_name("login.session")
    assert stored_phones(pending) == []
    for p in tg_home.rglob("*"):
        if p.is_file():
            assert PHONE.lstrip("+").encode() not in p.read_bytes(), p.name


def test_runner_client_has_entity_cache_off(tg_home):
    pytest.importorskip("telethon")
    from tg_recap import runner
    paths.write_json(paths.credentials_file(), {"api_id": int(API_ID), "api_hash": API_HASH})
    paths.write_private(paths.session_file(), "")
    paths.session_file().unlink()
    client = login_backend._default_client_factory(str(paths.session_base()), int(API_ID), API_HASH)
    client.session.close()
    rc = runner.telethon_client()
    assert rc is not None and rc.session.save_entities is False
    rc.session.close()
