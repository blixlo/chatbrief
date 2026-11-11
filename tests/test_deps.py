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
