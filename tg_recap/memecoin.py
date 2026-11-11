"""Detect memecoin tickers, map CAs to names, count mentions, flag reported buys."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime

from . import alerts

DEFAULT_BUY_SOL, DEFAULT_BUY_USD = 10.0, 2000.0
BUY_MAX_SOL, BUY_MAX_USD = 20_000.0, 5_000_000.0
MIN_CHATS, MIN_ONE_CHAT, MIN_SENDERS, MIN_BUY_MSGS = 2, 5, 2, 2
NEIGHBOR_MSGS, NEIGHBOR_SECS = 2, 120
UNNAMED = "Unnamed token"
LAST_MEMECOIN_AT = "last_memecoin_at"

TICKER_STOP = {
    "I", "OK", "AM", "PM", "USD", "USDT", "USDC", "EUR", "GBP", "JPY",
    "SOL", "BTC", "ETH", "WETH", "WSOL", "BNB", "XRP", "ADA", "AVAX", "MATIC", "DOT",
    "ZEC", "HYPE", "JUP", "JUPSOL", "CBBTC", "OKX", "MCP", "NVDAX", "CRCLX", "META",
    "MET", "PUMP", "ORE", "KOL", "CASHTAG", "AIRDROP", "NOT", "THIS", "V4", "VC",
    "RWA", "AGENT", "AI",
    "UTC", "PST", "PDT", "PT", "ET", "EST", "EDT", "CST", "CDT", "MST", "MDT", "GMT", "BST",
    "TX", "CA", "DM", "ID", "TG", "UK", "EU", "USA", "API", "URL", "APP", "BOT", "VIP",
    "NEW", "OLD", "BIG", "LOW", "HIGH", "MAX", "MIN", "ATH", "ATL", "MC", "MCAP", "FDV",
    "TVL", "LP", "WL", "KYC", "DYOR", "NFA", "GM", "GN", "LFG", "WAGMI", "NGMI", "IMO",
    "FOMO", "YOLO", "OTC", "CEO", "CTO", "COO", "NFT", "DEX", "CEX", "DAO", "FAQ", "ASAP",
    "EOD", "ETA", "TBA", "TBD", "ALERT", "WHALE", "BUY", "SELL", "BOUGHT", "SOLD", "SWAP",
    "THE", "AND", "FOR", "LINK", "VOLUME", "LIQ", "POOL", "MINT", "BURN", "LOCK", "OPEN",
}
# Exact or (if 4+ chars) contained in a ticker. Filter only; never printed.
_BLOCK = frozenset({
    "FUCK", "SHIT", "CUNT", "ASSHOLE", "BITCH", "BASTARD", "DICK", "PISS", "SLUT",
    "WHORE", "FAG", "FAGGOT", "NIGGER", "NIGGA", "RETARD", "RAPE", "KYS",
})

_EVM = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
_SOL = re.compile(
    r"\b(?=[1-9A-HJ-NP-Za-km-z]*\d)(?=[1-9A-HJ-NP-Za-km-z]*[A-Za-z])[1-9A-HJ-NP-Za-km-z]{32,44}\b"
)
_SOL_AMT = re.compile(r"(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*SOL\b", re.I)
_USD_AMT = re.compile(r"\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)([kKmMbB])?\b")
_BUY = re.compile(r"\b(bought|buy|buys|buying|purchased|purchase|spent|spending)\b|🟢", re.I)
_SELL = re.compile(r"\b(sold|selling|sells)\b|🔴", re.I)
_SWAP_BUY = re.compile(
    r"\bswapped\s+(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*SOL\b\s+for\b", re.I
)
_METRIC_SPAN = re.compile(
    r"(?i)(?:\b(?:m(?:arket)?\s*cap|mcap|fdv|liq(?:uidity)?|tvl|vol(?:ume)?|holders?|mc|ath|cap)\b"
    r"\s*[:=]?\s*\$?\s*[\d,.]+\s*[kmb]?\b|"
    r"\$\s*[\d,.]+\s*[kmb]?\s*"
    r"\b(?:m(?:arket)?\s*cap|mcap|fdv|liq(?:uidity)?|tvl|vol(?:ume)?|holders?|mc|ath|cap)\b)"
)
_NAME_LEFT = re.compile(r"\b([A-Z][A-Za-z0-9]{1,29})\s*\(\s*\$?([A-Za-z][A-Za-z0-9]{1,9})\s*\)")
_NAME_RIGHT = re.compile(
    r"\$?([A-Za-z][A-Za-z0-9]{1,9})\s*(?:\(|[-–—|:]\s*)([A-Z][A-Za-z0-9]{1,29})\)?"
)


def buy_thresholds(cfg=None) -> tuple[float, float]:
    sol = getattr(cfg, "memecoin_buy_sol", DEFAULT_BUY_SOL) if cfg is not None else DEFAULT_BUY_SOL
    usd = getattr(cfg, "memecoin_buy_usd", DEFAULT_BUY_USD) if cfg is not None else DEFAULT_BUY_USD
    return float(sol), float(usd)


def _blocked(tok: str) -> bool:
    u = (tok or "").upper()
    if u in _BLOCK:
        return True
    return any(b in u for b in _BLOCK if len(b) >= 4)


def _extra_stop(cfg=None) -> set[str]:
    raw = getattr(cfg, "memecoin_ticker_stop", None) if cfg is not None else None
    return {str(s).strip().lstrip("$").upper() for s in (raw or []) if str(s).strip()}


def tickers_in(text: str, extra_stop: set[str] | None = None) -> list[str]:
    stop = TICKER_STOP if extra_stop is None else TICKER_STOP | extra_stop
    out: list[str] = []
    for tok in alerts.pick_tickers(alerts.tidy(text or "")):
        if tok not in stop and not _blocked(tok) and tok not in out:
            out.append(tok)
    return out


def contracts_in(text: str) -> list[str]:
    """Canonical CA strings (EVM lowercased, Solana as written)."""
    found: list[str] = []
    for m in _EVM.finditer(text or ""):
        found.append(m.group(0).lower())
    stripped = _EVM.sub(" ", text or "")
    for m in _SOL.finditer(stripped):
        found.append(m.group(0))
    return list(dict.fromkeys(found))


_WALLET_LEFT = re.compile(
    r"\b(?:wallets?|buyers?|traders?|holders?|from|by|sender|signer|"
    r"send(?:ing)?\s+to|sent\s+to|deposit(?:ed|s|ing)?(?:\s+to)?)\s*[:#=]?\s*$",
    re.I,
)
_WALLET_RIGHT = re.compile(r"^\s*(?:bought|sold|swapped|buys|sells|buying|selling)\b", re.I)
_TOKEN_LEFT = re.compile(
    r"\b(?:(?:token|contract)\s+)?(?:ca|contract|address|addr|mint|token)s?\s*[:#=]?\s*$",
    re.I,
)
_TOKEN_HOSTS = ("dexscreener.com/", "pump.fun/", "birdeye.so/", "solscan.io/")


def _addr_spans(text: str, addr: str):
    t = text or ""
    if addr.startswith("0x"):
        for m in _EVM.finditer(t):
            if m.group(0).lower() == addr.lower():
                yield m.start(), m.end()
        return
    start = 0
    while True:
        i = t.find(addr, start)
        if i < 0:
            return
        yield i, i + len(addr)
        start = i + 1


def _wallet_context(text: str, addr: str) -> bool:
    t = text or ""
    for start, end in _addr_spans(t, addr):
        if _WALLET_LEFT.search(t[:start]) or _WALLET_RIGHT.search(t[end:]):
            return True
    return False


def _in_token_url(text: str, addr: str) -> bool:
    t = text or ""
    for host in _TOKEN_HOSTS:
        if re.search(re.escape(host) + r"\S*" + re.escape(addr), t, re.I):
            return True
    return False


def _near_ticker(text: str, start: int, end: int, extra=None, window: int = 80) -> bool:
    lo, hi = max(0, start - window), min(len(text), end + window)
    return bool(tickers_in(text[lo:hi], extra))


def token_context(text: str, addr: str, extra=None) -> bool:
    """True when addr looks like a token CA, not a personal wallet."""
    if (addr or "").lower().endswith("pump"):
        return True
    t = text or ""
    if _in_token_url(t, addr):
        return True
    if _wallet_context(t, addr):
        return False
    for start, end in _addr_spans(t, addr):
        if _TOKEN_LEFT.search(t[:start]) or _near_ticker(t, start, end, extra):
            return True
    return False


def token_cas_in(text: str, extra=None) -> list[str]:
    """CAs in this text that appear in token context (label, token link, ticker, or *pump)."""
    return [ca for ca in contracts_in(text) if token_context(text, ca, extra)]


def _parse_num(num: str, suffix: str | None = None) -> float:
    n = float(num.replace(",", ""))
    if suffix:
        n *= {"k": 1e3, "m": 1e6, "b": 1e9}[suffix.lower()]
    return n


def _is_buy_clause(clause: str) -> bool:
    if _SELL.search(clause) and not _BUY.search(clause) and not _SWAP_BUY.search(clause):
        return False
    return bool(_BUY.search(clause) or _SWAP_BUY.search(clause))


def _clauses(text: str) -> list[str]:
    parts = []
    for line in alerts.GLYPHS.sub("\n", text or "").splitlines():
        parts.extend(re.split(r"\s*[|•·]\s*|\s+[–—]\s+", line))
    return [p.strip() for p in parts if p.strip()]


def parse_buys(text: str) -> list[tuple[float, str]]:
    """Reported (amount, 'SOL'|'USD') tied to a buy on the same clause. Not verified."""
    if not text:
        return []
    buys: list[tuple[float, str]] = []
    for raw in _clauses(text):
        clause = _METRIC_SPAN.sub(" ", raw)
        if not _is_buy_clause(clause):
            continue
        seen = set()
        for m in _SWAP_BUY.finditer(clause):
            amt = _parse_num(m.group(1))
            buys.append((amt, "SOL"))
            seen.add((round(amt, 6), "SOL"))
        for m in _SOL_AMT.finditer(clause):
            amt = _parse_num(m.group(1))
            if (round(amt, 6), "SOL") in seen:
                continue
            buys.append((amt, "SOL"))
        for m in _USD_AMT.finditer(clause):
            if re.search(r"\$[A-Za-z][A-Za-z0-9]{1,9}\s*\(?\s*$", clause[:m.start()]):
                continue
            buys.append((_parse_num(m.group(1), m.group(2)), "USD"))
    out = []
    for amt, unit in buys:
        if unit == "SOL" and 0 < amt <= BUY_MAX_SOL:
            out.append((amt, unit))
        elif unit == "USD" and 0 < amt <= BUY_MAX_USD:
            out.append((amt, unit))
    return out


def names_for(text: str, tickers: list[str]) -> dict[str, str]:
    """Display names next to a ticker, e.g. 'Pepe ($PEPE)'."""
    out: dict[str, str] = {}
    if not text or not tickers:
        return out
    want = {t.upper() for t in tickers}
    for m in _NAME_LEFT.finditer(text):
        tok = m.group(2).upper()
        if tok in want and m.group(1).upper() not in TICKER_STOP:
            out.setdefault(tok, m.group(1))
    for m in _NAME_RIGHT.finditer(text):
        tok = m.group(1).upper()
        if tok in want and m.group(2).upper() not in TICKER_STOP and m.group(2).upper() != tok:
            out.setdefault(tok, m.group(2))
    return out


def flagged_buys(buys: list[tuple[float, str]], cfg=None) -> list[tuple[float, str]]:
    sol_min, usd_min = buy_thresholds(cfg)
    return [b for b in buys if (b[1] == "SOL" and sol_min <= b[0] <= BUY_MAX_SOL)
            or (b[1] == "USD" and usd_min <= b[0] <= BUY_MAX_USD)]


def format_buy(buys: list[tuple[float, str]]) -> str | None:
    """Prefer SOL when a reported buy was in SOL."""
    if not buys:
        return None
    max_sol = max((a for a, u in buys if u == "SOL"), default=None)
    if max_sol is not None:
        return _fmt_sol(max_sol)
    max_usd = max((a for a, u in buys if u == "USD"), default=None)
    return _fmt_usd(max_usd) if max_usd is not None else None


def _fmt_sol(n: float) -> str:
    s = f"{n:.4f}".rstrip("0").rstrip(".")
    return f"{s} SOL"


def _fmt_usd(n: float) -> str:
    if abs(n - round(n)) < 1e-9:
        return f"${n:,.0f}"
    return f"${n:,.2f}".rstrip("0").rstrip(".")


def _nearby_indices(msgs: list[dict], i: int) -> list[int]:
    mid, ts, out = msgs[i], msgs[i].get("ts"), []
    for j, m in enumerate(msgs):
        if j == i:
            continue
        if abs(j - i) <= NEIGHBOR_MSGS:
            out.append(j)
            continue
        other = m.get("ts")
        if ts is not None and other is not None:
            try:
                if abs((other - ts).total_seconds()) <= NEIGHBOR_SECS:
                    out.append(j)
            except Exception:  # noqa: BLE001
                continue
    return out


def _associate(msgs: list[dict], i: int, cas: list[str], tickers: list[str], extra=None) -> list[str]:
    if tickers:
        return tickers
    if not cas:
        return []
    neighbors = []
    for j in _nearby_indices(msgs, i):
        neighbors.extend(tickers_in(msgs[j].get("text") or "", extra))
    uniq = list(dict.fromkeys(neighbors))
    return uniq[:1] if uniq else []


def _tableish(text: str, tickers: list[str]) -> bool:
    short = [t for t in tickers if len(t) <= 3]
    return len(tickers) >= 5 or len(short) >= 4 or (text.count("|") >= 3 and len(short) >= 2)


def _hits_from_records(records: list, cfg=None) -> list[dict]:
    extra = _extra_stop(cfg)
    hits = []
    for rec in records:
        if rec.get("skipped"):
            continue
        msgs, chat, seen_bot = rec.get("messages") or [], rec.get("name") or "chat", set()
        kept = []
        for m in msgs:
            text = m.get("text") or ""
            if m.get("bot"):
                sig = " ".join(text.split())
                if sig in seen_bot:
                    continue
                seen_bot.add(sig)
            kept.append(m)
        extracted = []
        for m in kept:
            text = m.get("text") or ""
            toks = tickers_in(text, extra)
            all_cas = contracts_in(text)
            group_cas = [ca for ca in all_cas if not _wallet_context(text, ca)]
            show_cas = [ca for ca in group_cas if token_context(text, ca, extra)]
            extracted.append((toks, group_cas, show_cas, parse_buys(text), names_for(text, toks),
                              _tableish(text, toks)))
        for i, m in enumerate(kept):
            tickers, cas, show_cas, buys, names, table = extracted[i]
            tickers = _associate(kept, i, cas, tickers, extra)
            if not tickers and not cas:
                continue
            base = {"chat": chat, "sender": m.get("sender") or m.get("who") or "someone",
                    "ts": m.get("ts"), "table": table}
            if not tickers and cas:
                for ca in cas:
                    hits.append({**base, "ticker": None, "name": None, "cas": [ca],
                                 "show_cas": [ca] if ca in show_cas else [], "buys": buys})
                continue
            for tok in tickers:
                hits.append({**base, "ticker": tok, "name": names.get(tok),
                             "cas": list(cas) if len(tickers) == 1 else [],
                             "show_cas": list(show_cas) if len(tickers) == 1 else [],
                             "buys": buys if len(tickers) == 1 else []})
    return hits


def _group_hits(hits: list[dict]) -> list[list[dict]]:
    """Merge hits that share a CA or the same ticker."""
    ca_to_tickers: dict[str, Counter] = defaultdict(Counter)
    for h in hits:
        tok = h["ticker"]
        for ca in h["cas"]:
            if tok:
                ca_to_tickers[ca][tok] += 1
    ca_ticker = {ca: counts.most_common(1)[0][0] for ca, counts in ca_to_tickers.items() if counts}
    groups: dict[str, list[dict]] = defaultdict(list)
    for h in hits:
        keys = []
        if h["ticker"]:
            keys.append("t:" + h["ticker"])
        for ca in h["cas"]:
            tok = ca_ticker.get(ca) or h["ticker"]
            keys.append("t:" + tok if tok else "c:" + ca)
        if not keys:
            continue
        key = next((k for k in keys if k.startswith("t:")), keys[0])
        groups[key].append(h)
    return list(groups.values())


def _iso(ts) -> str:
    if ts is None:
        return ""
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


def _display(group: list[dict]) -> str:
    tickers = Counter(h["ticker"] for h in group if h["ticker"])
    if tickers:
        return "$" + tickers.most_common(1)[0][0]
    names = Counter(h["name"] for h in group if h["name"])
    if names:
        return names.most_common(1)[0][0]
    return UNNAMED


def _buy_msg_count(group: list[dict], cfg=None) -> int:
    return sum(1 for h in group if flagged_buys(h["buys"], cfg))


def _qualifies(group: list[dict], cfg=None) -> bool:
    by_chat: dict[str, dict] = {}
    for h in group:
        row = by_chat.setdefault(h["chat"], {"n": 0, "senders": set()})
        row["n"] += 1
        row["senders"].add(h["sender"])
    if len(by_chat) >= MIN_CHATS:
        return True
    if any(v["n"] >= MIN_ONE_CHAT and len(v["senders"]) >= MIN_SENDERS for v in by_chat.values()):
        return True
    return _buy_msg_count(group, cfg) >= MIN_BUY_MSGS


def _junk_short(group: list[dict], ticker: str) -> bool:
    core = ticker.lstrip("$")
    return 2 <= len(core) <= 3 and group and all(h.get("table") for h in group)


def _show_ca_enabled(cfg=None) -> bool:
    if cfg is None:
        return True
    return bool(getattr(cfg, "memecoin_show_ca", True))


def _ca_fields(group: list[dict], show_ca: bool) -> dict:
    all_cas = [ca for h in group for ca in h["cas"]]
    displayable = {ca for h in group for ca in (h.get("show_cas") or [])}
    if not any(h.get("ticker") for h in group):
        displayable.update(ca for ca, n in Counter(all_cas).items() if n >= 2)
    counts = Counter(ca for ca in all_cas if ca in displayable)
    out = {
        "address_sightings": len(all_cas),
        "distinct_addresses": len(set(all_cas)),
    }
    if show_ca and counts:
        top, top_n = counts.most_common(1)[0]
        out["ca"] = top
        out["ca_sightings"] = top_n
        out["other_cas"] = len(counts) - 1
    return out


def mentions_from_records(records: list, cfg=None) -> list[dict]:
    """Tokens that cross a mention or big-buy threshold. Public CAs included when enabled."""
    rows = []
    show_ca = _show_ca_enabled(cfg)
    for group in _group_hits(_hits_from_records(records, cfg)):
        flagged = flagged_buys([b for h in group for b in h["buys"]], cfg)
        if not _qualifies(group, cfg):
            continue
        label = _display(group)
        if _blocked(label.lstrip("$")) or _junk_short(group, label):
            continue
        chats = list(dict.fromkeys(h["chat"] for h in group))
        times = [h["ts"] for h in group if h["ts"] is not None]
        row = {
            "ticker": label,
            "mentions": len(group),
            "chats": len(chats),
            "chat_names": chats,
            "first_seen": _iso(min(times) if times else None),
            "biggest_buy": format_buy(flagged),
        }
        row.update(_ca_fields(group, show_ca))
        rows.append(row)
    rows.sort(key=lambda r: (-r["chats"], -r["mentions"], r["first_seen"] or ""))
    return rows


def parse_window(value: str | None) -> int | None:
    """Parse '1h' / '24h' into whole hours."""
    if value is None or str(value).strip() == "":
        return None
    m = re.fullmatch(r"(\d+)\s*h", str(value).strip(), re.I)
    if not m or int(m.group(1)) < 1:
        raise ValueError("window must be whole hours, like 1h or 24h")
    return int(m.group(1))
