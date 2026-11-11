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
