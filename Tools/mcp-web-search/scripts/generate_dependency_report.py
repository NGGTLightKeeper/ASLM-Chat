#!/usr/bin/env python3
# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

"""Generate a dependency report for Python files in the repository.

The report is intended as a helper when preparing ``pyproject.toml``.
It walks Python files, parses imports via AST, and writes a text log with
per-file sections plus an aggregate list of third-party package roots.

Example
-------
python scripts/generate_dependency_report.py
python scripts/generate_dependency_report.py --root . --out tmp/dependency_report.txt
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_EXCLUDES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "archive",
    "logs",
    "tmp",
    "_cache",
}


@dataclass(frozen=True)
class ModuleImports:
    path: Path
    stdlib: tuple[str, ...]
    third_party: tuple[str, ...]
    first_party: tuple[str, ...]
    relative: tuple[str, ...]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="scripts/generate_dependency_report.py")
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan. Default: current directory.",
    )
    parser.add_argument(
        "--out",
        default="tmp/dependency_report.txt",
        help="Output text file. Default: tmp/dependency_report.txt",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        help="Include tests/ in the report. By default tests are skipped.",
    )
    return parser.parse_args()


def _iter_python_files(root: Path, *, include_tests: bool) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        rel_parts = path.relative_to(root).parts
        if any(part in DEFAULT_EXCLUDES for part in rel_parts):
            continue
        if not include_tests and rel_parts and rel_parts[0] == "tests":
            continue
        files.append(path)
    return sorted(files)


def _top_level_roots(root: Path) -> set[str]:
    roots: set[str] = set()
    for child in root.iterdir():
        if child.name in DEFAULT_EXCLUDES:
            continue
        if child.is_dir():
            roots.add(child.name)
        elif child.suffix == ".py":
            roots.add(child.stem)
    return roots


def _safe_parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except UnicodeDecodeError:
        return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    except SyntaxError:
        return None


def _collect_imports(tree: ast.AST, *, first_party_roots: set[str]) -> tuple[set[str], set[str], set[str], set[str]]:
    stdlib: set[str] = set()
    third_party: set[str] = set()
    first_party: set[str] = set()
    relative: set[str] = set()

    stdlib_names = set(sys.stdlib_module_names)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.strip()
                if not name:
                    continue
                root = name.split(".", 1)[0]
                if root in first_party_roots:
                    first_party.add(name)
                elif root in stdlib_names:
                    stdlib.add(name)
                else:
                    third_party.add(name)
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").strip()
            if node.level and module:
                relative.add("." * node.level + module)
                continue
            if node.level and not module:
                relative.add("." * node.level)
                continue
            if not module:
                continue
            root = module.split(".", 1)[0]
            if root in first_party_roots:
                first_party.add(module)
            elif root in stdlib_names:
                stdlib.add(module)
            else:
                third_party.add(module)

    return stdlib, third_party, first_party, relative


def _scan_file(path: Path, *, root: Path, first_party_roots: set[str]) -> ModuleImports:
    tree = _safe_parse(path)
    if tree is None:
        return ModuleImports(
            path=path.relative_to(root),
            stdlib=(),
            third_party=(),
            first_party=(),
            relative=("<<syntax-error-or-unparseable>>",),
        )
    stdlib, third_party, first_party, relative = _collect_imports(tree, first_party_roots=first_party_roots)
    return ModuleImports(
        path=path.relative_to(root),
        stdlib=tuple(sorted(stdlib)),
        third_party=tuple(sorted(third_party)),
        first_party=tuple(sorted(first_party)),
        relative=tuple(sorted(relative)),
    )


def _header_label(path: Path) -> str:
    stem = path.stem.replace("-", "_").replace(".", "_")
    return stem.upper()


def _render_section(title: str, values: tuple[str, ...]) -> list[str]:
    lines = [f"{title}:"]
    if not values:
        lines.append("  -")
        return lines
    for value in values:
        lines.append(f"  - {value}")
    return lines


def _build_report(root: Path, modules: list[ModuleImports]) -> str:
    lines: list[str] = []
    external_roots: set[str] = set()
    package_usage: dict[str, list[str]] = defaultdict(list)

    for module in modules:
        for dep in module.third_party:
            dep_root = dep.split(".", 1)[0]
            external_roots.add(dep_root)
            package_usage[dep_root].append(module.path.as_posix())

    for module in modules:
        title = _header_label(module.path)
        lines.append("=" * 35)
        lines.append(title)
        lines.append("=" * 35)
        lines.append(f"file: {module.path.as_posix()}")
        lines.extend(_render_section("stdlib", module.stdlib))
        lines.extend(_render_section("third_party", module.third_party))
        lines.extend(_render_section("first_party", module.first_party))
        lines.extend(_render_section("relative", module.relative))
        lines.append("")

    lines.append("=" * 35)
    lines.append("THIRD_PARTY_PACKAGE_ROOTS")
    lines.append("=" * 35)
    if not external_roots:
        lines.append("-")
    else:
        for name in sorted(external_roots):
            users = ", ".join(sorted(package_usage[name]))
            lines.append(f"{name}: {users}")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path

    files = _iter_python_files(root, include_tests=bool(args.include_tests))
    first_party_roots = _top_level_roots(root)
    modules = [_scan_file(path, root=root, first_party_roots=first_party_roots) for path in files]
    report = _build_report(root, modules)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    print(f"Saved: {out_path}")
    print(f"Scanned files: {len(modules)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
