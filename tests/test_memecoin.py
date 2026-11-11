"""Memecoin mention detection, thresholds, spam discount, CA redaction, buy parsing."""
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from tg_recap import collect as C
from tg_recap import config, paths, runner, settings_cli
from tg_recap import __main__ as cli
from tg_recap.config import Config
from tg_recap.memecoin import (
    LAST_MEMECOIN_AT, UNNAMED, contracts_in, flagged_buys, format_buy, mentions_from_records,
    parse_buys, parse_window, tickers_in,
)
from tg_recap.render import header, memecoin_line, render
from conftest import NOW, FakeClient, Msg, ago, mkdialog

CA1 = "FAKE111111111111111111111111111111111111111"
CA2 = "FAKE222222222222222222222222222222222222222"
EVM = "0x2222222222222222222222222222222222222222"
END = datetime(2026, 11, 11, 11, 20, tzinfo=timezone.utc)
START = END - timedelta(hours=24)


def rec(name, msgs, **kw):
    return {"key": name, "name": name, "kind": kw.get("kind", "group"), "muted": kw.get("muted", False),
            "archived": False, "rule": kw.get("rule"), "messages": msgs}


def msg(who, minutes, text, sender=None, bot=False):
    return {"who": who, "sender": sender or who, "ts": END - timedelta(minutes=minutes),
            "text": text, "by_me": False, "bot": bot, "reply_to_me": False, "mentions_me": False}


def digest(records, cfg=None):
    return C.build_digest(records, cfg or Config(), START, END)


# --- detection ----------------------------------------------------------------

def test_cashtags_and_allcaps_with_stoplist():
    text = "ATH for $PEPE and BONK vs USD SOL BTC ETH CA TVL"
    assert tickers_in(text) == ["PEPE", "BONK"]
    assert "SOL" not in tickers_in("bought 12.5 SOL of $WIF")
    assert tickers_in("$abc") == ["ABC"]


def test_solana_and_evm_contract_detection():
    assert contracts_in(f"ca {CA1} and also {EVM}") == [EVM, CA1]
    assert contracts_in("short 7xKX not an address") == []
    assert contracts_in("0x1234") == []  # too short


def test_ticker_bound_to_ca_in_same_message_and_nearby():
    records = [
        rec("Alpha", [
            msg("Ann", 30, f"$PEPE {CA1}"),
            msg("Bob", 20, "this one is interesting"),
        ]),
        rec("Beta", [
            msg("Cara", 18, CA1),  # bare CA, ticker is in a nearby message
            msg("Dan", 17, "that's $PEPE"),
        ]),
    ]
    rows = mentions_from_records(records)
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "$PEPE"
    assert row["chats"] == 2 and row["mentions"] >= 3
    assert row["address_sightings"] >= 2 and row["distinct_addresses"] == 1
    blob = json.dumps(rows) + memecoin_line(row, {"start": START.isoformat(), "end": END.isoformat(),
                                                  "tz": "America/Los_Angeles"})
    assert CA1 not in blob


def test_name_next_to_ticker():
    records = [
        rec("Alpha", [msg("Ann", 10, f"Pepe ($PEPE) {CA1}")]),
        rec("Beta", [msg("Bob", 8, "$PEPE let's go")]),
    ]
    row = mentions_from_records(records)[0]
    assert row["ticker"] == "$PEPE"


# --- thresholds and spam ------------------------------------------------------

def test_two_chats_qualify_even_with_one_mention_each():
    records = [
        rec("Alpha", [msg("Ann", 10, "$BONK is moving")]),
        rec("Beta", [msg("Bob", 8, "looking at $BONK")]),
    ]
    rows = mentions_from_records(records)
    assert rows[0]["ticker"] == "$BONK" and rows[0]["chats"] == 2 and rows[0]["mentions"] == 2


def test_five_in_one_chat_needs_two_senders():
    spam = [msg("Spammer", 50 - i, f"$SPAM call {i}") for i in range(6)]
    assert mentions_from_records([rec("Only", spam)]) == []
    mixed = spam[:4] + [msg("Other", 10, "$SPAM maybe"), msg("Other", 9, "$SPAM again")]
    rows = mentions_from_records([rec("Only", mixed)])
    assert rows[0]["ticker"] == "$SPAM" and rows[0]["chats"] == 1 and rows[0]["mentions"] == 6


def test_one_chat_four_mentions_does_not_qualify():
    recs = [rec("Only", [msg("Ann", 10 - i, "$NOPE hi") for i in range(2)] +
                [msg("Bob", 5 - i, "$NOPE there") for i in range(2)])]
    assert mentions_from_records(recs) == []


def test_rank_by_chats_then_mentions():
    recs = [
        rec("A", [msg("Ann", 20, "$AAA"), msg("Bob", 19, "$BBB"), msg("Cara", 18, "$BBB")]),
        rec("B", [msg("Dan", 17, "$AAA")]),
        rec("C", [msg("Eve", 16, "$AAA")]),
    ]
    rows = mentions_from_records(recs)
    assert [r["ticker"] for r in rows] == ["$AAA"]
    assert rows[0]["chats"] == 3 and rows[0]["mentions"] == 3


# --- buys ---------------------------------------------------------------------

@pytest.mark.parametrize("text,expect", [
    ("bought 12.5 SOL", [(12.5, "SOL")]),
    ("Buy $3,200", [(3200.0, "USD")]),
    ("Buy $3.2k", [(3200.0, "USD")]),
    ("🟢 15 SOL", [(15.0, "SOL")]),
    ("15 SOL buy", [(15.0, "SOL")]),
    ("$3,200 buy", [(3200.0, "USD")]),
    ("bought $PEPE for 15 SOL", [(15.0, "SOL")]),
    ("sold 20 SOL", []),
    ("🔴 15 SOL", []),
    ("MCap: $3,200", []),
    ("MC: $2.5M", []),
    ("Whale bought 1210 $ABCX ($30k)", []),
    ("10 SOL", []),
    ("just $PEPE", []),
    ("swapped 20 SOL for $FAKEM", [(20.0, "SOL")]),
    ("swapped $FAKEM for 20 SOL", []),
    ("spent 12 SOL on $FAKEM", [(12.0, "SOL")]),
    ("🟢 Buy 12.5 SOL $FAKEM", [(12.5, "SOL")]),
])
def test_parse_buys(text, expect):
    assert parse_buys(text) == expect


def test_buy_thresholds_default_and_configurable():
    assert flagged_buys([(10, "SOL"), (9.9, "SOL"), (2000, "USD"), (1999, "USD")]) == \
        [(10, "SOL"), (2000, "USD")]
    cfg = Config(memecoin_buy_sol=50, memecoin_buy_usd=10_000)
    assert flagged_buys([(12.5, "SOL"), (5000, "USD")], cfg) == []
    assert flagged_buys([(50, "SOL"), (10_000, "USD")], cfg) == [(50, "SOL"), (10_000, "USD")]


def test_buy_only_needs_two_qualifying_buy_messages():
    recs = [rec("Alpha", [msg("Ann", 10, "🟢 bought 15 SOL of $WIF")])]
    assert mentions_from_records(recs) == []
    recs = [rec("Alpha", [msg("Ann", 10, "🟢 bought 15 SOL of $WIF"),
                          msg("Bob", 8, "spent 12 SOL on $WIF")])]
    rows = mentions_from_records(recs)
    assert rows[0]["ticker"] == "$WIF"
    assert rows[0]["biggest_buy"] == "15 SOL"
    assert rows[0]["chats"] == 1 and rows[0]["mentions"] == 2


def test_sub_threshold_buy_is_not_enough_on_its_own():
    recs = [rec("Alpha", [msg("Ann", 10, "bought 9 SOL of $WIF")])]
    assert mentions_from_records(recs) == []


# --- render / digest placement / disclaimer / redaction -----------------------

def test_section_after_needs_you_and_disclaimer_when_present():
    records = [
        rec("Work Group", [msg("Alice", 40, "thanks, looks good")]),
        rec("Alpha", [msg("Ann", 30, "$BONK here"), msg("Ann", 10, "🟢 bought 15 SOL of $BONK")]),
        rec("Beta", [msg("Bob", 20, "also $BONK")]),
    ]
    # add a needs-you item via mention flag
    records[0]["messages"][0]["mentions_me"] = True
    records[0]["messages"][0]["who"] = "Alice"
    d = digest(records)
    text = render(d)
    assert "Needs you" in text and "Memecoin mentions" in text
    assert text.index("Needs you") < text.index("Memecoin mentions")
    assert "Conversations" in text
    assert text.index("Memecoin mentions") < text.index("Conversations")
    assert "• $BONK —" in text
    assert "biggest reported buy: 15 SOL" in text
    assert "Alpha, Beta" in text
    assert text.rstrip().splitlines()[-1] == "Recap only, not financial advice."
    assert d["show_disclaimer"] is True


def test_empty_section_is_omitted_and_no_disclaimer_without_market():
    records = [rec("Book Club", [msg("Alice", 10, "we decided on the next book, see you Friday")])]
    d = digest(records)
    text = render(d)
    assert "Memecoin mentions" not in text
    assert "financial advice" not in text
    assert d["memecoin_mentions"] == []


def test_ca_never_appears_in_digest_or_render():
    records = [
        rec("Alpha", [msg("Ann", 20, f"$PEPE ca {CA1}")]),
        rec("Beta", [msg("Bob", 10, f"same token {CA1}")]),
    ]
    d = digest(records)
    text = render(d)
    blob = json.dumps(d) + text
    for bad in (CA1, EVM, "0x2222"):
        assert bad not in blob
    row = d["memecoin_mentions"][0]
    assert "same address seen" in memecoin_line(row, d["window"])
    assert CA1 not in memecoin_line(row, d["window"])


def test_unnamed_token_when_only_a_ca_is_known():
    recs = [
        rec("Alpha", [msg("Ann", 10, f"this {CA1}")]),
        rec("Beta", [msg("Bob", 8, f"same {CA1}")]),
    ]
    row = mentions_from_records(recs)[0]
    assert row["ticker"] == UNNAMED
    assert CA1 not in json.dumps(row)
    assert row["address_sightings"] == 2


def test_memecoin_only_render_is_silent_when_empty():
    d = digest([rec("Book Club", [msg("Alice", 10, "see you Friday")])])
    assert render(d, memecoin_only=True) == ""
    d2 = digest([
        rec("Alpha", [msg("Ann", 10, "$BONK")]),
        rec("Beta", [msg("Bob", 8, "$BONK")]),
    ])
    text = render(d2, memecoin_only=True)
    assert text.startswith("ChatBrief ·")
    assert "Memecoin mentions" in text
    assert "Needs you" not in text and "Conversations" not in text
    assert "Recap only, not financial advice." in text


def test_header_still_shows_both_dates_clearly():
    w = {"start": datetime(2026, 11, 10, 11, 20, tzinfo=timezone.utc).isoformat(),
         "end": datetime(2026, 11, 11, 11, 20, tzinfo=timezone.utc).isoformat(),
         "tz": "America/Los_Angeles"}
    assert header(w) == "ChatBrief · Nov 10, 3:20 AM to Nov 11, 3:20 AM PT"


# --- window / config / runner -------------------------------------------------

def test_parse_window():
    assert parse_window("1h") == 1 and parse_window("24h") == 24
    assert parse_window(None) is None
    with pytest.raises(ValueError):
        parse_window("0h")
    with pytest.raises(ValueError):
        parse_window("90m")


def test_window_for_override_and_memecoin_state_key():
    end = END
    st = {"last_recap_at": (end - timedelta(hours=3)).isoformat(),
          LAST_MEMECOIN_AT: (end - timedelta(hours=2)).isoformat()}
    start, got = C.window_for(st, Config(), end, hours=24)
    assert (got, got - start) == (end, timedelta(hours=24))
    start, _ = C.window_for(st, Config(), end, state_key=LAST_MEMECOIN_AT)
    assert start == end - timedelta(hours=2)
    start, _ = C.window_for({"salt": "s"}, Config(), end, state_key=LAST_MEMECOIN_AT, default_hours=1)
    assert start == end - timedelta(hours=1)


def test_settings_and_set_memecoin_roundtrip(tg_home):
    from types import SimpleNamespace as NS
    out, err = io.StringIO(), io.StringIO()
    rc = settings_cli.cmd_set(NS(name="memecoin-buy-sol", value=["25"]), out=out, err=err)
    assert rc == 0 and err.getvalue() == "" and "25 SOL" in out.getvalue()
    import sys
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        assert cli.cmd_set_memecoin(NS(buy_sol=None, buy_usd=5000)) == 0
    finally:
        sys.stdout = old
    assert "25 SOL" in buf.getvalue() and "$5,000" in buf.getvalue()
    c = config.load()
    assert (c.memecoin_buy_sol, c.memecoin_buy_usd) == (25.0, 5000.0)


def test_run_memecoin_only_does_not_advance_last_recap_at(tg_home):
    earlier = ago(60).isoformat()
    paths.write_json(paths.state_file(), {"salt": "s", "last_recap_at": earlier, "directory": {}})
    d1 = mkdialog(1, "Alpha", [Msg(1, "🟢 bought 15 SOL of $WIF", ago(30))])
    d2 = mkdialog(2, "Beta", [Msg(2, "$WIF here too", ago(20))])
    out, err = io.StringIO(), io.StringIO()

    def factory():
        return FakeClient([d1, d2])

    rc = runner.run(factory, now=NOW, out=out, err=err, memecoin_only=True)
    assert rc == 0 and err.getvalue() == ""
    text = out.getvalue()
    assert "Memecoin mentions" in text and "$WIF" in text
    assert "Conversations" not in text
    st = paths.read_json(paths.state_file())
    assert st["last_recap_at"] == earlier
    assert st[LAST_MEMECOIN_AT] == NOW.isoformat()
    assert not paths.recaps_dir().exists() or not any(paths.recaps_dir().iterdir())


def test_run_dry_run_alias_does_not_write_state(tg_home):
    earlier = ago(60).isoformat()
    paths.write_json(paths.state_file(), {"salt": "s", "last_recap_at": earlier, "directory": {}})
    before = paths.state_file().read_bytes()
    d = mkdialog(1, "Alpha", [Msg(1, "🟢 bought 20 SOL of $WIF", ago(30))])
    assert runner.run(lambda: FakeClient([d]), now=NOW, out=io.StringIO(), err=io.StringIO(),
                      peek=True, memecoin_only=True, window_hours=24) == 0
    assert paths.state_file().read_bytes() == before


def test_cli_flags(monkeypatch):
    seen = {}
    monkeypatch.setattr(runner, "run", lambda **k: seen.update(k) or 0)
    monkeypatch.setattr(cli, "require_telethon", lambda: None, raising=False)
    assert cli.main(["run", "--memecoin-only", "--window", "1h"]) == 0
    assert seen == {"peek": False, "memecoin_only": True, "window_hours": 1}
    seen.clear()
    assert cli.main(["run", "--dry-run", "--window", "24h"]) == 0
    assert seen == {"peek": True, "window_hours": 24}
    seen.clear()
    assert cli.main(["collect", "--peek", "--memecoin-only"]) == 0
    assert seen == {"as_json": True, "peek": True, "memecoin_only": True}


def test_metric_cards_are_not_buys():
    """Paraphrased whale/trending/bot cards: mcap/vol/fdv/liq are not buys."""
    cards = [
        "A whale bought 15 SOL of $FAKEM — MC $2.98B · FDV $176M · Vol $58.57M",
        "Trending alert $FAKEM  MCap: $51.2k  Holders: 1.1K  Liquidity: $9.8k",
        "New pair $FAKEM  MC $1.2M  Liq $80k  Vol $400k",
        "Watch card $FAKEM  market cap $2.98B  ATH $0.42  TVL $12M",
        "FDV $176M · volume $58.57M · cap $3.1B on $FAKEM",
    ]
    for text in cards:
        buys = parse_buys(text)
        assert all(u != "USD" or a < 10000 for a, u in buys), (text, buys)
    assert parse_buys(cards[0]) == [(15.0, "SOL")]
    assert parse_buys(cards[1]) == []
    assert parse_buys("bought $2.98B of $FAKEM") == []  # sanity cap
    assert parse_buys("bought 25000 SOL of $FAKEM") == []  # sanity cap


def test_format_buy_prefers_sol_and_drops_trailing_zeros():
    assert format_buy([(15.0, "SOL"), (3200.0, "USD")]) == "15 SOL"
    assert format_buy([(3200.0, "USD")]) == "$3,200"
    assert format_buy([(15.50, "SOL")]) == "15.5 SOL"
    assert format_buy([(1999.0, "USD")]) == "$1,999"


def test_address_count_hidden_when_only_one():
    records = [
        rec("Alpha", [msg("Ann", 20, "$PEPE ca " + CA1)]),
        rec("Beta", [msg("Bob", 10, "also $PEPE")]),
    ]
    d = digest(records)
    line = memecoin_line(d["memecoin_mentions"][0], d["window"])
    assert "same address seen" not in line
    records[1]["messages"][0]["text"] = "same token " + CA1
    d = digest(records)
    line = memecoin_line(d["memecoin_mentions"][0], d["window"])
    assert "same address seen 2×" in line


def test_table_short_tickers_are_filtered_and_cap_is_ten():
    board = "Board: $DEF $EXP $AXI $MAE $BAN $BLO $TRO $TRT $GT $FMO $COV $PHO $PDR $STB $BNK"
    recs = [
        rec("Trader Den", [msg("Board Bot", 10, board, bot=True)]),
        rec("Alpha Group", [msg("Board Bot", 10, board, bot=True)]),
    ]
    rows = mentions_from_records(recs)
    junk = {r["ticker"] for r in rows}
    for tok in ["$DEF", "$EXP", "$AXI", "$MAE", "$BAN", "$BLO", "$GT", "$BNK"]:
        assert tok not in junk
    # a real token mentioned on its own in two chats still lists, even if short
    recs[0]["messages"].append(msg("Ann", 8, "I like $DEF here"))
    recs[1]["messages"].append(msg("Bob", 7, "$DEF looking busy"))
    tickers = {r["ticker"] for r in mentions_from_records(recs)}
    assert "$DEF" in tickers


def test_section_caps_at_ten_and_shows_more():
    recs = []
    for i in range(12):
        tok = f"$TOK{i:02d}"
        recs.append(rec(f"ChatA{i}", [msg("Ann", 20, tok)]))
        recs.append(rec(f"ChatB{i}", [msg("Bob", 19, tok)]))
    text = render(digest(recs))
    assert text.count("• $TOK") == 10
    assert "…and 2 more" in text


def test_repeated_bot_posts_count_once():
    text = "🟢 bought 15 SOL of $WIF"
    recs = [rec("Lab", [msg("AlertBot", 10 - i, text, sender="bot-1", bot=True) for i in range(6)]
                + [msg("AlertBot", 3, "🟢 bought 12 SOL of $WIF", sender="bot-1", bot=True)])]
    # 6 identical posts collapse to 1, plus a second distinct buy -> qualifies
    rows = mentions_from_records(recs)
    assert rows[0]["ticker"] == "$WIF"
    assert rows[0]["mentions"] == 2


def test_stoplist_and_profanity_are_dropped():
    recs = [
        rec("Alpha", [msg("Ann", 10, "$HYPE $JUP $ZEC $FUCK")]),
        rec("Beta", [msg("Bob", 8, "$HYPE $JUP $ZEC $FUCK")]),
    ]
    tickers = {r["ticker"] for r in mentions_from_records(recs)}
    assert tickers == set()
    cfg = Config(memecoin_ticker_stop=["WIF"])
    recs = [
        rec("Alpha", [msg("Ann", 10, "$WIF $BONK")]),
        rec("Beta", [msg("Bob", 8, "$WIF $BONK")]),
    ]
    tickers = {r["ticker"] for r in mentions_from_records(recs, cfg)}
    assert tickers == {"$BONK"}
