#!/usr/bin/env python3
"""Rename the product in the hand-written docs and skill copies.

The name lives in tg_recap/branding.py (PRODUCT_NAME). To rename:
  1. edit PRODUCT_NAME in tg_recap/branding.py
  2. python3 tools/apply_branding.py --from "<old name>"
  3. python3 tools/build_code_skill.py
Code, CLI help and the recap header read the constant directly; the generated
code skills render {{PRODUCT_NAME}} from it. tests/test_branding.py fails if any
user-facing text still carries another name. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {"skills/telegram-recap-code/SKILL.md", "skills/telegram-recap-code-tests/SKILL.md"}


def product_name(root: Path = ROOT) -> str:
    text = (root / "tg_recap" / "branding.py").read_text(encoding="utf-8")
    return re.search(r'^PRODUCT_NAME = "([^"\\]+)"$', text, re.M).group(1)


def doc_files(root: Path = ROOT) -> list[Path]:
    """User-facing markdown written by hand (README, docs/, skill copies)."""
    files = [root / "README.md", *sorted((root / "docs").glob("*.md")), *sorted((root / "skills").glob("*/SKILL.md"))]
    return [f for f in files if f.is_file() and f.relative_to(root).as_posix() not in GENERATED]


def main(argv=None, root: Path = ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="old", required=True, help="the previous product name")
    args = ap.parse_args(argv)
    new = product_name(root)
    changed = 0
    for f in doc_files(root):
        text = f.read_text(encoding="utf-8")
        out = text.replace(args.old, new)
        if out != text:
            f.write_text(out, encoding="utf-8")
            changed += 1
            print(f"updated {f.relative_to(root)}")
    print(f"{changed} file(s) now say {new!r}. Next: python3 tools/build_code_skill.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
