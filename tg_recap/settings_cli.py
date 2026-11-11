"""`settings show | set | chat | keyword` - local only, never contacts Telegram.

Chat titles come from the directory the last recap run saved in state.json
(titles only, keyed by the same salted chat key). Raw Telegram IDs are never
stored or printed. Matching is fuzzy, but an unclear match is reported, not
guessed.
"""
from __future__ import annotations

import difflib
import sys

from . import collect, config

BOOL_FIELDS = {"include-muted": "include_muted", "include-archived": "include_archived",
               "include-dms": "include_dms", "collapse-alert-bots": "collapse_alert_bots"}
TRUE = {"on", "true", "yes", "1", "y"}
FALSE = {"off", "false", "no", "0", "n"}
NUM_FIELDS = {"memecoin-buy-sol": "memecoin_buy_sol", "memecoin-buy-usd": "memecoin_buy_usd"}
SETTABLE = sorted(list(BOOL_FIELDS) + list(NUM_FIELDS) +
                  ["length", "timezone", "priority-keywords", "frequency", "daily-hour",
                   "memecoin-stoplist"])


def _onoff(v: bool) -> str:
    return "on" if v else "off"


def _fmt_sol(n) -> str:
    s = f"{float(n):.4f}".rstrip("0").rstrip(".")
    return f"{s} SOL"


def _fmt_usd(n) -> str:
    n = float(n)
    if abs(n - round(n)) < 1e-9:
        return f"${n:,.0f}"
    return f"${n:,.2f}"


def show_lines(cfg) -> list[str]:
    freq = cfg.frequency + (f" every {cfg.custom_hours}h" if cfg.frequency == "custom" else "")
    if cfg.frequency == "daily":
        freq += f" at {cfg.daily_hour}:00"
    rules = sorted(cfg.chat_rules.values(), key=lambda r: r["title"].casefold())
    return [
        "Recap settings",
        f"Length: {cfg.length}",
        f"Frequency: {freq} · {cfg.timezone}",
        f"Muted chats: {'shown under Also active' if cfg.include_muted else 'off'}",
        f"Archived chats: {_onoff(cfg.include_archived)}",
        f"One-to-one chats: {_onoff(cfg.include_dms)}",
        f"Alert-bot feeds: {'collapsed to one line each' if cfg.collapse_alert_bots else 'shown like other chats'}",
        "Priority keywords: " + (", ".join(cfg.priority_keywords) if cfg.priority_keywords else "none"),
        f"Memecoin buy alerts: {_fmt_sol(cfg.memecoin_buy_sol)} or {_fmt_usd(cfg.memecoin_buy_usd)} (as reported)",
        "Memecoin ticker stoplist: " + (", ".join(cfg.memecoin_ticker_stop) or "none"),
        "Chat rules: " + ("; ".join(f"{r['title']}: {r['rule']}" for r in rules) if rules else "none"),
    ]


def match_chat(query: str, directory: dict) -> tuple[str | None, list[str]]:
    """Return (key, []) on a clear match, else (None, candidate titles)."""
    q = " ".join(query.split()).casefold()
    if not q:
        return None, []
    titles = {k: v.get("title", "") for k, v in directory.items() if v.get("title")}
    exact = [k for k, t in titles.items() if t.casefold() == q]
    if len(exact) == 1:
        return exact[0], []
    if len(exact) > 1:
        return None, sorted({titles[k] for k in exact})
    contains = [k for k, t in titles.items() if q in t.casefold()]
    close = [k for k, t in titles.items() if difflib.SequenceMatcher(None, q, t.casefold()).ratio() >= 0.8]
    cands = list(dict.fromkeys(contains + close))
    if len(cands) == 1:
        return cands[0], []
    return None, sorted({titles[k] for k in cands})[:5]


def _parse_bool(value: str) -> bool:
    v = value.strip().casefold()
    if v in TRUE:
        return True
    if v in FALSE:
        return False
    raise config.SettingsError("use on or off")


def cmd_show(args, out=None) -> int:
    out = out or sys.stdout
    cfg = config.load()
    if getattr(args, "json", False):
        import json
        data = {k: getattr(cfg, k) for k in config.SCHEMA if k != "chat_rules"}
        data["chat_rules"] = [{"title": r["title"], "rule": r["rule"]} for r in cfg.chat_rules.values()]
        print(json.dumps(data, indent=2), file=out)
    else:
        print("\n".join(show_lines(cfg)), file=out)
    return 0


def cmd_set(args, out=None, err=None) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    cfg = config.load()
    name, value = args.name, " ".join(args.value).strip()
    try:
        if name in BOOL_FIELDS:
            setattr(cfg, BOOL_FIELDS[name], _parse_bool(value))
            msg = f"{name.replace('-', ' ').capitalize()}: {_onoff(getattr(cfg, BOOL_FIELDS[name]))}."
        elif name == "length":
            cfg.length = value.casefold()
            msg = f"Recap length: {cfg.length}."
        elif name == "timezone":
            cfg.timezone = value
            msg = f"Timezone: {value}."
        elif name == "daily-hour":
            cfg.daily_hour = int(value)
            msg = f"Daily recap hour: {cfg.daily_hour}:00 · cron {config.cron_for(cfg)}."
        elif name == "priority-keywords":
            cfg.priority_keywords = [k.strip() for k in value.split(",") if k.strip()]
            msg = "Priority keywords: " + (", ".join(cfg.priority_keywords) or "none") + "."
        elif name in NUM_FIELDS:
            field = NUM_FIELDS[name]
            setattr(cfg, field, float(value))
            msg = (f"Memecoin buy alerts: {_fmt_sol(cfg.memecoin_buy_sol)} or "
                   f"{_fmt_usd(cfg.memecoin_buy_usd)} (as reported, not verified).")
        elif name == "memecoin-stoplist":
            cfg.memecoin_ticker_stop = [k.strip() for k in value.replace(",", " ").split() if k.strip()]
            msg = "Memecoin ticker stoplist: " + (", ".join(cfg.memecoin_ticker_stop) or "none") + "."
        elif name == "frequency":
            parts = value.split()
            freq = {"every-4-hours": "4h", "4h": "4h", "hourly": "hourly", "every-hour": "hourly",
                    "daily": "daily", "custom": "custom"}.get(parts[0].casefold() if parts else "")
            if freq is None:
                raise config.SettingsError("frequency must be daily, every-4-hours, hourly, or custom N")
            cfg.frequency = freq
            cfg.custom_hours = int(parts[1]) if freq == "custom" and len(parts) > 1 else None
            cfg.validate()
            warn = config.plan_warning(cfg)
            msg = f"Frequency: {freq} · cron {config.cron_for(cfg)} · {cfg.timezone}" + \
                  (f" ({warn})" if warn else "") + ". Update the routine to this cron."
        else:
            raise config.SettingsError(f"unknown setting; use one of {', '.join(SETTABLE)}")
        config.save(cfg)
    except (config.SettingsError, ValueError) as exc:
        print(f"Not saved: {exc}.", file=err)
        return 1
    print(msg, file=out)
    return 0


def cmd_keyword(args, out=None, err=None) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    cfg = config.load()
    word = " ".join(args.word).strip()
    have = [k for k in cfg.priority_keywords if k.casefold() != word.casefold()]
    cfg.priority_keywords = have + [word] if args.action == "add" else have
    try:
        config.save(cfg)
    except config.SettingsError as exc:
        print(f"Not saved: {exc}.", file=err)
        return 1
    print(f"Priority keyword {'added' if args.action == 'add' else 'removed'}: {word}.", file=out)
    return 0


def cmd_chat(args, out=None, err=None) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    cfg = config.load()
    query = " ".join(args.title)
    directory = collect.load_state().get("directory", {})
    # rules already saved count as known chats too (by their stored title)
    known = {**{k: {"title": r["title"]} for k, r in cfg.chat_rules.items()}, **directory}
    key, cands = match_chat(query, known)
    if key is None:
        if cands:
            print(f"Not saved: “{query}” matches more than one chat: {'; '.join(cands)}. "
                  "Say the exact title.", file=err)
        else:
            print(f"Not saved: no chat called “{query}” in the last recap. Chats are learned on each "
                  "recap run.", file=err)
        return 1
    title = known[key]["title"]
    if args.rule == "default":
        cfg.chat_rules.pop(key, None)
        msg = f"{title}: back to the default."
    else:
        cfg.chat_rules[key] = {"title": title, "rule": args.rule}
        msg = {"include": f"{title}: always included.", "skip": f"{title}: skipped in your recap.",
               "count-only": f"{title}: shown as a count only."}[args.rule]
    config.save(cfg)
    print(msg, file=out)
    return 0


def add_parser(sub) -> None:
    s = sub.add_parser("settings", help="show or change recap settings (local only)")
    ss = s.add_subparsers(dest="settings_cmd", required=True)
    p = ss.add_parser("show", help="human-readable settings, no IDs")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_show)
    p = ss.add_parser("set", help="set one setting: " + ", ".join(SETTABLE))
    p.add_argument("name", choices=SETTABLE, metavar="NAME")
    p.add_argument("value", nargs="+")
    p.set_defaults(fn=cmd_set)
    p = ss.add_parser("chat", help="per-chat rule by title: include | skip | count-only | default")
    p.add_argument("title", nargs="+")
    p.add_argument("rule", choices=["include", "skip", "count-only", "default"])
    p.set_defaults(fn=cmd_chat)
    p = ss.add_parser("keyword", help="add or remove one priority keyword")
    p.add_argument("action", choices=["add", "remove"])
    p.add_argument("word", nargs="+")
    p.set_defaults(fn=cmd_keyword)
