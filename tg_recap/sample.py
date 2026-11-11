"""Built-in, clearly fake example data for `python -m tg_recap sample`.

Everything here is synthetic: invented chat names, invented people, invented
tokens. It runs through the same build_digest + fallback render as a real run.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .collect import build_digest
from .config import Config
from .render import render

LABEL = "EXAMPLE DATA — not a real recap. No real chats, names, or messages."


def _m(who, minutes_ago, text, end, *, me=False, bot=False, reply=False, mention=False, sender=None):
    return {"who": "You" if me else who, "sender": sender or who, "ts": end - timedelta(minutes=minutes_ago),
            "text": text, "by_me": me, "bot": bot, "reply_to_me": reply, "mentions_me": mention}


def sample_records(end: datetime) -> list:
    def rec(name, kind, msgs, muted=False):
        return {"key": name, "name": name, "kind": kind, "muted": muted, "archived": False, "rule": None,
                "messages": msgs}
    whales = [_m("Whale Watch Bot", 600 - i * 6, f"🐋 Whale bought {1200 + i * 37} {tok} on the example dex",
                 end, bot=True) for i, tok in enumerate(["$FAKEA", "$FAKEB", "$FAKEA", "$FAKEC"] * 22 + ["$FAKEA"] * 2)]
    return [
        rec("Example Book Club", "group", [
            _m("You", 700, "I can host in December if that helps.", end, me=True),
            _m("Sample Person A", 650, "That would be great. Can you also pick the next book? We need it by Friday.",
               end, reply=True),
            _m("Sample Person B", 640, "We'll go with the café on Thursday at 7 pm for November.", end),
            _m("Sample Person C", 600, "Works for me, see you there.", end),
        ]),
        rec("Example Project Team", "group", [
            _m("Sample Person D", 420, "@you could you review the draft budget before the call?", end, mention=True),
            _m("Sample Person E", 400, "Agreed to push the launch to next Tuesday so QA can finish.", end),
            _m("Sample Person D", 380, "I'll update the timeline doc tonight.", end),
        ] + [_m("Sample Person E", 300 - i, f"Small note {i} about copy edits.", end) for i in range(6)]),
        rec("Example Markets Chat", "group", [
            _m("Sample Person F", 200, "The community call moved to Friday 10 am.", end),
            _m("Sample Person G", 190, "Market looked choppy today, nothing decided.", end),
            _m("Sample Person F", 180, "Token unlock schedule is on the example site.", end),
        ]),
        rec("Whale Watch (example)", "channel", whales),
        rec("Example Neighborhood", "group", [_m("Sample Person H", 90 - i, f"Lost cat update {i}.", end)
                                               for i in range(4)], muted=True),
        rec("Example News Channel", "channel", [_m("Example News Channel", 50 - i, t, end) for i, t in enumerate([
            "Road works close the example bridge this weekend.", "Library hours change in December.",
            "Rain expected through Thursday.", "School board meets next week to talk budgets.",
            "The farmers market moves indoors for winter.", "New bike lanes open downtown."])], muted=True),
    ] + [rec(f"Example Quiet {i}", "group", []) for i in range(5)]


def sample_digest(now: datetime | None = None, tz: str = "America/Los_Angeles") -> dict:
    end = now or datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=24)
    return build_digest(sample_records(end), Config(timezone=tz), start, end)


def sample_text(now: datetime | None = None, tz: str = "America/Los_Angeles") -> str:
    return f"{LABEL}\n\n{render(sample_digest(now, tz))}"
