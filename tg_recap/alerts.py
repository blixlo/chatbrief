"""Alert-shaped text: glyph and stat-line stripping, alert nouns, ticker picking.

Pure helpers used by collect.py (and so by the fallback text):

  tidy(text)          drops tree/box-drawing glyphs (├ └ │ ─ ┃ ╰ ▪ ...) and, when a
                      message looks like a bot card, its raw stat lines
                      ("MCap: $51.2k", "Holders: 1.1K") and link-label stubs
                      ("| Trade"). Human messages keep their words.
  alert_shaped(...)   True for a bot card (glyphs, 2+ stat lines, or a bot
                      message with alert words). Those are summarised, not quoted.
  message_kind(text)  trending alert | new listing | whale alert | buy/sell alert
                      | None, from the message pattern (never from the bot's name).
  feed_noun(texts, n) the noun for a feed line, pluralised for n.
  pick_tickers(...)   $TICKER and plain ALL-CAPS words (2-10 chars; 'CA:'-style
                      labels skipped). Rejects
                      anything address-like: base58/EVM strings or fragments
                      ("Ab3d…xYz9", "0x12…ab"), mixed-case runs, digits inside,
                      and high-entropy strings.
"""
from __future__ import annotations

import math
import re
from collections import Counter

GLYPHS = re.compile(r"[\u2500-\u259F\u25A0-\u25FF\u2794\u27A4\u21B3\u2937]+")
_STAT = re.compile(
    r"^\W*[A-Za-z][\w .#/()&'%+-]{0,28}?\s*[:=]\s*[-+~≈<>]?\s*[$€£]?\s*\d[\d.,]*\s*[%a-zA-Z]{0,3}\b.*$")
_NUMERIC = re.compile(r"^[\W\d.,%$€£kKmMbBxX\s]+$")
_LINK_STUB = re.compile(r"^\W*[A-Za-z]{2,12}\W*$")
_ALERTISH = re.compile(r"(\b(alert|whale|bought|sold|swap(?:ped)?|buy|sell|minted|liquidat\w*|signal|new pair|"
                       r"listing|trending)\b|🚨|🐋|🔔|📈|📉|🔥)", re.I)

KINDS = [
    ("trending alert", re.compile(r"\btrending\b|\bmindshare\b", re.I)),
    ("new listing", re.compile(r"\bnew (?:listing|pair|token|launch)\b|\bjust (?:listed|launched)\b|"
                               r"\blisted on\b|\blaunched\b", re.I)),
    ("whale alert", re.compile(r"\bwhales?\b|🐋|🐳", re.I)),
    ("buy/sell alert", re.compile(r"\b(?:bought|sold|buys?|sells?|swap(?:ped|s)?)\b|🟢|🔴", re.I)),
]
GENERIC_ALERT, GENERIC_POST = "alert", "automated post"

_B58 = "1-9A-HJ-NP-Za-km-z"
_HEX = re.compile(r"0x[0-9a-fA-F]{4,}")
_LONG_B58 = re.compile(rf"[{_B58}]{{20,}}")
_ELLIPSIS = re.compile(rf"([{_B58}]*)(?:…|\.{{2,}})([{_B58}]*)")


def _mixed(s: str) -> bool:
    return bool(re.search(r"\d", s) and re.search(r"[A-Za-z]", s)) or (s.lower() != s and s.upper() != s)


def addressy(s: str) -> bool:
    """An address or a shortened fragment of one ('7xKX…9fQ2', '0x12ab…', '…Ab3d')."""
    if _HEX.search(s) or _LONG_B58.search(s):
        return True
    for m in _ELLIPSIS.finditer(s):
        a, b = m.group(1), m.group(2)
        if len(a) >= 2 and len(b) >= 2:
            return True
        side = a or b
        if side and (_mixed(side) or len(side) >= 4):
            return True  # one-sided fragment glued to an ellipsis ('AKPP…', '…9fQ2')
    return False


_CASHTAG = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,9})(?![A-Za-z0-9])")
_ALLCAPS = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,9}(?![A-Za-z0-9])")
_EDGE = "()[]{}<>.,:;!?\"'#*_|/\\~`“”‘’«»"


def _segments(text: str) -> tuple[list[str], int, bool]:
    had_glyphs = bool(GLYPHS.search(text))
    parts = []
    for line in GLYPHS.sub("\n", text).splitlines():
        parts += [p for p in re.split(r"\s+\|\s+", line)] if had_glyphs or " | " in line else [line]
    parts = [p.strip() for p in parts if p.strip()]
    stats = sum(1 for p in parts if _STAT.match(p) or _NUMERIC.match(p))
    return parts, stats, had_glyphs


def tidy(text: str) -> str:
    """Text with glyphs removed; for bot-card-shaped text also stat lines and link stubs."""
    if not text:
        return ""
    parts, stats, had_glyphs = _segments(text)
    if not (had_glyphs or stats >= 2):
        return "\n".join(p for p in parts)
    kept = []
    for i, p in enumerate(parts):
        if _STAT.match(p) or _NUMERIC.match(p):
            continue
        if i and _LINK_STUB.match(p) and not _ALERTISH.search(p):
            continue
        kept.append(p.strip(" -–—:"))
    return " — ".join(k for k in kept if k)


def alert_shaped(text: str, bot: bool = False) -> bool:
    if not text:
        return False
    _, stats, had_glyphs = _segments(text)
    return had_glyphs or stats >= 2 or (bot and bool(_ALERTISH.search(text)))


def message_kind(text: str) -> str | None:
    for noun, pat in KINDS:
        if pat.search(text or ""):
            return noun
    return None


def plural(noun: str, n: int) -> str:
    return noun if n == 1 else noun + "s"


def feed_noun(texts: list[str], n: int | None = None) -> str:
    n = len(texts) if n is None else n
    kinds = Counter(k for k in (message_kind(t) for t in texts) if k)
    if kinds:
        noun, hits = kinds.most_common(1)[0]
        if hits * 2 >= len(texts):
            return plural(noun, n)
    if texts and sum(1 for t in texts if _ALERTISH.search(t or "")) * 2 >= len(texts):
        return plural(GENERIC_ALERT, n)
    return plural(GENERIC_POST, n)


def _entropy(s: str) -> float:
    c = Counter(s)
    return -sum(v / len(s) * math.log2(v / len(s)) for v in c.values())


def is_ticker(tok: str, chunk: str) -> bool:
    """tok is the ticker text (no $); chunk is the whitespace-delimited word it sits in."""
    if not 2 <= len(tok) <= 10 or tok.isdigit():
        return False
    if re.search(r"\d\D", tok) or sum(ch.isdigit() for ch in tok) > 2:
        return False  # digits only at the end, at most two (e.g. ABC2)
    core = chunk.strip(_EDGE).lstrip("$")
    if addressy(chunk):
        return False
    if core and core.upper() != tok.upper():
        runs = re.findall(r"[A-Za-z0-9]+", core)
        if any(len(r) > 10 for r in runs):
            return False
        if any(re.search(r"[a-z]", r) and re.search(r"[A-Z]", r) and re.search(r"\d", r) for r in runs):
            return False
    if len(tok) >= 6 and re.search(r"\d", tok) and _entropy(tok) >= 2.5:
        return False
    return True


def pick_tickers(text: str) -> list[str]:
    """Tickers, uppercased and unique per text: $TICKERs first, then plain ALL-CAPS words."""
    cash, caps = [], []
    for chunk in (text or "").split():
        for m in _CASHTAG.finditer(chunk):
            cash.append((m.group(1), chunk))
        if "$" not in chunk and not chunk.endswith(":"):  # 'CA:' / 'TVL:' are labels
            caps += [(t, chunk) for t in _ALLCAPS.findall(chunk)]
    out = []
    for tok, chunk in cash + caps:
        if is_ticker(tok, chunk) and tok.upper() not in out:
            out.append(tok.upper())
    return out


def summary(text: str, tokens: list[str]) -> str:
    """'Trending alert (TI)' style summary of one alert-shaped message."""
    noun = message_kind(text) or (GENERIC_ALERT if _ALERTISH.search(text or "") else GENERIC_POST)
    noun = noun[:1].upper() + noun[1:]
    return f"{noun} ({', '.join(tokens[:2])})" if tokens else noun
