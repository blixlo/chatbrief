"""Collector routing, needs-you logic, feeds, header, disclaimer, caps, fallback text."""
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from tg_recap import collect as C
from tg_recap.config import LENGTH_CAPS, Config
from tg_recap.readonly import ReadOnlyClient, ReadOnlyViolation
from tg_recap.render import header, render, window_label
from conftest import ME_ID, NOW, NS, Ent, FakeClient, Inner, Msg, ago, mkdialog, run

ME = Ent(first_name="Owner", username="owner_handle", id=ME_ID)
ALICE = Ent(first_name="Alice", last_name="Example", id=11)
BOB = Ent(first_name="Bob", id=12)
ALERT_BOT = Ent(first_name="Watch Bot", id=13, bot=True)


class MessageEntityMentionName:  # named like Telethon's entity types
    def __init__(self, offset, length, user_id):
        self.offset, self.length, self.user_id = offset, length, user_id


class MessageEntityMention:
    def __init__(self, offset, length):
        self.offset, self.length = offset, length


async def _nosleep(_):
    return None


def collect(dialogs, cfg=None, hours=12):
    state = {"salt": "s", "last_recap_at": (NOW - timedelta(hours=hours)).isoformat()}
    fake = FakeClient(dialogs, me=ME)
    client = ReadOnlyClient(fake, min_interval=0, sleep=_nosleep)
    return run(C.collect(client, cfg or Config(), state, NOW)), fake, state


def world():
    work = mkdialog(1, "Work Group", [
        Msg(1, "lunch?", ago(300), sender=BOB),
        Msg(2, "I posted the doc", ago(290), out=True, sender=ME),
        Msg(3, "thanks, looks good", ago(200), reply_to_msg_id=2, sender=ALICE),
        Msg(4, "Owner can you review by Friday?", ago(100), sender=BOB,
            entities=[MessageEntityMentionName(0, 5, ME_ID)]),
        Msg(5, "we decided to ship v2", ago(90), sender=ALICE),
        Msg(6, "deadline is Nov 14", ago(80), sender=ALICE),
    ])
    quiet = mkdialog(2, "Old Chat", [Msg(21, "ages ago", ago(60 * 40), sender=BOB)])
    mine_only = mkdialog(3, "Notes To Self Group", [Msg(22, "note", ago(30), out=True, sender=ME)])
    muted = mkdialog(4, "Muted Group", [Msg(30, "anyone up for tennis", ago(10), sender=BOB),
                                        Msg(31, "me", ago(9), sender=ALICE)],
                     dialog=Inner(NS(mute_until=NOW + timedelta(days=365))))
    archived = mkdialog(5, "Archived Group", [Msg(40, "@owner_handle hey", ago(10), sender=BOB)], archived=True)
    whales = mkdialog(6, "Whale Watch", [
        Msg(100 + i, f"🐋 Whale bought {1000 + i * 7} {tok} (${i}k)", ago(200 - i), sender=ALERT_BOT)
        for i, tok in enumerate(["$ABCX", "$XYZQ", "$ABCX"] * 30)])
    return [work, quiet, mine_only, muted, archived, whales]


def names(seq):
    return [x["name"] for x in seq]


# --- 2. muted / archived / quiet --------------------------------------------------

def test_muted_shown_in_also_active_and_never_quiet():
    d, _, _ = collect(world())
    assert names(d["also_active"]) == ["Muted Group"] and d["also_active"][0]["new_messages"] == 2
    assert "Muted Group" not in names(d["conversations"])
    # quiet = Old Chat + the chat where only you posted; nothing with new messages from others
    assert d["quiet_count"] == 2
    text = render(d)
    assert "Also active: Muted Group (2 new)." in text and "2 other chats had no new messages." in text
    assert text.index("Alert feeds") < text.index("Also active")


def test_muted_off_and_archived_on():
    d, _, _ = collect(world(), Config(include_muted=False))
    assert d["also_active"] == [] and d["quiet_count"] == 2
    assert "Archived Group" not in json.dumps(d)
    d, _, _ = collect(world(), Config(include_archived=True))
    assert any(i["chat"] == "Archived Group" and i["kind"] == "mention" for i in d["needs_you"])


def test_dms_follow_setting():
    dm = mkdialog(7, "Alice Example", [Msg(50, "hi there, are you free Friday?", ago(5), sender=ALICE)])
    dm.entity = ALICE
    d, _, _ = collect([dm])
    assert names(d["conversations"]) == ["Alice Example"]
    d, _, _ = collect([dm], Config(include_dms=False))
    assert d["conversations"] == [] and d["quiet_count"] == 0


# --- 3. alert feeds ------------------------------------------------------------------

def test_bot_feed_collapses_to_one_line_below_conversations():
    d, _, _ = collect(world())
    assert d["alert_feeds"] == [{"name": "Whale Watch", "count": 90, "noun": "whale alerts",
                                 "top": ["ABCX", "XYZQ"], "market_related": True,
                                 "source": "Watch Bot"}]
    text = render(d)
    assert "• Whale Watch: 90 whale alerts from Watch Bot, mostly ABCX and XYZQ." in text
    assert text.index("Conversations") < text.index("Alert feeds")
    assert "Whale Watch" not in names(d["conversations"])


def test_templated_single_sender_channel_is_a_feed_without_bot_flag():
    swaps = Ent(title="Swap Alerts", broadcast=True, id=70)
    ch = mkdialog(8, "Swap Alerts", [Msg(200 + i, f"Swapped {i * 3 + 1} SOL for {i * 11 + 5} $MOCKZ on Raydium",
                                          ago(100 - i), sender=swaps, post=True) for i in range(12)])
    ch.entity = swaps
    d, _, _ = collect([ch])
    assert d["alert_feeds"][0]["name"] == "Swap Alerts" and d["alert_feeds"][0]["count"] == 12
    assert d["alert_feeds"][0]["top"][0] == "MOCKZ"


def test_varied_single_author_channel_is_not_a_feed():
    news = Ent(title="Town News", broadcast=True, id=71)
    texts = ["Road works close the bridge this weekend.", "Library hours change in December.",
             "Rain expected through Thursday.", "School board meets next week.",
             "The farmers market moves indoors.", "New bike lanes open downtown."]
    ch = mkdialog(9, "Town News", [Msg(300 + i, t, ago(60 - i), sender=news, post=True) for i, t in enumerate(texts)])
    ch.entity = news
    d, _, _ = collect([ch])
    assert d["alert_feeds"] == [] and names(d["conversations"]) == ["Town News"]


def test_collapse_setting_off_and_chat_rules():
    d, _, _ = collect(world(), Config(collapse_alert_bots=False))
    assert d["alert_feeds"] == [] and "Whale Watch" in names(d["conversations"])
    key = C.chat_key(world()[5], "s")
    d, _, _ = collect(world(), Config(chat_rules={key: {"title": "Whale Watch", "rule": "count-only"}}))
    assert d["count_only"] == [{"name": "Whale Watch", "new_messages": 90}] and d["alert_feeds"] == []
    assert "Count only: Whale Watch (90 new)." in render(d)
    d, _, _ = collect(world(), Config(chat_rules={key: {"title": "Whale Watch", "rule": "skip"}}))
    assert "Whale Watch" not in json.dumps(d)
    mkey = C.chat_key(world()[3], "s")
    d, _, _ = collect(world(), Config(chat_rules={mkey: {"title": "Muted Group", "rule": "include"}}))
    assert "Muted Group" in names(d["conversations"]) and d["also_active"] == []


# --- 4. needs you ---------------------------------------------------------------------

def test_real_replies_and_mentions_only():
    d, _, _ = collect(world())
    needs = [(i["kind"], i["who"], i["chat"]) for i in d["needs_you"]]
    assert needs == [("reply", "Alice Example", "Work Group"), ("mention", "Bob", "Work Group")]
    assert d["needs_you"][1]["text"] == "Owner can you review by Friday?"
    text = render(d)
    assert "• Alice Example replied to you in Work Group: Thanks, looks good." in text


def test_own_channel_posts_never_count_as_you():
    own = Ent(title="My Channel", broadcast=True, id=80)
    ch = mkdialog(10, "My Channel", [
        Msg(1, "post one", ago(100), out=True, post=True, sender=own),
        Msg(2, "follow-up to the last post", ago(90), out=True, post=True, sender=own, reply_to_msg_id=1),
        Msg(3, "reply from a channel post", ago(80), post=True, sender=own, reply_to_msg_id=1),
    ])
    ch.entity = own
    group = mkdialog(11, "Discussion", [
        Msg(5, "bot answer", ago(50), sender=ALERT_BOT, reply_to_msg_id=4),
        Msg(6, "a human reply to the channel post", ago(40), sender=BOB, reply_to_msg_id=7),
        Msg(8, "flag only, no entity", ago(30), sender=BOB, mentioned=True),
        Msg(9, "@someoneelse look", ago(20), sender=BOB, entities=[MessageEntityMention(0, 12)]),
        Msg(10, "hey someone", ago(19), sender=BOB, entities=[MessageEntityMentionName(4, 7, 999)]),
    ], older=[Msg(4, "my command", ago(60 * 30), sender=ME),
              Msg(7, "forwarded channel post", ago(60 * 30), out=True, post=True, sender=own)])
    d, fake, _ = collect([ch, group])
    assert d["needs_you"] == []
    assert "get_messages" in fake.calls  # older referenced messages were checked


def test_reply_to_older_own_message_and_text_mention():
    g = mkdialog(12, "Club", [Msg(2, "yes, Saturday works for everyone here.", ago(20), sender=ALICE,
                                  reply_to_msg_id=1),
                              Msg(3, "ping @Owner_Handle when you can", ago(10), sender=BOB)],
                 older=[Msg(1, "Saturday?", ago(60 * 20), sender=ME)])
    d, _, _ = collect([g])
    assert [i["kind"] for i in d["needs_you"]] == ["reply", "mention"]


@pytest.mark.parametrize("text,limit,expect", [
    ("Short one.", 50, "Short one."),
    ("First sentence here. Second one?", 80, "Second one?"),
    ("This is a fairly long message that keeps going without any stop at all here", 30,
     "This is a fairly long message…"),
    ("Supercalifragilisticexpialidocious", 20, "Supercalifragilisticexpialidocious"),
    ("Supercalifragilisticexpialidocious and more", 20, "Supercalifragilisticexpialidocious…"),
    ("@owner_handle, can you check?", 80, "Can you check?"),
    ("send to 0x1111111111111111111111111111111111111111 please?", 80, "Send to [address removed] please?"),
])
def test_sentence_cut_at_boundaries(text, limit, expect):
    out = C.sentence(text, limit)
    assert out == expect
    if out.endswith("…"):  # the kept part ends on a whole word of the original
        stem = out[:-1]
        assert text.startswith(stem) and text[len(stem)] == " "


def test_shorten_never_cuts_mid_word():
    t = "alpha beta gamma delta epsilon zeta eta theta"
    for n in range(6, len(t)):
        out = C.shorten(t, n)
        assert len(out) <= n or out.count(" ") == 0
        assert out == t or (out.endswith("…") and out[:-1] in [" ".join(t.split()[:k]) for k in range(1, 9)])


# --- 5. header --------------------------------------------------------------------------

def _w(start, end, tz="America/Los_Angeles"):
    return {"start": start.isoformat(), "end": end.isoformat(), "tz": tz}


def test_header_across_midnight_shows_both_dates():
    w = _w(datetime(2026, 11, 10, 11, 20, tzinfo=timezone.utc), datetime(2026, 11, 11, 11, 20, tzinfo=timezone.utc))
    assert header(w) == "ChatBrief · Nov 10, 3:20 AM to Nov 11, 3:20 AM PT"


def test_header_same_day_still_shows_both_dates():
    w = _w(datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc), datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc))
    assert window_label(w) == "Nov 10, 8:00 AM to Nov 10, 12:00 PM PT"


def test_header_across_dst_changes():
    # US fall back: Sun Nov 1 2026, 2:00 AM PDT -> 1:00 AM PST
    w = _w(datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc), datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc))
    assert window_label(w) == "Oct 31, 8:00 AM to Nov 1, 8:00 AM PT"
    # US spring forward: Sun Mar 8 2026
    w = _w(datetime(2026, 3, 7, 16, 0, tzinfo=timezone.utc), datetime(2026, 3, 8, 15, 0, tzinfo=timezone.utc))
    assert window_label(w) == "Mar 7, 8:00 AM to Mar 8, 8:00 AM PT"
    w = _w(datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc), datetime(2026, 3, 29, 12, 0, tzinfo=timezone.utc),
           "Europe/Berlin")
    assert window_label(w) == "Mar 28, 1:00 PM to Mar 29, 2:00 PM CEST"
    assert window_label(_w(NOW - timedelta(hours=1), NOW, "America/New_York")).endswith(" ET")


# --- 6. disclaimer ------------------------------------------------------------------------

def test_disclaimer_only_with_market_chats_and_exactly_one_line():
    d, _, _ = collect(world())
    text = render(d)
    assert text.rstrip().splitlines()[-1] == "Recap only, not financial advice."
    assert text.count("financial advice") == 1
    calm = [mkdialog(1, "Book Club", [Msg(1, "we decided on the next book, see you Friday", ago(30), sender=ALICE)])]
    d, _, _ = collect(calm)
    assert d["show_disclaimer"] is False and "financial advice" not in render(d)
    coins = [mkdialog(2, "Coin Talk", [Msg(1, "token chart looks bullish", ago(20), sender=BOB),
                                       Msg(2, "we decided to wait for the unlock", ago(10), sender=ALICE)])]
    d, _, _ = collect(coins)
    assert d["show_disclaimer"] and d["disclaimer"] == "Recap only, not financial advice."


# --- caps --------------------------------------------------------------------------------

def _big_world(n_chats=25, n_msgs=80, size=400):
    return [mkdialog(i, f"Chat {i}", [Msg(i * 1000 + j, ("word " * (size // 5)).strip() + f" {j}.", ago(500 - j),
                                          sender=BOB if j % 2 else ALICE) for j in range(n_msgs)])
            for i in range(n_chats)]


@pytest.mark.parametrize("length", ["short", "standard", "detailed"])
def test_length_caps(length):
    caps = LENGTH_CAPS[length]
    d, _, _ = collect(_big_world(), Config(length=length), hours=24)
    convs = d["conversations"]
    assert len(convs) == caps["max_chats"] and d["more_conversations"] == 25 - caps["max_chats"]
    total = 0
    for c in convs:
        assert len(c["messages"]) <= caps["chat_msgs"]
        assert c["new_messages"] == 80
        for m in c["messages"]:
            assert len(m["text"]) <= caps["msg_chars"] and not re.search(r"\w…\w", m["text"])
            total += len(m["text"])
        assert c["omitted_messages"] == 80 - len(c["messages"])
    assert total <= caps["total_chars"]


def test_budget_scales_with_length():
    sizes = {}
    for length in ("short", "standard", "detailed"):
        d, _, _ = collect(_big_world(), Config(length=length), hours=24)
        sizes[length] = len(json.dumps(d))
    assert sizes["short"] < sizes["standard"] < sizes["detailed"]


# --- privacy / read-only -----------------------------------------------------------------

def test_no_ids_or_addresses_in_json_or_text():
    w = world() + [mkdialog(13, "Coin Talk", [Msg(1, "ca 0x2222222222222222222222222222222222222222 and "
                                                    "call +1 555 010 9999 see t.me/+FakeInvite", ago(5), sender=BOB)])]
    d, _, state = collect(w)
    blob = json.dumps(d) + render(d)
    for bad in ("0x2222222222222222222222222222222222222222", "555 010 9999", "FakeInvite", "owner_handle"):
        assert bad not in blob
    for raw_id in ("1001", "1006", "1013"):
        assert raw_id not in blob
    assert all(len(k) == 16 for k in state["directory"])
    assert all(set(v) == {"title", "kind"} for v in state["directory"].values())


def test_read_only_wrapper_still_blocks_writes():
    fake = FakeClient([])
    ro = ReadOnlyClient(fake, min_interval=0, sleep=_nosleep)
    for name in ("send_message", "send_read_acknowledge", "send_reaction", "edit_message", "delete_messages",
                 "forward_messages", "pin_message", "sign_in"):
        with pytest.raises(ReadOnlyViolation):
            getattr(ro, name)

    class SendReactionRequest:
        pass

    class ReadHistoryRequest:
        pass

    for req in (SendReactionRequest(), ReadHistoryRequest()):
        with pytest.raises(ReadOnlyViolation):
            run(ro(req))
    assert fake.calls == []


def test_collect_only_uses_read_calls():
    _, fake, _ = collect(world())
    assert set(fake.calls) <= {"get_me", "iter_dialogs", "iter_messages", "get_messages"}


def test_empty_run_renders_nothing():
    d, _, _ = collect([mkdialog(1, "Q", [Msg(1, "hi", ago(60 * 30), sender=BOB)])])
    assert render(d) == "" and d["quiet_count"] == 1
    d, _, _ = collect([world()[3]])  # only a muted chat: no recap
    assert render(d) == ""


def test_telegram_service_chat_is_excluded():
    from tg_recap.collect import TELEGRAM_SERVICE_ID
    tg = Ent(first_name="Telegram", id=TELEGRAM_SERVICE_ID)
    service = mkdialog(50, "Telegram", [
        Msg(1, "Login code: 12345. Do not give this to anyone.", ago(5), sender=tg),
    ])
    service.entity = tg
    service.id = TELEGRAM_SERVICE_ID
    work = mkdialog(1, "Work Group", [Msg(2, "we decided to ship v2 on Friday", ago(10), sender=ALICE)])
    d, fake, _ = collect([service, work])
    blob = json.dumps(d) + render(d)
    assert "12345" not in blob and "Login code" not in blob
    assert "Telegram" not in blob
    assert names(d["conversations"]) == ["Work Group"]
    assert "iter_messages" in fake.calls  # work was read
    # the service dialog itself was not walked for messages: only one iter_messages (work)
    assert fake.calls.count("iter_messages") == 1


def test_forwarded_login_code_is_redacted_in_output():
    g = mkdialog(1, "Work Group", [
        Msg(1, "Login code: 12345 got forwarded here, ignore it.", ago(10), sender=BOB),
        Msg(2, "we decided to ship v2 on Friday", ago(9), sender=ALICE),
    ])
    d, _, _ = collect([g])
    blob = json.dumps(d) + render(d)
    assert "12345" not in blob
    assert "Login code:" not in blob
    assert "[code removed]" in blob
