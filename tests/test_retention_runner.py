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
