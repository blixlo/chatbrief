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
