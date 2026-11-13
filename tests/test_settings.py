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
