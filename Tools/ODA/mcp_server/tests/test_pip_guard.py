"""Unit tests for pip-guard argument parsing."""
from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

GUARD_PATH = Path(__file__).resolve().parents[2] / "sandbox" / "pip-guard"


@pytest.fixture(scope="module")
def pip_guard():
    if not GUARD_PATH.is_file():
        pytest.skip(f"pip-guard not found: {GUARD_PATH}")
    loader = SourceFileLoader("pip_guard", str(GUARD_PATH))
    spec = importlib.util.spec_from_loader("pip_guard", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_normalize_name_rejects_flags(pip_guard):
    assert pip_guard.normalize_name("-q") == ""
    assert pip_guard.normalize_name("pandas") == "pandas"
    assert pip_guard.normalize_name("pandas==2.2.3") == "pandas"


def test_collect_install_args_keeps_flags(pip_guard):
    args = pip_guard.collect_install_args(["pip", "install", "-q", "pandas"])
    assert "-q" in args
    assert "pandas" in args


def test_package_names_exclude_flags(pip_guard):
    install_args = pip_guard.collect_install_args(["pip", "install", "-q", "tabulate"])
    names = [
        pip_guard.normalize_name(a)
        for a in install_args
        if not a.startswith("-") and pip_guard.normalize_name(a)
    ]
    assert names == ["tabulate"]
