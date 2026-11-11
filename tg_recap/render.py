"""Deterministic fallback recap, for when the agent can't write one itself.

Layout (sections appear only when they have something):

    ChatBrief · Nov 10, 3:20 AM to Nov 11, 3:20 AM PT   (branding.PRODUCT_NAME)

    Needs you
    • Alice replied to you in Work Group: Thanks, that looks good.

    Conversations
    Work Group (6 new from Alice, Bob)
    • Alice said: We decided to ship v2.

    Alert feeds
    • Whale Watch: 90 whale alerts, mostly ABC and XYZ.
    • Lab Group: 1 trending alert from Some Bot (TI).

    Also active: Muted Group (4 new), Big Channel (12 new).
    Count only: Some Chat (8 new).
    3 other chats had no new messages.

    Recap only, not financial advice.      (only when market/crypto chats appear)

Returns "" when nothing needs you and no conversation or feed has news.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .branding import PRODUCT_NAME
from .collect import DISCLAIMER, shorten
from .redact import redact

ZONE_LABELS = {
    "America/Los_Angeles": "PT", "America/Vancouver": "PT", "America/Tijuana": "PT",
    "America/Denver": "MT", "America/Edmonton": "MT", "America/Phoenix": "MT", "America/Boise": "MT",
    "America/Chicago": "CT", "America/Winnipeg": "CT", "America/Mexico_City": "CT",
    "America/New_York": "ET", "America/Toronto": "ET", "America/Detroit": "ET",
    "America/Anchorage": "AKT", "Pacific/Honolulu": "HT", "UTC": "UTC", "Etc/UTC": "UTC",
}
_VERB = {"reply": "replied to you in", "mention": "mentioned you in"}
_HIGHLIGHT = {"decision": "said", "date": "noted", "ask": "asked"}


def zone_label(tz_name: str, dt: datetime) -> str:
    return ZONE_LABELS.get(tz_name) or dt.strftime("%Z") or tz_name


def _stamp(dt: datetime) -> str:
    return f"{dt.strftime('%b')} {dt.day}, {dt.strftime('%I:%M %p').lstrip('0')}"


def window_label(window: dict) -> str:
    tz = ZoneInfo(window["tz"])
    start = datetime.fromisoformat(window["start"]).astimezone(tz)
    end = datetime.fromisoformat(window["end"]).astimezone(tz)
    return f"{_stamp(start)} to {_stamp(end)} {zone_label(window['tz'], end)}"


def header(window: dict) -> str:
    return f"{PRODUCT_NAME} · {window_label(window)}"


def _ca_label(item: dict) -> str | None:
    ca = item.get("ca")
    if not ca:
        return None
    n = int(item.get("ca_sightings") or 0)
    bit = f"CA `{ca}`" + (f" (seen {n}×)" if n else "")
    other = int(item.get("other_cas") or 0)
    if other:
        bit += f" +{other} other CA{'s' if other != 1 else ''} seen"
    return bit


def memecoin_line(item: dict, window: dict) -> str:
    tz = ZoneInfo(window["tz"])
    raw = item.get("first_seen") or ""
    first = datetime.fromisoformat(raw).astimezone(tz) if raw else None
    n, c = int(item.get("mentions") or 0), int(item.get("chats") or 0)
    parts = [f"{n} mention{'s' if n != 1 else ''} in {c} chat{'s' if c != 1 else ''}"]
    ca_bit = _ca_label(item)
    label = item.get("ticker") or "Unnamed token"
    if ca_bit:
        label = ca_bit if label == "Unnamed token" else f"{label} · {ca_bit}"
    else:
        sightings = int(item.get("address_sightings") or 0)
        if sightings >= 2:
            if int(item.get("distinct_addresses") or 1) > 1:
                parts.append(f"addresses seen {sightings}×")
            else:
                parts.append(f"same address seen {sightings}×")
    if first is not None:
        parts.append(f"first seen {_stamp(first)}")
    if item.get("biggest_buy"):
        parts.append(f"biggest reported buy: {item['biggest_buy']}")
    chats = ", ".join(item.get("chat_names") or [])
    tail = f" — {chats}" if chats else ""
    return f"• {label} — {', '.join(parts)}{tail}"


def _names(people: list[str]) -> str:
    people = [p for p in people if p and p != "You"]
    if not people:
        return ""
    if len(people) == 1:
        return people[0]
    return ", ".join(people[:-1]) + " and " + people[-1]


def _end(s: str) -> str:
    return s if s.endswith((".", "!", "?", "…")) else s + "."


def needs_line(item: dict) -> str:
    who, chat = item.get("who") or "Someone", item["chat"]
    if item["kind"] == "keyword":
        return f"• {who} in {chat} (flagged “{item.get('keyword')}”): {_end(item['text'])}"
    return f"• {who} {_VERB[item['kind']]} {chat}: {_end(item['text'])}"


def conversation_lines(conv: dict, bullets: int) -> list[str]:
    n = conv["new_messages"]
    who = _names(conv.get("people", []))
    head = f"{conv['name']} ({n} new{' from ' + who if who else ''})"
    out = [head]
    for h in conv.get("highlights", [])[:bullets]:
        out.append(f"• {h['who']} {_HIGHLIGHT.get(h['kind'], 'said')}: {_end(h['text'])}")
    if len(out) == 1:
        latest = next((m for m in reversed(conv.get("messages", [])) if m["who"] != "You"), None)
        if latest:
            out.append(f"• Latest from {latest['who']}: {_end(shorten(latest['text'], 160))}")
    return out


def feed_line(feed: dict) -> str:
    """'mostly A and B' only for 2+ items with 2 tickers; otherwise '(A)' or nothing."""
    top = feed.get("top") or []
    src = f" from {feed['source']}" if feed.get("source") else ""
    if top and feed["count"] > 1 and len(top) > 1:
        tail = f", mostly {' and '.join(top)}"
    elif top:
        tail = f" ({', '.join(top)})"
    else:
        tail = ""
    return f"• {feed['name']}: {feed['count']} {feed['noun']}{src}{tail}."


def _coin_block(coins: list, window: dict) -> list[str]:
    shown, more = coins[:10], max(0, len(coins) - 10)
    lines = ["Memecoin mentions"] + [memecoin_line(i, window) for i in shown]
    if more:
        lines.append(f"…and {more} more")
    return lines


def _counts(label: str, rows: list[dict]) -> str:
    return f"{label}: " + ", ".join(f"{r['name']} ({r['new_messages']} new)" for r in rows) + "."


def _keep_cas(coins: list) -> list[str]:
    return [c["ca"] for c in coins if c.get("ca")]


def _redact_recap(text: str, coins: list) -> str:
    return redact(text, keep_addresses=_keep_cas(coins))


def render(digest: dict, bullets: int | None = None, memecoin_only: bool = False) -> str:
    needs = digest.get("needs_you", [])
    convs = digest.get("conversations", [])
    feeds = digest.get("alert_feeds", [])
    coins = digest.get("memecoin_mentions") or []
    if memecoin_only:
        if not coins:
            return ""
        lines = [header(digest["window"]), ""] + _coin_block(coins, digest["window"]) + ["", DISCLAIMER]
        return _redact_recap("\n".join(lines).rstrip() + "\n", coins)
    if not (needs or convs or feeds or coins):
        return ""
    if bullets is None:
        bullets = {"short": 1, "standard": 2, "detailed": 3}.get(digest.get("length", "standard"), 2)
    lines = [header(digest["window"]), ""]
    if needs:
        lines += ["Needs you"] + [needs_line(i) for i in needs] + [""]
    if coins:
        lines += _coin_block(coins, digest["window"]) + [""]
    if convs:
        lines.append("Conversations")
        for c in convs:
            lines += conversation_lines(c, bullets)
        more = digest.get("more_conversations", 0)
        if more:
            lines.append(f"{more} more {'chat' if more == 1 else 'chats'} had new messages not shown.")
        lines.append("")
    if feeds:
        lines += ["Alert feeds"] + [feed_line(f) for f in feeds] + [""]
    tail = []
    if digest.get("also_active"):
        tail.append(_counts("Also active", digest["also_active"]))
    if digest.get("count_only"):
        tail.append(_counts("Count only", digest["count_only"]))
    q = int(digest.get("quiet_count", 0))
    if q:
        tail.append(f"{q} other {'chat' if q == 1 else 'chats'} had no new messages.")
    lines += tail
    if digest.get("show_disclaimer") or coins:
        lines += ["", DISCLAIMER]
    return _redact_recap("\n".join(lines).rstrip() + "\n", coins)
