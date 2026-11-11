#!/usr/bin/env python3
"""Generate the code skills from the repo source.

Usage (from the repo root):

    python3 tools/build_code_skill.py

Since v0.1.5 the source is split in two skills, each under the 176 KiB budget:
  skills/telegram-recap-code/SKILL.md        tg_recap/, requirements*.txt,
                                             pyproject.toml, install.sh, README.md,
                                             plus the stdlib extractor
  skills/telegram-recap-code-tests/SKILL.md  tests/ (same sha256 checks; uses
                                             the extractor from telegram-recap-code)
Does not embed skills/, tools/, docs/, .venv, or .git. If a rendered skill would
exceed the budget, prints a proposal and exits non-zero without writing.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT_FILES = frozenset(
    {
        "README.md",
        "install.sh",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
    }
)
DIR_PREFIXES = ("tg_recap/", "tests/")
SIZE_LIMIT = 192 * 1024
TOOLS = Path(__file__).resolve().parent
EXTRACTOR_PATH = TOOLS / "extract_code_skill.py"
SKILL_REL = Path("skills") / "telegram-recap-code" / "SKILL.md"
TESTS_SKILL_REL = Path("skills") / "telegram-recap-code-tests" / "SKILL.md"
CODE, TESTS = "telegram-recap-code", "telegram-recap-code-tests"
SKILL_PATHS = {CODE: SKILL_REL, TESTS: TESTS_SKILL_REL}

FRONTMATTER = """\
---
name: telegram-recap-code
description: 'Source code for {{PRODUCT_NAME}} - use from telegram-recap-setup to write the code to disk before installing.'
---
"""

HOW_TO = """\
# {{PRODUCT_NAME}} source code

{{PRODUCT_NAME}} is an unofficial app that works alongside Telegram. It uses the Telegram API and is not affiliated with or endorsed by Telegram.

This skill holds the {{PRODUCT_NAME}} source so a bot that only has the skills (no git checkout) can write the code to disk and install it.

## How to extract

Live skill files live at `/home/box/agent-data/workflows/<id>/SKILL.md`. Read this skill and run its extractor into `telegram-recap-agent/` (or another empty target directory).

1. Save the extractor script below as a `.py` file (Python stdlib only; no extra packages).
2. Run: `python3 extract_code_skill.py <path-to-this-SKILL.md> <target-dir>`
   To include the tests too, pass both skills (the tests live in the sibling `telegram-recap-code-tests` skill): `python3 extract_code_skill.py <this SKILL.md> <telegram-recap-code-tests SKILL.md> <target-dir>`
3. The extractor writes every file listed below, sets `install.sh` executable, and verifies each sha256. On a mismatch it prints the path and the expected vs actual hash, writes nothing, and exits non-zero.
4. Then run `./install.sh` from the target directory (see `telegram-recap-setup`).

### Extractor

"""


def repo_root(start: Path | None = None) -> Path:
    if start is not None:
        return start.resolve()
    return TOOLS.parent


TESTS_FRONTMATTER = """\
---
name: telegram-recap-code-tests
description: 'Test suite for {{PRODUCT_NAME}} - extract after telegram-recap-code, with the same extractor and sha256 checks.'
---
"""

TESTS_HOW_TO = """\
# {{PRODUCT_NAME}} tests

The offline test suite (`tests/`) for the source in `telegram-recap-code`. Extract both skills into the same directory with the extractor embedded in `telegram-recap-code`:

    python3 extract_code_skill.py <telegram-recap-code SKILL.md> <this SKILL.md> <target-dir>

Every file below carries its sha256; a mismatch stops the extract before anything is written. The tests need nothing beyond `requirements-dev.txt` and never touch the network.
"""


def include(rel: str, skill: str | None = None) -> bool:
    is_test = rel.startswith("tests/")
    if skill == TESTS:
        return is_test
    if skill == CODE and is_test:
        return False
    if rel in ROOT_FILES:
        return True
    return any(rel.startswith(prefix) for prefix in DIR_PREFIXES)


def _is_embeddable(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix == ".pyc" or path.name.startswith("."):
        return False
    return "__pycache__" not in path.parts and ".pytest_cache" not in path.parts


def listed_files(root: Path, skill: str | None = None) -> list[str]:
    """Working-tree files that belong in the skill (tracked or not).

    Uses git ls-files when a repo is present, then adds any matching files
    on disk so a newly added test is embedded before the first commit.
    """
    found: set[str] = set()
    git_dir = root / ".git"
    if git_dir.exists():
        raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
        for item in raw.split(b"\0"):
            if not item:
                continue
            rel = item.decode("utf-8")
            if include(rel, skill) and _is_embeddable(root / rel):
                found.add(rel)
    for name in ROOT_FILES:
        if skill != TESTS and _is_embeddable(root / name):
            found.add(name)
    for prefix in DIR_PREFIXES:
        directory = root / prefix.rstrip("/")
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not _is_embeddable(path):
                continue
            rel = path.relative_to(root).as_posix()
            if include(rel, skill):
                found.add(rel)
    if not found:
        raise SystemExit("No source files matched the code-skill include list.")
    return sorted(found)


def read_utf8(path: Path) -> str:
    data = path.read_bytes()
    if b"\0" in data:
        raise SystemExit(f"{path} looks binary; the code skill only embeds UTF-8 text.")
    if not data.endswith(b"\n"):
        raise SystemExit(f"{path} is missing a trailing newline; refuse to embed it.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"{path} is not UTF-8: {exc}") from exc


def choose_fence(chunks: list[str]) -> str:
    n = 5
    while n <= 20:
        fence = "~" * n
        if all(fence not in chunk for chunk in chunks):
            return fence
        n += 1
    raise SystemExit("Could not find a tilde fence that is absent from every file.")


def sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def product_name(root: Path) -> str:
    """PRODUCT_NAME from <root>/tg_recap/branding.py (parsed, not imported)."""
    import re
    text = read_utf8(root / "tg_recap" / "branding.py")
    m = re.search(r'^PRODUCT_NAME = "([^"\\]+)"$', text, re.M)
    if not m:
        raise SystemExit("PRODUCT_NAME not found in tg_recap/branding.py")
    return m.group(1)


def _brand(text: str, name: str) -> str:
    return text.replace("{{PRODUCT_NAME}}", name)


def render_skill(root: Path, skill: str = CODE) -> str:
    root = root.resolve()
    name = product_name(root)
    if not EXTRACTOR_PATH.is_file():
        raise SystemExit(f"Extractor not found: {EXTRACTOR_PATH}")
    extractor = read_utf8(EXTRACTOR_PATH)
    files = [(rel, read_utf8(root / rel)) for rel in listed_files(root, skill)]
    fence = choose_fence([extractor, *(content for _rel, content in files)])
    if skill == TESTS:
        parts = [_brand(TESTS_FRONTMATTER, name), _brand(TESTS_HOW_TO, name), "\n## Files\n"]
    else:
        parts = [_brand(FRONTMATTER, name), _brand(HOW_TO, name), fence, " python\n", extractor]
        if not extractor.endswith("\n"):
            parts.append("\n")
        parts.extend([fence, "\n\n## Files\n"])
    for rel, content in files:
        digest = sha256_text(content)
        parts.append(f"\n### file: {rel}\nsha256: {digest}\n{fence}\n{content}")
        if not content.endswith("\n"):
            parts.append("\n")
        parts.append(f"{fence}\n")
    return "".join(parts)


def write_skill(root: Path) -> list[Path]:
    rendered = {}
    for skill, rel in SKILL_PATHS.items():
        text = render_skill(root, skill)
        size = len(text.encode("utf-8"))
        if size > SIZE_LIMIT:
            print(
                f"Rendered {skill} is {size} bytes ({len(listed_files(root, skill))} files), over the "
                f"{SIZE_LIMIT} byte budget. Not writing anything.\n"
                "Proposal (do not apply silently): split this skill further by directory "
                "(for example tg_recap/login_* into a third skill) rather than raising the budget.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        rendered[skill] = (rel, text, size)
    written = []
    for skill, (rel, text, size) in rendered.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"Wrote {dest} ({size} bytes, {len(listed_files(root, skill))} embedded files)")
        written.append(dest)
    return written


def main() -> None:
    write_skill(repo_root())


if __name__ == "__main__":
    main()
