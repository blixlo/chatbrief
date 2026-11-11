"""CLI: python -m tg_recap {login,status,set-frequency,run,sample} (or `tg-recap ...`
when the package is pip-installed).

`login --cards <step>` is the default sign-in: one secret-request card (env var)
per value, one resumable step per process (see login_cards.py). `login` with no
flag prints that usage and exits 1. Opt-in fallbacks: `login --terminal`
(interactive prompts) and `login --web` (127.0.0.1 page).

Exit codes shared with `run`: 0 ok, 2 lock held, 3 session revoked, 4 flood stop,
5 not set up, 7 settings invalid. `login` also exits 1 when sign-in wasn't finished. Any command also exits 6 if Telethon isn't installed for this
Python (see deps.EXIT_MISSING_DEPS); stdout stays empty, stderr is one line.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config, paths
from .deps import require_telethon
from .lock import SessionLock


def cmd_login(args) -> int:
    if args.cards:
        from .login_cards import login as cards_login
        return cards_login(args.cards)
    if args.mode == "web":
        from .login_web import serve
        return serve(port=args.port)
    if args.mode == "terminal":
        from .login_terminal import login
        return login()
    from .login_cards import USAGE
    print(USAGE)
    return 1


def cmd_status(args) -> int:
    """Local-only status. Never contacts Telegram."""
    cfg = config.load()
    state = paths.read_json(paths.state_file(), {}) or {}
    info = {
        "signed_in_files_present": paths.credentials_file().exists() and paths.session_file().exists(),
        "frequency": cfg.frequency,
        "custom_hours": cfg.custom_hours,
        "timezone": cfg.timezone,
        "cron": config.cron_for(cfg),
        "warning": config.plan_warning(cfg),
        "last_recap_at": state.get("last_recap_at"),
        "run_in_progress": SessionLock().is_held_elsewhere(),
        "data_dir": str(paths.home()),
    }
    if args.json:
        print(json.dumps(info, indent=2))
    else:
        print(f"Signed in (session files present): {'yes' if info['signed_in_files_present'] else 'no'}")
        freq = cfg.frequency + (f" ({cfg.custom_hours}h)" if cfg.custom_hours else "")
        print(f"Frequency: {freq} · cron {info['cron']} · {cfg.timezone}")
        if info["warning"]:
            print(f"Note: {info['warning']}")
        print(f"Last recap: {info['last_recap_at'] or 'none yet'}")
        print(f"Run in progress: {'yes' if info['run_in_progress'] else 'no'}")
        print("End the session any time: Telegram Settings > Devices.")
    return 0


def cmd_set_frequency(args) -> int:
    cfg = config.load()
    cfg.frequency = {"every-4-hours": "4h", "4h": "4h", "hourly": "hourly", "every-hour": "hourly",
                     "daily": "daily", "custom": "custom"}[args.frequency]
    cfg.custom_hours = args.hours if cfg.frequency == "custom" else None
    if args.timezone:
        cfg.timezone = args.timezone
    if args.daily_hour is not None:
        cfg.daily_hour = args.daily_hour
    try:
        config.save(cfg)
    except ValueError as exc:
        print(f"Not saved: {exc}", file=sys.stderr)
        return 1
    out = {"frequency": cfg.frequency, "custom_hours": cfg.custom_hours, "timezone": cfg.timezone,
           "cron": config.cron_for(cfg), "warning": config.plan_warning(cfg)}
    print(json.dumps(out) if args.json else
          f"Saved: {cfg.frequency} · cron {out['cron']} · {cfg.timezone}"
          + (f"\nNote: {out['warning']}" if out["warning"] else ""))
    return 0


def _run_kwargs(args, *, as_json: bool = False) -> dict:
    kw = {"peek": bool(getattr(args, "peek", False) or getattr(args, "dry_run", False))}
    if as_json:
        kw["as_json"] = True
    if getattr(args, "memecoin_only", False):
        kw["memecoin_only"] = True
    window = getattr(args, "window", None)
    if window is not None:
        kw["window_hours"] = window
    return kw


def cmd_run(args) -> int:
    from .runner import run
    return run(**_run_kwargs(args))


def cmd_collect(args) -> int:
    from .runner import run
    return run(**_run_kwargs(args, as_json=True))


def cmd_set_memecoin(args) -> int:
    cfg = config.load()
    if args.buy_sol is not None:
        cfg.memecoin_buy_sol = args.buy_sol
    if args.buy_usd is not None:
        cfg.memecoin_buy_usd = args.buy_usd
    try:
        config.save(cfg)
    except ValueError as exc:
        print(f"Not saved: {exc}", file=sys.stderr)
        return 1
    from .settings_cli import _fmt_sol, _fmt_usd
    print(f"Memecoin buy alerts: {_fmt_sol(cfg.memecoin_buy_sol)} or "
          f"{_fmt_usd(cfg.memecoin_buy_usd)} (as reported, not verified).")
    return 0


def cmd_consent(args, out=None) -> int:
    from . import consent
    out = out or sys.stdout
    if args.action == "show":
        out.write(consent.WARNING + "\n\n")
        state = "accepted" if consent.accepted() else "not accepted yet"
        out.write(f"Status: {state} (terms version {consent.TERMS_VERSION}).\n")
        return 0
    rec = consent.accept()
    out.write(f"Recorded: accepted Telegram API terms 1.5 warning at {rec['tos_1_5_accepted_at']} "
              f"(terms version {rec['terms_version']}).\n")
    return 0


def cmd_sample(args) -> int:
    from .sample import sample_text
    sys.stdout.write(sample_text(tz=config.load().timezone))
    return 0


def main(argv=None) -> int:
    from .branding import PRODUCT_NAME
    p = argparse.ArgumentParser(prog="tg-recap", description=f"{PRODUCT_NAME} (read-only)")
    sub = p.add_subparsers(dest="cmd", required=True)
    from .login_cards import STEPS as CARD_STEPS
    s = sub.add_parser("login", help="sign in once; default is --cards <step> (secret-request cards)")
    mode = s.add_mutually_exclusive_group()
    mode.add_argument("--cards", choices=CARD_STEPS, metavar="STEP",
                      help="default: one resumable step per secret card: " + ", ".join(CARD_STEPS))
    mode.add_argument("--terminal", dest="mode", action="store_const", const="terminal",
                      help="fallback: type your details in this terminal")
    mode.add_argument("--web", dest="mode", action="store_const", const="web",
                      help="fallback: a sign-in page on 127.0.0.1")
    s.set_defaults(mode=None, cards=None)
    s.add_argument("--port", type=int, default=8765, help="port for --web only")
    s.set_defaults(fn=cmd_login)
    s = sub.add_parser("status", help="local status; never contacts Telegram")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)
    s = sub.add_parser("set-frequency", help="daily (default), every-4-hours, hourly, or custom --hours N")
    s.add_argument("frequency", choices=["daily", "every-4-hours", "4h", "hourly", "every-hour", "custom"])
    s.add_argument("--hours", type=int, help="custom interval in whole hours (minimum 1)")
    s.add_argument("--timezone", help="IANA zone, default America/Los_Angeles")
    s.add_argument("--daily-hour", type=int, help="local hour 0-23 for daily recaps (default 8)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_set_frequency)
    peek_help = "read but don't write state.json (test/manual runs)"
    window_help = "lookback window in whole hours, e.g. 1h or 24h"
    memecoin_help = "print only Memecoin mentions (nothing if empty); own state key"
    def _add_run_flags(parser):
        from .memecoin import parse_window
        def window_type(value):
            try:
                return parse_window(value)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(str(exc)) from exc
        parser.add_argument("--peek", action="store_true", help=peek_help)
        parser.add_argument("--dry-run", action="store_true", help="same as --peek")
        parser.add_argument("--memecoin-only", action="store_true", help=memecoin_help)
        parser.add_argument("--window", type=window_type, metavar="Nh", help=window_help)
    s = sub.add_parser("run", help="one recap run; prints the fallback recap or nothing")
    _add_run_flags(s)
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("collect", help="one recap run; prints JSON for the agent to write the recap from")
    _add_run_flags(s)
    s.set_defaults(fn=cmd_collect)
    s = sub.add_parser("set-memecoin", help="set reported-buy thresholds for Memecoin mentions")
    s.add_argument("--buy-sol", type=float, help="SOL threshold (default 10)")
    s.add_argument("--buy-usd", type=float, help="USD threshold (default 2000)")
    s.set_defaults(fn=cmd_set_memecoin)
    from .settings_cli import add_parser as add_settings
    add_settings(sub)
    sub.add_parser("sample", help="print a sample recap from fake example data").set_defaults(fn=cmd_sample)
    s = sub.add_parser("consent", help="show or accept the Telegram API terms (1.5) warning; "
                                       "needed before sign-in, collect and run")
    s.add_argument("action", choices=["show", "accept"])
    s.set_defaults(fn=cmd_consent)
    args = p.parse_args(argv)
    if args.cmd == "consent":
        return args.fn(args)  # local only; works before Telethon is installed
    missing = require_telethon()
    if missing is not None:
        return missing
    try:
        return args.fn(args)
    except config.SettingsError as exc:
        print(f"SETTINGS_INVALID: {exc}.", file=sys.stderr)
        return 7


if __name__ == "__main__":
    sys.exit(main())
