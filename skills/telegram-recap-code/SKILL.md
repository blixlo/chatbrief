---
name: telegram-recap-code
description: 'Source code for ChatBrief - use from telegram-recap-setup to write the code to disk before installing.'
---
# ChatBrief source code

ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.

This skill holds the ChatBrief source so a bot that only has the skills (no git checkout) can write the code to disk and install it.

## How to extract

Live skill files live at `/home/box/agent-data/workflows/<id>/SKILL.md`. Read this skill and run its extractor into `telegram-recap-agent/` (or another empty target directory).

1. Save the extractor script below as a `.py` file (Python stdlib only; no extra packages).
2. Run: `python3 extract_code_skill.py <path-to-this-SKILL.md> <target-dir>`
   To include the tests too, pass both skills (the tests live in the sibling `telegram-recap-code-tests` skill): `python3 extract_code_skill.py <this SKILL.md> <telegram-recap-code-tests SKILL.md> <target-dir>`
3. The extractor writes every file listed below, sets `install.sh` executable, and verifies each sha256. On a mismatch it prints the path and the expected vs actual hash, writes nothing, and exits non-zero.
4. Then run `./install.sh` from the target directory (see `telegram-recap-setup`).

### Extractor

~~~~~ python
#!/usr/bin/env python3
"""Extract ChatBrief source from a telegram-recap-code SKILL.md.

Stdlib only. Usage:

    python3 extract_code_skill.py <SKILL.md> [<more SKILL.md> ...] <target-dir>

Pass telegram-recap-code first, then telegram-recap-code-tests to add tests/.

Writes every `### file:` block, sets install.sh executable, and verifies
each sha256 before writing anything. A mismatch prints the path and
expected vs actual hash and exits non-zero.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

FILE_HEAD = re.compile(r"^### file: (.+)$")
SHA_LINE = re.compile(r"^sha256: ([0-9a-f]{64})$")
FENCE_OPEN = re.compile(r"^(~{5,})(?:[ \t]+\S+)?[ \t]*$")


def fail(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def safe_relpath(raw: str) -> str:
    rel = raw.strip()
    if not rel:
        fail(f"Refusing unsafe path: {raw!r}")
    path = Path(rel)
    if path.is_absolute() or rel.startswith("/") or rel.startswith("\\") or rel.startswith("~"):
        fail(f"Refusing unsafe path: {raw!r}")
    if ".." in path.parts or path.parts[:1] == ("..",):
        fail(f"Refusing unsafe path: {raw!r}")
    return path.as_posix()


def parse_files(text: str) -> list[tuple[str, str, str]]:
    """Return a list of (relpath, expected_sha256, content)."""
    lines = text.splitlines()
    out: list[tuple[str, str, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        match = FILE_HEAD.match(lines[i])
        if not match:
            i += 1
            continue
        rel = safe_relpath(match.group(1))
        i += 1
        while i < n and lines[i].strip() == "":
            i += 1
        if i >= n:
            fail(f"Missing sha256 for {rel}")
        hashed = SHA_LINE.match(lines[i])
        if not hashed:
            fail(f"Expected 'sha256: <hex>' after ### file: {rel}, got: {lines[i]!r}")
        expected = hashed.group(1)
        i += 1
        while i < n and lines[i].strip() == "":
            i += 1
        if i >= n:
            fail(f"Missing opening fence for {rel}")
        fence = FENCE_OPEN.match(lines[i])
        if not fence:
            fail(f"Expected a tilde fence after sha256 for {rel}, got: {lines[i]!r}")
        mark = fence.group(1)
        i += 1
        body: list[str] = []
        closed = False
        while i < n:
            if lines[i] == mark:
                closed = True
                i += 1
                break
            body.append(lines[i])
            i += 1
        if not closed:
            fail(f"Unclosed fence for {rel}")
        content = "\n".join(body) + "\n"
        out.append((rel, expected, content))
    return out


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def extract(skill_md: Path, target: Path) -> int:
    if not skill_md.is_file():
        fail(f"SKILL.md not found: {skill_md}")
    files = parse_files(skill_md.read_text(encoding="utf-8"))
    if not files:
        fail(f"No '### file:' blocks found in {skill_md}")

    mismatches: list[str] = []
    for rel, expected, content in files:
        actual = sha256_text(content)
        if actual != expected:
            mismatches.append(
                f"  {rel}\n    expected {expected}\n    actual   {actual}"
            )
    if mismatches:
        fail("sha256 mismatch; refusing to write any files:\n" + "\n".join(mismatches))

    target.mkdir(parents=True, exist_ok=True)
    for rel, _expected, content in files:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        if Path(rel).name == "install.sh":
            dest.chmod(dest.stat().st_mode | 0o111)
    print(f"Extracted {len(files)} files into {target}")
    return len(files)


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        fail("Usage: python3 extract_code_skill.py <SKILL.md> [<more SKILL.md> ...] <target-dir>", code=2)
    target = Path(args[-1])
    for skill in args[:-1]:  # check every skill before writing any
        files = parse_files(Path(skill).read_text(encoding="utf-8")) if Path(skill).is_file() else None
        if not files:
            fail(f"No '### file:' blocks found in {skill}")
        bad = [rel for rel, expected, content in files if sha256_text(content) != expected]
        if bad:
            fail("sha256 mismatch; refusing to write any files:\n" + "\n".join(f"  {skill}: {r}" for r in bad))
    for skill in args[:-1]:
        extract(Path(skill), target)


if __name__ == "__main__":
    main()
~~~~~

## Files

### file: README.md
sha256: 125df59325fa4467fc11691c11eee3b5dbf52059b47c846e3414bf92182df1b8
~~~~~
# ChatBrief

**ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.**

**At a glance**

- Telegram API Terms section 1.5 restricts using Telegram data for AI; an AI-written recap may fall under it, so read the terms and accept the risk yourself (`consent accept`, see below).
- Read-only: it never sends, posts, reacts or marks anything read in Telegram.
- Main focus: memecoin mentions across your chats (tokens seen in several chats, big reported buys, with the public contract address when one is known), plus a general chat recap.
- Install: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`, then `.venv/bin/python -m tg_recap --help`.
- Recap only, not financial advice.

Source code: https://github.com/blixlo/chatbrief. No license is granted; all rights reserved.

A personal recap of your own Telegram that you run yourself. It reads the groups, chats and channels you are already in and sends you one short summary of what is worth your attention, mentions of you first. Read-only. Any topic. Recaps are not financial advice.

## Privacy first: how the session works

ChatBrief signs in **as you**, using Telethon (a standard Telegram client library) on your own machine. It reads your chats through your existing account session, the same way your Telegram app does. No bot is added to your groups, and nobody in them sees anything new. It only reads: it doesn't post, react, join, or leave.

**How it connects:** only to Telegram's official web endpoints (`wss://pluto|venus|aurora|vesta|flora.web.telegram.org/apiws`, the same ones Telegram Web uses) over normal HTTPS on port 443, as a standard WebSocket carrying Telegram's own encrypted MTProto. Data centers are picked by number from that fixed list, never from an IP address. There is no proxy option and none is used.

Your phone number, login code, and two-step password are used once to sign in and are never saved or logged. We never see them, and neither does anyone else's machine. Only three things are kept on your machine, readable only by you (folder `~/.tg_recap`, mode 0700, files 0600): your API ID, your API hash, and Telegram's session file. The session file is a full key to your account: treat it like a password. You can end that session any time in Telegram under **Settings > Devices**.

It never marks messages as read, so your chats stay unread in your own apps.

## Setup (self-serve)

1. Get your own API ID and API hash at [my.telegram.org](https://my.telegram.org) (official steps: [core.telegram.org/api/obtaining_api_id](https://core.telegram.org/api/obtaining_api_id)).
2. Install, using your own Python (a virtual environment is optional, not required):
   ```
   ./install.sh
   ```
   That runs `"${PYTHON:-python3}" -m pip install --user -r requirements.txt`. If pip refuses because this Python is externally managed (PEP 668), it creates a local `.venv` and installs there instead. Note the Python it prints (your `python3`, or `.venv/bin/python` on fallback) and use that for every later command. You can also set `PYTHON` first (`PYTHON=python3 ./install.sh`), or install yourself:
   ```
   python3 -m pip install --user -r requirements.txt
   ```
   If that is refused, the venv fallback is:
   ```
   python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
   ```
   `python3 -m pip install --user .` (or `pip install .` inside a venv) also works: `pyproject.toml` pins Telethon 1.45.0 and websockets 17.4.

   The commands below use `python3`; substitute `.venv/bin/python` if install fell back to a venv.
3. Read the terms warning (see "Telegram API terms" below) and, if you agree, run `python3 -m tg_recap consent accept`. Then sign in once. The default is resumable steps, each reading one value from an env var (a Grok Bot secret-request card sets these): `login --cards save-api` (`TG_RECAP_API_ID`, `TG_RECAP_API_HASH`), `send-code` (`TG_RECAP_PHONE`), `sign-in` (`TG_RECAP_CODE`, plus `TG_RECAP_PHONE` again; the phone is never stored on disk), and `password` (`TG_RECAP_2FA`, only after exit 10). `login --cards reset` clears an unfinished sign-in. Exit codes: 0 ok, 1 failed, 2 lock held, 4 flood stop, 5 not set up, 10 need 2FA, 11 wrong code, 12 wrong password, 13 code expired (start again at send-code), 14 bad phone, 15 bad API values, 16 env var missing (named), 17 no sign-in in progress. Between steps, `~/.tg_recap/pending/` (0700, files 0600) holds Telethon's pending session and the code hash; it's removed on success. Plain `login` only prints the steps.

   Fallbacks: `login --terminal` asks for the same values in a terminal (API hash and password hidden); `login --web` serves a page on `http://127.0.0.1:...`. Never paste a code or password into a chat. Nothing you enter is printed or logged. With a pip install, `tg-recap login ...` works too.
4. Pick how often: `python3 -m tg_recap set-frequency daily` (default), `every-4-hours`, `hourly`, or `custom --hours N` (minimum 1). Hourly runs about 24 times a day and uses more of your Grok Bot plan. Timezone defaults to America/Los_Angeles (`--timezone`).
5. Schedule `python3 -m tg_recap collect` (JSON for an agent to write the recap from) or `python3 -m tg_recap run` (the built-in fallback text) with the cron shown by `status`.

## Commands

| Command | What it does |
|---|---|
| `python -m tg_recap login --cards STEP` | Default sign-in: `save-api`, `send-code`, `sign-in`, `password`, `reset` |
| `python -m tg_recap login --terminal` / `--web` | Fallbacks: terminal prompts / page on 127.0.0.1 |
| `python -m tg_recap status` | Local status, cron and last recap time. Never contacts Telegram |
| `python -m tg_recap set-frequency ...` | Save frequency/timezone, print the cron |
| `python -m tg_recap collect` | One recap run. Prints JSON for the agent (plus `fallback_text`) |
| `python -m tg_recap consent show` / `consent accept` | Show the Telegram API terms (1.5) warning / record your yes (needed before sign-in, `collect` and `run`) |
| `python -m tg_recap run` | One recap run. Prints the fallback recap, or nothing |
| `... collect --peek` / `... run --peek` | Test or manual run: same full read, but the window isn't advanced and `state.json` isn't written at all (no window, no chat-title directory); no recap copy is saved. JSON has `"peek": true` |
| `python -m tg_recap settings show` | Your settings, no IDs |
| `python -m tg_recap settings set NAME VALUE` | `length`, `include-muted`, `include-archived`, `include-dms`, `collapse-alert-bots`, `only-included-chats`, `timezone`, `priority-keywords`, `frequency`, `daily-hour` |
| `python -m tg_recap settings chat TITLE include\|skip\|count-only\|default` | Per-chat rule (fuzzy title match; ambiguity is reported) |
| `python -m tg_recap settings keyword add\|remove WORD` | Priority keywords, flagged first |
| `python -m tg_recap sample` | Prints a sample recap from fake example data |

`run`/`collect` exit codes: 0 ok, 9 the terms warning hasn't been accepted (`consent accept`), 2 another run holds the session lock, 3 session not active (sign in again), 4 Telegram asked to slow down twice, 5 not set up yet, 7 `settings.json` didn't validate, 8 couldn't reach Telegram's web endpoint (DNS, TLS, WebSocket handshake or timeout; one line naming only the error type, after at most 2 attempts; sign-in steps use the same code). Any command exits 6 if Telethon 1.45.0 or websockets 17.4 isn't installed for that Python (stderr is one line telling you to `pip install -r requirements.txt`); stdout stays empty.

**Existing sessions (v0.1.5 and earlier)** keep working: the same `session.session` file and auth key are used; only the transport changed. On first use the stored data-center address is rewritten to that data center's web host. If the session points at a data center outside 1-5, or Telegram no longer knows the auth key, `run` exits 3 with a clear line and nothing is worked around: sign in again.

## What a recap contains

Header with both dates and a short zone label (`ChatBrief · Nov 10, 3:20 AM to Nov 11, 3:20 AM PT`), then:

1. **Needs you:** replies to your own messages, @mentions of you (Telegram mention entities, or `@yourname` typed as plain text), and any message containing one of your priority keywords (not from bots). Posts made as your own channel never count as you. Each shows the sender and one clean sentence, cut at a word boundary with an ellipsis.
2. **Memecoin mentions:** tokens that show up in 2+ chats (or 5+ times in one chat from 2+ people), or that have two or more reported buys at or above the threshold (default 10 SOL or $2,000). Each line shows the ticker and, by default, the most-seen public contract address in a code span (so you can tell coins apart), plus mention counts and any big reported buy. Hide addresses with `settings set memecoin-show-ca off`.
3. **Conversations:** what happened, what was decided, dates. With `collect`, the agent writes these in plain sentences from trimmed messages; `run` prints a sentence-style fallback.
4. **Alert feeds:** automated feeds collapse to one line each, below the conversations (e.g. `Whale Watch: 90 whale alerts, mostly ABC and XYZ`). A feed is a DM with a bot, a chat whose new messages all came from bots (even one), a chat where bots sent at least 60% of 3+ new messages, or a chat where one sender sent at least 80% of 5+ messages that look templated. A bot posting in a group shows once, tied to that group (`Lab Group: 1 trending alert from Some Bot (TI)`); the same alerts in its DM aren't repeated. The noun comes from the messages (trending alert, new listing, whale alert, buy/sell alert, alert, automated post), not the bot's name. Tickers are `$TICKER` or plain ALL-CAPS words of 2-10 characters; anything that looks like an address or a fragment of one is skipped. Bot cards are summarised (`Trending alert (TI)`), never quoted: tree glyphs (├ └ │) and raw stat lines are stripped, and text is cut only at a sentence or word boundary. Turn off with `settings set collapse-alert-bots off`.
5. **Also active:** muted chats with a count (on by default). **Count only:** chats you set to count-only.
6. `N other chats had no new messages.` A chat with new messages is never counted as quiet.
7. `Recap only, not financial advice.` only when market or crypto chats appear.

Length (`short`, `standard`, `detailed`) sets the caps: characters per message (200/300/500), messages per chat (15/30/60), total characters (6k/15k/40k) and chats shown (6/10/20). In conversations and other recap text, wallet-like strings, t.me links, phone numbers and numeric IDs are removed. Public token contract addresses are shown only in the Memecoin mentions section (off with `settings set memecoin-show-ca off`). Personal wallet addresses stay hidden.

## Telegram API terms (section 1.5) and consent

[Telegram's API Terms of Service](https://core.telegram.org/api/terms), section 1.5, say: "you are prohibited from using, accessing or aggregating data obtained from the Telegram platform to train, fine-tune or otherwise engage in the development, enhancement or deployment of artificial intelligence, machine learning models and similar technologies."

This is an AI agent that reads your chats to write recaps, so before sign-in it shows this warning and asks you to confirm:

> ChatBrief is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.
>
> Before you sign in: Telegram's API Terms of Service, section 1.5 (https://core.telegram.org/api/terms), say:
> "you are prohibited from using, accessing or aggregating data obtained from the Telegram platform to train, fine-tune or otherwise engage in the development, enhancement or deployment of artificial intelligence, machine learning models and similar technologies."
>
> ChatBrief is an AI agent that reads your chats to write your recaps. Telegram may consider that against its API terms. Telegram's stated remedy for a breach is to notify the account responsible for the app, and if it isn't fixed within 10 days, to cut off that app's access to the Telegram API (your API ID). ChatBrief never trains on your chats or uses them to build any model. Use it at your own risk.
>
> To continue, confirm that you have read this and accept the risk.

`python -m tg_recap consent show` prints it; `python -m tg_recap consent accept` records your yes as exactly two keys in `~/.tg_recap/settings.json` (0600): `tos_1_5_accepted_at` (ISO time) and `terms_version` (`tg-api-tos-1.5/2026-11-11`). Nothing else is stored. Until then every sign-in path (`login --cards` except `reset`, `--terminal`, `--web`), `collect` and `run` exit **9 `CONSENT_REQUIRED`** with one line, without contacting Telegram.

**Upgrading an existing install (v0.1.7 or earlier):** there is no consent record yet, so scheduled runs exit 9 after the upgrade until you accept. The run skill has the agent show the warning and ask you to confirm in chat; it runs `consent accept` only after your explicit yes. Your session and settings are untouched.

## Settings

`~/.tg_recap/settings.json` (0600, folder 0700), validated with defaults: `include_muted` true, `include_archived` false, `include_dms` true, `length` standard, `collapse_alert_bots` true, `priority_keywords` empty, `memecoin_show_ca` true, `only_included_chats` false (when on, only chats with an include or count-only rule are read; later-joined chats stay out), `memecoin_buy_sol` 10, `memecoin_buy_usd` 2000, `frequency`/`timezone` (stored for the schedule; the code uses the timezone), and per-chat rules stored by an internal salted chat key with the title. Chat titles for matching come from the last recap run (kept in `state.json`, titles only). Raw Telegram IDs are never stored or shown. An older `config.json` is read once if `settings.json` doesn't exist yet. See `docs/sample_recap_v0.1.5.md` for a synthetic example.

## Retention (this code's own cache)

Fetched data is deleted right after the recap is rendered. Rendered recap text is kept for at most 72 hours, then deleted on the next run. This covers only files this code writes; it does not touch Telegram or your apps.

## Open question

Telegram API Terms of Service section 1.5 (rules on AI and machine-learning use of Telegram data) and how it applies to an AI-written personal recap is an **open, unresolved question**. Read the [terms](https://core.telegram.org/api/terms) and decide for yourself before using this; the consent step above makes that an explicit choice.

## Self-serve

This is a template you run on your own machine with your own account. Nobody else logs in, inspects, or holds your session. No wallet keys or seeds are involved; it does hold Telegram account access through the session file.

## Development

Install test deps for the same interpreter install used (`requirements-dev.txt` also pulls in `requirements.txt`):

```
python3 -m pip install --user -r requirements-dev.txt && python3 -m pytest -q
```

(fully offline, fake client). If install fell back to a venv, use `.venv/bin/python -m pip install -r requirements-dev.txt && .venv/bin/python -m pytest -q` instead. `./install.sh --dev` does that install step. You can also `pip install -e ".[dev]"`. Plain `pytest` from the repo root works too, without installing the package (`pythonpath = ["."]` in `pyproject.toml`).

## Product name

The name shown to users lives in one place: `PRODUCT_NAME` in `tg_recap/branding.py` (currently "ChatBrief"). Telegram's API terms: the title must not include "Telegram" (2.3), the disclosure above must stay in the description and docs (2.2), and no Telegram logo or icon may be used (2.4). Code, CLI help and the recap header read the constant; the generated code skills render it. To rename: edit the constant, run `python3 tools/apply_branding.py --from "<old name>"` (README, docs and skill copies), then `python3 tools/build_code_skill.py`. `tests/test_branding.py` fails if any user-facing text still uses another name.
~~~~~

### file: install.sh
sha256: 99ecc6ad5582cc425e06ed05b50612efa77a59731d39e7692bb050d940bd5bc0
~~~~~
#!/bin/sh
# Install ChatBrief dependencies for the chosen interpreter.
# Tries: "$PYTHON" -m pip install --user -r requirements.txt
# Falls back to a local .venv when pip refuses (PEP 668 externally-managed).
# A venv is an option, not a requirement. Usage:
#   ./install.sh           # runtime deps (requirements.txt)
#   ./install.sh --dev     # plus pytest (requirements-dev.txt)
#   PYTHON=python3 ./install.sh
set -eu

cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if [ "${1:-}" = "--dev" ]; then
  REQ="$PWD/requirements-dev.txt"
else
  REQ="$PWD/requirements.txt"
fi

if ! PY=$("$PYTHON" -c 'import sys; print(sys.executable)'); then
  echo "Could not run PYTHON='$PYTHON'. Install Python 3 or set PYTHON to one." >&2
  exit 1
fi

log() { printf '%s
' "$*"; }

install_venv() {
  log "pip --user was refused (this Python is externally managed, PEP 668). Creating a local .venv instead."
  if [ ! -x .venv/bin/python ]; then
    "$PY" -m venv .venv
  fi
  .venv/bin/python -m pip install -r "$REQ"
  log "Installed into .venv. Use this Python for every command:"
  log "  $PWD/.venv/bin/python -m tg_recap ..."
}

log_file=$(mktemp)
trap 'rm -f "$log_file"' EXIT

if "$PY" -m pip install --user -r "$REQ" >"$log_file" 2>&1; then
  cat "$log_file"
  log "Installed for $PY. Use this Python for every command:"
  log "  $PY -m tg_recap ..."
else
  status=$?
  cat "$log_file"
  if grep -qiE 'externally-managed|EXTERNALLY-MANAGED' "$log_file"; then
    install_venv
  else
    log "Install failed (exit $status). If this Python is externally managed, run:"
    log "  $PY -m venv .venv && .venv/bin/python -m pip install -r $REQ"
    exit "$status"
  fi
fi
~~~~~

### file: pyproject.toml
sha256: ae319ef4f2dd3ffbf9162faa79613cf4b18282ac6e7a5d2c6424f7532cf45e1f
~~~~~
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "tg-recap"
version = "0.1.9"
description = "A personal, read-only recap of your own Telegram that you run yourself."
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "telethon==1.45.0",
    "websockets==17.4",
]

[project.scripts]
tg-recap = "tg_recap.__main__:main"

[project.optional-dependencies]
dev = [
    "pytest==9.2.0",
]

[tool.setuptools.packages.find]
include = ["tg_recap*"]
namespaces = false

[tool.pytest.ini_options]
testpaths = ["tests"]
# bare `pytest` (no `python -m`) imports tg_recap from the repo root without installing it
pythonpath = ["."]
~~~~~

### file: requirements-dev.txt
sha256: 11b0006f4e3d389726c8528c5b6797083f14aeaf1ea854cb961f975ad0ae3b39
~~~~~
-r requirements.txt
pytest==9.2.0
~~~~~

### file: requirements.txt
sha256: 052c25bf8b0a459390ee9705269e5c6dc02456342298246393989ec133a4a37b
~~~~~
telethon==1.45.0
websockets==17.4
~~~~~

### file: tg_recap/__init__.py
sha256: 18c92c9dfd12fff8cf375880a70e81d0a90ab9db720367bd7fc19670862bcd82
~~~~~
"""ChatBrief (name: branding.PRODUCT_NAME): a read-only, self-run recap of your own Telegram chats."""

__version__ = "0.1.9"
~~~~~

### file: tg_recap/__main__.py
sha256: 217ccf0970f8b982bdefd4bf433ca55bd040191da8702cc342eaa57828b21dfa
~~~~~
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
~~~~~

### file: tg_recap/alerts.py
sha256: 2bc0825d1418914882bf21b0e77b316cd45d66afd3306e6e3264c7a1e34913f9
~~~~~
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
~~~~~

### file: tg_recap/branding.py
sha256: 387911079c98bbf52e380004e62e3b0f79d3a4aa01093a5c14a0af397894eb8d
~~~~~
"""The product name, in one place.

Telegram's API terms: the title must not include "Telegram" (2.3), users must be
told the app uses the Telegram API (2.2, see DISCLOSURE below), and no Telegram
logo or icon may be used (2.4). Change PRODUCT_NAME here, then run
`python3 tools/apply_branding.py --from "<old name>"` to update the README and
skill copies, and `python3 tools/build_code_skill.py` to rebuild the code skills.
tests/test_branding.py fails if any user-facing text still uses another name.
"""
PRODUCT_NAME = "ChatBrief"

# Shown verbatim in docs, skills, both sign-in screens and at the top of the 1.5 warning.
DISCLOSURE = (f"{PRODUCT_NAME} is an unofficial app that works alongside Telegram. It uses the Telegram API "
              "and is not affiliated with or endorsed by Telegram.")
~~~~~

### file: tg_recap/collect.py
sha256: ff37117bb6955c583cf5b92f32987bf94cb502b86a8728c7a115e6c5314ff865
~~~~~
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
~~~~~

### file: tg_recap/config.py
sha256: f6387a455d529da1736843e436c0aadec96574151c4014ef8c25b208b1603848
~~~~~
"""User settings in ~/.tg_recap/settings.json (0600, folder 0700).

Validated against SCHEMA with defaults. Older installs kept frequency and
timezone in config.json; it is read once as a fallback when settings.json is
missing. Chat rules are stored by internal chat key (a salted hash, never a
Telegram ID) with the title shown to you.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from zoneinfo import ZoneInfo

from . import paths

FREQUENCIES = ("daily", "4h", "hourly", "custom")
LENGTHS = ("short", "standard", "detailed")
CHAT_RULES = ("include", "skip", "count-only")
DEFAULT_TZ = "America/Los_Angeles"
MIN_HOURS = 1
MAX_KEYWORDS = 30
PLAN_WARNING = "runs about 24 times a day and uses more of your Grok Bot plan"

# Caps per length: chars per message, messages per chat, total chars across chats,
# chats shown, and fallback bullets per chat.
LENGTH_CAPS = {
    "short": {"msg_chars": 200, "chat_msgs": 15, "total_chars": 6000, "max_chats": 6, "bullets": 1},
    "standard": {"msg_chars": 300, "chat_msgs": 30, "total_chars": 15000, "max_chats": 10, "bullets": 2},
    "detailed": {"msg_chars": 500, "chat_msgs": 60, "total_chars": 40000, "max_chats": 20, "bullets": 3},
}

# field -> (type, description). Used for validation and `settings show`.
SCHEMA = {
    "frequency": (str, "daily | 4h | hourly | custom (stored for the schedule)"),
    "custom_hours": ((int, type(None)), "whole hours >= 1, only for custom"),
    "daily_hour": (int, "local hour 0-23 for daily recaps"),
    "timezone": (str, "IANA zone, e.g. America/Los_Angeles"),
    "include_muted": (bool, "muted chats appear under Also active"),
    "include_archived": (bool, "archived chats are read"),
    "include_dms": (bool, "one-to-one chats are read"),
    "length": (str, "short | standard | detailed"),
    "priority_keywords": (list, "words flagged first"),
    "collapse_alert_bots": (bool, "alert-bot feeds collapse to one line"),
    "chat_rules": (dict, "chat key -> {title, rule: include | skip | count-only}"),
    "memecoin_buy_sol": ((int, float), "reported SOL buy threshold (default 10)"),
    "memecoin_buy_usd": ((int, float), "reported USD buy threshold (default 2000)"),
    "memecoin_ticker_stop": (list, "extra tickers to ignore in Memecoin mentions"),
    "memecoin_show_ca": (bool, "show public token CAs in Memecoin mentions (default on)"),
    "only_included_chats": (bool, "only chats ruled include or count-only are read (default off)"),
}


class SettingsError(ValueError):
    pass


@dataclass
class Config:
    frequency: str = "daily"
    custom_hours: int | None = None
    daily_hour: int = 8
    timezone: str = DEFAULT_TZ
    include_muted: bool = True
    include_archived: bool = False
    include_dms: bool = True
    length: str = "standard"
    priority_keywords: list = field(default_factory=list)
    collapse_alert_bots: bool = True
    chat_rules: dict = field(default_factory=dict)
    memecoin_buy_sol: float = 10.0
    memecoin_buy_usd: float = 2000.0
    memecoin_ticker_stop: list = field(default_factory=list)
    memecoin_show_ca: bool = True
    only_included_chats: bool = False

    def validate(self) -> "Config":
        for name, (typ, _desc) in SCHEMA.items():
            value = getattr(self, name)
            if typ is int and isinstance(value, bool) or not isinstance(value, typ):
                raise SettingsError(f"{name} has the wrong type")
        if self.frequency not in FREQUENCIES:
            raise SettingsError(f"frequency must be one of {', '.join(FREQUENCIES)}")
        if self.frequency == "custom":
            if self.custom_hours is None:
                raise SettingsError("custom frequency needs --hours")
            self.custom_hours = normalize_hours(self.custom_hours)
        else:
            self.custom_hours = None
        if not 0 <= int(self.daily_hour) <= 23:
            raise SettingsError("daily hour must be 0-23")
        try:
            ZoneInfo(self.timezone)
        except Exception:  # noqa: BLE001
            raise SettingsError("timezone must be an IANA zone like America/Los_Angeles") from None
        if self.length not in LENGTHS:
            raise SettingsError(f"length must be one of {', '.join(LENGTHS)}")
        kws = []
        for k in self.priority_keywords:
            if not isinstance(k, str) or not k.strip() or len(k) > 40:
                raise SettingsError("priority keywords must be short words or phrases")
            if k.strip().casefold() not in {x.casefold() for x in kws}:
                kws.append(k.strip())
        if len(kws) > MAX_KEYWORDS:
            raise SettingsError(f"at most {MAX_KEYWORDS} priority keywords")
        self.priority_keywords = kws
        for key, rule in self.chat_rules.items():
            if not isinstance(key, str) or not isinstance(rule, dict) or rule.get("rule") not in CHAT_RULES \
                    or not isinstance(rule.get("title"), str):
                raise SettingsError("chat_rules entries need a title and a rule (include, skip, count-only)")
        for name in ("memecoin_buy_sol", "memecoin_buy_usd"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SettingsError(f"{name} has the wrong type")
            if value < 0:
                raise SettingsError(f"{name} must be 0 or more")
            setattr(self, name, float(value))
        stops = []
        for k in self.memecoin_ticker_stop:
            if not isinstance(k, str) or not k.strip() or len(k) > 16:
                raise SettingsError("memecoin ticker stop entries must be short tickers")
            tok = k.strip().lstrip("$").upper()
            if tok not in stops:
                stops.append(tok)
        if len(stops) > MAX_KEYWORDS:
            raise SettingsError(f"at most {MAX_KEYWORDS} extra memecoin stop tickers")
        self.memecoin_ticker_stop = stops
        return self

    @property
    def interval_hours(self) -> int:
        return {"daily": 24, "4h": 4, "hourly": 1}.get(self.frequency) or int(self.custom_hours)

    @property
    def caps(self) -> dict:
        return LENGTH_CAPS[self.length]

    def rule_for(self, key: str) -> str | None:
        r = self.chat_rules.get(key)
        return r["rule"] if r else None


def normalize_hours(hours) -> int:
    h = int(hours)
    if float(hours) != h:
        raise SettingsError("custom interval must be a whole number of hours")
    if h < MIN_HOURS:
        raise SettingsError(f"custom interval must be at least {MIN_HOURS} hour")
    return h


def _from_dict(data: dict) -> Config:
    known = {k: v for k, v in (data or {}).items() if k in Config.__dataclass_fields__}
    try:
        return Config(**known).validate()
    except TypeError:
        raise SettingsError("settings.json has an unexpected shape") from None


def load() -> Config:
    data = paths.read_json(paths.settings_file())
    if data is not None and not isinstance(data, dict):
        raise SettingsError("settings.json has an unexpected shape")
    if not any(k in Config.__dataclass_fields__ for k in (data or {})):
        # legacy config.json keeps frequency/timezone; also when settings.json holds only the consent record
        legacy = paths.read_json(paths.config_file(), {}) or {}
        data = {**(legacy if isinstance(legacy, dict) else {}), **(data or {})}
    return _from_dict(data)


def save(cfg: Config) -> None:
    """Write settings; the consent record (consent.KEYS) already in the file is kept."""
    from .consent import preserved
    cfg.validate()
    paths.write_json(paths.settings_file(), {**asdict(cfg), **preserved()})


def cron_for(cfg: Config) -> str:
    """Cron string (in cfg.timezone) for the routine that runs the recap.

    custom N hours: N < 24 -> "0 */N * * *" (cron restarts the count at midnight
    when 24 is not a multiple of N); N >= 24 -> every round(N/24) days at daily_hour.
    """
    cfg.validate()
    if cfg.frequency == "daily":
        return f"0 {cfg.daily_hour} * * *"
    if cfg.frequency == "4h":
        return "0 */4 * * *"
    if cfg.frequency == "hourly":
        return "0 * * * *"
    n = cfg.custom_hours
    if n == 1:
        return "0 * * * *"
    if n < 24:
        return f"0 */{n} * * *"
    days = max(1, round(n / 24))
    return f"0 {cfg.daily_hour} * * *" if days == 1 else f"0 {cfg.daily_hour} */{days} * *"


def plan_warning(cfg: Config) -> str | None:
    """Warning shown by the frequency picker; None when the choice is light."""
    cfg.validate()
    n = cfg.interval_hours
    if n == 1:
        return PLAN_WARNING
    if n < 4:
        return f"runs about {24 // n} times a day and uses more of your Grok Bot plan"
    return None
~~~~~

### file: tg_recap/consent.py
sha256: 5e891cf0df02d926c4f0674185d6c481253c663775ce54cf5258103321de47f4
~~~~~
"""Consent gate for Telegram API Terms of Service section 1.5 (AI use of data).

Sign-in, `collect` and `run` refuse (exit 9 CONSENT_REQUIRED) until the owner
has read WARNING and run `consent accept`. Accepting records exactly two keys in
~/.tg_recap/settings.json (0600): tos_1_5_accepted_at (ISO time, UTC) and
terms_version. Nothing else is stored. A new TERMS_VERSION asks again.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import paths
from .branding import DISCLOSURE, PRODUCT_NAME  # noqa: F401 - DISCLOSURE re-exported

EXIT_CONSENT = 9
TERMS_URL = "https://core.telegram.org/api/terms"
TERMS_VERSION = "tg-api-tos-1.5/2026-11-11"
KEYS = ("tos_1_5_accepted_at", "terms_version")

CLAUSE = ("you are prohibited from using, accessing or aggregating data obtained from the Telegram platform to "
          "train, fine-tune or otherwise engage in the development, enhancement or deployment of artificial "
          "intelligence, machine learning models and similar technologies.")
WARNING = (
    f"{DISCLOSURE}\n\n"
    f"Before you sign in: Telegram's API Terms of Service, section 1.5 ({TERMS_URL}), say:\n"
    f"\"{CLAUSE}\"\n\n"
    f"{PRODUCT_NAME} is an AI agent that reads your chats to write your recaps. Telegram may consider that "
    "against its API terms. Telegram's stated remedy for a breach is to notify the account responsible for the "
    "app, and if it isn't fixed within 10 days, to cut off that app's access to the Telegram API (your API ID). "
    f"{PRODUCT_NAME} never trains on your chats or uses them to build any model. Use it at your own risk.\n\n"
    "To continue, confirm that you have read this and accept the risk."
)
REQUIRED_MSG = (f"CONSENT_REQUIRED: {PRODUCT_NAME} needs your OK on Telegram's API terms (section 1.5) first. "
                "Run `consent show`, then `consent accept` only after you agree.")


def _settings() -> dict:
    data = paths.read_json(paths.settings_file(), {})
    return data if isinstance(data, dict) else {}


def accepted() -> bool:
    data = _settings()
    return isinstance(data.get("tos_1_5_accepted_at"), str) and data.get("terms_version") == TERMS_VERSION


def accept(now: datetime | None = None) -> dict:
    """Record consent: only the two KEYS are added; other settings are kept as they are."""
    now = now or datetime.now(timezone.utc)
    record = {"tos_1_5_accepted_at": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
              "terms_version": TERMS_VERSION}
    paths.ensure_dir()
    paths.write_json(paths.settings_file(), {**_settings(), **record})
    paths.tighten(paths.settings_file())
    return record


def preserved(existing: dict | None = None) -> dict:
    """The consent keys from settings.json, so other writers keep them."""
    data = _settings() if existing is None else existing
    return {k: data[k] for k in KEYS if k in data}


def require(err) -> int | None:
    """Print one line and return 9 when consent is missing, else None."""
    if accepted():
        return None
    print(REQUIRED_MSG, file=err, flush=True)
    return EXIT_CONSENT
~~~~~

### file: tg_recap/deps.py
sha256: 8031df2a7fc73120bc40ceb839e68dfaf00afe54f78fb501c83aa1c0345629a6
~~~~~
"""Runtime dependency checks: fail with one line, not a traceback."""
from __future__ import annotations

import sys

TELETHON_VERSION = "1.45.0"
WEBSOCKETS_VERSION = "17.4"
EXIT_MISSING_DEPS = 6


def missing_telethon_message(executable: str | None = None) -> str:
    exe = executable or sys.executable
    return (
        f"Telethon {TELETHON_VERSION} isn't installed for this Python ({exe}). "
        f"Run: {exe} -m pip install -r requirements.txt"
    )


def missing_websockets_message(executable: str | None = None) -> str:
    exe = executable or sys.executable
    return (
        f"websockets {WEBSOCKETS_VERSION} isn't installed for this Python ({exe}). "
        f"Run: {exe} -m pip install -r requirements.txt"
    )


def require_telethon() -> int | None:
    """Return exit code 6 if Telethon or websockets is missing, otherwise None."""
    try:
        import telethon  # noqa: F401
    except ImportError:
        print(missing_telethon_message(), file=sys.stderr)
        return EXIT_MISSING_DEPS
    try:
        import websockets.asyncio.client  # noqa: F401
    except ImportError:
        print(missing_websockets_message(), file=sys.stderr)
        return EXIT_MISSING_DEPS
    return None


require_deps = require_telethon
~~~~~

### file: tg_recap/lock.py
sha256: 4768c2b14cdac8f47e7d87cc9f8cd0f7ef42e4de07a3b06360c768a55703c7e1
~~~~~
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
~~~~~

### file: tg_recap/login_backend.py
sha256: a8ce122cddc55a3a3fa3661b97cd115c4bb547f2686eedfb04204249c531a8b6
~~~~~
"""Shared Telethon sign-in steps for the terminal login (default) and the web fallback.

Only these client methods are ever used here: LOGIN_METHODS. They are the
login calls themselves; nothing else is sent to Telegram. After sign-in, every
scheduled run goes through readonly.ReadOnlyClient, which denies sign_in and
send_code_request (and every write) outright.

Telethon errors are translated into the small exceptions below, raised
``from None`` and carrying no message, so a phone number, login code or
two-step password can never ride along in an exception, a traceback or a log.
"""
from __future__ import annotations

import logging

from . import paths
from .readonly import _flood_seconds

LOGIN_METHODS = frozenset({"connect", "send_code_request", "sign_in", "disconnect"})

# Keep Telethon quiet during sign-in; our own messages never include values.
logging.getLogger("telethon").setLevel(logging.WARNING)


class LoginError(Exception):
    """Base for sign-in outcomes. Never carries user-typed values."""

    def __init__(self):
        super().__init__()


class PasswordNeeded(LoginError):
    """The account has a two-step password."""


class CodeInvalid(LoginError):
    """Telegram rejected the login code."""


class CodeExpired(LoginError):
    """The login code expired; a new one has to be requested."""


class PasswordInvalid(LoginError):
    """Telegram rejected the two-step password."""


class PhoneInvalid(LoginError):
    """Telegram rejected the phone number format."""


class ApiInvalid(LoginError):
    """Telegram rejected the API ID / API hash pair."""


class FloodWait(LoginError):
    """Telegram asked to wait before trying again."""

    def __init__(self, seconds: int):
        super().__init__()
        self.seconds = int(seconds)


class ConnectFailed(LoginError):
    """Couldn't reach Telegram's web endpoint (DNS, TLS, WebSocket, timeout)."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind


class TelegramRefused(LoginError):
    """Any other Telegram error. Only the error type name is kept."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind


_BY_NAME = {
    "SessionPasswordNeededError": PasswordNeeded,
    "PhoneCodeInvalidError": CodeInvalid,
    "PhoneCodeEmptyError": CodeInvalid,
    "PhoneCodeExpiredError": CodeExpired,
    "PasswordHashInvalidError": PasswordInvalid,
    "PhoneNumberInvalidError": PhoneInvalid,
    "ApiIdInvalidError": ApiInvalid,
    "ApiIdPublishedFloodError": ApiInvalid,
}


def translate(exc: BaseException) -> LoginError:
    """Map a Telethon (or other) error to a value-free LoginError."""
    if isinstance(exc, LoginError):
        return exc
    secs = _flood_seconds(exc)
    if secs is not None:
        return FloodWait(secs)
    cls = _BY_NAME.get(type(exc).__name__)
    if cls is not None:
        return cls()
    if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
        from .transport_wss import last_connect_error  # noqa: WPS433 - lazy: needs telethon
        return ConnectFailed(getattr(exc, "kind", None) or last_connect_error() or type(exc).__name__)
    return TelegramRefused(type(exc).__name__)


def _default_client_factory(session: str, api_id: int, api_hash: str):
    from .transport_wss import WebTelegramClient, quiet_telethon_logs
    quiet_telethon_logs()
    client = WebTelegramClient(session, api_id, api_hash, receive_updates=False, flood_sleep_threshold=0)
    no_entity_cache(client)
    return client


def no_entity_cache(client):
    """Stop Telethon caching users/chats (names, usernames, phone numbers) in the
    session sqlite file. Sign-in returns your own user (with your phone number),
    so without this the number would land on disk."""
    session = getattr(client, "session", None)
    if session is not None and hasattr(session, "save_entities"):
        session.save_entities = False
    return client


class TelethonBackend:
    """Real sign-in through Telethon. Offline tests inject a fake ``client_factory``."""

    def __init__(self, client_factory=None, session_base=None):
        self._factory = client_factory or _default_client_factory
        self._session_base = session_base  # default: paths.session_base()
        self.client = None
        self._phone = None
        self._hash = None

    @property
    def phone_code_hash(self):
        return self._hash

    def restore(self, phone: str, phone_code_hash: str) -> None:
        """Resume in a new process: phone from the caller, hash from pending state."""
        self._phone, self._hash = phone, phone_code_hash

    def _session_file(self):
        base = self._session_base or paths.session_base()
        return base.with_name(base.name + ".session")

    async def _call(self, name: str, *args, **kwargs):
        if name not in LOGIN_METHODS:  # defensive: login touches nothing else
            raise TelegramRefused("NotALoginCall")
        try:
            return await getattr(self.client, name)(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - translated, values dropped
            err = translate(exc)
        raise err from None

    async def start(self, api_id: int, api_hash: str):
        base = self._session_base or paths.session_base()
        paths.ensure_dir(base.parent)
        self.client = self._factory(str(base), int(api_id), api_hash)
        await self._call("connect")
        paths.tighten(self._session_file())

    async def send_code(self, phone: str):
        sent = await self._call("send_code_request", phone)
        self._phone, self._hash = phone, sent.phone_code_hash

    async def resend_code(self):
        """Ask for a fresh code after CodeExpired (same login call, same phone)."""
        sent = await self._call("send_code_request", self._phone)
        self._hash = sent.phone_code_hash

    async def sign_in_code(self, code: str):
        await self._call("sign_in", phone=self._phone, code=code, phone_code_hash=self._hash)

    async def sign_in_password(self, password: str):
        await self._call("sign_in", password=password)

    async def finish(self):
        self._phone = self._hash = None
        if self.client is not None:
            await self._call("disconnect")
        paths.tighten(self._session_file())

    async def abort(self):
        self._phone = self._hash = None
        if self.client is not None:
            try:
                await self._call("disconnect")
            finally:
                paths.tighten(self._session_file())


def save_credentials(api_id: int, api_hash: str) -> None:
    """Persist only api_id + api_hash (0600) and force the session file to 0600."""
    paths.ensure_dir()
    paths.write_json(paths.credentials_file(), {"api_id": int(api_id), "api_hash": api_hash})
    paths.tighten(paths.session_file())
~~~~~

### file: tg_recap/login_cards.py
sha256: ab1d77efbf2520209021cd5dbcd707916de0d65e5515a1a21a20d31908c41c9a
~~~~~
"""Resumable sign-in by secret-request cards (the default): `login --cards <step>`.

Each card is one value, delivered as an env var. Each step runs in its own
process, reads only its own vars, and keeps what the next step needs on disk.
  save-api   TG_RECAP_API_ID + TG_RECAP_API_HASH -> credentials.json (0600)
  send-code  TG_RECAP_PHONE -> pending/ (0700): Telethon session + state.json
             (phone_code_hash, stage), files 0600
  sign-in    TG_RECAP_CODE + TG_RECAP_PHONE -> done, or 10 NEED_2FA
  password   TG_RECAP_2FA -> done
  reset      wipe pending/
On success the session moves to ~/.tg_recap/tg_recap.session (0600) and
pending/ is removed. The phone is never written to disk in any form (a hash of
it is easy to reverse): sign-in re-reads TG_RECAP_PHONE, which stays set after
its card. Telethon's entity cache is off, so your own user record (with your
number) isn't saved in the sqlite session either. Values are never printed,
logged or saved; messages name only the step, the env var or the error kind.
Exit codes: the EXIT_* constants below (9 CONSENT_REQUIRED: run `consent accept` after
reading `consent show`; 8 CONNECT_FAILED: Telegram's web endpoint
unreachable); 6 MISSING_DEPS comes from the CLI.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from datetime import datetime, timezone

from . import consent, paths
from .lock import LockHeld, SessionLock
from .login_backend import (ApiInvalid, CodeExpired, CodeInvalid, FloodWait, LoginError,
                            PasswordInvalid, PasswordNeeded, PhoneInvalid, TelegramRefused, ConnectFailed,
                            TelethonBackend, save_credentials)

ENV_API_ID = "TG_RECAP_API_ID"
ENV_API_HASH = "TG_RECAP_API_HASH"
ENV_PHONE = "TG_RECAP_PHONE"
ENV_CODE = "TG_RECAP_CODE"
ENV_2FA = "TG_RECAP_2FA"
ENV_VARS = (ENV_API_ID, ENV_API_HASH, ENV_PHONE, ENV_CODE, ENV_2FA)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_LOCK = 2
EXIT_FLOOD = 4
EXIT_CONNECT = 8
EXIT_NOT_SET_UP = 5
EXIT_NEED_2FA = 10
EXIT_CODE_INVALID = 11
EXIT_PASSWORD_INVALID = 12
EXIT_CODE_EXPIRED = 13
EXIT_PHONE_INVALID = 14
EXIT_API_INVALID = 15
EXIT_MISSING_ENV = 16
EXIT_NO_PENDING = 17

STEPS = ("save-api", "send-code", "sign-in", "password", "reset")

USAGE = (
    "Sign in with secret-request cards (one value each), then run each step:\n"
    f"  login --cards save-api    reads {ENV_API_ID}, {ENV_API_HASH}\n"
    f"  login --cards send-code   reads {ENV_PHONE}\n"
    f"  login --cards sign-in     reads {ENV_CODE} and {ENV_PHONE} (exit 10 = send the {ENV_2FA} card)\n"
    f"  login --cards password    reads {ENV_2FA}\n"
    "  login --cards reset       wipes an unfinished sign-in\n"
    "Fallbacks: login --terminal (type in a terminal) or login --web (127.0.0.1 page).\n"
    "Never type these values into a chat."
)


class _Exit(Exception):
    def __init__(self, code: int, message: str = ""):
        super().__init__()
        self.code, self.message = code, message


def _env(env, name: str) -> str:
    value = (env.get(name) or "").strip()
    if not value:
        raise _Exit(EXIT_MISSING_ENV, f"MISSING_ENV: {name} isn't set. Send the {name} secret card, then run "
                                      "this step again.")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clear_pending() -> None:
    shutil.rmtree(paths.pending_dir(), ignore_errors=True)


def _tighten_tree(root) -> None:
    if not root.exists():
        return
    os.chmod(root, paths.DIR_MODE)
    for p in root.rglob("*"):
        os.chmod(p, paths.DIR_MODE if p.is_dir() else paths.FILE_MODE)


def _creds():
    creds = paths.read_json(paths.credentials_file()) or {}
    if not creds.get("api_id") or not creds.get("api_hash"):
        raise _Exit(EXIT_NOT_SET_UP, "NOT_SET_UP: no saved API ID / API hash yet. Run `login --cards save-api` "
                                     "first.")
    return int(creds["api_id"]), creds["api_hash"]


def _pending():
    state = paths.read_json(paths.pending_state_file())
    if not state or not state.get("phone_code_hash") or not \
            (paths.pending_dir() / (paths.pending_session_base().name + ".session")).exists():
        raise _Exit(EXIT_NO_PENDING, "NO_PENDING: no sign-in in progress. Run `login --cards send-code` first.")
    return state


class CardLogin:
    def __init__(self, env=None, client_factory=None, out=None, err=None):
        self.env = os.environ if env is None else env
        self.factory = client_factory
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self._loop = None

    def say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def _backend(self):
        return TelethonBackend(client_factory=self.factory, session_base=paths.pending_session_base())

    def _close(self, backend) -> None:
        try:
            self._run(backend.abort())  # disconnect only; keeps pending files
        except BaseException:  # noqa: BLE001
            pass
        _tighten_tree(paths.pending_dir())

    def _finish(self, backend) -> None:
        self._run(backend.finish())
        pending_session = paths.pending_dir() / (paths.pending_session_base().name + ".session")
        final = paths.session_file()
        for stale in (final.with_name(final.name + "-journal"),):
            if stale.exists():
                stale.unlink()
        os.replace(pending_session, final)
        paths.tighten(final)
        clear_pending()

    # --- steps --------------------------------------------------------------
    def save_api(self) -> int:
        api_id = _env(self.env, ENV_API_ID)
        api_hash = _env(self.env, ENV_API_HASH)
        if not api_id.isdigit() or int(api_id) <= 0 or len(api_hash) < 16:
            raise _Exit(EXIT_API_INVALID, f"API_INVALID: {ENV_API_ID} must be a whole number and {ENV_API_HASH} "
                                          "the hash from my.telegram.org. Re-send those cards.")
        clear_pending()  # a pending sign-in belongs to the old API values
        save_credentials(int(api_id), api_hash)
        self.say("Saved the API ID and API hash (owner-only). Next: the phone card, then "
                 "`login --cards send-code`.")
        return EXIT_OK

    def send_code(self) -> int:
        api_id, api_hash = _creds()
        phone = _env(self.env, ENV_PHONE)
        clear_pending()
        paths.ensure_dir(paths.pending_dir())
        backend = self._backend()
        try:
            self._run(backend.start(api_id, api_hash))
            self._run(backend.send_code(phone))
            paths.write_json(paths.pending_state_file(),
                             {"phone_code_hash": backend.phone_code_hash, "stage": "code", "created_at": _now()})
        except BaseException:
            self._close(backend)
            clear_pending()
            raise
        self._close(backend)
        self.say("Telegram sent a login code to your Telegram app. Next: the code card, then "
                 "`login --cards sign-in`.")
        return EXIT_OK

    def sign_in(self) -> int:
        state = _pending()
        code = _env(self.env, ENV_CODE)
        phone = _env(self.env, ENV_PHONE)
        api_id, api_hash = _creds()
        backend = self._backend()
        try:
            self._run(backend.start(api_id, api_hash))
            backend.restore(phone, state["phone_code_hash"])
            self._run(backend.sign_in_code(code))
        except PasswordNeeded:
            self._close(backend)
            state["stage"] = "password"
            paths.write_json(paths.pending_state_file(), state)
            _tighten_tree(paths.pending_dir())
            raise _Exit(EXIT_NEED_2FA, f"NEED_2FA: your account has a two-step password. Next: the {ENV_2FA} "
                                       "card, then `login --cards password`.") from None
        except CodeInvalid:
            self._close(backend)
            raise _Exit(EXIT_CODE_INVALID, f"CODE_INVALID: Telegram didn't accept that code. Re-send the "
                                           f"{ENV_CODE} card, then run sign-in again.") from None
        except CodeExpired:
            self._close(backend)
            clear_pending()
            raise _Exit(EXIT_CODE_EXPIRED, "CODE_EXPIRED: that code expired; the unfinished sign-in was cleared. "
                                           f"Start again at `login --cards send-code`, then a new {ENV_CODE} "
                                           "card.") from None
        except BaseException:
            self._close(backend)
            raise
        self._finish(backend)
        return self._signed_in()

    def password(self) -> int:
        state = _pending()
        if state.get("stage") != "password":
            raise _Exit(EXIT_NO_PENDING, "NO_PENDING: no two-step password is pending. Run "
                                         "`login --cards sign-in` first.")
        password = _env(self.env, ENV_2FA)
        api_id, api_hash = _creds()
        backend = self._backend()
        try:
            self._run(backend.start(api_id, api_hash))
            self._run(backend.sign_in_password(password))
        except PasswordInvalid:
            self._close(backend)
            raise _Exit(EXIT_PASSWORD_INVALID, f"PASSWORD_INVALID: Telegram didn't accept that two-step password. "
                                               f"Re-send the {ENV_2FA} card, then run password again.") from None
        except BaseException:
            self._close(backend)
            raise
        finally:
            password = None
        self._finish(backend)
        return self._signed_in()

    def reset(self) -> int:
        clear_pending()
        self.say("Cleared any unfinished sign-in. Saved API values and an existing session were kept.")
        return EXIT_OK

    def _signed_in(self) -> int:
        self.say("Signed in. Session saved under ~/.tg_recap (owner-only). End it any time in Telegram "
                 "Settings > Devices.")
        return EXIT_OK

    # --- entry --------------------------------------------------------------
    def run(self, step: str) -> int:
        if step not in STEPS:
            print(USAGE, file=self.err)
            return EXIT_FAILED
        os.umask(0o077)
        paths.ensure_dir()
        try:
            lock = SessionLock().acquire()
        except LockHeld:
            print("LOCK_HELD: a recap run is using the session right now. Try this step again in a minute.",
                  file=self.err, flush=True)
            return EXIT_LOCK
        self._loop = asyncio.new_event_loop()
        try:
            fn = {"save-api": self.save_api, "send-code": self.send_code, "sign-in": self.sign_in,
                  "password": self.password, "reset": self.reset}[step]
            return fn()
        except _Exit as ex:
            print(ex.message, file=self.err, flush=True)
            return ex.code
        except PhoneInvalid:
            print(f"PHONE_INVALID: Telegram didn't accept that phone number. Re-send the {ENV_PHONE} card "
                  "(international format, like +1 then the number), then run send-code again.",
                  file=self.err, flush=True)
            return EXIT_PHONE_INVALID
        except ApiInvalid:
            print(f"API_INVALID: Telegram didn't accept the API ID / API hash. Re-send the {ENV_API_ID} and "
                  f"{ENV_API_HASH} cards, then run save-api again.", file=self.err, flush=True)
            return EXIT_API_INVALID
        except FloodWait as fw:
            clear_pending()
            print(f"FLOOD_STOP: Telegram asked to wait {fw.seconds}s. The unfinished sign-in was cleared; "
                  "start again at send-code later.", file=self.err, flush=True)
            return EXIT_FLOOD
        except ConnectFailed as cf:
            print(f"CONNECT_FAILED: couldn't reach Telegram's web endpoint ({cf.kind}). Nothing was saved by "
                  f"this step; tell the user and stop. Run {step} again later.", file=self.err, flush=True)
            return EXIT_CONNECT
        except TelegramRefused as tr:
            print(f"FAILED: Telegram didn't accept the {step} step ({tr.kind}).", file=self.err, flush=True)
            return EXIT_FAILED
        except LoginError as le:
            print(f"FAILED: {step} didn't finish ({type(le).__name__}).", file=self.err, flush=True)
            return EXIT_FAILED
        except (KeyboardInterrupt, EOFError):
            print(f"FAILED: {step} was cancelled.", file=self.err, flush=True)
            return EXIT_FAILED
        except Exception as exc:  # noqa: BLE001 - kind only, never values or a traceback
            print(f"FAILED: {step} stopped ({type(exc).__name__}).", file=self.err, flush=True)
            return EXIT_FAILED
        finally:
            lock.release()
            self._loop.close()
            _tighten_tree(paths.pending_dir())
            paths.tighten(paths.session_file())


def login(step: str, env=None, client_factory=None, out=None, err=None) -> int:
    """Every step except `reset` needs the API-terms consent first (exit 9 without it)."""
    logging.getLogger("telethon").setLevel(logging.CRITICAL)
    if step != "reset":
        refused = consent.require(err or sys.stderr)
        if refused is not None:
            return refused
    return CardLogin(env, client_factory, out, err).run(step)
~~~~~

### file: tg_recap/login_terminal.py
sha256: 6e0245b1da5b2c6a13757f06503cbfb62ab64a74757a3e2a09b6c166876b0eba
~~~~~
"""Interactive terminal sign-in (the default): `python -m tg_recap login`.

The user runs this in a terminal on the machine that will hold the session and
types their own details. Prompts, in order:
  API ID (shown as typed) and API hash (hidden), unless saved ones are reused,
  phone number (input), login code (input), and the two-step password
  (hidden, getpass) only when Telegram says the account has one.

Uses the same Telethon send_code_request / sign_in steps as the web fallback
(login_backend.TelethonBackend). Nothing else is sent to Telegram.

Saved (dir 0700, files 0600): credentials.json (api_id + api_hash) and
Telethon's session file tg_recap.session. Never printed, logged or saved: the
phone number, login code, two-step password, or session contents. Errors are
reported by kind only, never with the values, and never as a traceback.

Exit codes: 0 signed in, 1 not finished (cancelled, too many wrong tries, or
Telegram refused), 2 LOCK_HELD (a recap run is using the session),
4 FLOOD_STOP (Telegram asked to wait), 8 CONNECT_FAILED (Telegram's web endpoint
unreachable), 9 CONSENT_REQUIRED (run `consent accept` after reading `consent show`).
"""
from __future__ import annotations

import asyncio
import getpass
import logging
import os
import sys

from . import consent, paths
from .branding import PRODUCT_NAME
from .lock import LockHeld, SessionLock
from .login_backend import (ApiInvalid, CodeExpired, CodeInvalid, FloodWait, LoginError,
                            PasswordInvalid, PasswordNeeded, PhoneInvalid, TelegramRefused, ConnectFailed,
                            TelethonBackend, save_credentials)

EXIT_OK, EXIT_NOT_FINISHED, EXIT_LOCK, EXIT_FLOOD, EXIT_CONNECT = 0, 1, 2, 4, 8
MAX_TRIES = 3      # per prompt: API values, phone, code, password
MAX_RESENDS = 1    # fresh codes requested after an expired one

INTRO = (
    f"{PRODUCT_NAME}: sign in\n"
    f"{consent.DISCLOSURE}\n"
    "This signs in as you with Telethon, on this computer only. It only reads your chats.\n"
    "Type your details here yourself, never in a chat. Hidden fields don't show what you type.\n"
    "Your phone number, login code and two-step password are used once and are never saved,\n"
    "shown back or logged. Kept on this computer, readable only by you: your API ID, API hash\n"
    "and Telegram's session file (~/.tg_recap). End the session any time in Telegram under\n"
    "Settings > Devices. Ctrl+C cancels.\n"
)
API_HELP = ("Get your own API ID and API hash at https://my.telegram.org (API development tools).\n"
            "Telegram's steps: https://core.telegram.org/api/obtaining_api_id\n")
NOT_SAVED = "Nothing about your phone, code or password was saved."


class _Stop(Exception):
    def __init__(self, code: int, message: str):
        super().__init__()
        self.code, self.message = code, message


def _valid_api(api_id: str, api_hash: str) -> bool:
    return api_id.isdigit() and len(api_hash) >= 16


class TerminalLogin:
    def __init__(self, backend=None, input_fn=input, getpass_fn=getpass.getpass, out=None, err=None):
        self.backend = backend or TelethonBackend()
        self.input = input_fn
        self.getpass = getpass_fn
        self.out = out or sys.stdout
        self.err = err or sys.stderr
        self._loop = asyncio.new_event_loop()

    # --- helpers ------------------------------------------------------------
    def say(self, text: str) -> None:
        print(text, file=self.out, flush=True)

    def warn(self, text: str) -> None:
        print(text, file=self.err, flush=True)

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    # --- steps --------------------------------------------------------------
    def _api_values(self):
        saved = paths.read_json(paths.credentials_file()) or {}
        if saved.get("api_id") and saved.get("api_hash"):
            answer = self.input("Use the API ID and API hash already saved on this computer? [Y/n]: ")
            if answer.strip().lower() in ("", "y", "yes"):
                return int(saved["api_id"]), saved["api_hash"]
        self.say(API_HELP)
        for left in range(MAX_TRIES - 1, -1, -1):
            api_id = self.input("API ID: ").strip()
            api_hash = self.getpass("API hash (hidden): ").strip()
            if _valid_api(api_id, api_hash):
                return int(api_id), api_hash
            api_id = api_hash = None
            self.warn("That API ID or API hash doesn't look right. Copy both from my.telegram.org."
                      + (f" {left} tries left." if left else ""))
        raise _Stop(EXIT_NOT_FINISHED, "Too many tries for the API ID / API hash.")

    def _phone(self):
        for left in range(MAX_TRIES - 1, -1, -1):
            phone = self.input("Phone number, international format (for example +1 then your number): ").strip()
            try:
                if not phone:
                    raise PhoneInvalid()
                self._run(self.backend.send_code(phone))
                self.say("Telegram sent a login code to your Telegram app.")
                return
            except PhoneInvalid:
                self.warn("Telegram didn't accept that phone number. Use international format."
                          + (f" {left} tries left." if left else ""))
            finally:
                phone = None
        raise _Stop(EXIT_NOT_FINISHED, "Too many tries for the phone number.")

    def _code(self) -> bool:
        """Return True when a two-step password is needed next."""
        wrong = resends = 0
        while True:
            code = self.input("Login code: ").strip()
            try:
                self._run(self.backend.sign_in_code(code))
                return False
            except PasswordNeeded:
                return True
            except CodeInvalid:
                wrong += 1
                if wrong >= MAX_TRIES:
                    raise _Stop(EXIT_NOT_FINISHED, "Too many wrong login codes.") from None
                self.warn(f"That code didn't work. {MAX_TRIES - wrong} tries left.")
            except CodeExpired:
                if resends >= MAX_RESENDS:
                    raise _Stop(EXIT_NOT_FINISHED, "The login code expired again.") from None
                resends += 1
                self._run(self.backend.resend_code())
                self.warn("That code expired. Telegram sent a new one; type the new code.")
            finally:
                code = None

    def _password(self):
        for left in range(MAX_TRIES - 1, -1, -1):
            password = self.getpass("Two-step password (hidden): ")
            try:
                self._run(self.backend.sign_in_password(password))
                return
            except PasswordInvalid:
                self.warn("That two-step password didn't work." + (f" {left} tries left." if left else ""))
            finally:
                password = None
        raise _Stop(EXIT_NOT_FINISHED, "Too many wrong two-step passwords.")

    def _flow(self) -> int:
        self.say(INTRO)
        api_id, api_hash = self._api_values()
        self._run(self.backend.start(api_id, api_hash))
        try:
            self._phone()
        except ApiInvalid:
            raise _Stop(EXIT_NOT_FINISHED, "Telegram didn't accept that API ID / API hash. "
                                           "Check both on my.telegram.org.") from None
        if self._code():
            self.say("Your account has a two-step password.")
            self._password()
        self._run(self.backend.finish())
        save_credentials(api_id, api_hash)
        api_hash = None
        return EXIT_OK

    def run(self) -> int:
        os.umask(0o077)
        paths.ensure_dir()
        try:
            lock = SessionLock().acquire()
        except LockHeld:
            self.warn("LOCK_HELD: A recap run is using the session right now. Try again in a minute.")
            self._loop.close()
            return EXIT_LOCK
        code, ok = EXIT_NOT_FINISHED, False
        try:
            code = self._flow()
            ok = code == EXIT_OK
        except _Stop as stop:
            self.warn(f"Sign-in not finished: {stop.message} {NOT_SAVED}")
            code = stop.code
        except FloodWait as fw:
            self.warn(f"FLOOD_STOP: Telegram asked to wait {fw.seconds}s before another sign-in try. "
                      f"{NOT_SAVED} Try again later.")
            code = EXIT_FLOOD
        except (KeyboardInterrupt, EOFError):
            self.warn(f"Sign-in cancelled. {NOT_SAVED}")
            code = EXIT_NOT_FINISHED
        except ConnectFailed as cf:
            self.warn(f"CONNECT_FAILED: couldn't reach Telegram's web endpoint ({cf.kind}). {NOT_SAVED}")
            code = EXIT_CONNECT
        except TelegramRefused as tr:
            self.warn(f"Telegram didn't accept the sign-in ({tr.kind}). {NOT_SAVED}")
            code = EXIT_NOT_FINISHED
        except LoginError as le:
            self.warn(f"Sign-in not finished ({type(le).__name__}). {NOT_SAVED}")
            code = EXIT_NOT_FINISHED
        except Exception as exc:  # noqa: BLE001 - kind only, never values or a traceback
            self.warn(f"Sign-in stopped ({type(exc).__name__}). {NOT_SAVED}")
            code = EXIT_NOT_FINISHED
        finally:
            if not ok:
                try:
                    self._run(self.backend.abort())
                except BaseException:  # noqa: BLE001
                    pass
            lock.release()
            self._loop.close()
            paths.tighten(paths.session_file())
        if ok:
            self.say("Signed in. Session saved under ~/.tg_recap (owner-only). "
                     "End it any time in Telegram Settings > Devices.")
        return code


def login(backend=None, input_fn=input, getpass_fn=getpass.getpass, out=None, err=None) -> int:
    logging.getLogger("telethon").setLevel(logging.CRITICAL)
    refused = consent.require(err or sys.stderr)
    if refused is not None:
        return refused  # 9: accept the API-terms warning first (`consent accept`)
    return TerminalLogin(backend, input_fn, getpass_fn, out, err).run()
~~~~~

### file: tg_recap/login_web.py
sha256: ba4bdc30c70e4fa08642cb19b99eb7cd3d5d47ebea216279427ff385ead5ff9b
~~~~~
"""Optional web fallback for sign-in, served ONLY on 127.0.0.1 (stdlib only).

The default is the terminal sign-in (login_terminal.py). Some desktops block
loopback pages in the browser on purpose; this page is only for machines that
allow it: `python -m tg_recap login --web`.

Steps: API ID + API hash -> phone -> login code -> two-step password (if set).
Saved to disk (dir 0700, files 0600): api_id + api_hash (credentials.json) and
Telethon's session file. Never written to disk or logs: phone number, login
code, two-step password. They live only in this process's memory during
sign-in, and every reference is dropped as soon as sign-in finishes.
The HTTP server's request logging is disabled.
"""
from __future__ import annotations

import asyncio
import html
import logging
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import sys

from . import consent, paths
from .branding import PRODUCT_NAME
from .login_backend import PasswordNeeded, TelethonBackend, save_credentials  # noqa: F401

HOST = "127.0.0.1"  # never configurable
DEFAULT_PORT = 8765

PRIVACY = (
    f"<p><b>{html.escape(consent.DISCLOSURE)}</b></p>"
    f"<p>{html.escape(PRODUCT_NAME)} signs in <b>as you</b>, using Telethon (a standard Telegram client "
    "library) on your own machine. It reads your chats through your existing account session, the "
    "same way your Telegram app does. No bot is added to your groups, and nobody in them sees anything "
    "new. It only reads: it doesn't post, react, join, or leave.</p>"
    "<p>Your phone number, login code, and two-step password are used once to sign in and are never "
    "saved or logged. We never see them, and neither does anyone else's machine. Only three things are "
    "kept on your machine, readable only by you: your API ID, your API hash, and Telegram's session file. "
    "You can end that session any time in Telegram under <b>Settings &gt; Devices</b>.</p>"
)

STEPS = {
    "api": ("Step 1 of 4: your API ID and API hash",
            "<p>Get your own API ID and API hash at <a href='https://my.telegram.org' target='_blank' "
            "rel='noopener'>my.telegram.org</a> (API development tools). Telegram's official steps: "
            "<a href='https://core.telegram.org/api/obtaining_api_id' target='_blank' rel='noopener'>"
            "core.telegram.org/api/obtaining_api_id</a>.</p>",
            [("api_id", "API ID", "text"), ("api_hash", "API hash", "password")]),
    "phone": ("Step 2 of 4: your phone number",
              "<p>Use international format, for example +1 and your number. Telegram will send a code "
              "to your Telegram app.</p>", [("phone", "Phone number", "tel")]),
    "code": ("Step 3 of 4: login code",
             "<p>Enter the code Telegram just sent to your Telegram app.</p>",
             [("code", "Login code", "text")]),
    "password": ("Step 4 of 4: two-step password",
                 "<p>Your account has a two-step password. It is used once here and is not kept.</p>",
                 [("password", "Two-step password", "password")]),
}

log = logging.getLogger("tg_recap.login")


class LoginFlow:
    def __init__(self, backend):
        self.backend = backend
        self.step = "api"
        self.error = ""
        self.token = secrets.token_urlsafe(24)
        self._api = None  # (api_id, api_hash) kept in memory until sign-in succeeds
        self.done = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._lock = threading.Lock()

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=120)

    def submit(self, form: dict) -> None:
        with self._lock:
            self.error = ""
            try:
                if self.step == "api":
                    api_id = (form.get("api_id") or "").strip()
                    api_hash = (form.get("api_hash") or "").strip()
                    if not api_id.isdigit() or len(api_hash) < 16:
                        self.error = "That API ID or API hash doesn't look right. Copy both from my.telegram.org."
                        return
                    self._run(self.backend.start(int(api_id), api_hash))
                    self._api = (int(api_id), api_hash)
                    self.step = "phone"
                elif self.step == "phone":
                    self._run(self.backend.send_code((form.get("phone") or "").strip()))
                    self.step = "code"
                elif self.step == "code":
                    try:
                        self._run(self.backend.sign_in_code((form.get("code") or "").strip()))
                        self._success()
                    except PasswordNeeded:
                        self.step = "password"
                elif self.step == "password":
                    self._run(self.backend.sign_in_password(form.get("password") or ""))
                    self._success()
            except Exception as exc:  # noqa: BLE001 - show type only, never values
                self.error = (f"Telegram didn't accept that ({type(exc).__name__}). "
                              "Check it and try again, or restart with `python -m tg_recap login --web`.")
            finally:
                form.clear()  # drop phone / code / password references

    def _success(self):
        self._run(self.backend.finish())
        api_id, api_hash = self._api
        save_credentials(api_id, api_hash)
        self._api = None
        self.step = "done"
        self.done.set()

    def close(self):
        if self.step != "done":
            try:
                self._run(self.backend.abort())
            except Exception:  # noqa: BLE001
                pass
        self._api = None
        self._loop.call_soon_threadsafe(self._loop.stop)


def page(flow: LoginFlow) -> str:
    if flow.step == "done":
        body = ("<h2>Signed in</h2><p>Your session is saved on your machine, readable only by you. "
                "You can close this tab and go back to your Grok Bot chat.</p>"
                "<p>To end the session later: Telegram <b>Settings &gt; Devices</b>.</p>")
    else:
        title, intro, fields = STEPS[flow.step]
        inputs = "".join(
            f"<label>{html.escape(label)}<br><input name='{name}' type='{typ}' autocomplete='off' "
            f"required></label><br>" for name, label, typ in fields)
        err = f"<p class='err'>{html.escape(flow.error)}</p>" if flow.error else ""
        body = (f"<h2>{html.escape(title)}</h2>{intro}{err}<form method='post' action='/'>"
                f"<input type='hidden' name='token' value='{flow.token}'>{inputs}"
                f"<button type='submit'>Continue</button></form>")
    return ("<!doctype html><html><head><meta charset='utf-8'><title>"
            f"{html.escape(PRODUCT_NAME)}: sign in"
            "</title><meta name='referrer' content='no-referrer'><style>body{font-family:system-ui;"
            "max-width:640px;margin:2em auto;padding:0 1em;line-height:1.5}input{width:100%;"
            "padding:.5em;margin:.3em 0 1em}.err{color:#b00}.box{background:#f4f4f4;padding:.5em 1em;"
            "border-radius:8px}</style></head><body><h1>"
            f"{html.escape(PRODUCT_NAME)}</h1>"
            f"<div class='box'>{PRIVACY}</div>{body}<p><small>Self-serve setup. This page runs only "
            "on this computer (127.0.0.1). Type your details here, never in a chat.</small></p>"
            "</body></html>")


def make_handler(flow: LoginFlow, port_ref: list):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # never log requests
            return

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            return host in {f"127.0.0.1:{port_ref[0]}", f"localhost:{port_ref[0]}"}

        def _send(self, code: int, text: str):
            data = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, "forbidden")
            self._send(200, page(flow))

        def do_POST(self):
            if not self._host_ok():
                return self._send(403, "forbidden")
            length = min(int(self.headers.get("Content-Length") or 0), 8192)
            raw = self.rfile.read(length).decode("utf-8", "replace")
            form = {k: v[0] for k, v in parse_qs(raw).items()}
            raw = None
            if form.get("token") != flow.token:
                form.clear()
                return self._send(403, "forbidden")
            flow.submit(form)
            self._send(200, page(flow))
            if flow.step == "done":
                threading.Thread(target=self.server.shutdown, daemon=True).start()
    return Handler


def make_server(backend=None, port: int = DEFAULT_PORT):
    os.umask(0o077)
    paths.ensure_dir()
    flow = LoginFlow(backend or TelethonBackend())
    port_ref = [port]
    server = ThreadingHTTPServer((HOST, port), make_handler(flow, port_ref))
    port_ref[0] = server.server_address[1]
    return server, flow


def serve(port: int = DEFAULT_PORT, backend=None) -> int:
    refused = consent.require(sys.stderr)
    if refused is not None:
        return refused  # 9: accept the API-terms warning first
    server, flow = make_server(backend, port)
    url = f"http://{HOST}:{server.server_address[1]}/"
    print(f"Open this page on this computer to sign in: {url}", flush=True)
    print("Type your details on that page only, never in a chat. Ctrl+C stops it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        flow.close()
    if flow.step == "done":
        print("Signed in. Session saved under ~/.tg_recap (owner-only).", flush=True)
        return 0
    print("Login not finished. Run `python -m tg_recap login` again when ready.", flush=True)
    return 1
~~~~~

### file: tg_recap/memecoin.py
sha256: 8034073e53c5c78378a4453561c5a621ce8db1614e338c425952c622a6bfd41b
~~~~~
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
~~~~~

### file: tg_recap/paths.py
sha256: a9bf34af4855687d8d706b09dcf7a5e97fb1f7df75e31c7b8b61a5cabfd7c8de
~~~~~
"""Owner-only storage under ~/.tg_recap (override with TG_RECAP_HOME).

Directories are created 0700 and files are written 0600. Nothing here ever
stores a phone number, login code or two-step password.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DIR_MODE = 0o700
FILE_MODE = 0o600


def home() -> Path:
    return Path(os.environ.get("TG_RECAP_HOME", str(Path.home() / ".tg_recap")))


def ensure_dir(path: Path | None = None) -> Path:
    path = Path(path) if path else home()
    path.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    os.chmod(path, DIR_MODE)
    return path


def credentials_file() -> Path:
    return home() / "credentials.json"  # api_id + api_hash only


def session_base() -> Path:
    return home() / "tg_recap"  # Telethon appends ".session"


def session_file() -> Path:
    return home() / "tg_recap.session"


def pending_dir() -> Path:
    return home() / "pending"  # in-progress card sign-in (login --cards)


def pending_session_base() -> Path:
    return pending_dir() / "login"  # Telethon appends ".session"


def pending_state_file() -> Path:
    return pending_dir() / "state.json"  # phone_code_hash + stage; never the phone


def settings_file() -> Path:
    return home() / "settings.json"  # user settings (config.SCHEMA)


def config_file() -> Path:
    return home() / "config.json"  # legacy (v0.1.0-v0.1.4); read once if settings.json is missing


def state_file() -> Path:
    return home() / "state.json"


def lock_file() -> Path:
    return home() / "session.lock"


def raw_dir() -> Path:
    return home() / "cache" / "raw"


def recaps_dir() -> Path:
    return home() / "cache" / "recaps"


def write_private(path: Path, data: str) -> None:
    """Atomically write text with 0600 perms inside a 0700 dir."""
    path = Path(path)
    ensure_dir(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
    finally:
        if tmp.exists():
            os.chmod(tmp, FILE_MODE)
    os.replace(tmp, path)
    os.chmod(path, FILE_MODE)


def write_json(path: Path, obj) -> None:
    write_private(path, json.dumps(obj, indent=2, sort_keys=True))


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def tighten(path: Path) -> None:
    """Force 0600 on an existing file (e.g. Telethon's session file)."""
    if Path(path).exists():
        os.chmod(path, FILE_MODE)
~~~~~

### file: tg_recap/readonly.py
sha256: fc0c9cc3a086cc4d8cceb1e8826fef45c7a70c40ef9a3f711f1b4db20c683184
~~~~~
"""Read-only wrapper around a Telethon client.

Only the methods in ALLOWED_METHODS can be used, and only the raw TL requests
in ALLOWED_RAW_REQUESTS can be sent with ``client(request)``. Everything else
(send, edit, delete, join, leave, react, mark-read / send_read_acknowledge /
ReadHistoryRequest, ...) raises ReadOnlyViolation before reaching Telegram.
Nothing here marks a chat as read, so chats stay unread in your own apps.

Rate limiting: at most one call every ``min_interval`` seconds.
FLOOD_WAIT: the first one is slept once (if it is not longer than
``max_flood_sleep``); a second one, or an over-long one, stops the run with
FloodStop.
"""
from __future__ import annotations

import asyncio
import time

ALLOWED_METHODS = frozenset({
    "connect",
    "disconnect",
    "is_user_authorized",
    "get_me",
    "get_entity",
    "iter_dialogs",
    "get_dialogs",
    "iter_messages",
    "get_messages",
})

# Raw requests (client(request)) that are allowed, by TL class name. All read-only.
ALLOWED_RAW_REQUESTS = frozenset({
    "GetFullUserRequest",
    "GetFullChatRequest",
    "GetFullChannelRequest",
})

# Never allowed, listed explicitly so the intent is obvious and tested.
DENIED_ALWAYS = frozenset({
    "send_message", "send_file", "forward_messages", "edit_message",
    "delete_messages", "delete_dialog", "send_read_acknowledge", "pin_message",
    "unpin_message", "edit_permissions", "kick_participant", "edit_admin",
    "__call__", "sign_in", "sign_up", "send_code_request", "log_out",
})

_ITER_METHODS = frozenset({"iter_dialogs", "iter_messages"})


class ReadOnlyViolation(PermissionError):
    """A non-allowlisted Telegram call was attempted."""


class FloodStop(RuntimeError):
    """Telegram asked us to slow down twice (or for too long); the run stops."""


def _flood_seconds(exc: BaseException) -> int | None:
    try:
        from telethon.errors import FloodWaitError  # type: ignore
        if isinstance(exc, FloodWaitError):
            return int(exc.seconds)
    except ImportError:  # pragma: no cover - telethon always installed in practice
        pass
    if type(exc).__name__ == "FloodWaitError" and hasattr(exc, "seconds"):
        return int(exc.seconds)
    return None


class ReadOnlyClient:
    def __init__(self, client, *, min_interval: float = 0.5, max_flood_sleep: int = 600,
                 sleep=asyncio.sleep, clock=time.monotonic):
        object.__setattr__(self, "_client", client)
        object.__setattr__(self, "_min_interval", min_interval)
        object.__setattr__(self, "_max_flood_sleep", max_flood_sleep)
        object.__setattr__(self, "_sleep", sleep)
        object.__setattr__(self, "_clock", clock)
        object.__setattr__(self, "_last_call", None)
        object.__setattr__(self, "_flood_waited", False)

    # --- guards -----------------------------------------------------------
    def __setattr__(self, name, value):
        raise ReadOnlyViolation("ReadOnlyClient attributes are fixed")

    def __getattr__(self, name):
        if name in DENIED_ALWAYS or name not in ALLOWED_METHODS:
            raise ReadOnlyViolation(f"Telegram method '{name}' is not on the read-only allowlist")
        target = getattr(self._client, name)
        if name in _ITER_METHODS:
            return self._wrap_iter(name, target)
        return self._wrap_call(name, target)

    async def __call__(self, request, *args, **kwargs):
        rname = type(request).__name__
        if rname not in ALLOWED_RAW_REQUESTS:
            raise ReadOnlyViolation(f"Raw request '{rname}' is not on the read-only allowlist")
        return await self._guarded(lambda: self._client(request, *args, **kwargs))

    # --- rate limit + flood handling --------------------------------------
    async def _throttle(self):
        now = self._clock()
        last = self._last_call
        if last is not None:
            wait = self._min_interval - (now - last)
            if wait > 0:
                await self._sleep(wait)
        object.__setattr__(self, "_last_call", self._clock())

    async def _handle_flood(self, seconds: int):
        if self._flood_waited:
            raise FloodStop(
                f"Telegram asked to wait again ({seconds}s) after one wait already. "
                "This run stopped to protect your account; the next scheduled run will try again.")
        if seconds > self._max_flood_sleep:
            raise FloodStop(
                f"Telegram asked to wait {seconds}s, longer than the {self._max_flood_sleep}s limit. "
                "This run stopped; the next scheduled run will try again.")
        object.__setattr__(self, "_flood_waited", True)
        await self._sleep(seconds)

    async def _guarded(self, make_call):
        while True:
            await self._throttle()
            try:
                result = make_call()
                if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                    result = await result
                return result
            except Exception as exc:  # noqa: BLE001
                secs = _flood_seconds(exc)
                if secs is None:
                    raise
                await self._handle_flood(secs)

    def _wrap_call(self, name, target):
        async def call(*args, **kwargs):
            return await self._guarded(lambda: target(*args, **kwargs))
        call.__name__ = name
        return call

    def _wrap_iter(self, name, target):
        """Buffer the whole iteration so a FLOOD_WAIT retry restarts cleanly."""
        ro = self

        async def collect_all(args, kwargs):
            async def run():
                return [item async for item in target(*args, **kwargs)]
            return await ro._guarded(run)

        def iterator(*args, **kwargs):
            async def gen():
                for item in await collect_all(args, kwargs):
                    yield item
            return gen()
        iterator.__name__ = name
        return iterator
~~~~~

### file: tg_recap/redact.py
sha256: eb6830510ed9cefb13228a142799c423daeee1474659563af7a8ba1ac2e62673
~~~~~
"""Strip identifiers and secrets from text before it leaves the collector.

Removed: wallet-looking strings (EVM 0x..., Solana/base58, Bitcoin), long hex
blobs, t.me / telegram.me links (incl. invite links), x.com/twitter status
links, URL query/fragment strings, phone numbers, numeric Telegram IDs,
login/verification codes, passwords, and seed/recovery phrases. Public token
CAs may be left in place when the caller passes them in keep_addresses
(Memecoin mentions only).
"""
from __future__ import annotations

import re

_X_STATUS = re.compile(r"(?:https?://)?(?:www\.)?(?:x|twitter)\.com/[^\s/]+/status/\S+", re.I)
_URL = re.compile(r"https?://[^\s<>]+", re.I)
_QUERY_AFTER_REDACT = re.compile(r"\[(?:id|address|link) removed\][?#]\S+")
_SECRETS = [
    (re.compile(
        r"\b(?:seed\s*phrase|recovery\s*phrase|secret\s*phrase|mnemonic(?:\s*phrase)?)"
        r"\s*[:=]?\s*(?:\S+\s+){11,23}\S+",
        re.I,
    ), "[seed phrase removed]"),
    (re.compile(r"\b(?:password|passwd|passphrase)\s*[:=]\s*\S+", re.I), "[password removed]"),
    (re.compile(
        r"(?:(?:login|verification|authentication|auth|one[-\s]*time)\s+)(?:codes?|otp)"
        r"\s*[:=]?\s*\d{4,8}"
        r"|\b(?:login|verification|authentication|auth)\s+codes?\b(?:\s+\w+){0,3}\s*[:=]?\s*\d{4,8}"
        r"|\b(?:codes?|otp)\s*[:=]\s*\d{4,8}"
        r"|\b\d{5,6}\b(?=(?:\s+\w+){0,4}\s*(?:login\s+)?(?:codes?|otp|verification))"
        r"|(?:(?:login\s+)?(?:codes?|otp|verification))(?:\s+\w+){0,3}\s*[:=]?\s*\d{5,6}\b",
        re.I,
    ), "[code removed]"),
]
_PATTERNS = [
    (re.compile(r"(?:https?://)?(?:www\.)?(?:t|telegram)\.(?:me|dog)/\S+", re.I), "[link removed]"),
    (re.compile(r"tg://\S+", re.I), "[link removed]"),
    (re.compile(r"\b0x[a-fA-F0-9]{40,64}\b"), "[address removed]"),
    (re.compile(r"\bbc1[a-z0-9]{25,60}\b", re.I), "[address removed]"),
    (re.compile(r"\b(?=[1-9A-HJ-NP-Za-km-z]*\d)(?=[1-9A-HJ-NP-Za-km-z]*[A-Za-z])[1-9A-HJ-NP-Za-km-z]{32,44}\b"), "[address removed]"),
    (re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b"), "[address removed]"),
    (re.compile(r"\b[a-fA-F0-9]{48,}\b"), "[address removed]"),
    (re.compile(r"\+\d[\d\s().-]{6,}\d"), "[phone removed]"),
    (re.compile(r"(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"), "[phone removed]"),
    (re.compile(r"(?<![\d.,])-?\d{7,}(?![\d.,]*\d)"), "[id removed]"),
]


def _strip_urls(text: str) -> str:
    text = _X_STATUS.sub("[link removed]", text)
    return _URL.sub(lambda m: re.split(r"[?#]", m.group(0), maxsplit=1)[0], text)


def _hold_addresses(text: str, addresses) -> tuple[str, list[tuple[str, str]]]:
    """Swap keep-list CAs for placeholders so later patterns can't chew them."""
    held: list[tuple[str, str]] = []
    out = text
    for addr in addresses or []:
        if not addr:
            continue
        variants = [addr]
        if addr.lower() != addr:
            variants.append(addr.lower())
        for v in dict.fromkeys(variants):
            if v and v in out:
                token = f"KEEPCA{len(held)}MARKER"
                out = out.replace(v, token)
                held.append((token, v))
    return out, held


def redact(text: str, keep_addresses: list[str] | set[str] | None = None) -> str:
    if not text:
        return ""
    out, held = _hold_addresses(text, keep_addresses)
    out = _strip_urls(out)
    for pattern, repl in _SECRETS + _PATTERNS:
        out = pattern.sub(repl, out)
    out = _QUERY_AFTER_REDACT.sub("[link removed]", out)
    for token, addr in held:
        out = out.replace(token, addr)
    return out


_ADDRESSY = re.compile(r"\b0x[a-fA-F0-9]{40}\b|\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")


def looks_like_address(text: str) -> bool:
    return bool(text and _ADDRESSY.search(text))
~~~~~

### file: tg_recap/render.py
sha256: deb0478c60ffa25f4f53752416a9b08239d0c1f2a78b8f064c2b6f64318f046a
~~~~~
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
~~~~~

### file: tg_recap/retention.py
sha256: bb9899449d32d7aa2416f8e527dfa31ad6c65583ac64f6cf1fe96c3c31376f53
~~~~~
"""Retention for this code's own cache (not Telegram, not your apps).

- Raw fetched data (the digest input JSON) is deleted as soon as the recap
  is rendered.
- Rendered recap text is kept for at most 72 hours (the spec proposes
  24-72 h; we use the upper bound), then deleted on the next run.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import paths

RECAP_TTL = timedelta(hours=72)


def _stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_raw(digest: dict, now: datetime) -> Path:
    path = paths.raw_dir() / f"{_stamp(now)}.json"
    paths.ensure_dir(paths.home() / "cache")
    paths.write_private(path, json.dumps(digest))
    return path


def delete_raw() -> int:
    n = 0
    d = paths.raw_dir()
    if d.exists():
        for f in d.iterdir():
            if f.is_file():
                f.unlink()
                n += 1
    return n


def save_recap(text: str, now: datetime) -> Path | None:
    if not text:
        return None
    paths.ensure_dir(paths.home() / "cache")
    path = paths.recaps_dir() / f"{_stamp(now)}.txt"
    paths.write_private(path, text)
    return path


def purge_recaps(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    d = paths.recaps_dir()
    n = 0
    if not d.exists():
        return 0
    for f in d.glob("*.txt"):
        try:
            made = datetime.strptime(f.stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if now - made > RECAP_TTL:
            f.unlink()
            n += 1
    return n
~~~~~

### file: tg_recap/runner.py
sha256: 34082be9e0b5de994f797d9c156a9ea3b18effe389604dcfca0803d2b3fdcbf4
~~~~~
"""One scheduled run: lock -> collect -> (JSON for the agent | fallback text) -> retention.

`run`     prints the deterministic fallback recap (or nothing).
`collect` prints one JSON object: the digest the agent writes the recap from,
          plus "fallback_text" and "nothing_to_report".
`--peek`  (either command) does the same full read-only pass but writes nothing
          under ~/.tg_recap: the window is not advanced, state.json is not written
          at all (no window, no chat-title directory, no new salt), and no recap
          copy is saved. Only the session lock is taken and released (Telethon
          itself may still update session.session). JSON output gains "peek": true.
          Use it for test or manual runs so the next scheduled run keeps its window.

Exit codes (stderr carries one short plain line, stdout stays empty):
  0  ok (stdout is the recap / JSON; recap text empty when nothing qualified)
  2  LOCK_HELD        another run is using the session
  3  SESSION_REVOKED  not signed in / session ended in Telegram Settings > Devices
  4  FLOOD_STOP       Telegram asked to slow down twice; run stopped
  5  NOT_SET_UP       no credentials yet; run setup first
  7  SETTINGS_INVALID ~/.tg_recap/settings.json didn't validate (field named)
  9  CONSENT_REQUIRED the API-terms 1.5 warning hasn't been accepted (`consent accept`)
  8  CONNECT_FAILED   couldn't reach Telegram's web endpoint (DNS, TLS, WebSocket
                      handshake or timeout); stderr names only the error type

Transport: Telegram's official web endpoints, wss://<dc>.web.telegram.org:443/apiws
(transport_wss.py). A saved session keeps its auth key and DC; if Telegram no
longer knows the key (AuthKeyNotFound / unregistered) or the session points at a
DC with no web endpoint, the run exits 3 and asks for a new sign-in; nothing
tries to repair the session.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone

from . import collect as collect_mod
from . import config, paths, retention
from .lock import LockHeld, SessionLock
from .readonly import FloodStop, ReadOnlyClient
from .render import render
from . import consent
from .branding import PRODUCT_NAME
from .memecoin import LAST_MEMECOIN_AT

EXIT_OK, EXIT_LOCK, EXIT_REVOKED, EXIT_FLOOD, EXIT_NOT_SET_UP, EXIT_SETTINGS = 0, 2, 3, 4, 5, 7
EXIT_CONNECT = 8
REVOKED_MSG = ("SESSION_REVOKED: Your Telegram session isn't active (it may have been ended in "
               "Settings > Devices). Run setup again to sign in.")
DC_MSG = ("SESSION_REVOKED: Your saved Telegram session points at a data center this version can't reach "
          "over Telegram's web endpoints. Run setup again to sign in.")
_REVOKED_ERRORS = {"AuthKeyUnregisteredError", "SessionRevokedError", "SessionExpiredError",
                   "UserDeactivatedError", "UserDeactivatedBanError", "AuthKeyDuplicatedError",
                   "AuthKeyNotFound", "AuthKeyInvalidError", "AuthKeyPermEmptyError"}


def _connect_msg(exc) -> str:
    from .transport_wss import last_connect_error
    kind = getattr(exc, "kind", None) or last_connect_error() or type(exc).__name__
    return (f"CONNECT_FAILED: Couldn't reach Telegram's web endpoint ({kind}). Nothing was read; "
            "the next scheduled run will try again.")


class NotAuthorized(RuntimeError):
    pass


def telethon_client():
    creds = paths.read_json(paths.credentials_file())
    if not creds or not paths.session_file().exists():
        return None
    from .login_backend import no_entity_cache
    from .transport_wss import WebTelegramClient, quiet_telethon_logs
    quiet_telethon_logs()
    return no_entity_cache(WebTelegramClient(str(paths.session_base()), int(creds["api_id"]), creds["api_hash"],
                                             receive_updates=False, flood_sleep_threshold=0))


async def _collect(raw_client, cfg, state, now, *, window_hours=None, state_key="last_recap_at",
                  default_hours=None):
    client = ReadOnlyClient(raw_client)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise NotAuthorized()
        return await collect_mod.collect(client, cfg, state, now, window_hours=window_hours,
                                         state_key=state_key, default_hours=default_hours)
    finally:
        await client.disconnect()
        paths.tighten(paths.session_file())


def run(client_factory=telethon_client, now: datetime | None = None, out=sys.stdout, err=sys.stderr,
        as_json: bool = False, peek: bool = False, memecoin_only: bool = False,
        window_hours: int | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    try:
        cfg = config.load()
    except config.SettingsError as exc:
        print(f"SETTINGS_INVALID: {exc}. Fix it with `settings set ...` or `settings show`.", file=err)
        return EXIT_SETTINGS
    refused = consent.require(err)
    if refused is not None:
        return refused  # 9: nothing is read until the owner accepts the terms warning
    try:
        lock = SessionLock().acquire()
    except LockHeld as exc:
        print(f"LOCK_HELD: {exc}", file=err)
        return EXIT_LOCK
    try:
        try:
            raw_client = client_factory()
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ == "UnknownDc":
                print(DC_MSG, file=err)
                return EXIT_REVOKED
            raise
        if raw_client is None:
            print(f"NOT_SET_UP: {PRODUCT_NAME} isn't signed in yet. Run setup first.", file=err)
            return EXIT_NOT_SET_UP
        state = collect_mod.load_state()
        state_key = LAST_MEMECOIN_AT if memecoin_only else "last_recap_at"
        default_hours = 1 if memecoin_only else None
        try:
            digest = asyncio.run(_collect(raw_client, cfg, state, now, window_hours=window_hours,
                                          state_key=state_key, default_hours=default_hours))
        except FloodStop as exc:
            print(f"FLOOD_STOP: {exc}", file=err)
            return EXIT_FLOOD
        except NotAuthorized:
            print(REVOKED_MSG, file=err)
            return EXIT_REVOKED
        except Exception as exc:  # noqa: BLE001
            if type(exc).__name__ in _REVOKED_ERRORS:
                print(REVOKED_MSG, file=err)
                return EXIT_REVOKED
            if type(exc).__name__ == "UnknownDc":
                print(DC_MSG, file=err)
                return EXIT_REVOKED
            if isinstance(exc, (ConnectionError, TimeoutError)):
                print(_connect_msg(exc), file=err)
                return EXIT_CONNECT
            raise
        text = render(digest, memecoin_only=memecoin_only)
        if not peek:
            if not memecoin_only:
                retention.write_raw(digest, now)
                retention.save_recap(text, now)
                retention.delete_raw()
                retention.purge_recaps(now)
                state["last_recap_at"] = digest["window"]["end"]
            else:
                state[LAST_MEMECOIN_AT] = digest["window"]["end"]
            collect_mod.save_state(state)
        if as_json:
            extra = {"peek": True} if peek else {}
            if memecoin_only:
                extra["memecoin_only"] = True
            out.write(json.dumps({**digest, "fallback_text": text, "nothing_to_report": not text, **extra},
                                 ensure_ascii=False, indent=1) + "\n")
        elif text:
            out.write(text)
        return EXIT_OK
    finally:
        if not peek:
            retention.delete_raw()
        lock.release()
~~~~~

### file: tg_recap/sample.py
sha256: 7942c96bab16e07361f1b288d0c5701c45a4cfdce93e92f29daba8f4faa431d2
~~~~~
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
~~~~~

### file: tg_recap/settings_cli.py
sha256: 21bff4df19113c4f06d1dab7b392630de756a389bffca606513f7a96b54509e3
~~~~~
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
               "include-dms": "include_dms", "collapse-alert-bots": "collapse_alert_bots",
               "memecoin-show-ca": "memecoin_show_ca",
               "only-included-chats": "only_included_chats"}
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
        f"Memecoin contract addresses: {_onoff(cfg.memecoin_show_ca)}",
        f"Only included chats: {_onoff(cfg.only_included_chats)}",
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
            on = _onoff(getattr(cfg, BOOL_FIELDS[name]))
            if name == "memecoin-show-ca":
                msg = f"Memecoin contract addresses: {on}."
            elif name == "only-included-chats":
                msg = f"Only included chats: {on}" + \
                    (" (every chat without an include or count-only rule is left out)." if on == "on" else ".")
            else:
                msg = f"{name.replace('-', ' ').capitalize()}: {on}."
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
~~~~~

### file: tg_recap/transport_wss.py
sha256: 1b57249d6a63146c1ab96697fbef53ac7204cf5412668a083365b09bfa412d97
~~~~~
"""Connect to Telegram over its official web endpoints: WebSocket over TLS.

Telegram Web (and GramJS with useWSS) reach Telegram at
wss://<name>.web.telegram.org:443/apiws with WebSocket subprotocol "binary",
carrying obfuscated MTProto ("obfuscated2" with the abridged codec). That goes
over normal HTTPS egress, so it works where raw TCP to the data-center IPs
doesn't.

What this module does:
  - ConnectionWss: a Telethon Connection that reuses Telethon's own
    ConnectionTcpObfuscated framing (ObfuscatedIO + AbridgedPacketCodec) and only
    swaps the byte stream: a WebSocket instead of a TCP socket.
  - WebTelegramClient: a TelegramClient whose data centers resolve by DC id to
    the hardcoded web hostnames below. IP addresses from help.getConfig or a
    migrate error are never used (it never even calls help.getConfig). A fresh
    session starts on venus (DC2); a session saved by an older version keeps its
    DC id and auth key, and only its stored address is rewritten to the web host.
  - No proxy of any kind. The WebSocket library's environment-proxy detection is
    switched off explicitly.

Telethon internals relied on (1.45.0, pinned): Connection._connect / _reader /
_writer / _ip / _dc_id, ObfuscatedConnection, ObfuscatedIO, AbridgedPacketCodec,
TelegramClient._get_dc and session.set_dc. tests/test_transport_wss.py checks
each of them offline.
"""
from __future__ import annotations

import asyncio
import logging

from telethon import TelegramClient
from telethon.network.connection.tcpobfuscated import ConnectionTcpObfuscated

WEB_HOSTS = {
    1: "pluto.web.telegram.org",
    2: "venus.web.telegram.org",
    3: "aurora.web.telegram.org",
    4: "vesta.web.telegram.org",
    5: "flora.web.telegram.org",
}
DEFAULT_DC = 2
PORT = 443
PATH = "/apiws"
SUBPROTOCOL = "binary"
CONNECT_TIMEOUT = 15        # seconds per attempt (DNS + TLS + WebSocket handshake)
CONNECT_RETRIES = 1         # Telethon retries this many times: 2 attempts per connect, total
RETRY_DELAY = 2
MAX_MESSAGE = 16 * 1024 * 1024

_last_error: list[str] = []


class UnknownDc(ConnectionError):
    """A DC id with no web endpoint. Never falls back to an IP."""


class WssConnectError(ConnectionError):
    """DNS, TLS, WebSocket handshake or timeout. Carries only the error type name."""

    def __init__(self, kind: str):
        super().__init__(kind)
        self.kind = kind


def web_host(dc_id) -> str:
    try:
        return WEB_HOSTS[int(dc_id)]
    except (KeyError, TypeError, ValueError):
        raise UnknownDc("no Telegram web endpoint for this data center") from None


def url_for(dc_id) -> str:
    return f"wss://{web_host(dc_id)}:{PORT}{PATH}"


def last_connect_error() -> str | None:
    return _last_error[-1] if _last_error else None


async def _open_websocket(url: str, timeout: float):
    from websockets.asyncio.client import connect
    return await connect(url, subprotocols=[SUBPROTOCOL], proxy=None, compression=None,
                         open_timeout=timeout, ping_interval=None, max_size=MAX_MESSAGE,
                         user_agent_header=None)


class _WsReader:
    """StreamReader-like: readexactly(n) over WebSocket binary messages."""

    def __init__(self, ws):
        self._ws = ws
        self._buf = bytearray()

    async def readexactly(self, n: int) -> bytes:
        while len(self._buf) < n:
            try:
                msg = await self._ws.recv()
            except Exception as exc:  # noqa: BLE001 - closed / reset: Telethon expects IOError
                partial = bytes(self._buf)
                self._buf.clear()
                raise asyncio.IncompleteReadError(partial, n) from exc
            self._buf += msg if isinstance(msg, (bytes, bytearray)) else msg.encode()
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


class _WsWriter:
    """StreamWriter-like: write() buffers, drain() sends one binary message."""

    def __init__(self, ws):
        self._ws = ws
        self._buf = bytearray()

    def write(self, data: bytes) -> None:
        self._buf += data

    async def drain(self) -> None:
        if not self._buf:
            return
        data = bytes(self._buf)
        self._buf.clear()
        try:
            await self._ws.send(data)
        except Exception as exc:  # noqa: BLE001
            raise ConnectionResetError(type(exc).__name__) from None

    def close(self) -> None:
        pass  # the WebSocket closes in wait_closed()

    async def wait_closed(self) -> None:
        try:
            await self._ws.close()
        except Exception:  # noqa: BLE001 - closing never raises
            pass


class ConnectionWss(ConnectionTcpObfuscated):
    """Obfuscated MTProto (abridged) over wss://<dc web host>:443/apiws."""

    open_websocket = staticmethod(_open_websocket)  # tests swap in a fake

    async def _connect(self, timeout=None, ssl=None):
        url = url_for(self._dc_id)  # by DC id only; self._ip is never dialed
        try:
            ws = await asyncio.wait_for(self.open_websocket(url, timeout or CONNECT_TIMEOUT),
                                        timeout=(timeout or CONNECT_TIMEOUT) + 5)
        except Exception as exc:  # noqa: BLE001 - name only, never the message
            _last_error.append(type(exc).__name__)
            del _last_error[:-5]
            raise WssConnectError(type(exc).__name__) from None
        self._reader = _WsReader(ws)
        self._writer = _WsWriter(ws)
        self._codec = self.packet_codec(self)
        self._init_conn()
        await self._writer.drain()

    def __str__(self):
        try:
            return f"{web_host(self._dc_id)}:{PORT}/Wss"
        except UnknownDc:
            return "unknown-dc/Wss"


class _WebDc:
    def __init__(self, dc_id: int):
        self.id = int(dc_id)
        self.ip_address = web_host(dc_id)
        self.port = PORT


class WebTelegramClient(TelegramClient):
    """TelegramClient that only ever talks to Telegram's web endpoints."""

    def __init__(self, session, api_id, api_hash, **kwargs):
        for banned in ("proxy", "connection", "use_ipv6", "local_addr"):
            if kwargs.pop(banned, None) not in (None, False):
                raise ValueError(f"{banned} is not configurable for the web transport")
        kwargs.setdefault("connection_retries", CONNECT_RETRIES)
        kwargs.setdefault("retry_delay", RETRY_DELAY)
        kwargs.setdefault("timeout", CONNECT_TIMEOUT)
        kwargs.setdefault("request_retries", 2)
        kwargs.setdefault("auto_reconnect", False)
        super().__init__(session, api_id, api_hash, connection=ConnectionWss, use_ipv6=False, **kwargs)
        point_session_at_web(self.session)

    async def _get_dc(self, dc_id, cdn=False):
        """Resolve a DC by id to its web host. Never calls help.getConfig and never
        uses an IP (the getDC(web=true) behaviour of Telegram Web / GramJS)."""
        if cdn:
            raise UnknownDc("CDN data centers aren't used by this read-only recap")
        return _WebDc(dc_id)


def point_session_at_web(session) -> None:
    """Store the web host for the session's DC (DC2 for a new session).
    Telethon's SQLite set_dc keeps the auth key; only the address changes."""
    dc_id = session.dc_id or DEFAULT_DC
    host = web_host(dc_id)
    if session.server_address != host or session.port != PORT or session.dc_id != dc_id:
        session.set_dc(dc_id, host, PORT)
        session.save()


def quiet_telethon_logs() -> None:
    """Telethon logs reconnect warnings with addresses and tracebacks; keep stderr to our one line."""
    logging.getLogger("telethon").setLevel(logging.CRITICAL)
~~~~~
