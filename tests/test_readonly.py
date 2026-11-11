import pytest

from tg_recap.deps import missing_telethon_message

pytest.importorskip("telethon", reason=missing_telethon_message())
from telethon import functions
from telethon.errors import FloodWaitError

from tg_recap.readonly import ALLOWED_METHODS, FloodStop, ReadOnlyClient, ReadOnlyViolation
from conftest import FakeClient, Msg, ago, mkdialog, run


def ro(client, **kw):
    slept = []

    async def sleep(s):
        slept.append(s)
    return ReadOnlyClient(client, sleep=sleep, **kw), slept


@pytest.mark.parametrize("name", ["send_message", "send_read_acknowledge", "send_file", "delete_messages",
                                  "edit_message", "forward_messages", "delete_dialog", "log_out",
                                  "sign_in", "send_code_request", "join_chat",
                                  "send_reaction", "pin_message", "unpin_message", "anything_else"])
def test_write_and_read_ack_methods_blocked(name):
    fake = FakeClient([])
    client, _ = ro(fake)
    with pytest.raises(ReadOnlyViolation):
        getattr(client, name)
    assert "send_message" not in fake.calls and "send_read_acknowledge" not in fake.calls


@pytest.mark.parametrize("req", [
    functions.messages.ReadHistoryRequest(peer="me", max_id=0),
    functions.channels.ReadHistoryRequest(channel="me", max_id=0),
    functions.messages.SendMessageRequest(peer="me", message="x"),
    functions.channels.JoinChannelRequest(channel="me"),
    functions.channels.LeaveChannelRequest(channel="me"),
    functions.messages.ImportChatInviteRequest(hash="x"),
    functions.messages.SendReactionRequest(peer="me", msg_id=1),
    functions.messages.UpdatePinnedMessageRequest(peer="me", id=1),
])
def test_raw_write_and_readhistory_requests_blocked(req):
    fake = FakeClient([])
    client, _ = ro(fake)
    with pytest.raises(ReadOnlyViolation):
        run(client(req))
    assert fake.calls == []


def test_allowlisted_raw_request_passes():
    fake = FakeClient([])
    client, _ = ro(fake)
    assert run(client(functions.users.GetFullUserRequest(id="me"))) == "raw-ok"


def test_allowlisted_reads_work_and_setattr_blocked():
    d = mkdialog(1, "G", [Msg(1, "hi", ago(5))])
    fake = FakeClient([d])
    client, _ = ro(fake)

    async def go():
        me = await client.get_me()
        ds = [x async for x in client.iter_dialogs()]
        ms = [x async for x in client.iter_messages(d.entity)]
        return me, ds, ms
    me, ds, ms = run(go())
    assert me.first_name == "Owner" and len(ds) == 1 and len(ms) == 1
    with pytest.raises(ReadOnlyViolation):
        client.foo = 1
    assert ALLOWED_METHODS.isdisjoint({"send_message", "send_read_acknowledge", "delete_messages"})


class Flaky(FakeClient):
    def __init__(self, fails, seconds=5):
        super().__init__([])
        self.fails, self.seconds = fails, seconds

    async def get_me(self):
        if self.fails:
            self.fails -= 1
            raise FloodWaitError(request=None, capture=self.seconds)
        return "me"


def test_flood_wait_sleeps_once_then_succeeds():
    client, slept = ro(Flaky(1), min_interval=0)
    assert run(client.get_me()) == "me"
    assert 5 in slept


def test_flood_wait_repeat_stops_run():
    client, slept = ro(Flaky(5), min_interval=0)
    with pytest.raises(FloodStop):
        run(client.get_me())
    assert slept.count(5) == 1


def test_flood_wait_too_long_stops_without_sleeping():
    client, slept = ro(Flaky(1, seconds=99999), min_interval=0)
    with pytest.raises(FloodStop):
        run(client.get_me())
    assert 99999 not in slept


def test_rate_limit_sleeps_between_calls():
    t = [0.0]
    client, slept = ro(FakeClient([]), min_interval=1.0)
    object.__setattr__(client, "_clock", lambda: t[0])

    async def go():
        await client.get_me()
        await client.get_me()
    run(go())
    assert slept and slept[0] == pytest.approx(1.0)
