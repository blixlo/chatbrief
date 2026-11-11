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
