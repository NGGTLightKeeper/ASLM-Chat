"""Tests for intent classification and compound pipeline normalization."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path("src")))
os.environ["SANDBOX_HOST_WORKSPACE"] = str(Path(".").resolve().parent.parent)

from sandbox.intent import Intent, classify, NormalizedCommand


def test_open_variants():
    """All read-like commands classify as OPEN."""
    cases = [
        "cat file.py",
        "head -n 30 file.py",
        "tail -n 20 file.py",
        "less file.py",
        "more file.py",
        "sed -n '1,30p' file.py",
    ]
    for cmd in cases:
        nc = classify(cmd)
        assert nc is not None, f"Got None for: {cmd}"
        assert nc.intent == Intent.OPEN, f"Expected OPEN for: {cmd}, got {nc.intent}"
    print(f"PASS: {len(cases)} OPEN variants all classified correctly")


def test_open_line_ranges():
    """head/tail/sed extract line ranges."""
    nc = classify("head -n 30 file.py")
    assert nc.start_line == 1
    assert nc.end_line == 30, f"end_line={nc.end_line}"

    nc = classify("sed -n '10,50p' file.py")
    assert nc.start_line == 10, f"start_line={nc.start_line}"
    assert nc.end_line == 50, f"end_line={nc.end_line}"

    print("PASS: line ranges from head/sed extracted correctly")


def test_locate_variants():
    """All search commands classify as LOCATE."""
    cases = [
        ("grep -r pattern .", "pattern"),
        ("grep -ri Pattern src/", "Pattern"),
        ("rg pattern src/", "pattern"),
        ("egrep pattern file.py", "pattern"),
    ]
    for cmd, expected_pattern in cases:
        nc = classify(cmd)
        assert nc is not None, f"Got None for: {cmd}"
        assert nc.intent == Intent.LOCATE, f"Expected LOCATE for: {cmd}, got {nc.intent}"
        assert nc.pattern == expected_pattern, f"Expected pattern={expected_pattern!r}, got {nc.pattern!r} for: {cmd}"
    print(f"PASS: {len(cases)} LOCATE variants all classified correctly")


def test_survey_variants():
    """ls/tree/find classify as SURVEY."""
    cases = ["ls .", "ls -la src/", "tree -L 2", "find . -name '*.py'"]
    for cmd in cases:
        nc = classify(cmd)
        assert nc is not None, f"Got None for: {cmd}"
        assert nc.intent == Intent.SURVEY, f"Expected SURVEY for: {cmd}, got {nc.intent}"
    print(f"PASS: {len(cases)} SURVEY variants classified correctly")


def test_compound_cat_head():
    """cat file | head -n 20 → OPEN with line range."""
    nc = classify("cat file.py | head -n 20")
    assert nc is not None, "Got None for compound cat|head"
    assert nc.intent == Intent.OPEN, f"Expected OPEN, got {nc.intent}"
    assert nc.was_compound is True
    assert nc.end_line == 20, f"Expected end_line=20, got {nc.end_line}"
    assert nc.target == "file.py", f"Expected target=file.py, got {nc.target}"
    print(f"PASS: cat file | head -n 20 → OPEN [1:20] (was_compound={nc.was_compound})")


def test_compound_cat_grep():
    """cat file | grep pattern → LOCATE."""
    nc = classify("cat file.py | grep pattern")
    assert nc is not None, "Got None for compound cat|grep"
    assert nc.intent == Intent.LOCATE, f"Expected LOCATE, got {nc.intent}"
    assert nc.was_compound is True
    assert nc.pattern == "pattern", f"Expected pattern='pattern', got {nc.pattern!r}"
    assert nc.target == "file.py", f"Expected target=file.py, got {nc.target}"
    print(f"PASS: cat file | grep pattern → LOCATE (was_compound={nc.was_compound})")


def test_compound_head_grep():
    """head -n 50 file | grep pattern → LOCATE."""
    nc = classify("head -n 50 file.py | grep pattern")
    assert nc is not None
    assert nc.intent == Intent.LOCATE, f"Expected LOCATE, got {nc.intent}"
    assert nc.was_compound is True
    print(f"PASS: head -n 50 file | grep pattern → LOCATE")


def test_run_commands_return_none():
    """Execution commands return None (→ real bash)."""
    run_cases = [
        "python script.py",
        "pytest tests/",
        "npm install",
        "git status",
        "curl https://example.com",
        "make build",
        "pip install requests",
    ]
    for cmd in run_cases:
        nc = classify(cmd)
        # These should either return None or Intent.RUN
        if nc is not None:
            assert nc.intent == Intent.RUN, f"Expected RUN for: {cmd}, got {nc.intent}"
    print(f"PASS: {len(run_cases)} RUN commands handled correctly")


def test_chains_return_none():
    """&&, ||, ;, subshells, redirections → None (real bash)."""
    chain_cases = [
        "echo hello && cat file.py",
        "cat file.py || echo failed",
        "cat file.py; cat other.py",
        "cat $(find . -name main.py)",
        "cat file.py > output.txt",
        "cat file.py >> output.txt",
    ]
    for cmd in chain_cases:
        nc = classify(cmd)
        # These must not be routed as OPEN/LOCATE/SURVEY
        if nc is not None:
            assert nc.intent not in (Intent.OPEN, Intent.LOCATE, Intent.SURVEY), (
                f"Should not route {cmd!r} as {nc.intent}"
            )
    print(f"PASS: {len(chain_cases)} compound chains correctly passed to real bash")


def test_locate_case_sensitivity():
    """grep -i → case_sensitive=False."""
    nc = classify("grep -ri pattern src/")
    assert nc is not None
    assert nc.intent == Intent.LOCATE
    assert nc.case_sensitive is False, f"Expected case_sensitive=False"
    print(f"PASS: grep -ri → case_sensitive=False")


def test_locate_rg_type_flag():
    """rg --type py → glob_pattern=*.py."""
    nc = classify("rg pattern --type py src/")
    assert nc is not None
    assert nc.intent == Intent.LOCATE
    assert nc.glob_pattern == "*.py", f"Expected glob=*.py, got {nc.glob_pattern}"
    print(f"PASS: rg --type py → glob_pattern=*.py")


if __name__ == "__main__":
    tests = [
        test_open_variants,
        test_open_line_ranges,
        test_locate_variants,
        test_survey_variants,
        test_compound_cat_head,
        test_compound_cat_grep,
        test_compound_head_grep,
        test_run_commands_return_none,
        test_chains_return_none,
        test_locate_case_sensitivity,
        test_locate_rg_type_flag,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            import traceback
            print(f"FAIL: {t.__name__}: {e}")
            traceback.print_exc()
            failed += 1
        print()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
