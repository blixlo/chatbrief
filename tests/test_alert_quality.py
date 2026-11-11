"""v0.1.7 quality fixes, on synthetic data shaped like real alert bots (no real data).

All names, tickers and addresses below are made up. FAKE_ADDR is a random-looking
base58 string, not a real account.
"""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import NOW, Ent, FakeClient, Msg, ago, mkdialog
from tg_recap import __main__ as cli, alerts, collect as C, paths, runner
from tg_recap.config import Config
from tg_recap.readonly import ReadOnlyClient
from tg_recap.render import feed_line, render

ROOT = Path(__file__).resolve().parents[1]
FAKE_ADDR = "Fk3xQ9wZ7aB2cD4eF6gH8jK1mN5pR7sT9uV2wX4yZ6"
TRENDING = ("Trending Alert: Mindshare Radar TI\n"
            f"├ {FAKE_ADDR}\n"
            "├ Mindshare: 25.4%\n├ MCap: $51.2k\n├ Holders: 1.1K (10 whales)\n"
            "├ Liquidity: $9.8k\n└ Fresh Wallets: 3.80%\n#solana | Trade")
LAB_BOT = Ent(first_name="Sample Alert Bot #2", id=41, bot=True)
PERSON = Ent(first_name="Sample Person", id=42)


def _nosleep(_):
    async def n():
        return None
    return n()


def _collect(dialogs, cfg=None):
    import asyncio
    state = {"salt": "s", "last_recap_at": ago(60 * 12).isoformat()}
    client = ReadOnlyClient(FakeClient(dialogs), min_interval=0, sleep=_nosleep)
    return asyncio.run(C.collect(client, cfg or Config(), state, NOW))


def _bot_dm(name, bot, msgs):
    d = mkdialog(90, name, msgs)
    d.entity = bot
    return d


# --- 1. all-bot groups are feeds, one line per bot+chat --------------------------------

def test_group_with_only_bot_posts_is_a_feed_tied_to_the_chat():
    lab = mkdialog(80, "Sample Lab V2🤖", [Msg(1, TRENDING, ago(40), sender=LAB_BOT)])
    d = _collect([lab])
    assert d["conversations"] == []
    (feed,) = d["alert_feeds"]
    assert feed["name"] == "Sample Lab V2🤖" and feed["count"] == 1 and feed["source"] == "Sample Alert Bot #2"
    assert feed["noun"] == "trending alert" and feed["top"] == ["TI"]
    assert "• Sample Lab V2🤖: 1 trending alert from Sample Alert Bot #2 (TI)." in render(d)


def test_same_bot_in_group_and_dm_appears_once():
    lab = mkdialog(80, "Sample Lab V2🤖", [Msg(1, TRENDING, ago(40), sender=LAB_BOT)])
    dm = _bot_dm("Sample Alert Bot #2", LAB_BOT, [Msg(2, TRENDING, ago(40), sender=LAB_BOT)])
    d = _collect([lab, dm])
    assert [f["name"] for f in d["alert_feeds"]] == ["Sample Lab V2🤖"]
    assert render(d).count("Sample Alert Bot #2") == 1


def test_bot_dm_keeps_only_alerts_not_seen_in_the_group():
    lab = mkdialog(80, "Sample Lab V2🤖", [Msg(1, TRENDING, ago(40), sender=LAB_BOT)])
    dm = _bot_dm("Sample Alert Bot #2", LAB_BOT, [Msg(2, TRENDING, ago(40), sender=LAB_BOT),
                                                   Msg(3, "🐋 Whale bought 900 $FAKEW", ago(30), sender=LAB_BOT)])
    d = _collect([lab, dm])
    rows = {f["name"]: f for f in d["alert_feeds"]}
    assert rows["Sample Alert Bot #2"]["count"] == 1 and rows["Sample Alert Bot #2"]["noun"] == "whale alert"


def test_mixed_group_stays_a_conversation_and_bot_card_is_summarised():
    g = mkdialog(81, "Sample Traders", [Msg(1, "anyone around for the call at 5 pm?", ago(50), sender=PERSON),
                                        Msg(2, TRENDING, ago(40), sender=LAB_BOT)])
    d = _collect([g])
    (conv,) = d["conversations"]
    card = [m for m in conv["messages"] if m["who"] == "Sample Alert Bot #2"][0]
    assert card["text"] == "Trending alert (TI)" and card["summarized"] is True
    blob = json.dumps(d, ensure_ascii=False) + render(d)
    for junk in ("├", "└", "MCap", "Holders:", FAKE_ADDR):
        assert junk not in blob


# --- 2. no 'mostly' for one item or one ticker ----------------------------------------------

@pytest.mark.parametrize("count,top,expect", [
    (1, ["TI"], "• F: 1 trending alert (TI)."),
    (5, ["TI"], "• F: 5 trending alerts (TI)."),
    (1, ["AB", "CD"], "• F: 1 trending alert (AB, CD)."),
    (5, ["AB", "CD"], "• F: 5 trending alerts, mostly AB and CD."),
    (3, [], "• F: 3 trending alerts."),
])
def test_feed_line_mostly_rules(count, top, expect):
    noun = alerts.plural("trending alert", count)
    assert feed_line({"name": "F", "count": count, "noun": noun, "top": top}) == expect


# --- 3. ticker picker ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "CA: Fk3x…Z6aB", "QZXWVK…pump", "0x12ab…9f", "new: 0x12ab34cd", "AKPPUF… launched",
    "…Q9WZ7A", "token Fk3xQ9wZ7aB2", "ABC123DEF", "A1B2C3", "$A1B2C3", "XKCDQWERTYZ", "x/Fk3xQ9wZ7aB2cD4eF6gH8",
])
def test_address_like_strings_are_not_tickers(text):
    assert alerts.pick_tickers(text) == []


@pytest.mark.parametrize("text,expect", [
    ("$TI looks hot", ["TI"]), ("buy $bonk now", ["BONK"]), ("BONK and WIF up", ["BONK", "WIF"]),
    ("ABC2 listed", ["ABC2"]), ("$PEPE2 pair", ["PEPE2"]), ("($FAKEA)", ["FAKEA"]),
    ("$FAKEB then FAKEC", ["FAKEB", "FAKEC"]),
])
def test_real_tickers_are_kept(text, expect):
    assert alerts.pick_tickers(text) == expect


def test_top_tokens_ignore_stat_labels_and_fragments():
    texts = [f"🚨 Buy alert $FAKEA\n├ TVL: $5k\n├ CA: Fk3x…Z6aB", "🚨 Buy alert $FAKEA AKPPUF…pump"]
    assert C.top_tokens(texts) == ["FAKEA"]


# --- 4. nouns from the message pattern ----------------------------------------------------------

@pytest.mark.parametrize("texts,noun", [
    ([TRENDING] * 3, "trending alerts"),
    (["🐋 Whale bought 1200 $FAKEA"] * 2, "whale alerts"),
    (["Bought 3 SOL of $FAKEA", "Sold 2 SOL of $FAKEB"], "buy/sell alerts"),
    (["New pair: $FAKEN on example dex", "Just listed $FAKEM"], "new listings"),
    (["🚨 Alert: price moved"] * 2, "alerts"),
    (["Daily report ready", "Weekly report ready"], "automated posts"),
])
def test_feed_noun_from_messages(texts, noun):
    assert alerts.feed_noun(texts) == noun


def test_whale_name_does_not_make_whale_noun():
    bot = Ent(first_name="Whale Watch Bot", id=43, bot=True)
    feed = _bot_dm("Whale Watch", bot, [Msg(1, "New pair: $FAKEN on example dex", ago(20), sender=bot)])
    d = _collect([feed])
    assert d["alert_feeds"][0]["noun"] == "new listing"


# --- 5. glyphs, stat lines, boundaries ----------------------------------------------------------

def test_tidy_strips_glyphs_and_stat_lines():
    out = C.clean(TRENDING)
    assert out.startswith("Trending Alert: Mindshare Radar TI")
    assert not any(ch in out for ch in "├└│─┃") and "MCap" not in out and "Trade" not in out


def test_human_text_keeps_its_words():
    t = "ETA: 5 pm tomorrow, see you there.\nBring the slides."
    assert C.clean(t) == "ETA: 5 pm tomorrow, see you there. Bring the slides."


def test_fallback_never_quotes_a_bot_card():
    g = mkdialog(81, "Sample Traders", [Msg(1, "ok", ago(50), sender=PERSON),
                                        Msg(2, TRENDING, ago(40), sender=LAB_BOT)])
    text = render(_collect([g]))
    assert "Trending alert (TI)" in text and "Mindshare:" not in text and "├" not in text


def test_shorten_prefers_sentence_then_word_boundary():
    assert C.shorten("First sentence here. Second one is long and keeps going on", 30) == "First sentence here."
    assert C.shorten("alpha beta gamma delta", 14) == "alpha beta…"
    assert C.shorten("x" * 50 + " tail", 10) == "(long text)"
    assert C.shorten("abcdefghijkl rest", 10) == "abcdefghijkl…"


# --- 6. --peek ------------------------------------------------------------------------------------

def _factory(dialogs):
    def make():
        return FakeClient(dialogs)
    return make


def test_peek_reads_everything_and_writes_no_state(tg_home):
    d = mkdialog(1, "Team", [Msg(1, "@owner_handle can you check this?", ago(30))])
    out = io.StringIO()
    assert runner.run(_factory([d]), now=NOW, out=out, err=io.StringIO(), as_json=True, peek=True) == 0
    data = json.loads(out.getvalue())
    assert data["peek"] is True and data["needs_you"][0]["kind"] == "mention"
    assert not paths.state_file().exists()
    assert not paths.recaps_dir().exists() or not any(paths.recaps_dir().iterdir())


def test_peek_leaves_existing_state_byte_identical(tg_home):
    paths.write_json(paths.state_file(), {"salt": "s", "last_recap_at": ago(60).isoformat(), "directory": {}})
    before = paths.state_file().read_bytes()
    d = mkdialog(1, "Team", [Msg(1, "hello there", ago(30))])
    assert runner.run(_factory([d]), now=NOW, out=io.StringIO(), err=io.StringIO(), peek=True) == 0
    assert paths.state_file().read_bytes() == before
    assert runner.run(_factory([d]), now=NOW, out=io.StringIO(), err=io.StringIO()) == 0
    assert paths.read_json(paths.state_file())["last_recap_at"] == NOW.isoformat()


@pytest.mark.parametrize("argv,kw", [(["collect", "--peek"], {"as_json": True, "peek": True}),
                                     (["run", "--peek"], {"peek": True}),
                                     (["collect"], {"as_json": True, "peek": False})])
def test_cli_peek_flag(monkeypatch, argv, kw):
    seen = {}
    monkeypatch.setattr(runner, "run", lambda **k: seen.update(k) or 0)
    monkeypatch.setattr(cli, "require_telethon", lambda: None, raising=False)
    assert cli.main(argv) == 0
    assert seen == kw


# --- 9. bare pytest finds tg_recap ----------------------------------------------------------------

def test_bare_pytest_imports_package_without_install():
    if sys.version_info < (3, 11):
        pytest.skip("-P needs Python 3.11+")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    probe = ("import sys, pytest; sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', "
             "'tests/test_redact.py']))")
    p = subprocess.run([sys.executable, "-P", "-c", probe], cwd=ROOT, env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout[-400:] + p.stderr[-400:]
