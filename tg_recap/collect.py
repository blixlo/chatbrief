"""Collect recap input from your dialogs (read-only), as structured JSON.

Two stages:
  fetch (async)  reads dialogs and messages through ReadOnlyClient and turns each
                 chat into a plain record (display names only, no IDs).
  build_digest   pure function: routes each chat (conversation, alert feed,
                 Also active, count only, quiet, skipped), finds what needs you,
                 and trims messages to the length caps. The agent writes the
                 recap from this; render.py is the deterministic fallback.

Needs you (tier 1) counts only:
  - a reply whose replied-to message was sent by you (your user, not a channel
    you post as), from a person (not a bot, not a channel post), and
  - a real mention of you: a mention entity for your user, or "@yourname".
Your own channel's posts are never "you" and never count.

Alert-bot feeds (heuristics, see is_feed): a DM with a bot; a chat where bots
sent at least 60% of new messages; or one sender sent at least 80% of at
least 5 new messages and they look templated (same opening words in at least
40%, or alert words in at least 60%).

A chat whose new messages all came from bots is a feed too, however few. A bot
that posts in one group shows once, as that group's feed with `source` set; the
same alerts in its own DM are dropped (exact text match after cleaning).

Feed nouns come from the message pattern (trending alert, new listing, whale
alert, buy/sell alert, alert, automated post), never from the bot's name.

Quiet = no new messages from anyone but you. A chat with new messages is never
counted as quiet.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import paths
from . import alerts
from . import memecoin as memecoin_mod
from .redact import looks_like_address, redact

FETCH_LIMIT = 500           # newest messages read per chat per window
DIRECTORY_MAX = 500         # chat titles remembered for `settings chat`
DISCLAIMER = "Recap only, not financial advice."

DECISION = re.compile(r"\b(decided|we'?ll go with|let'?s go with|agreed|approved|final(?:ized)? (?:call|decision)|"
                      r"confirmed|it'?s settled|going with)\b", re.I)
DATE = re.compile(
    r"\b(deadline|due|by (?:mon|tue|wed|thu|fri|sat|sun)\w*|by (?:tomorrow|tonight|eod|end of (?:day|week))|"
    r"tomorrow|tonight|next (?:week|month|mon|tue|wed|thu|fri|sat|sun)\w*|"
    r"(?:mon|tues?|wed(?:nes)?|thu(?:rs)?|fri|sat(?:ur)?|sun)day|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]* \d{1,2}\b|"
    r"\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{1,2}(?::\d{2})? ?(?:am|pm)|eod|asap)\b", re.I)
ASK = re.compile(r"\b(can you|could you|would you|will you|please|pls|need you to|can someone|anyone able to|"
                 r"who can)\b", re.I)
MARKET = re.compile(r"\b(crypto|token|coin|btc|bitcoin|eth|ethereum|solana|memecoin|pump|dump|airdrop|defi|nft|"
                    r"dex|trading|chart|market|stocks?|bullish|bearish|wallet|degen|usdc|usdt|mcap|market cap|"
                    r"whale|liquidity|longs?|shorts?|ape[ds]?|moon(?:ing)?)\b", re.I)
CASHTAG = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,9})\b")
ALERT = re.compile(r"(\b(alert|whale|bought|sold|swap(?:ped)?|transfer(?:red)?|buy|sell|minted|liquidat\w*|"
                   r"signal|new pair|listing)\b|🚨|🐋|🔔|📈|📉)", re.I)
ALLCAPS = re.compile(r"\b[A-Z][A-Z0-9]{1,9}\b")
TOKEN_STOP = {"I", "OK", "AM", "PM", "USD", "UTC", "PST", "PDT", "PT", "ET", "TX", "CA", "DM", "NEW", "ALERT",
              "WHALE", "BUY", "SELL", "BOUGHT", "SOLD", "SWAP", "THE", "AND", "FOR", "LINK", "ID", "TG"}
_SIG_SUB = [(re.compile(r"\[(?:address|link|phone|id) removed\]"), " X "), (CASHTAG, " T "),
            (re.compile(r"[\d.,]+[kKmMbB%]?"), " N "), (ALLCAPS, " T ")]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is None:
        return None
    if isinstance(dt, (int, float)):
        return datetime.fromtimestamp(dt, timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def display_name(entity) -> str:
    if entity is None:
        return "someone"
    title = getattr(entity, "title", None)
    if title:
        return title
    parts = [getattr(entity, "first_name", None), getattr(entity, "last_name", None)]
    return " ".join(p for p in parts if p) or "someone"


def is_muted(dialog, now: datetime) -> bool:
    inner = getattr(dialog, "dialog", None)
    ns = getattr(inner, "notify_settings", None) or getattr(dialog, "notify_settings", None)
    mute_until = getattr(ns, "mute_until", None)
    return bool(mute_until) and _aware(mute_until) > now


def is_archived(dialog) -> bool:
    return bool(getattr(dialog, "archived", False) or getattr(dialog, "folder_id", None) == 1)


def chat_kind(dialog) -> str:
    """dm | bot | group | channel (from the entity's shape; no IDs used)."""
    ent = getattr(dialog, "entity", None)
    if getattr(ent, "bot", False):
        return "bot"
    if getattr(dialog, "is_user", None) or (ent is not None and not getattr(ent, "title", None)):
        return "dm"
    if getattr(dialog, "is_channel", False) and not getattr(dialog, "is_group", False) \
            or getattr(ent, "broadcast", False):
        return "channel"
    return "group"


# --- text helpers --------------------------------------------------------------

def clean(text: str) -> str:
    """Redacted, glyph- and stat-line-free, whitespace collapsed (see alerts.tidy)."""
    return " ".join(alerts.tidy(redact(text or "")).split())


def shorten(text: str, limit: int) -> str:
    """Trim to <= limit chars, only at a sentence or word boundary; never mid-word.
    Prefers the last sentence end in the second half of the limit (no ellipsis), else
    the last whole word plus '…'. A first word longer than the limit is kept whole if
    it fits in 2x the limit, otherwise replaced by '(long text)'."""
    t = text.strip()
    if len(t) <= limit:
        return t
    head = t[:limit]
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s)", head + " ") if m.end() >= limit // 2]
    if ends and ends[-1] <= limit:
        return head[: ends[-1]]
    cut = t[: limit - 1]
    if not t[limit - 1].isspace():
        cut = cut[: cut.rfind(" ")] if " " in cut else ""
    cut = cut.rstrip(" ,;:-–—")
    if not cut:
        word = t.split(" ", 1)[0]
        if len(word) > 2 * limit:
            return "(long text)"
        return word if word == t else word + "…"
    return cut + "…"


_LEAD_MENTIONS = re.compile(r"^(?:@\w+[,:]?\s+)+")


def sentence(text: str, limit: int = 160) -> str:
    """One clean sentence: the first that asks, decides or dates something, else the
    first. Redacted, leading @mentions dropped, cut at a word boundary with '…'."""
    t = _LEAD_MENTIONS.sub("", clean(text))
    if not t:
        return ""
    parts = [p for p in re.split(r"(?<=[.!?])\s+", t) if p]
    pick = next((p for p in parts if "?" in p or ASK.search(p) or DECISION.search(p) or DATE.search(p)), parts[0])
    out = pick if len(pick) <= limit else shorten(pick, limit)
    return out[:1].upper() + out[1:]


def _signature(text: str) -> tuple:
    t = redact(text or "")
    for pat, rep in _SIG_SUB:
        t = pat.sub(rep, t)
    words = re.findall(r"[^\W\d_]+|[TNX]", t.lower(), re.UNICODE)
    return tuple(words[:4])


def top_tokens(texts: list[str], exclude: str = "", n: int = 2) -> list[str]:
    """Most common tickers ($TICKER or plain ALL-CAPS, 2-10 chars); address-like
    strings and fragments are rejected (alerts.pick_tickers)."""
    skip = {w.upper() for w in re.findall(r"\w+", exclude)} | TOKEN_STOP | memecoin_mod.TICKER_STOP
    counts = Counter()
    for t in texts:
        for tok in alerts.pick_tickers(alerts.tidy(redact(t or ""))):
            if tok not in skip:
                counts[tok] += 1
    return [w for w, _ in counts.most_common(n)]


# --- state ------------------------------------------------------------------------

def chat_key(dialog, salt: str) -> str:
    raw = str(getattr(dialog, "id", "")) or display_name(getattr(dialog, "entity", None))
    return hashlib.sha256((salt + raw).encode()).hexdigest()[:16]


_chat_key = chat_key  # older name


def load_state() -> dict:
    st = paths.read_json(paths.state_file(), {}) or {}
    st.setdefault("salt", secrets.token_hex(16))
    st.pop("baselines", None)  # busy-thread baselines are no longer used
    st.setdefault("directory", {})
    return st


def save_state(st: dict) -> None:
    paths.write_json(paths.state_file(), st)


def window_for(state: dict, cfg, now: datetime | None = None, *, hours: int | None = None,
               state_key: str = "last_recap_at", default_hours: int | None = None) -> tuple[datetime, datetime]:
    end = _aware(now) or _now()
    if hours is not None:
        return end - timedelta(hours=hours), end
    last = state.get(state_key)
    fallback = default_hours if default_hours is not None else cfg.interval_hours
    start = datetime.fromisoformat(last) if last else end - timedelta(hours=fallback)
    return _aware(start), end


# --- fetch --------------------------------------------------------------------------

def _mentions_me(m, text: str, me_id, handle: str | None) -> bool:
    for e in getattr(m, "entities", None) or []:
        kind = type(e).__name__
        if kind in ("MessageEntityMentionName", "InputMessageEntityMentionName"):
            uid = getattr(e, "user_id", None)
            if uid is not None and (uid == me_id or getattr(uid, "user_id", None) == me_id):
                return True
        elif kind == "MessageEntityMention" and handle:
            off, ln = getattr(e, "offset", 0), getattr(e, "length", 0)
            if text[off:off + ln].casefold() == f"@{handle}":
                return True
    return bool(handle) and re.search(rf"(?<![\w@])@{re.escape(handle)}\b", text, re.I) is not None


# Official Telegram service notifications (login codes, etc.). Never recapped.
TELEGRAM_SERVICE_ID = 777000


def is_telegram_service(*objs) -> bool:
    """True if any object is the official Telegram service account. Ids stay internal."""
    for obj in objs:
        if obj is None:
            continue
        if getattr(obj, "id", None) == TELEGRAM_SERVICE_ID:
            return True
        if getattr(obj, "sender_id", None) == TELEGRAM_SERVICE_ID:
            return True
        if is_telegram_service(getattr(obj, "entity", None), getattr(obj, "sender", None)):
            return True
    return False


def _sent_by_me(m, me_id) -> bool:
    """Your own user sent it. Posts made as a channel (post=True) are not 'you'."""
    if getattr(m, "post", False):
        return False
    sid = getattr(m, "sender_id", None)
    if sid is not None and me_id is not None:
        return sid == me_id
    return bool(getattr(m, "out", False))


async def fetch(client, cfg, state: dict, start: datetime, end: datetime) -> tuple[list, dict]:
    me = await client.get_me()
    me_id = getattr(me, "id", None)
    handle = (getattr(me, "username", None) or "").casefold() or None
    salt = state["salt"]
    directory = state.setdefault("directory", {})
    records = []
    async for dialog in client.iter_dialogs():
        if is_telegram_service(dialog, getattr(dialog, "entity", None)):
            continue
        name = getattr(dialog, "name", None) or display_name(getattr(dialog, "entity", None))
        key = chat_key(dialog, salt)
        kind = chat_kind(dialog)
        directory[key] = {"title": clean(name)[:80], "kind": kind}
        rec = {"key": key, "name": shorten(clean(name), 64), "kind": kind, "muted": is_muted(dialog, end),
               "archived": is_archived(dialog), "rule": cfg.rule_for(key), "messages": []}
        if not _wanted(rec, cfg):
            rec["skipped"] = True
            records.append(rec)
            continue
        last_date = _aware(getattr(dialog, "date", None))
        if last_date is not None and last_date < start:
            records.append(rec)
            continue
        raw = []
        async for m in client.iter_messages(dialog.entity, offset_date=start, reverse=True, limit=FETCH_LIMIT):
            d = _aware(getattr(m, "date", None))
            if d is not None and start <= d <= end:
                raw.append(m)
        mine = {m.id for m in raw if _sent_by_me(m, me_id)}
        wanted = {getattr(m, "reply_to_msg_id", None) for m in raw if not _sent_by_me(m, me_id)}
        wanted.discard(None)
        unknown = [i for i in wanted if i not in mine and i not in {m.id for m in raw}][:100]
        if unknown:
            older = await client.get_messages(dialog.entity, ids=unknown)
            mine |= {o.id for o in (older or []) if o is not None and _sent_by_me(o, me_id)}
        for m in raw:
            if is_telegram_service(m, getattr(m, "sender", None)):
                continue
            text = getattr(m, "message", None) or getattr(m, "text", None) or ""
            sender = getattr(m, "sender", None)
            by_me = _sent_by_me(m, me_id)
            own_post = bool(getattr(m, "out", False)) and bool(getattr(m, "post", False))
            is_bot = bool(getattr(sender, "bot", False))
            person = not (by_me or own_post or is_bot or getattr(m, "post", False))
            rec["messages"].append({
                "who": "You" if by_me else display_name(sender if sender is not None else dialog.entity),
                "sender": str(getattr(m, "sender_id", None) or display_name(sender)),
                "ts": _aware(m.date), "text": text, "by_me": by_me or own_post, "bot": is_bot,
                "reply_to_me": person and getattr(m, "reply_to_msg_id", None) in mine,
                "mentions_me": not (by_me or own_post or is_bot) and _mentions_me(m, text, me_id, handle),
            })
        records.append(rec)
    if len(directory) > DIRECTORY_MAX:
        for k in list(directory)[: len(directory) - DIRECTORY_MAX]:
            directory.pop(k, None)
    return records, state


def _wanted(rec: dict, cfg) -> bool:
    if rec["rule"] == "skip":
        return False
    if getattr(cfg, "only_included_chats", False):
        # allow-list mode: chats without an include/count-only rule (including ones joined later) are left out
        return rec["rule"] in ("include", "count-only")
    if rec["rule"] in ("include", "count-only"):
        return True
    if rec["archived"] and not cfg.include_archived:
        return False
    if rec["kind"] == "dm" and not cfg.include_dms:
        return False
    return True


# --- analysis (pure) ----------------------------------------------------------------

def is_feed(rec: dict) -> bool:
    msgs = [m for m in rec["messages"] if not m["by_me"]]
    if rec["kind"] == "bot":
        return bool(msgs)
    n = len(msgs)
    if n and all(m["bot"] for m in msgs):
        return True  # every new message came from bots, however few
    if n < 3:
        return False
    if sum(m["bot"] for m in msgs) / n >= 0.6:
        return True
    top_share = Counter(m["sender"] for m in msgs).most_common(1)[0][1] / n
    if n < 5 or top_share < 0.8:
        return False
    sig_share = Counter(_signature(m["text"]) for m in msgs).most_common(1)[0][1] / n
    alert_share = sum(1 for m in msgs if ALERT.search(m["text"] or "")) / n
    return sig_share >= 0.4 or alert_share >= 0.6


def feed_line(rec: dict) -> dict:
    """One feed row. The noun comes from the message pattern (alerts.feed_noun), never
    from the chat or bot name. A group fed by a single sender names it in
    `source`, so 'Lab Group: 1 trending alert from Some Bot' appears once."""
    msgs = [m for m in rec["messages"] if not m["by_me"]]
    texts = [m["text"] for m in msgs]
    noun = alerts.feed_noun(texts, len(msgs))
    row = {"name": rec["name"], "count": len(msgs), "noun": noun,
           "top": top_tokens(texts, exclude=rec["name"]),
           "market_related": noun.startswith("whale") or is_market(rec["name"], texts)}
    senders = {m["who"] for m in msgs}
    if rec["kind"] == "group" and len(senders) == 1:
        (who,) = senders
        base = re.sub(r"\s*\(.*?\)\s*", " ", rec["name"]).strip().casefold()
        if base and base not in who.casefold() and who.casefold() not in base:
            row["source"] = who
    return row


def _dedupe_feeds(feed_recs: list) -> list:
    """Drop a bot DM's copies of alerts that same bot also posted in a group feed."""
    by_source = {}
    for rec in feed_recs:
        if rec["kind"] != "bot":
            for m in rec["messages"]:
                if not m["by_me"]:
                    by_source.setdefault(m["who"].casefold(), set()).add(clean(m["text"]))
    out = []
    for rec in feed_recs:
        if rec["kind"] == "bot" and rec["name"].casefold() in by_source:
            seen = by_source[rec["name"].casefold()]
            msgs = [m for m in rec["messages"] if m["by_me"] or clean(m["text"]) not in seen]
            if not any(not m["by_me"] for m in msgs):
                continue
            rec = {**rec, "messages": msgs}
        out.append(rec)
    return out


def is_market(name: str, texts: list[str]) -> bool:
    if MARKET.search(name or "") or CASHTAG.search(name or ""):
        return True
    hits = sum(1 for t in texts if t and (MARKET.search(t) or CASHTAG.search(t) or looks_like_address(t)))
    return hits >= 2 or (texts and hits / len(texts) >= 0.3) or any(looks_like_address(t or "") for t in texts)


def _keyword(text: str, keywords: list[str]) -> str | None:
    for k in keywords:
        if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text or "", re.I):
            return k
    return None


DECISION_NEG = re.compile(r"\b(nothing|not|no|never|isn'?t|hasn'?t|haven'?t|wasn'?t|un)\b\W+(?:\w+\W+){0,2}?"
                          r"(decided|agreed|approved|confirmed|settled)\b", re.I)


def _flag(text: str) -> str | None:
    if DECISION.search(text) and not DECISION_NEG.search(text):
        return "decision"
    if ASK.search(text) and ("?" in text or re.search(r"\byou\b", text, re.I)):
        return "ask"
    if DATE.search(text):
        return "date"
    return None


def build_digest(records: list, cfg, start: datetime, end: datetime) -> dict:
    caps = cfg.caps
    needs, convs, feed_recs, also, counts, quiet = [], [], [], [], [], 0
    for rec in records:
        if rec.get("skipped"):
            continue
        others = [m for m in rec["messages"] if not m["by_me"]]
        if not others:
            quiet += 1
            continue
        for m in others:
            kw = _keyword(m["text"], cfg.priority_keywords)
            kind = "reply" if m["reply_to_me"] else "mention" if m["mentions_me"] else "keyword" if kw else None
            if kind and not (kind == "keyword" and m["bot"]):
                item = {"chat": rec["name"], "kind": kind, "who": m["who"],
                        "text": sentence(m["text"], min(caps["msg_chars"], 200)), "ts": m["ts"].isoformat()}
                if kind == "keyword":
                    item["keyword"] = kw
                needs.append(item)
        if rec["rule"] == "count-only":
            counts.append({"name": rec["name"], "new_messages": len(others)})
        elif cfg.collapse_alert_bots and rec["rule"] != "include" and is_feed(rec):
            feed_recs.append(rec)
        elif rec["muted"] and rec["rule"] != "include":
            if cfg.include_muted:
                also.append({"name": rec["name"], "new_messages": len(others),
                             "market_related": is_market(rec["name"], [m["text"] for m in others])})
        else:
            convs.append(_conversation(rec, others, cfg))
    order = {"reply": 0, "mention": 1, "keyword": 2}
    needs.sort(key=lambda i: (order[i["kind"]], i["ts"]))
    needs_chats = Counter(i["chat"] for i in needs)
    convs.sort(key=lambda c: (-needs_chats.get(c["name"], 0), -len(c["highlights"]), -c["new_messages"]))
    _apply_budget(convs, caps)
    shown, overflow = convs[: caps["max_chats"]], convs[caps["max_chats"]:]
    feeds = sorted((feed_line(r) for r in _dedupe_feeds(feed_recs)), key=lambda f: -f["count"])
    mentions = memecoin_mod.mentions_from_records(_dedupe_feeds(records), cfg)
    market = any(c["market_related"] for c in shown) or any(f["market_related"] for f in feeds) \
        or any(a["market_related"] for a in also) or bool(mentions)
    return {
        "window": {"start": start.isoformat(), "end": end.isoformat(), "tz": cfg.timezone},
        "length": cfg.length,
        "needs_you": needs[: max(5, caps["max_chats"])],
        "memecoin_mentions": mentions,
        "conversations": shown,
        "more_conversations": len(overflow),
        "alert_feeds": feeds,
        "also_active": sorted(also, key=lambda a: -a["new_messages"]),
        "count_only": counts,
        "quiet_count": quiet,
        "show_disclaimer": bool(market),
        "disclaimer": DISCLAIMER if market else "",
    }


def _conversation(rec: dict, others: list, cfg) -> dict:
    caps = cfg.caps
    msgs = rec["messages"][-caps["chat_msgs"]:]
    highlights = []
    for m in others:
        f = None if (m["reply_to_me"] or m["mentions_me"] or m["bot"]) else _flag(m["text"] or "")
        if f:
            highlights.append({"kind": f, "who": m["who"], "text": sentence(m["text"], 160)})
    people = Counter(m["who"] for m in others)
    return {
        "name": rec["name"], "kind": rec["kind"], "new_messages": len(others),
        "people": [w for w, _ in people.most_common(3)], "highlights": highlights,
        "market_related": is_market(rec["name"], [m["text"] for m in others]),
        "messages": [{"who": m["who"], "time": m["ts"].isoformat(), "text": _message_text(m, caps),
                      **({"summarized": True} if alerts.alert_shaped(m["text"], m["bot"]) else {}),
                      **({"reply_to_you": True} if m["reply_to_me"] else {}),
                      **({"mentions_you": True} if m["mentions_me"] else {})}
                     for m in msgs if clean(m["text"])],
        "omitted_messages": max(0, len(rec["messages"]) - len(msgs)),
    }


def _message_text(m: dict, caps: dict) -> str:
    """Alert-shaped messages become a short summary ('Trending alert (TI)'), never a quote."""
    if alerts.alert_shaped(m["text"], m["bot"]):
        return alerts.summary(m["text"], top_tokens([m["text"]]))
    return shorten(clean(m["text"]), caps["msg_chars"])


def _apply_budget(convs: list, caps: dict) -> None:
    left = caps["total_chars"]
    for c in convs:
        kept = []
        for m in reversed(c["messages"]):  # keep the newest when the budget runs out
            if left - len(m["text"]) < 0:
                break
            left -= len(m["text"])
            kept.append(m)
        c["omitted_messages"] += len(c["messages"]) - len(kept)
        c["messages"] = list(reversed(kept))


async def collect(client, cfg, state: dict, now: datetime | None = None, *,
                  window_hours: int | None = None, state_key: str = "last_recap_at",
                  default_hours: int | None = None) -> dict:
    """Return the digest dict. `client` should be a ReadOnlyClient."""
    start, end = window_for(state, cfg, now, hours=window_hours, state_key=state_key,
                            default_hours=default_hours)
    records, _ = await fetch(client, cfg, state, start, end)
    return build_digest(records, cfg, start, end)
