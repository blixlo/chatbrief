"""Terminal sign-in, fully offline: a fake Telethon client, scripted input()/getpass().

Sentinel values below are fake and exist only in this test. None of them may
appear in stdout, stderr, logs, or any file except the API hash in
credentials.json (the only kept secret besides Telethon's session file).
"""
import logging
import os

import pytest

from tg_recap import __main__ as cli
from tg_recap import login_backend, login_terminal, paths
from tg_recap.lock import SessionLock
from login_fakes import (FloodWaitError, PasswordHashInvalidError, PhoneCodeExpiredError,  # noqa: E402
                         PhoneCodeInvalidError, PhoneNumberInvalidError, SessionPasswordNeededError)

PHONE = "+15550009876"
CODE = "13579"
PASSWORD = "sentinel-two-step-pw-41"
API_ID = "7654321"
API_HASH = "sentinel-api-hash-not-real-1"
SESSION_BYTES = b"SQLite format 3\x00sentinel-session-blob"


class SentCode:
    def __init__(self, n):
        self.phone_code_hash = f"hash-{n}"


class FakeTelethonClient:
    """Offline stand-in for TelegramClient. Records method names only."""

    def __init__(self, session, api_id, api_hash, script=None):
        self.session_path = session + ".session"
        self.calls = []
        self.script = dict(script or {})
        self.sent = 0
        self.signed_in = False

    def _fail(self, key):
        queue = self.script.get(key) or []
        if queue:
            raise queue.pop(0)

    async def connect(self):
        self.calls.append("connect")
        with open(self.session_path, "wb") as fh:  # Telethon creates its SQLite file
            fh.write(SESSION_BYTES)
        os.chmod(self.session_path, 0o644)  # loose on purpose: login must tighten it

    async def send_code_request(self, phone):
        self.calls.append("send_code_request")
        self._fail("send_code")
        self.sent += 1
        return SentCode(self.sent)

    async def sign_in(self, phone=None, code=None, phone_code_hash=None, password=None):
        self.calls.append("sign_in")
        if password is not None:
            self._fail("password")
        else:
            assert phone_code_hash == f"hash-{self.sent}"
            self._fail("code")
        self.signed_in = True
        return object()

    async def disconnect(self):
        self.calls.append("disconnect")

    # never reachable from login
    async def send_message(self, *a, **k):
        self.calls.append("send_message")


class Inputs:
    def __init__(self, typed, hidden):
        self.typed, self.hidden = list(typed), list(hidden)
        self.prompts = []

    def input(self, prompt=""):
        self.prompts.append(prompt)
        if not self.typed:
            raise EOFError
        return self.typed.pop(0)

    def getpass(self, prompt=""):
        self.prompts.append(prompt)
        if not self.hidden:
            raise EOFError
        return self.hidden.pop(0)


def make(script=None):
    holder = {}

    def factory(session, api_id, api_hash):
        holder["client"] = FakeTelethonClient(session, api_id, api_hash, script)
        return holder["client"]
    return login_backend.TelethonBackend(client_factory=factory), holder


def all_bytes(root):
    out = b""
    for dirpath, _, files in os.walk(root):
        for f in files:
            out += open(os.path.join(dirpath, f), "rb").read()
    return out


def assert_no_secrets(capsys, caplog, tg_home, *, hash_on_disk):
    cap = capsys.readouterr()
    text = cap.out + cap.err + caplog.text
    for secret in (PHONE, PHONE.lstrip("+"), CODE, PASSWORD, API_HASH, SESSION_BYTES.decode("latin-1")):
        assert secret not in text, "secret leaked to output/logs"
    blob = all_bytes(tg_home) if tg_home.exists() else b""
    for secret in (PHONE, PHONE.lstrip("+"), CODE, PASSWORD):
        assert secret.encode() not in blob, "secret written to disk"
    assert (API_HASH.encode() in blob) == hash_on_disk
    return cap


def run_login(backend, inputs):
    return login_terminal.login(backend, inputs.input, inputs.getpass)


@pytest.fixture(autouse=True)
def _all_logs(caplog):
    caplog.set_level(logging.DEBUG)


def test_happy_path_no_two_step(tg_home, capsys, caplog):
    backend, h = make()
    inputs = Inputs([API_ID, PHONE, CODE], [API_HASH])
    assert run_login(backend, inputs) == 0
    client = h["client"]
    assert client.calls == ["connect", "send_code_request", "sign_in", "disconnect"]
    assert set(client.calls) <= login_backend.LOGIN_METHODS
    assert inputs.prompts[1].startswith("API hash")  # hash read via getpass
    assert not any("password" in p.lower() for p in inputs.prompts)  # no 2FA prompt
    assert paths.read_json(paths.credentials_file()) == {"api_id": int(API_ID), "api_hash": API_HASH}
    cap = assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=True)
    assert "Signed in" in cap.out


def test_two_step_password_path_and_file_modes(tg_home, capsys, caplog):
    backend, h = make({"code": [SessionPasswordNeededError(None)]})
    inputs = Inputs([API_ID, PHONE, CODE], [API_HASH, PASSWORD])
    assert run_login(backend, inputs) == 0
    assert h["client"].calls == ["connect", "send_code_request", "sign_in", "sign_in", "disconnect"]
    assert inputs.prompts[-1].startswith("Two-step password")
    session = paths.session_file()
    assert session.read_bytes() == SESSION_BYTES
    assert oct(os.stat(session).st_mode & 0o777) == "0o600"
    assert oct(os.stat(paths.credentials_file()).st_mode & 0o777) == "0o600"
    assert oct(os.stat(tg_home).st_mode & 0o777) == "0o700"
    for f in tg_home.iterdir():
        assert oct(os.stat(f).st_mode & 0o777) == "0o600", f.name
    assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=True)


def test_wrong_code_retries_then_succeeds(tg_home, capsys, caplog):
    backend, h = make({"code": [PhoneCodeInvalidError(None), PhoneCodeInvalidError(None)]})
    inputs = Inputs([API_ID, PHONE, "00000", "11111", CODE], [API_HASH])
    assert run_login(backend, inputs) == 0
    assert h["client"].calls.count("sign_in") == 3
    cap = assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=True)
    assert "1 tries left" in cap.err and "00000" not in cap.err + cap.out


def test_wrong_code_too_many_times_stops_and_saves_nothing(tg_home, capsys, caplog):
    backend, h = make({"code": [PhoneCodeInvalidError(None)] * 3})
    inputs = Inputs([API_ID, PHONE, CODE, CODE, CODE], [API_HASH])
    assert run_login(backend, inputs) == 1
    assert h["client"].calls.count("sign_in") == login_terminal.MAX_TRIES
    assert not paths.credentials_file().exists()
    cap = assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=False)
    assert "Too many wrong login codes" in cap.err and "Traceback" not in cap.err


def test_expired_code_requests_one_new_code(tg_home, capsys, caplog):
    backend, h = make({"code": [PhoneCodeExpiredError(None)]})
    inputs = Inputs([API_ID, PHONE, CODE, CODE], [API_HASH])
    assert run_login(backend, inputs) == 0
    assert h["client"].calls.count("send_code_request") == 2
    cap = assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=True)
    assert "expired" in cap.err


def test_wrong_password_retries(tg_home, capsys, caplog):
    backend, _ = make({"code": [SessionPasswordNeededError(None)],
                       "password": [PasswordHashInvalidError(None)]})
    inputs = Inputs([API_ID, PHONE, CODE], [API_HASH, "wrong-pw-sentinel", PASSWORD])
    assert run_login(backend, inputs) == 0
    cap = assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=True)
    assert "two-step password didn't work" in cap.err and "wrong-pw-sentinel" not in cap.err


def test_wrong_phone_retries(tg_home, capsys, caplog):
    backend, h = make({"send_code": [PhoneNumberInvalidError(None)]})
    inputs = Inputs([API_ID, "12", PHONE, CODE], [API_HASH])
    assert run_login(backend, inputs) == 0
    assert h["client"].calls.count("send_code_request") == 2
    assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=True)


@pytest.mark.parametrize("where", ["send_code", "code"])
def test_flood_wait_exits_4_flood_stop(tg_home, capsys, caplog, where):
    backend, h = make({where: [FloodWaitError(420)]})
    inputs = Inputs([API_ID, PHONE, CODE], [API_HASH])
    assert run_login(backend, inputs) == 4
    assert h["client"].calls[-1] == "disconnect"
    assert not paths.credentials_file().exists()
    cap = assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=False)
    assert cap.err.startswith("FLOOD_STOP") or "\nFLOOD_STOP" in cap.err
    assert "420s" in cap.err


def test_unexpected_error_prints_kind_only_no_traceback(tg_home, capsys, caplog):
    class Boom(Exception):
        pass
    backend, _ = make({"code": [Boom(f"details {PHONE} {CODE}")]})
    inputs = Inputs([API_ID, PHONE, CODE], [API_HASH])
    assert run_login(backend, inputs) == 1
    cap = assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=False)
    assert "(Boom)" in cap.err and "Traceback" not in cap.err


def test_cancel_with_ctrl_d_or_ctrl_c(tg_home, capsys, caplog):
    backend, _ = make()
    assert run_login(backend, Inputs([API_ID, PHONE], [API_HASH])) == 1  # EOF at code prompt
    backend, _ = make()

    def interrupt(prompt=""):
        raise KeyboardInterrupt
    assert login_terminal.login(backend, interrupt, interrupt) == 1
    cap = assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=False)
    assert "cancelled" in cap.err


def test_bad_api_values_are_rejected_before_any_telegram_call(tg_home, capsys, caplog):
    backend, h = make()
    inputs = Inputs(["abc"] * 3, ["short"] * 3)
    assert run_login(backend, inputs) == 1
    assert "client" not in h  # never even built a client
    assert not paths.credentials_file().exists()


def test_reuses_saved_api_values(tg_home, capsys, caplog):
    paths.write_json(paths.credentials_file(), {"api_id": int(API_ID), "api_hash": API_HASH})
    backend, _ = make()
    inputs = Inputs(["", PHONE, CODE], [])
    assert run_login(backend, inputs) == 0
    assert inputs.prompts[0].startswith("Use the API ID")
    assert_no_secrets(capsys, caplog, tg_home, hash_on_disk=True)


def test_lock_held_exits_2(tg_home, capsys):
    holder = SessionLock().acquire()
    try:
        import subprocess
        import sys
        code = ("import sys; from tg_recap import login_terminal as t; "
                "sys.exit(t.login(None, lambda p='': '', lambda p='': ''))")
        env = {**os.environ, "PYTHONPATH": str(paths.Path(__file__).resolve().parents[1])}
        res = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    finally:
        holder.release()
    assert res.returncode == 2 and res.stderr.startswith("LOCK_HELD")


def test_cli_login_terminal_and_web_are_opt_in(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "require_telethon", lambda: None)
    monkeypatch.setattr(login_terminal, "login", lambda *a, **k: calls.append("terminal") or 0)
    import tg_recap.login_web as web
    monkeypatch.setattr(web, "serve", lambda port: calls.append(("web", port)) or 0)
    assert cli.main(["login"]) == 1  # plain login: usage only, nothing runs
    assert "--cards" in capsys.readouterr().out
    assert cli.main(["login", "--terminal"]) == 0
    assert cli.main(["login", "--web", "--port", "9999"]) == 0
    assert calls == ["terminal", ("web", 9999)]
    with pytest.raises(SystemExit):
        cli.main(["login", "--web", "--terminal"])


def test_real_telethon_errors_translate_without_values():
    errors = pytest.importorskip("telethon.errors")
    cases = {
        errors.SessionPasswordNeededError(None): login_backend.PasswordNeeded,
        errors.PhoneCodeInvalidError(None): login_backend.CodeInvalid,
        errors.PhoneCodeExpiredError(None): login_backend.CodeExpired,
        errors.PasswordHashInvalidError(None): login_backend.PasswordInvalid,
        errors.PhoneNumberInvalidError(None): login_backend.PhoneInvalid,
        errors.ApiIdInvalidError(None): login_backend.ApiInvalid,
    }
    for exc, cls in cases.items():
        got = login_backend.translate(exc)
        assert type(got) is cls and str(got) == "" and got.args == ()
    flood = login_backend.translate(errors.FloodWaitError(None, capture=30))
    assert isinstance(flood, login_backend.FloodWait) and flood.seconds == 30


def test_backend_drops_exception_context():
    import asyncio
    backend, h = make({"code": [PhoneCodeInvalidError(None)]})

    async def go():
        await backend.start(int(API_ID), API_HASH)
        await backend.send_code(PHONE)
        await backend.sign_in_code(CODE)
    with pytest.raises(login_backend.CodeInvalid) as e:
        asyncio.run(go())
    assert e.value.__cause__ is None and e.value.__suppress_context__
