---
name: telegram-recap-code-tests
description: 'Test suite for ChatBrief - extract after telegram-recap-code, with the same extractor and sha256 checks.'
---
# ChatBrief tests

The offline test suite (`tests/`) for the source in `telegram-recap-code`. Extract both skills into the same directory with the extractor embedded in `telegram-recap-code`:

    python3 extract_code_skill.py <telegram-recap-code SKILL.md> <this SKILL.md> <target-dir>

Every file below carries its sha256; a mismatch stops the extract before anything is written. The tests need nothing beyond `requirements-dev.txt` and never touch the network.

## Files

### file: tests/conftest.py
sha256: 20e4f70998a0c083ed450e2ec0c738d4cce425055048eb8c131aaf8a2cc8510f
~~~~~
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
~~~~~

### file: tests/login_fakes.py
sha256: b97e1fbc5d2418edd67494d3e2d545a959b36da07d590bcebd501937b7341cec
~~~~~
"""Offline stand-ins for Telethon's login errors. login_backend maps errors by
type name (as readonly.py does for FloodWaitError), so these need no network."""


class _TgErr(Exception):
    def __init__(self, *args):  # like Telethon, str() never includes request values
        super().__init__("The request was rejected (caused by a login request)")


class SessionPasswordNeededError(_TgErr):
    pass


class PhoneCodeInvalidError(_TgErr):
    pass


class PhoneCodeExpiredError(_TgErr):
    pass


class PasswordHashInvalidError(_TgErr):
    pass


class PhoneNumberInvalidError(_TgErr):
    pass


class FloodWaitError(_TgErr):
    def __init__(self, seconds):
        super().__init__()
        self.seconds = seconds
~~~~~

### file: tests/test_alert_quality.py
sha256: 1df6614dc77f5308013540793f61ab938b71efe4e16416a662639e31c157ed40
~~~~~
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
~~~~~

### file: tests/test_branding.py
sha256: 36123b05e654afad9f9e7a49cd0906821c552e8ae6aa816fccb0b5fd0d043ac6
~~~~~
"""Product name and Telegram API terms 2.2-2.4, checked against tg_recap.branding.PRODUCT_NAME.

- 2.3: every product title (README/skill headings, CLI help, sign-in pages, recap
  header) equals PRODUCT_NAME, which must not contain "Telegram"; no leftover old
  title (the earlier "Unofficial Telegram ..." name) anywhere user-facing.
- 2.2: the disclosure sentence is in the README, the skill copies and the sign-in UIs.
- 2.4: no logo or icon files, and no image tags in docs or pages.
Internal ids stay as they are: the tg_recap package and skill slugs like telegram-recap-code.
"""
import contextlib
import importlib.util
import io
import re
import shutil
from pathlib import Path

import pytest

from tg_recap import __main__ as cli, login_terminal, login_web
from tg_recap.branding import PRODUCT_NAME
from tg_recap.consent import DISCLOSURE
from tg_recap.render import header, render
from tg_recap.sample import sample_digest, sample_text

ROOT = Path(__file__).resolve().parents[1]
# built in pieces so this file (embedded in the tests skill) doesn't match itself
OLD_TITLE = re.compile("(?:unofficial" + r"\s+)?" + "telegram" + r"[\s_]+" + "recap(?:" + r"\s+" + "agent)?", re.I)
IMAGE = re.compile(r"!\[[^\]\n]*\]\([^)\n]+\)|<img\b|<svg\b|rel=['\"]?(?:shortcut )?icon", re.I)


def leftovers(text: str) -> list[str]:
    return [text[max(0, m.start() - 30): m.end() + 10] for m in OLD_TITLE.finditer(text)]


def user_facing_files() -> list[Path]:
    files = [ROOT / "README.md", ROOT / "install.sh", *sorted((ROOT / "docs").glob("*.md")),
             *sorted((ROOT / "skills").glob("*/SKILL.md")), *sorted((ROOT / "tg_recap").glob("*.py")),
             *sorted((ROOT / "tools").glob("*.py"))]
    return [f for f in files if f.is_file()]


def _rel(p):
    return p.relative_to(ROOT).as_posix()


def test_product_name_has_no_telegram():
    assert PRODUCT_NAME.strip() == PRODUCT_NAME and "telegram" not in PRODUCT_NAME.casefold()


@pytest.mark.parametrize("path", user_facing_files(), ids=_rel)
def test_no_old_title_in_user_facing_files(path):
    assert leftovers(path.read_text(encoding="utf-8")) == []


def _titles(md: str) -> list[str]:
    return [line[2:].strip() for line in md.splitlines() if line.startswith("# ")]


def test_readme_and_skill_titles_are_product_name():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert _titles(readme)[0] == PRODUCT_NAME
    for f in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = f.read_text(encoding="utf-8")
        title = _titles(text)[0]
        assert title.split(":")[0].split(" ")[0] == PRODUCT_NAME, _rel(f)
        assert "telegram" not in title.casefold(), _rel(f)
        desc = re.search(r"^description: (.*)$", text, re.M).group(1)
        assert PRODUCT_NAME in desc, _rel(f)


def _help(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        cli.main(argv)
    return buf.getvalue()


def test_cli_title_sign_in_titles_and_recap_header():
    desc = _help(["--help"]).split("\n\n")[1].strip()
    assert desc.split(" (")[0] == PRODUCT_NAME
    for argv in (["--help"], ["consent", "--help"], ["collect", "--help"], ["login", "--help"]):
        assert leftovers(_help(argv)) == []
    assert login_terminal.INTRO.splitlines()[0] == f"{PRODUCT_NAME}: sign in"

    class Flow:
        step, error, token = "api", "", "t"
    page = login_web.page(Flow())
    assert re.search(r"<h1>(.*?)</h1>", page).group(1) == PRODUCT_NAME
    assert re.search(r"<title>(.*?)</title>", page).group(1).split(":")[0] == PRODUCT_NAME
    d = sample_digest()
    assert header(d["window"]).split(" · ")[0] == PRODUCT_NAME
    assert render(d).split(" · ")[0] == PRODUCT_NAME and leftovers(sample_text()) == []


def test_disclosure_is_verbatim_where_users_see_it():
    assert DISCLOSURE == (f"{PRODUCT_NAME} is an unofficial app that works alongside Telegram. It uses the Telegram API "
                          "and is not affiliated with or endorsed by Telegram.")
    assert DISCLOSURE in (ROOT / "README.md").read_text(encoding="utf-8")
    assert DISCLOSURE in login_terminal.INTRO and DISCLOSURE in login_web.PRIVACY
    for slug in ("setup", "getting-started", "run"):
        f = ROOT / "skills" / f"telegram-recap-{slug}" / "SKILL.md"
        if f.is_file():
            assert DISCLOSURE in f.read_text(encoding="utf-8"), slug


# the v0.1.8 wording, built in pieces so this file doesn't contain it
OLD_DISCLOSURE = re.compile("unofficial app " + "for Telegram", re.I)


@pytest.mark.parametrize("path", user_facing_files() + sorted((ROOT / "tests").glob("*.py")), ids=_rel)
def test_old_disclosure_wording_is_gone(path):
    assert not OLD_DISCLOSURE.search(path.read_text(encoding="utf-8"))


def test_disclosure_is_one_constant_used_by_code_and_skills():
    from tg_recap import branding, consent
    assert consent.DISCLOSURE is branding.DISCLOSURE
    assert consent.WARNING.splitlines()[0] == DISCLOSURE
    assert "part of the Telegram " + "ecosystem" not in DISCLOSURE
    for rel in ("skills/telegram-recap-code/SKILL.md",):
        f = ROOT / rel
        if f.is_file():
            assert DISCLOSURE in f.read_text(encoding="utf-8")[:3000], rel


def test_no_logo_or_icon():
    skip = {".git", ".venv", "__pycache__", ".pytest_cache"}
    for p in ROOT.rglob("*"):
        if skip & set(p.relative_to(ROOT).parts):
            continue
        assert p.suffix.lower() not in {".png", ".svg", ".ico", ".jpg", ".jpeg", ".gif", ".webp"}, _rel(p)
    for f in user_facing_files():  # generated code skills only embed the files checked here
        if f.suffix == ".md" and not f.parent.name.startswith("telegram-recap-code"):
            assert not IMAGE.search(f.read_text(encoding="utf-8")), _rel(f)

    class Flow:
        step, error, token = "api", "", "t"
    assert not IMAGE.search(login_web.page(Flow()))


def test_old_title_is_caught():
    for bad in ("Welcome to " + "Telegram" + " Recap", "Unofficial " + "Telegram" + " Recap setup",
                "telegram" + " recap " + "agent"):
        assert leftovers(bad) != []
    assert leftovers(f"{PRODUCT_NAME}, a recap of your Telegram chats; slug telegram-recap-code") == []


def test_rename_is_one_constant_plus_apply_branding(tmp_path):
    tool = ROOT / "tools" / "apply_branding.py"
    if not tool.is_file():
        pytest.skip("tools/ is not part of the extracted copy")
    spec = importlib.util.spec_from_file_location("apply_branding", tool)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "tg_recap").mkdir()
    (tmp_path / "skills" / "telegram-recap-run").mkdir(parents=True)
    (tmp_path / "tg_recap" / "branding.py").write_text('PRODUCT_NAME = "SampleName"\n')
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    shutil.copy(ROOT / "skills" / "telegram-recap-run" / "SKILL.md", tmp_path / "skills" / "telegram-recap-run" / "SKILL.md")
    with contextlib.redirect_stdout(io.StringIO()):
        assert mod.main(["--from", PRODUCT_NAME], root=tmp_path) == 0
    for f in (tmp_path / "README.md", tmp_path / "skills" / "telegram-recap-run" / "SKILL.md"):
        text = f.read_text()
        assert "SampleName" in text and PRODUCT_NAME not in text
    spec = importlib.util.spec_from_file_location("build_code_skill", ROOT / "tools" / "build_code_skill.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    assert b.product_name(tmp_path) == "SampleName" and b.product_name(ROOT) == PRODUCT_NAME
~~~~~

### file: tests/test_code_skill.py
sha256: 29414c05ba50e38507d4d16cbc6952d5b0964f70331e8e709fd15435e74394da
~~~~~
"""The generated code skills (telegram-recap-code + telegram-recap-code-tests) must match the repo."""
from __future__ import annotations

import importlib.util
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "telegram-recap-code" / "SKILL.md"
TESTS_SKILL = ROOT / "skills" / "telegram-recap-code-tests" / "SKILL.md"
BUILDER = ROOT / "tools" / "build_code_skill.py"
EXTRACTOR = ROOT / "tools" / "extract_code_skill.py"

SKIP_NO_SKILL = (
    "skills/telegram-recap-code/SKILL.md is absent "
    "(extracted copy without the skills tree)"
)


def _require_skill() -> None:
    if not SKILL.is_file() or not BUILDER.is_file():
        pytest.skip(SKIP_NO_SKILL)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_code_skills_are_up_to_date_and_under_budget():
    _require_skill()
    builder = _load(BUILDER, "build_code_skill")
    for skill, path in ((builder.CODE, SKILL), (builder.TESTS, TESTS_SKILL)):
        generated = builder.render_skill(ROOT, skill)
        if generated != path.read_text(encoding="utf-8"):
            pytest.fail(f"{path.relative_to(ROOT)} is out of date. Regenerate: python3 tools/build_code_skill.py")
        assert len(generated.encode()) <= builder.SIZE_LIMIT
    code = set(builder.listed_files(ROOT, builder.CODE))
    tests = set(builder.listed_files(ROOT, builder.TESTS))
    assert not code & tests and all(t.startswith("tests/") for t in tests)
    assert code | tests == set(builder.listed_files(ROOT))


def test_extractor_restores_repo_files_from_both_skills(tmp_path):
    _require_skill()
    ex = _load(EXTRACTOR, "extract_code_skill")
    dest = tmp_path / "out"
    ex.main([str(SKILL), str(TESTS_SKILL), str(dest)])
    builder = _load(BUILDER, "build_code_skill")
    for rel in builder.listed_files(ROOT):
        assert (dest / rel).read_bytes() == (ROOT / rel).read_bytes(), rel
    assert (dest / "install.sh").stat().st_mode & stat.S_IXUSR


def test_extractor_refuses_a_tampered_tests_skill(tmp_path):
    _require_skill()
    ex = _load(EXTRACTOR, "extract_code_skill")
    bad = tmp_path / "SKILL.md"
    bad.write_text(TESTS_SKILL.read_text(encoding="utf-8").replace("def test_", "def tset_", 1), encoding="utf-8")
    with pytest.raises(SystemExit):
        ex.main([str(SKILL), str(bad), str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()
~~~~~

### file: tests/test_collect_render.py
sha256: 5d62211ca59edd6200334b95bbc3d8397fb38ab4f40b3319533052adcd7c489c
~~~~~
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


def test_only_included_chats_is_an_allow_list_and_skips_reading_the_rest():
    dialogs = world()
    wk, whale = C.chat_key(dialogs[0], "s"), C.chat_key(dialogs[5], "s")
    rules = {wk: {"title": "Work Group", "rule": "include"}, whale: {"title": "Whale Watch", "rule": "count-only"}}
    d, fake, _ = collect(world(), Config(chat_rules=rules, only_included_chats=True))
    assert names(d["conversations"]) == ["Work Group"] and d["count_only"][0]["name"] == "Whale Watch"
    assert d["also_active"] == [] and d["alert_feeds"] == [] and "Muted Group" not in json.dumps(d)
    assert fake.calls.count("iter_messages") == 2  # only the two included chats are read
    # off: everything is covered as before
    d, fake, _ = collect(world(), Config(chat_rules=rules))
    assert fake.calls.count("iter_messages") > 2
    # on with no include rules: nothing is covered
    d, fake, _ = collect(world(), Config(only_included_chats=True))
    assert d["conversations"] == [] and d["also_active"] == [] and fake.calls.count("iter_messages") == 0
    # skip still wins, and a chat that appears later stays out
    rules[wk]["rule"] = "skip"
    d, _, _ = collect(world(), Config(chat_rules=rules, only_included_chats=True))
    assert "Work Group" not in json.dumps(d)
    late = mkdialog(9, "Late Joined", [Msg(90, "hello there", ago(5), sender=BOB)])
    d, _, _ = collect(world() + [late], Config(chat_rules=rules, only_included_chats=True))
    assert "Late Joined" not in json.dumps(d)


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
~~~~~

### file: tests/test_config.py
sha256: 1a4d40fba7331b12f1ca055c18a56b2a2f46e860518fad7eaea2d8cafc669587
~~~~~
import os

import pytest

from tg_recap import config, paths
from tg_recap.config import Config


def test_default_is_daily_la():
    c = config.load()
    assert c.frequency == "daily" and c.timezone == "America/Los_Angeles"
    assert config.cron_for(c) == "0 8 * * *" and config.plan_warning(c) is None


@pytest.mark.parametrize("freq,hours,cron", [
    ("4h", None, "0 */4 * * *"), ("hourly", None, "0 * * * *"),
    ("custom", 1, "0 * * * *"), ("custom", 6, "0 */6 * * *"),
    ("custom", 24, "0 8 * * *"), ("custom", 48, "0 8 */2 * *"),
])
def test_cron_strings(freq, hours, cron):
    assert config.cron_for(Config(frequency=freq, custom_hours=hours)) == cron


def test_hourly_warning_text():
    assert config.plan_warning(Config(frequency="hourly")) == \
        "runs about 24 times a day and uses more of your Grok Bot plan"
    assert config.plan_warning(Config(frequency="custom", custom_hours=1)) == config.PLAN_WARNING
    assert config.plan_warning(Config(frequency="4h")) is None


@pytest.mark.parametrize("bad", [0, -3, 0.5])
def test_custom_floor_is_one_hour(bad):
    with pytest.raises(ValueError):
        Config(frequency="custom", custom_hours=bad).validate()


def test_save_load_roundtrip_and_perms(tg_home):
    config.save(Config(frequency="custom", custom_hours=3, timezone="Europe/Berlin"))
    c = config.load()
    assert (c.frequency, c.custom_hours, c.timezone) == ("custom", 3, "Europe/Berlin")
    assert oct(os.stat(paths.settings_file()).st_mode & 0o777) == "0o600"


def test_bad_timezone_rejected():
    with pytest.raises(Exception):
        Config(timezone="Not/AZone").validate()
~~~~~

### file: tests/test_consent.py
sha256: b573b652fb924c6429cbd5879663903ec22f67d5072493a3d848b9c53a7c7225
~~~~~
"""Telegram API terms 1.5 consent gate: sign-in, collect and run refuse (exit 9) until accepted."""
import contextlib
import io
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from conftest import NOW, FakeClient, Msg, ago, mkdialog
from tg_recap import __main__ as cli, config, consent, login_cards, login_terminal, login_web, paths, runner

ROOT = Path(__file__).resolve().parents[1]
ENV = {"TG_RECAP_API_ID": "7654321", "TG_RECAP_API_HASH": "sentinel-consent-api-hash-01"}


def _never():
    raise AssertionError("must not touch Telegram before consent")


def _one_line(err: str):
    lines = err.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("CONSENT_REQUIRED:") and "consent accept" in lines[0]


def test_save_api_refuses_without_consent(tg_home, no_consent):
    err = io.StringIO()
    assert login_cards.login("save-api", env=ENV, client_factory=_never, out=io.StringIO(), err=err) == 9
    _one_line(err.getvalue())
    assert not paths.credentials_file().exists()


def test_every_card_step_but_reset_needs_consent(tg_home, no_consent):
    for step in login_cards.STEPS:
        rc = login_cards.login(step, env=ENV, client_factory=_never, out=io.StringIO(), err=io.StringIO())
        assert (rc != 9) if step == "reset" else (rc == 9), step


def test_terminal_and_web_login_refuse_without_consent(tg_home, no_consent, capsys):
    def no_input(*_a, **_k):
        raise AssertionError("prompted before consent")
    err = io.StringIO()
    assert login_terminal.login(backend=object(), input_fn=no_input, getpass_fn=no_input,
                                out=io.StringIO(), err=err) == 9
    _one_line(err.getvalue())
    assert login_web.serve(port=0, backend=object()) == 9
    _one_line(capsys.readouterr().err)


@pytest.mark.parametrize("as_json", [True, False])
def test_collect_and_run_refuse_without_consent(tg_home, no_consent, as_json):
    out, err = io.StringIO(), io.StringIO()
    assert runner.run(_never, now=NOW, out=out, err=err, as_json=as_json) == consent.EXIT_CONSENT == 9
    assert out.getvalue() == ""
    _one_line(err.getvalue())
    assert not paths.state_file().exists()


def test_after_accept_everything_works(tg_home, no_consent):
    rec = consent.accept(NOW)
    assert login_cards.login("save-api", env=ENV, client_factory=_never, out=io.StringIO(), err=io.StringIO()) == 0
    d = mkdialog(1, "Team", [Msg(1, "@owner_handle can you check this?", ago(30))])
    out = io.StringIO()
    assert runner.run(lambda: FakeClient([d]), now=NOW, out=out, err=io.StringIO(), as_json=True) == 0
    assert json.loads(out.getvalue())["needs_you"]
    assert rec["terms_version"] == consent.TERMS_VERSION


def test_settings_holds_only_the_two_keys_mode_600(tg_home, no_consent):
    consent.accept(NOW)
    f = paths.settings_file()
    data = json.loads(f.read_text())
    assert set(data) == {"tos_1_5_accepted_at", "terms_version"}
    assert datetime.fromisoformat(data["tos_1_5_accepted_at"]) == NOW
    assert data["terms_version"] == consent.TERMS_VERSION
    assert oct(os.stat(f).st_mode & 0o777) == "0o600"


def test_accept_keeps_existing_settings_and_save_keeps_consent(tg_home, no_consent):
    cfg = config.load()
    cfg.length = "short"
    config.save(cfg)
    consent.accept(NOW)
    assert config.load().length == "short"
    cfg = config.load()
    cfg.length = "detailed"
    config.save(cfg)
    assert consent.accepted() and config.load().length == "detailed"


def test_consent_only_settings_still_reads_legacy_config(tg_home, no_consent):
    paths.write_json(paths.config_file(), {"frequency": "4h", "timezone": "Europe/Berlin"})
    consent.accept(NOW)
    c = config.load()
    assert (c.frequency, c.timezone) == ("4h", "Europe/Berlin")


def test_old_terms_version_asks_again(tg_home, no_consent):
    paths.write_json(paths.settings_file(), {"tos_1_5_accepted_at": NOW.isoformat(), "terms_version": "old"})
    assert not consent.accepted()


def test_cli_consent_show_and_accept(tg_home, no_consent):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert cli.main(["consent", "show"]) == 0
    text = buf.getvalue()
    assert consent.DISCLOSURE in text and f"\"{consent.CLAUSE}\"" in text and "not accepted yet" in text
    with contextlib.redirect_stdout(io.StringIO()):
        assert cli.main(["consent", "accept"]) == 0
    assert consent.accepted()


def test_warning_says_the_required_things():
    w = consent.WARNING
    assert w.startswith(consent.DISCLOSURE)
    assert consent.DISCLOSURE == ("ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API "
                                  "and is not affiliated with or endorsed by Telegram.")
    assert consent.CLAUSE.startswith("you are prohibited from using, accessing or aggregating data")
    for must in ("AI agent that reads your chats", "may consider that against its API terms",
                 "cut off that app's access to the Telegram API", "never trains on your chats", "own risk"):
        assert must in w


def test_skills_and_readme_carry_disclosure_warning_and_private_note():
    priv = "Source code: https://github.com/blixlo/chatbrief. No license is granted; all rights reserved."
    readme = (ROOT / "README.md").read_text()
    assert consent.DISCLOSURE in readme and priv in readme
    setup = ROOT / "skills" / "telegram-recap-setup" / "SKILL.md"
    if not setup.is_file():
        pytest.skip("skills/ is not part of the extracted copy")
    s = setup.read_text()
    step1 = s[s.index("\n1. "): s.index("\n2. ")]
    for line in consent.WARNING.splitlines():
        if line:
            assert line in step1, line
    assert step1.index(consent.CLAUSE) < step1.index("./install.sh") < s.index("TG_RECAP_API_ID")
    gs = (ROOT / "skills" / "telegram-recap-getting-started" / "SKILL.md").read_text()
    body = gs.split("---", 2)[2]
    assert body.lstrip().split("\n", 2)[2].lstrip().startswith(f"**{consent.DISCLOSURE}**") and priv in gs
    run = (ROOT / "skills" / "telegram-recap-run" / "SKILL.md").read_text()
    assert "Exit 9 `CONSENT_REQUIRED`" in run and "explicit yes" in run and "consent accept" in run
~~~~~

### file: tests/test_deps.py
sha256: a0612c8c9ea8626c0f4c09dfd5c0e1a7ca9015c5e140cf56e20ee169a8e9fe89
~~~~~
"""CLI dependency check: missing Telethon exits 6 with one line, no traceback."""
import os
import subprocess
import sys
from pathlib import Path

from tg_recap.deps import EXIT_MISSING_DEPS, TELETHON_VERSION, missing_telethon_message

ROOT = Path(__file__).resolve().parents[1]

# Hide an already-installed Telethon so this test works under a full venv too.
_HIDE = (
    "import sys\n"
    "sys.modules['telethon'] = None\n"
    "for name in list(sys.modules):\n"
    "    if name.startswith('telethon.'):\n"
    "        del sys.modules[name]\n"
)


def _run(code: str):
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-c", _HIDE + code],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )


def test_missing_telethon_message_names_this_python():
    msg = missing_telethon_message()
    assert f"Telethon {TELETHON_VERSION} isn't installed for this Python ({sys.executable})." in msg
    assert f"Run: {sys.executable} -m pip install -r requirements.txt" in msg


def test_cli_status_without_telethon_exits_6():
    p = _run("from tg_recap.__main__ import main; raise SystemExit(main(['status']))")
    assert p.returncode == EXIT_MISSING_DEPS
    assert p.stdout == ""
    assert p.stderr.strip() == missing_telethon_message()
    assert "Traceback" not in p.stderr


def test_cli_help_works_without_telethon():
    p = _run("from tg_recap.__main__ import main; raise SystemExit(main(['--help']))")
    assert p.returncode == 0
    assert "status" in p.stdout
    assert p.stderr == ""


def test_cli_without_websockets_exits_6():
    from tg_recap.deps import missing_websockets_message
    hide = ("import sys\nsys.modules['websockets'] = None\n"
            "for n in list(sys.modules):\n    if n.startswith('websockets.'):\n        del sys.modules[n]\n")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    p = subprocess.run([sys.executable, "-c", hide + "from tg_recap.__main__ import main; "
                        "raise SystemExit(main(['status']))"], cwd=ROOT, env=env, capture_output=True, text=True)
    if p.returncode != EXIT_MISSING_DEPS and "Telethon" in p.stderr:
        import pytest
        pytest.skip("Telethon itself is missing here")
    assert p.returncode == EXIT_MISSING_DEPS and p.stdout == ""
    assert p.stderr.strip() == missing_websockets_message() and "Traceback" not in p.stderr
~~~~~

### file: tests/test_lock.py
sha256: 405962cccea7c79f27b1af7fc0b6af091e8b1cb37c417c99a87adfaa7f7ccae9
~~~~~
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tg_recap import paths
from tg_recap.lock import LockHeld, SessionLock

ROOT = Path(__file__).resolve().parents[1]


def test_second_process_cannot_take_lock(tg_home):
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import time,sys; from tg_recap.lock import SessionLock; l=SessionLock().acquire(); "
         "print('held', flush=True); time.sleep(30)"],
        cwd=ROOT, env={**os.environ, "TG_RECAP_HOME": str(tg_home)}, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(LockHeld):
            SessionLock().acquire()
        assert SessionLock().is_held_elsewhere()
    finally:
        holder.kill()
        holder.wait()
    lock = SessionLock().acquire()  # free again once the holder is gone
    lock.release()


def test_lock_file_is_owner_only(tg_home):
    with SessionLock():
        assert oct(os.stat(paths.lock_file()).st_mode & 0o777) == "0o600"
        assert oct(os.stat(tg_home).st_mode & 0o777) == "0o700"
~~~~~

### file: tests/test_login.py
sha256: f5be95c8a01a4448ee0e6374b80292da746e7a37a1cbd1abafa1a33f2209bed1
~~~~~
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
~~~~~

### file: tests/test_login_cards.py
sha256: c51abc362e1cde40afb944284fce54571d0de7592ce305227fd38a951ccfe6c2
~~~~~
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
~~~~~

### file: tests/test_login_terminal.py
sha256: e0a408cd1b2eaafca8f5e31db93982d664e07dde8c7a4e55c30c646152444eff
~~~~~
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
~~~~~

### file: tests/test_memecoin.py
sha256: cc32f463e100b66b9eeb12bb9243f4852096662fca3af69fdf693ed63d20eceb
~~~~~
"""Memecoin mention detection, thresholds, spam discount, public CA display, buy parsing."""
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
    parse_buys, parse_window, tickers_in, token_cas_in,
)
from tg_recap.render import header, memecoin_line, render
from conftest import NOW, FakeClient, Msg, ago, mkdialog

CA1 = "FAKE111111111111111111111111111111111111111"
CA2 = "FAKE222222222222222222222222222222222222222"
EVM = "0x2222222222222222222222222222222222222222"
PUMP = "FakeMint11111111111111111111111111pump"
WALLET = "WALLET11111111111111111111111111111111111"
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
    assert row["ca"] == CA1 and row["ca_sightings"] >= 2
    line = memecoin_line(row, {"start": START.isoformat(), "end": END.isoformat(),
                               "tz": "America/Los_Angeles"})
    assert CA1 in line and f"CA `{CA1}`" in line


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


def test_public_ca_appears_in_digest_and_render_by_default():
    records = [
        rec("Alpha", [msg("Ann", 20, f"$PEPE ca {CA1}")]),
        rec("Beta", [msg("Bob", 10, f"same token {CA1}")]),
    ]
    d = digest(records)
    text = render(d)
    row = d["memecoin_mentions"][0]
    assert row["ca"] == CA1
    line = memecoin_line(row, d["window"])
    assert f"$PEPE · CA `{CA1}` (seen 2×)" in line
    assert CA1 in text
    assert "same address seen" not in line
    # other recap redaction still holds
    assert EVM not in text


def test_unnamed_token_listed_under_its_ca():
    recs = [
        rec("Alpha", [msg("Ann", 10, f"this {CA1}")]),
        rec("Beta", [msg("Bob", 8, f"same {CA1}")]),
    ]
    row = mentions_from_records(recs)[0]
    assert row["ticker"] == UNNAMED
    assert row["ca"] == CA1 and row["ca_sightings"] == 2
    assert CA1 in json.dumps(row)
    line = memecoin_line(row, {"start": START.isoformat(), "end": END.isoformat(),
                               "tz": "America/Los_Angeles"})
    assert line.startswith(f"• CA `{CA1}` (seen 2×) —")
    assert "Unnamed token" not in line


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


def test_ca_shown_even_when_seen_once_and_multiple_cas_noted():
    records = [
        rec("Alpha", [msg("Ann", 20, "$PEPE ca " + CA1)]),
        rec("Beta", [msg("Bob", 10, "also $PEPE")]),
    ]
    d = digest(records)
    row = d["memecoin_mentions"][0]
    line = memecoin_line(row, d["window"])
    assert row["ca"] == CA1 and row["ca_sightings"] == 1
    assert f"CA `{CA1}` (seen 1×)" in line
    assert "same address seen" not in line
    records[1]["messages"][0]["text"] = "$PEPE ca " + CA2
    d = digest(records)
    row = d["memecoin_mentions"][0]
    line = memecoin_line(row, d["window"])
    # two different CAs, each seen once; most-seen is stable by Counter order of first max
    assert row["ca"] in (CA1, CA2) and row["other_cas"] == 1
    assert f"+1 other CA seen" in line
    assert CA1 in line or CA2 in line


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


def test_show_ca_setting_off_hides_addresses():
    records = [
        rec("Alpha", [msg("Ann", 20, f"$PEPE ca {CA1}")]),
        rec("Beta", [msg("Bob", 10, f"same token {CA1}")]),
    ]
    cfg = Config(memecoin_show_ca=False)
    rows = mentions_from_records(records, cfg)
    row = rows[0]
    assert "ca" not in row
    assert CA1 not in json.dumps(rows)
    line = memecoin_line(row, {"start": START.isoformat(), "end": END.isoformat(),
                               "tz": "America/Los_Angeles"})
    assert CA1 not in line
    assert "same address seen 2×" in line
    text = render(digest(records, cfg))
    assert CA1 not in text
    assert "same address seen 2×" in text


def test_token_context_and_wallet_exclusion():
    assert token_cas_in(f"$PEPE ca {CA1}") == [CA1]
    assert token_cas_in(f"https://dexscreener.com/solana/{CA1}") == [CA1]
    assert token_cas_in(f"https://pump.fun/{PUMP}") == [PUMP]
    assert token_cas_in(f"chart https://birdeye.so/token/{CA1}?chain=solana") == [CA1]
    assert token_cas_in(f"see https://solscan.io/token/{EVM}") == [EVM]
    assert PUMP in token_cas_in(f"new mint {PUMP}")  # pump suffix counts with no label
    assert token_cas_in(f"wallet {WALLET} bought 15 SOL of $PEPE") == []
    assert WALLET not in token_cas_in(f"sent to {WALLET}")
    # ticker + token CA in one message, buyer wallet hidden
    text = f"wallet {WALLET} bought 15 SOL of $PEPE ca {CA1}"
    assert token_cas_in(text) == [CA1]


def test_buyer_wallet_is_not_shown_on_a_ticker_row():
    records = [
        rec("Alpha", [msg("Ann", 20, f"wallet {WALLET} bought 15 SOL of $PEPE")]),
        rec("Beta", [msg("Bob", 10, f"$PEPE looking busy")]),
    ]
    row = mentions_from_records(records)[0]
    assert row["ticker"] == "$PEPE"
    assert row.get("ca") is None
    assert WALLET not in json.dumps(row)
    assert WALLET not in memecoin_line(row, {"start": START.isoformat(), "end": END.isoformat(),
                                            "tz": "America/Los_Angeles"})


def test_pump_suffix_ca_qualifies_without_a_ticker():
    recs = [
        rec("Alpha", [msg("Ann", 10, f"new coin {PUMP}")]),
        rec("Beta", [msg("Bob", 8, f"same {PUMP}")]),
    ]
    row = mentions_from_records(recs)[0]
    assert row["ca"] == PUMP
    assert PUMP in memecoin_line(row, {"start": START.isoformat(), "end": END.isoformat(),
                                       "tz": "America/Los_Angeles"})


def test_settings_memecoin_show_ca_roundtrip(tg_home):
    from types import SimpleNamespace as NS
    out, err = io.StringIO(), io.StringIO()
    rc = settings_cli.cmd_set(NS(name="memecoin-show-ca", value=["off"]), out=out, err=err)
    assert rc == 0 and err.getvalue() == "" and "Memecoin contract addresses: off." in out.getvalue()
    assert config.load().memecoin_show_ca is False
    out, err = io.StringIO(), io.StringIO()
    rc = settings_cli.cmd_set(NS(name="memecoin-show-ca", value=["on"]), out=out, err=err)
    assert rc == 0 and "Memecoin contract addresses: on." in out.getvalue()
    assert config.load().memecoin_show_ca is True
    shown = "\n".join(settings_cli.show_lines(config.load()))
    assert "Memecoin contract addresses: on" in shown


def test_only_included_chats_keeps_other_chats_out_of_memecoin_mentions(tg_home):
    from conftest import ME_ID, Ent, run
    from tg_recap.readonly import ReadOnlyClient

    async def nosleep(_):
        return None

    def build(cfg):
        sender = Ent(first_name="Ann", id=21)
        dialogs = [mkdialog(i, name, [Msg(i * 10, "$BONK looks active", ago(30), sender=sender)])
                   for i, name in ((1, "Alpha"), (2, "Beta"), (3, "Gamma"))]
        fake = FakeClient(dialogs, me=Ent(first_name="Owner", id=ME_ID))
        client = ReadOnlyClient(fake, min_interval=0, sleep=nosleep)
        state = {"salt": "s", "last_recap_at": (NOW - timedelta(hours=12)).isoformat()}
        return run(C.collect(client, cfg, state, NOW)), dialogs

    d, dialogs = build(Config())
    assert [m["ticker"] for m in d["memecoin_mentions"]] == ["$BONK"] and d["memecoin_mentions"][0]["chats"] == 3
    rules = {C.chat_key(x, "s"): {"title": x.name, "rule": "include"} for x in dialogs[:1]}
    d, _ = build(Config(chat_rules=rules, only_included_chats=True))
    assert d["memecoin_mentions"] == []  # one included chat is below the 2-chat threshold
    rules = {C.chat_key(x, "s"): {"title": x.name, "rule": "include"} for x in dialogs[:2]}
    d, _ = build(Config(chat_rules=rules, only_included_chats=True))
    row = d["memecoin_mentions"][0]
    assert row["chats"] == 2 and row["chat_names"] == ["Alpha", "Beta"]
~~~~~

### file: tests/test_readonly.py
sha256: d05abdf3cad526a4d16a76e0c4a2140e1555a40eb78f9007a4a45e228aa5d66f
~~~~~
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
~~~~~

### file: tests/test_redact.py
sha256: 238cebb5b85bcad058a074be3d54a4dae555fb8b7f7ec8497e94b5f961e93dc2
~~~~~
import pytest

from tg_recap.redact import redact

# All values below are made up for the test.
CASES = [
    ("buy 0x1111111111111111111111111111111111111111 now", "0x1111111111111111111111111111111111111111"),
    ("ca: 7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"),
    ("send to bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"),
    ("join https://t.me/+AbCdEfGhIjK123", "t.me/+AbCdEfGhIjK123"),
    ("old link t.me/joinchat/AAAAAEfake", "joinchat"),
    ("call me +1 555 010 9999", "555 010 9999"),
    ("or (555) 010-9999 tonight", "010-9999"),
    ("chat -1001234567890 has it", "1001234567890"),
    ("user 987654321 said hi", "987654321"),
]


@pytest.mark.parametrize("text,gone", CASES)
def test_redaction(text, gone):
    out = redact(text)
    assert gone not in out
    assert "removed]" in out


def test_ordinary_text_kept():
    t = "Meet Friday 7 pm, budget 1,500,000 and date 2026-11-10, price $42.50"
    assert redact(t) == t


def test_login_codes_and_secrets_stripped():
    # Synthetic only: these are not real credentials.
    cases = [
        ("Telegram said Login code: 12345. Do not share it.", "12345"),
        ("your verification code is 482910", "482910"),
        ("OTP: 998877", "998877"),
        ("code: 12345 sits here", "12345"),
        ("password: hunter2-example", "hunter2-example"),
        ("seed phrase: alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima",
         "alpha bravo charlie"),
    ]
    for text, gone in cases:
        out = redact(text)
        assert gone not in out, (text, out)
        assert "removed]" in out


def test_ordinary_numbers_and_dates_kept():
    t = "Meet Friday 7 pm, budget 1,500,000 and date 2026-11-10, price $42.50"
    assert redact(t) == t
    assert "12345" in redact("the room number is 12345 today")


def test_tracking_query_and_x_status_links_stripped():
    url = "https://example.com/post?a=secrettrack&s=20"
    assert redact(url) == "https://example.com/post"
    assert "secrettrack" not in redact("see " + url)
    xurl = "https://x.com/someone/status/1234567890123456789?a=track&s=20"
    out = redact("posted " + xurl)
    assert "1234567890123456789" not in out and "track" not in out and "x.com" not in out
    assert "[link removed]" in out
    leftover = "see [id removed]?a=track&s=20 end"
    assert "track" not in redact(leftover) and "?a=" not in redact(leftover)


def test_keep_addresses_preserves_listed_cas_only():
    ca = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    evm = "0x1111111111111111111111111111111111111111"
    other = "0x2222222222222222222222222222222222222222"
    text = f"token CA `{ca}` and wallet {evm} call +1 555 010 9999 also {other}"
    out = redact(text, keep_addresses=[ca])
    assert ca in out
    assert evm not in out and other not in out
    assert "555 010 9999" not in out
    assert "[address removed]" in out and "[phone removed]" in out
    # default redact still strips the CA
    assert ca not in redact(text)
~~~~~

### file: tests/test_retention_runner.py
sha256: 26fc77cd92cdb9963a448f95199a5b841ee04f07412283d2a5afa53b8f28f303
~~~~~
import io
import os
from datetime import timedelta

from tg_recap import paths, retention, runner
from tg_recap.lock import SessionLock
from tg_recap.sample import LABEL, sample_text
from conftest import NOW, FakeClient, Msg, ago, mkdialog


def test_retention_purges_after_72h(tg_home):
    old = retention.save_recap("old", NOW - timedelta(hours=73))
    keep = retention.save_recap("keep", NOW - timedelta(hours=71))
    assert retention.purge_recaps(NOW) == 1
    assert not old.exists() and keep.exists()
    assert oct(os.stat(keep).st_mode & 0o777) == "0o600"
    retention.write_raw({"x": 1}, NOW)
    assert retention.delete_raw() == 1 and not any(paths.raw_dir().iterdir())


def _fake_factory(dialogs, authorized=True):
    def make():
        c = FakeClient(dialogs)
        c.authorized = authorized
        make.client = c
        return c
    return make


def test_run_prints_recap_and_cleans_raw(tg_home):
    d = mkdialog(1, "Team", [Msg(1, "@owner_handle can you check this?", ago(30))])
    out, err = io.StringIO(), io.StringIO()
    factory = _fake_factory([d])
    rc = runner.run(factory, now=NOW, out=out, err=err)
    assert rc == 0 and out.getvalue().startswith("ChatBrief ·") and err.getvalue() == ""
    assert not paths.raw_dir().exists() or not any(paths.raw_dir().iterdir())
    assert len(list(paths.recaps_dir().glob("*.txt"))) == 1
    assert paths.read_json(paths.state_file())["last_recap_at"] == NOW.isoformat()
    assert "send_read_acknowledge" not in factory.client.calls


def test_run_quiet_prints_nothing(tg_home):
    out = io.StringIO()
    assert runner.run(_fake_factory([mkdialog(1, "Q", [Msg(1, "hi", ago(60 * 30))])]), now=NOW, out=out) == 0
    assert out.getvalue() == ""


def test_run_revoked_session(tg_home):
    out, err = io.StringIO(), io.StringIO()
    assert runner.run(_fake_factory([], authorized=False), now=NOW, out=out, err=err) == runner.EXIT_REVOKED
    assert out.getvalue() == "" and err.getvalue().startswith("SESSION_REVOKED")


def test_run_lock_held(tg_home):
    out, err = io.StringIO(), io.StringIO()
    with SessionLock():
        # flock is per open file description, so a second acquire in-process also fails
        assert runner.run(_fake_factory([]), now=NOW, out=out, err=err) == runner.EXIT_LOCK
    assert err.getvalue().startswith("LOCK_HELD") and out.getvalue() == ""


def test_run_not_set_up(tg_home):
    err = io.StringIO()
    assert runner.run(lambda: None, now=NOW, out=io.StringIO(), err=err) == runner.EXIT_NOT_SET_UP


def test_sample_is_labeled_fake():
    t = sample_text(NOW)
    assert t.startswith(LABEL) and "Example" in t and "other chats had no new messages." in t
    assert "Whale Watch (example): 90 whale alerts" in t


def test_collect_prints_json_for_the_agent(tg_home):
    import json
    d = mkdialog(1, "Team", [Msg(1, "@owner_handle can you check this?", ago(30))])
    out, err = io.StringIO(), io.StringIO()
    assert runner.run(_fake_factory([d]), now=NOW, out=out, err=err, as_json=True) == 0
    data = json.loads(out.getvalue())
    assert {"window", "needs_you", "conversations", "alert_feeds", "also_active", "count_only", "quiet_count",
            "show_disclaimer", "fallback_text", "nothing_to_report"} <= set(data)
    assert data["fallback_text"].startswith("ChatBrief ·") and data["nothing_to_report"] is False
    assert data["needs_you"][0]["kind"] == "mention"
    assert not paths.raw_dir().exists() or not any(paths.raw_dir().iterdir())
    st = paths.read_json(paths.state_file())
    assert list(st["directory"].values()) == [{"title": "Team", "kind": "group"}]


def test_invalid_settings_exit_7_before_touching_telegram(tg_home):
    paths.write_json(paths.settings_file(), {"length": "huge"})
    err = io.StringIO()
    factory = _fake_factory([])
    assert runner.run(factory, now=NOW, out=io.StringIO(), err=err) == runner.EXIT_SETTINGS == 7
    assert err.getvalue().startswith("SETTINGS_INVALID: length")
    assert not hasattr(factory, "client")
~~~~~

### file: tests/test_settings.py
sha256: e48166fb1c462ca3589436001684d6ee5cbb5c9e31dd95ff07364781111806db
~~~~~
"""settings.json schema, defaults, CLI (show/set/chat/keyword), modes, fuzzy matching."""
import io
import json
import os
from types import SimpleNamespace as NS

import pytest

from tg_recap import collect, config, paths, settings_cli
from tg_recap import __main__ as cli


def call(fn, **kw):
    out, err = io.StringIO(), io.StringIO()
    rc = fn(NS(**kw), out=out, err=err) if fn is not settings_cli.cmd_show else fn(NS(**kw), out=out)
    return rc, out.getvalue(), err.getvalue()


def seed_directory(*titles):
    st = collect.load_state()
    st["directory"] = {f"k{i:015d}": {"title": t, "kind": "group"} for i, t in enumerate(titles)}
    collect.save_state(st)
    return {t: k for k, t in ((k, v["title"]) for k, v in st["directory"].items())}


def test_defaults():
    c = config.load()
    assert (c.include_muted, c.include_archived, c.include_dms, c.length, c.collapse_alert_bots) == \
        (True, False, True, "standard", True)
    assert c.priority_keywords == [] and c.chat_rules == {} and c.timezone == "America/Los_Angeles"
    assert c.memecoin_show_ca is True and c.only_included_chats is False


def test_legacy_config_json_is_read_once(tg_home):
    paths.write_json(paths.config_file(), {"frequency": "4h", "timezone": "Europe/Berlin", "include_chats": ["x"]})
    c = config.load()
    assert (c.frequency, c.timezone) == ("4h", "Europe/Berlin")
    config.save(c)
    assert paths.settings_file().exists()


@pytest.mark.parametrize("data,field", [
    ({"length": "huge"}, "length"), ({"include_muted": "yes"}, "include_muted"),
    ({"priority_keywords": "a,b"}, "priority_keywords"), ({"timezone": "Not/AZone"}, "timezone"),
    ({"chat_rules": {"k": {"title": "x", "rule": "mute"}}}, "chat_rules"), ({"daily_hour": True}, "daily_hour"),
])
def test_schema_rejects_bad_values(tg_home, data, field):
    paths.write_json(paths.settings_file(), data)
    with pytest.raises(config.SettingsError) as e:
        config.load()
    assert field in str(e.value)


def test_set_and_show_roundtrip_with_modes(tg_home):
    for name, value, line in [
        ("length", ["short"], "Recap length: short."),
        ("include-muted", ["off"], "Include muted: off."),
        ("include-archived", ["on"], "Include archived: on."),
        ("include-dms", ["no"], "Include dms: off."),
        ("collapse-alert-bots", ["false"], "Collapse alert bots: off."),
        ("timezone", ["America/New_York"], "Timezone: America/New_York."),
        ("priority-keywords", ["launch,", "invoice"], "Priority keywords: launch, invoice."),
        ("frequency", ["every-4-hours"], "Frequency: 4h · cron 0 */4 * * * · America/New_York. "
                                         "Update the routine to this cron."),
    ]:
        rc, out, err = call(settings_cli.cmd_set, name=name, value=value)
        assert (rc, out.strip(), err) == (0, line, "")
        assert len(out.strip().splitlines()) == 1
    c = config.load()
    assert (c.length, c.include_muted, c.include_archived, c.include_dms, c.collapse_alert_bots) == \
        ("short", False, True, False, False)
    assert c.priority_keywords == ["launch", "invoice"] and c.frequency == "4h"
    assert oct(os.stat(paths.settings_file()).st_mode & 0o777) == "0o600"
    assert oct(os.stat(tg_home).st_mode & 0o777) == "0o700"
    rc, out, _ = call(settings_cli.cmd_show, json=False)
    assert "Length: short" in out and "Muted chats: off" in out and "Priority keywords: launch, invoice" in out


def test_set_rejects_bad_values_without_saving(tg_home, no_consent):
    rc, out, err = call(settings_cli.cmd_set, name="length", value=["huge"])
    assert rc == 1 and err.startswith("Not saved: length") and not paths.settings_file().exists()
    rc, _, err = call(settings_cli.cmd_set, name="include-muted", value=["maybe"])
    assert rc == 1 and "on or off" in err
    rc, _, err = call(settings_cli.cmd_set, name="frequency", value=["custom", "0"])
    assert rc == 1


def test_keywords_add_remove(tg_home):
    assert call(settings_cli.cmd_keyword, action="add", word=["invoice"])[1].strip() == "Priority keyword added: invoice."
    call(settings_cli.cmd_keyword, action="add", word=["Invoice"])
    assert config.load().priority_keywords == ["Invoice"]
    call(settings_cli.cmd_keyword, action="remove", word=["invoice"])
    assert config.load().priority_keywords == []


def test_chat_rules_fuzzy_and_ambiguity(tg_home):
    keys = seed_directory("Whale Watch", "Whale Watch Pro", "Book Club", "Family")
    rc, out, err = call(settings_cli.cmd_chat, title=["whale", "watch"], rule="skip")
    assert rc == 0 and out.strip() == "Whale Watch: skipped in your recap."  # exact (case-insensitive) wins
    rc, out, err = call(settings_cli.cmd_chat, title=["whale"], rule="count-only")
    assert rc == 1 and "matches more than one chat: Whale Watch; Whale Watch Pro" in err
    rc, out, _ = call(settings_cli.cmd_chat, title=["book"], rule="include")
    assert rc == 0 and out.strip() == "Book Club: always included."
    rc, out, _ = call(settings_cli.cmd_chat, title=["Famly"], rule="count-only")  # typo, one close match
    assert rc == 0 and out.strip() == "Family: shown as a count only."
    rc, _, err = call(settings_cli.cmd_chat, title=["Nonexistent"], rule="skip")
    assert rc == 1 and "no chat called" in err
    c = config.load()
    assert c.chat_rules == {keys["Whale Watch"]: {"title": "Whale Watch", "rule": "skip"},
                            keys["Book Club"]: {"title": "Book Club", "rule": "include"},
                            keys["Family"]: {"title": "Family", "rule": "count-only"}}
    rc, out, _ = call(settings_cli.cmd_chat, title=["Book", "Club"], rule="default")
    assert out.strip() == "Book Club: back to the default." and keys["Book Club"] not in config.load().chat_rules
    rc, out, _ = call(settings_cli.cmd_show, json=False)
    assert "Chat rules: Family: count-only; Whale Watch: skip" in out
    for k in keys.values():
        assert k not in out  # internal keys are never shown
    rc, out, _ = call(settings_cli.cmd_show, json=True)
    assert all(k not in out for k in keys.values()) and json.loads(out)["chat_rules"]


def test_cli_wiring(tg_home, monkeypatch, capsys):
    monkeypatch.setattr(cli, "require_telethon", lambda: None)
    assert cli.main(["settings", "set", "length", "detailed"]) == 0
    assert capsys.readouterr().out.strip() == "Recap length: detailed."
    assert cli.main(["settings", "show"]) == 0
    assert "Length: detailed" in capsys.readouterr().out
    paths.write_json(paths.settings_file(), {"length": "huge"})
    assert cli.main(["settings", "show"]) == 7
    assert capsys.readouterr().err.startswith("SETTINGS_INVALID: length")


def test_only_included_chats_setting_roundtrip(tg_home, no_consent):
    rc, out, err = call(settings_cli.cmd_show, json=False)
    assert "Only included chats: off" in out
    rc, out, err = call(settings_cli.cmd_set, name="only-included-chats", value=["on"])
    assert rc == 0 and err == "" and out.startswith("Only included chats: on")
    assert config.load().only_included_chats is True
    rc, out, _ = call(settings_cli.cmd_show, json=False)
    assert "Only included chats: on" in out
    rc, out, err = call(settings_cli.cmd_set, name="only-included-chats", value=["maybe"])
    assert rc == 1 and config.load().only_included_chats is True
    rc, out, err = call(settings_cli.cmd_set, name="only-included-chats", value=["off"])
    assert rc == 0 and config.load().only_included_chats is False
    paths.write_json(paths.settings_file(), {"only_included_chats": "yes"})
    with pytest.raises(config.SettingsError):
        config.load()
~~~~~

### file: tests/test_static.py
sha256: fdb8f3e6f69b60c8ba971c0c4eeb4f20b80ebbb52155568763dbc4c7f8210f7f
~~~~~
"""Static and offline checks against the real Telethon client (no network)."""
import re
from pathlib import Path

import pytest

from tg_recap.readonly import ReadOnlyClient, ReadOnlyViolation

PKG = Path(__file__).resolve().parents[1] / "tg_recap"


def test_no_write_or_read_ack_calls_in_source():
    pattern = re.compile(r"\.(send_message|send_file|send_read_acknowledge|delete_messages|edit_message|"
                         r"forward_messages|delete_dialog|log_out)\(|ReadHistoryRequest|JoinChannelRequest|"
                         r"ImportChatInviteRequest|LeaveChannelRequest")
    for f in (p for p in PKG.glob("*.py") if p.name != "readonly.py"):  # readonly.py names them to deny them
        assert not pattern.search(f.read_text()), f.name


def test_real_telethon_client_is_wrapped_offline(tmp_path):
    from tg_recap.deps import missing_telethon_message
    pytest.importorskip("telethon", reason=missing_telethon_message())
    from telethon import TelegramClient
    raw = TelegramClient(str(tmp_path / "s"), 1, "x" * 32, receive_updates=False)  # never connected
    ro = ReadOnlyClient(raw)
    for name in ("send_message", "send_read_acknowledge", "delete_messages", "sign_in"):
        with pytest.raises(ReadOnlyViolation):
            getattr(ro, name)
    assert callable(ro.iter_dialogs) and callable(ro.get_me)
~~~~~

### file: tests/test_transport_wss.py
sha256: 2c9d0f59dd2b96e655adac617fa467042a5fd7a75aca195bf10d8d51930dd22c
~~~~~
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
~~~~~
