"""The generated code skills (telegram-recap-code + telegram-recap-code-tests) must match the repo."""
from __future__ import annotations

import importlib.util
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "telegram-recap-code" / "SKILL.md"
TESTS_SKILL = ROOT / "skills" / "telegram-recap-code-tests" / "SKILL.md"
BUILDER = ROOT / "tools" / "build_code_skill.py"
EXTRACTOR = ROOT / "tools" / "extract_code_skill.py"

SKIP_NO_SKILL = (
    "skills/telegram-recap-code/SKILL.md is absent "
    "(extracted copy without the skills tree)"
)


def _require_skill() -> None:
    if not SKILL.is_file() or not BUILDER.is_file():
        pytest.skip(SKIP_NO_SKILL)


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_code_skills_are_up_to_date_and_under_budget():
    _require_skill()
    builder = _load(BUILDER, "build_code_skill")
    for skill, path in ((builder.CODE, SKILL), (builder.TESTS, TESTS_SKILL)):
        generated = builder.render_skill(ROOT, skill)
        if generated != path.read_text(encoding="utf-8"):
            pytest.fail(f"{path.relative_to(ROOT)} is out of date. Regenerate: python3 tools/build_code_skill.py")
        assert len(generated.encode()) <= builder.SIZE_LIMIT
    code = set(builder.listed_files(ROOT, builder.CODE))
    tests = set(builder.listed_files(ROOT, builder.TESTS))
    assert not code & tests and all(t.startswith("tests/") for t in tests)
    assert code | tests == set(builder.listed_files(ROOT))


def test_extractor_restores_repo_files_from_both_skills(tmp_path):
    _require_skill()
    ex = _load(EXTRACTOR, "extract_code_skill")
    dest = tmp_path / "out"
    ex.main([str(SKILL), str(TESTS_SKILL), str(dest)])
    builder = _load(BUILDER, "build_code_skill")
    for rel in builder.listed_files(ROOT):
        assert (dest / rel).read_bytes() == (ROOT / rel).read_bytes(), rel
    assert (dest / "install.sh").stat().st_mode & stat.S_IXUSR


def test_extractor_refuses_a_tampered_tests_skill(tmp_path):
    _require_skill()
    ex = _load(EXTRACTOR, "extract_code_skill")
    bad = tmp_path / "SKILL.md"
    bad.write_text(TESTS_SKILL.read_text(encoding="utf-8").replace("def test_", "def tset_", 1), encoding="utf-8")
    with pytest.raises(SystemExit):
        ex.main([str(SKILL), str(bad), str(tmp_path / "out")])
    assert not (tmp_path / "out").exists()
