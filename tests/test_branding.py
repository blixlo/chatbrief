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
