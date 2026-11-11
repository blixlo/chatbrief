"""Optional web fallback for sign-in, served ONLY on 127.0.0.1 (stdlib only).

The default is the terminal sign-in (login_terminal.py). Some desktops block
loopback pages in the browser on purpose; this page is only for machines that
allow it: `python -m tg_recap login --web`.

Steps: API ID + API hash -> phone -> login code -> two-step password (if set).
Saved to disk (dir 0700, files 0600): api_id + api_hash (credentials.json) and
Telethon's session file. Never written to disk or logs: phone number, login
code, two-step password. They live only in this process's memory during
sign-in, and every reference is dropped as soon as sign-in finishes.
The HTTP server's request logging is disabled.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import sys

from . import consent, paths
from .branding import PRODUCT_NAME
from .login_backend import PasswordNeeded, TelethonBackend, save_credentials  # noqa: F401

HOST = "127.0.0.1"  # never configurable
DEFAULT_PORT = 8765

PRIVACY = (
    f"<p><b>{html.escape(consent.DISCLOSURE)}</b></p>"
    f"<p>{html.escape(PRODUCT_NAME)} signs in <b>as you</b>, using Telethon (a standard Telegram client "
    "library) on your own machine. It reads your chats through your existing account session, the "
    "same way your Telegram app does. No bot is added to your groups, and nobody in them sees anything "
    "new. It only reads: it doesn't post, react, join, or leave.</p>"
    "<p>Your phone number, login code, and two-step password are used once to sign in and are never "
    "saved or logged. We never see them, and neither does anyone else's machine. Only three things are "
    "kept on your machine, readable only by you: your API ID, your API hash, and Telegram's session file. "
    "You can end that session any time in Telegram under <b>Settings &gt; Devices</b>.</p>"
)

STEPS = {
    "api": ("Step 1 of 4: your API ID and API hash",
            "<p>Get your own API ID and API hash at <a href='https://my.telegram.org' target='_blank' "
            "rel='noopener'>my.telegram.org</a> (API development tools). Telegram's official steps: "
            "<a href='https://core.telegram.org/api/obtaining_api_id' target='_blank' rel='noopener'>"
            "core.telegram.org/api/obtaining_api_id</a>.</p>",
            [("api_id", "API ID", "text"), ("api_hash", "API hash", "password")]),
    "phone": ("Step 2 of 4: your phone number",
              "<p>Use international format, for example +1 and your number. Telegram will send a code "
              "to your Telegram app.</p>", [("phone", "Phone number", "tel")]),
    "code": ("Step 3 of 4: login code",
             "<p>Enter the code Telegram just sent to your Telegram app.</p>",
             [("code", "Login code", "text")]),
    "password": ("Step 4 of 4: two-step password",
                 "<p>Your account has a two-step password. It is used once here and is not kept.</p>",
                 [("password", "Two-step password", "password")]),
}

log = logging.getLogger("tg_recap.login")


class LoginFlow:
    def __init__(self, backend):
        self.backend = backend
        self.step = "api"
        self.error = ""
        self.token = secrets.token_urlsafe(24)
        self._api = None  # (api_id, api_hash) kept in memory until sign-in succeeds
        self.done = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._lock = threading.Lock()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=120)

    def submit(self, form: dict) -> None:
        with self._lock:
            self.error = ""
            try:
                if self.step == "api":
                    api_id = (form.get("api_id") or "").strip()
                    api_hash = (form.get("api_hash") or "").strip()
                    if not api_id.isdigit() or len(api_hash) < 16:
                        self.error = "That API ID or API hash doesn't look right. Copy both from my.telegram.org."
                        return
                    self._run(self.backend.start(int(api_id), api_hash))
                    self._api = (int(api_id), api_hash)
                    self.step = "phone"
                elif self.step == "phone":
                    self._run(self.backend.send_code((form.get("phone") or "").strip()))
                    self.step = "code"
                elif self.step == "code":
                    try:
                        self._run(self.backend.sign_in_code((form.get("code") or "").strip()))
                        self._success()
                    except PasswordNeeded:
                        self.step = "password"
                elif self.step == "password":
                    self._run(self.backend.sign_in_password(form.get("password") or ""))
                    self._success()
            except Exception as exc:  # noqa: BLE001 - show type only, never values
                self.error = (f"Telegram didn't accept that ({type(exc).__name__}). "
                              "Check it and try again, or restart with `python -m tg_recap login --web`.")
            finally:
                form.clear()  # drop phone / code / password references

    def _success(self):
        self._run(self.backend.finish())
        api_id, api_hash = self._api
        save_credentials(api_id, api_hash)
        self._api = None
        self.step = "done"
        self.done.set()

    def close(self):
        if self.step != "done":
            try:
                self._run(self.backend.abort())
            except Exception:  # noqa: BLE001
                pass
        self._api = None
        self._loop.call_soon_threadsafe(self._loop.stop)


def page(flow: LoginFlow) -> str:
    if flow.step == "done":
        body = ("<h2>Signed in</h2><p>Your session is saved on your machine, readable only by you. "
                "You can close this tab and go back to your Grok Bot chat.</p>"
                "<p>To end the session later: Telegram <b>Settings &gt; Devices</b>.</p>")
    else:
        title, intro, fields = STEPS[flow.step]
        inputs = "".join(
            f"<label>{html.escape(label)}<br><input name='{name}' type='{typ}' autocomplete='off' "
            f"required></label><br>" for name, label, typ in fields)
        err = f"<p class='err'>{html.escape(flow.error)}</p>" if flow.error else ""
        body = (f"<h2>{html.escape(title)}</h2>{intro}{err}<form method='post' action='/'>"
                f"<input type='hidden' name='token' value='{flow.token}'>{inputs}"
                f"<button type='submit'>Continue</button></form>")
    return ("<!doctype html><html><head><meta charset='utf-8'><title>"
            f"{html.escape(PRODUCT_NAME)}: sign in"
            "</title><meta name='referrer' content='no-referrer'><style>body{font-family:system-ui;"
            "max-width:640px;margin:2em auto;padding:0 1em;line-height:1.5}input{width:100%;"
            "padding:.5em;margin:.3em 0 1em}.err{color:#b00}.box{background:#f4f4f4;padding:.5em 1em;"
            "border-radius:8px}</style></head><body><h1>"
            f"{html.escape(PRODUCT_NAME)}</h1>"
            f"<div class='box'>{PRIVACY}</div>{body}<p><small>Self-serve setup. This page runs only "
            "on this computer (127.0.0.1). Type your details here, never in a chat.</small></p>"
            "</body></html>")


def make_handler(flow: LoginFlow, port_ref: list):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # never log requests
            return

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            return host in {f"127.0.0.1:{port_ref[0]}", f"localhost:{port_ref[0]}"}

        def _send(self, code: int, text: str):
            data = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, "forbidden")
            self._send(200, page(flow))

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, "forbidden")
            length = min(int(self.headers.get("Content-Length") or 0), 8192)
            raw = self.rfile.read(length).decode("utf-8", "replace")
            form = {k: v[0] for k, v in parse_qs(raw).items()}
            raw = None
            if form.get("token") != flow.token:
                form.clear()
                return self._send(403, "forbidden")
            flow.submit(form)
            self._send(200, page(flow))
            if flow.step == "done":
                threading.Thread(target=self.server.shutdown, daemon=True).start()
    return Handler


def make_server(backend=None, port: int = DEFAULT_PORT):
    os.umask(0o077)
    paths.ensure_dir()
    flow = LoginFlow(backend or TelethonBackend())
    port_ref = [port]
    server = ThreadingHTTPServer((HOST, port), make_handler(flow, port_ref))
    port_ref[0] = server.server_address[1]
    return server, flow


def serve(port: int = DEFAULT_PORT, backend=None) -> int:
    refused = consent.require(sys.stderr)
    if refused is not None:
        return refused  # 9: accept the API-terms warning first
    server, flow = make_server(backend, port)
    url = f"http://{HOST}:{server.server_address[1]}/"
    print(f"Open this page on this computer to sign in: {url}", flush=True)
    print("Type your details on that page only, never in a chat. Ctrl+C stops it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        flow.close()
    if flow.step == "done":
        print("Signed in. Session saved under ~/.tg_recap (owner-only).", flush=True)
        return 0
    print("Login not finished. Run `python -m tg_recap login` again when ready.", flush=True)
    return 1
