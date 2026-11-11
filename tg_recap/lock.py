"""One-process session lock: two processes can never use the session at once."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path

from . import paths
from .branding import PRODUCT_NAME


class LockHeld(RuntimeError):
    """Another tg_recap process already holds the session lock."""


class SessionLock:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else paths.lock_file()
        self._fd: int | None = None

    def acquire(self) -> "SessionLock":
        paths.ensure_dir(self.path.parent)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, paths.FILE_MODE)
        os.chmod(self.path, paths.FILE_MODE)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise LockHeld(
                f"Another {PRODUCT_NAME} run is using the session right now. "
                "This run stopped; the next scheduled run will try again."
            ) from None
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        self._fd = fd
        return self

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def is_held_elsewhere(self) -> bool:
        """Non-destructive probe used by `status`."""
        if not self.path.exists():
            return False
        fd = os.open(self.path, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        except OSError:
            return True
        finally:
            os.close(fd)

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False
