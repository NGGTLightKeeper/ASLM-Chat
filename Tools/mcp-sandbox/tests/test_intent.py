"""Tests for intent classification and compound pipeline normalization."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["SANDBOX_HOST_WORKSPACE"] = str(ROOT)

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


def test_find_carries_name_and_type():
    """find -name '*.py' -type f → NormalizedCommand with name_pattern/find_type."""
    nc = classify('find . -name "*.py" -type f -maxdepth 2')
    assert nc is not None, "find with supported flags should classify"
    assert nc.intent == Intent.SURVEY
    assert nc.name_pattern == "*.py", f"name_pattern={nc.name_pattern!r}"
    assert nc.find_type == "file", f"find_type={nc.find_type!r}"
    assert nc.depth == 2, f"depth={nc.depth!r}"


def test_grep_context_carried():
    """grep -C 2 pattern file → context_before/after = 2."""
    nc = classify("grep -C 2 pattern file.py")
    assert nc is not None
    assert nc.intent == Intent.LOCATE
    assert nc.context_before == 2 and nc.context_after == 2, (
        f"context=({nc.context_before},{nc.context_after})"
    )

    nc = classify("grep -A 3 -B 1 pattern file.py")
    assert nc is not None
    assert nc.context_before == 1 and nc.context_after == 3


def test_ls_la_includes_hidden():
    """ls -la and combined short flags must enable include_hidden."""
    for cmd in ("ls -la", "ls -al", "ls -lah .", "ls -A"):
        nc = classify(cmd)
        assert nc is not None, cmd
        assert nc.intent == Intent.SURVEY
        assert nc.include_hidden is True, f"include_hidden False for: {cmd}"


def test_du_falls_through_to_bash():
    """du is NOT routed as a directory listing — must reach real bash."""
    nc = classify("du -sh .")
    # Either None (no routing) or RUN intent — must not be SURVEY.
    if nc is not None:
        assert nc.intent == Intent.RUN, f"du routed as {nc.intent}"


def test_find_unsupported_flags_fall_back():
    """find with -exec / -mtime / etc. must fall back to real bash."""
    for cmd in (
        "find . -name '*.log' -exec rm {} ;",
        "find . -mtime -7",
        "find . -iname '*.PY'",
        "find . -type l",
    ):
        nc = classify(cmd)
        if nc is not None:
            assert nc.intent == Intent.RUN, f"{cmd!r} routed as {nc.intent}"


def test_grep_files_with_matches():
    """grep -l changes output format to filenames — not implemented, fall back to bash."""
    nc = classify("grep -l pattern src/")
    # -l/-L are not handled by the router, so classifier returns None → real bash
    if nc is not None:
        assert nc.intent == Intent.RUN


def test_grep_inverted_falls_back():
    """grep -v changes semantics — fall back to real bash."""
    nc = classify("grep -v pattern file.py")
    if nc is not None:
        assert nc.intent == Intent.RUN


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
        test_find_carries_name_and_type,
        test_grep_context_carried,
        test_ls_la_includes_hidden,
        test_du_falls_through_to_bash,
        test_find_unsupported_flags_fall_back,
        test_grep_files_with_matches,
        test_grep_inverted_falls_back,
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
