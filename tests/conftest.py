import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc)  # 7:00 PM PST Nov 9
ME_ID = 1


@pytest.fixture(autouse=True)
def tg_home(tmp_path, monkeypatch, request):
    home = tmp_path / "tghome"
    monkeypatch.setenv("TG_RECAP_HOME", str(home))
    if "no_consent" not in request.fixturenames:
        from tg_recap import consent
        consent.accept(NOW)  # most tests run as an install that already accepted the terms warning
    return home


@pytest.fixture
def no_consent():
    """Marker fixture: this test's home starts without the API-terms consent."""
    return None


@dataclass
class Ent:
    title: str = None
    first_name: str = None
    last_name: str = None
    username: str = None
    id: int = None
    bot: bool = False
    broadcast: bool = False


@dataclass
class Msg:
    id: int
    message: str
    date: datetime
    out: bool = False
    mentioned: bool = False
    reply_to_msg_id: int = None
    sender: Ent = None
    sender_id: int = None
    post: bool = False
    entities: list = None

    def __post_init__(self):
        if self.sender_id is None and self.sender is not None:
            self.sender_id = self.sender.id


@dataclass
class NS:
    mute_until: datetime = None


@dataclass
class Inner:
    notify_settings: NS = field(default_factory=NS)


@dataclass
class Dialog:
    id: int
    name: str
    entity: Ent
    messages: list
    date: datetime = None
    archived: bool = False
    dialog: Inner = field(default_factory=Inner)
    older: list = field(default_factory=list)


class FakeClient:
    """Offline stand-in for TelegramClient. Records every call."""

    def __init__(self, dialogs, me=None):
        self.dialogs = dialogs
        self.me = me or Ent(first_name="Owner", username="owner_handle", id=ME_ID)
        self.calls = []
        self.authorized = True

    async def connect(self):
        self.calls.append("connect")

    async def disconnect(self):
        self.calls.append("disconnect")

    async def is_user_authorized(self):
        self.calls.append("is_user_authorized")
        return self.authorized

    async def get_me(self):
        self.calls.append("get_me")
        return self.me

    async def get_entity(self, x):
        self.calls.append("get_entity")
        return Ent(title="x")

    async def iter_dialogs(self, *a, **k):
        self.calls.append("iter_dialogs")
        for d in self.dialogs:
            yield d

    async def iter_messages(self, entity, *a, **k):
        self.calls.append("iter_messages")
        for d in self.dialogs:
            if d.entity is entity:
                for m in d.messages:
                    yield m

    async def get_messages(self, entity, ids=None, **k):
        self.calls.append("get_messages")
        for d in self.dialogs:
            if d.entity is entity:
                return [m for m in d.older if m.id in (ids or [])]
        return []

    # write methods that must never be reachable
    async def send_message(self, *a, **k):
        self.calls.append("send_message")

    async def send_read_acknowledge(self, *a, **k):
        self.calls.append("send_read_acknowledge")

    async def __call__(self, request):
        self.calls.append(type(request).__name__)
        return "raw-ok"


def ago(minutes):
    return NOW - timedelta(minutes=minutes)


def mkdialog(i, name, msgs, **kw):
    ent = Ent(title=name)
    last = max((m.date for m in msgs), default=ago(60 * 48))
    return Dialog(id=1000 + i, name=name, entity=ent, messages=msgs, date=last, **kw)


def run(coro):
    return asyncio.run(coro)


def pytest_report_header(config):
    try:
        import telethon
        return [f"telethon: {telethon.__version__}"]
    except ImportError:
        from tg_recap.deps import missing_telethon_message
        return [missing_telethon_message() + "  Tests that need Telethon will skip."]
