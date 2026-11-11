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
