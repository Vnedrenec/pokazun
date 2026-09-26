#!/usr/bin/env python3
"""Boundary gate: domain logic must not import aiogram directly.

Scans ``src/pokazun/search/**/*.py`` and ``src/pokazun/catalog/**/*.py``
from the repository root (derived from this file location, so the result
does not depend on the current working directory).

Forbidden: direct ``import aiogram`` / ``import aiogram.<...>`` and
``from aiogram... import ...`` in any nesting level. Relative imports
(``from .aiogram import ...``, ``level > 0``) address a local module of
this repository, not the third-party aiogram package, and are clean.
Strings and comments are not imports (AST based). An unparsable file
is a failure.

Empty-state contract (bootstrap):
- both domain dirs missing -> ``0 domain files``, exit 0;
- a domain dir exists but contains no ``.py`` -> failure (red);
- a missing dir before the task that creates it is not an error.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_DIRS = (REPO_ROOT / "src" / "pokazun" / "search", REPO_ROOT / "src" / "pokazun" / "catalog")


def _is_aiogram_import(node: ast.AST) -> str | None:
    """Return a description of the violation, or None if clean."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "aiogram" or alias.name.startswith("aiogram."):
                return f"forbidden direct import '{alias.name}'"
    elif isinstance(node, ast.ImportFrom):
        if node.level:
            # Relative import (``from .aiogram import Bot``): a local module
            # of this repository, not the third-party aiogram package.
            return None
        module = node.module or ""
        if module == "aiogram" or module.startswith("aiogram."):
            return f"forbidden direct import from '{module}'"
    return None


def violations_in_source(source: str) -> list[tuple[int, str]]:
    """Parse source and return [(lineno, detail)] for forbidden imports.

    Raises SyntaxError on unparsable source.
    """
    tree = ast.parse(source)
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        detail = _is_aiogram_import(node)
        if detail is not None:
            found.append((node.lineno, detail))
    return found


def check_file(path: Path, root: Path = REPO_ROOT) -> list[str]:
    """Check one file. Return list of formatted error strings (empty = clean)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"FAIL: {path.relative_to(root)}: cannot read: {exc}"]
    try:
        violations = violations_in_source(text)
    except SyntaxError as exc:
        loc = f"{exc.lineno}" if exc.lineno is not None else "?"
        return [f"FAIL: {path.relative_to(root)}:{loc}: syntax error: {exc.msg}"]
    rel = path.relative_to(root)
    return [f"FAIL: {rel}:{lineno}: {detail}" for lineno, detail in violations]


def collect_domain_files(root: Path = REPO_ROOT) -> tuple[list[Path], list[str]]:
    """Return (py_files, errors) where errors covers the empty-dir red case."""
    files: list[Path] = []
    errors: list[str] = []
    existing_dirs = 0
    for d in (root / "src" / "pokazun" / "search", root / "src" / "pokazun" / "catalog"):
        if d.is_dir():
            existing_dirs += 1
            found = sorted(d.rglob("*.py"))
            if not found:
                errors.append(
                    f"FAIL: {d.relative_to(root)} exists but contains no .py files"
                )
            files.extend(found)
    return sorted(files), errors


def run_scan(root: Path = REPO_ROOT) -> int:
    files, dir_errors = collect_domain_files(root)
    if not files and not dir_errors:
        # Both domain dirs missing (bootstrap before Task 1 of stage 4).
        print("0 domain files")
        return 0
    errors: list[str] = list(dir_errors)
    for path in files:
        errors.extend(check_file(path, root))
    if errors:
        for line in errors:
            print(line)
        print(f"FAIL: {len(errors)} violation(s) in {len(files)} domain file(s)")
        return 1
    print(f"OK: no forbidden aiogram imports in {len(files)} domain file(s)")
    return 0


def run_self_test() -> int:
    failures: list[str] = []

    def check(name: str, source: str, expect_violation: bool) -> None:
        try:
            violations = violations_in_source(source)
        except SyntaxError as exc:
            failures.append(f"{name}: unexpected SyntaxError: {exc}")
            print(f"self-test FAIL: {name}: unexpected SyntaxError")
            return
        got = bool(violations)
        if got == expect_violation:
            print(f"self-test PASS: {name}")
        else:
            failures.append(f"{name}: expected violation={expect_violation}, got={violations}")
            print(f"self-test FAIL: {name}: expected violation={expect_violation}, got={violations}")

    # Allowed import is green.
    check("allowed import math", "import math\n", False)
    # Import text inside a string is not an import.
    check("string with import text", 'x = "import aiogram"\n', False)
    # Import text inside a comment is not an import.
    check("comment with import text", "# import aiogram\nx = 1\n", False)
    # Both forbidden syntaxes are red.
    check("forbidden import aiogram", "import aiogram\n", True)
    check("forbidden import aiogram submodule", "import aiogram.types\n", True)
    check("forbidden from-import", "from aiogram import Bot\n", True)
    check("forbidden from-import submodule", "from aiogram.types import Message\n", True)
    # Nested blocks are still detected.
    check("nested import in function", "def f():\n    import aiogram\n", True)
    check("nested from-import in branch", "if True:\n    from aiogram import Bot\n", True)

    # Syntax error is red (must raise, not silently pass).
    try:
        violations_in_source("def broken(:\n")
        failures.append("syntax error: expected SyntaxError, parsed clean")
        print("self-test FAIL: syntax error: expected SyntaxError, parsed clean")
    except SyntaxError:
        print("self-test PASS: syntax error is red")

    # Empty-state contract on a temp root: both dirs missing -> 0 files, no errors.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        files, errs = collect_domain_files(tmp_root)
        if files == [] and errs == []:
            print("self-test PASS: both dirs missing -> 0 domain files")
        else:
            failures.append(f"empty-state missing-dirs: files={files} errs={errs}")
            print("self-test FAIL: both dirs missing -> 0 domain files")

    # Existing dir without .py -> red.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        (tmp_root / "src" / "pokazun" / "search").mkdir(parents=True)
        files, errs = collect_domain_files(tmp_root)
        if files == [] and len(errs) == 1:
            print("self-test PASS: existing dir without .py is red")
        else:
            failures.append(f"empty-state empty-dir: files={files} errs={errs}")
            print("self-test FAIL: existing dir without .py is red")

    # Forbidden file in temp search dir is reported with path and line.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        probe = tmp_root / "src" / "pokazun" / "search" / "probe.py"
        probe.parent.mkdir(parents=True)
        probe.write_text("import aiogram\n", encoding="utf-8")
        errs = check_file(probe, tmp_root)
        if len(errs) == 1 and "probe.py:1" in errs[0]:
            print("self-test PASS: probe reports path and line")
        else:
            failures.append(f"probe report: errs={errs}")
            print(f"self-test FAIL: probe reports path and line: {errs}")

    # run_scan propagates the empty-dir collection error to the final exit.
    # Guards M12 (``errors = []`` instead of ``errors = list(dir_errors)``).
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        (tmp_root / "src" / "pokazun" / "search").mkdir(parents=True)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = run_scan(tmp_root)
        if rc == 1 and "contains no .py files" in buf.getvalue():
            print("self-test PASS: scan propagates empty-dir error")
        else:
            failures.append(f"scan empty-dir propagation: rc={rc} out={buf.getvalue()!r}")
            print("self-test FAIL: scan propagates empty-dir error")

    # run_scan propagates a SyntaxError to the final exit.
    # Guards M13 (``check_file`` returning ``[]`` on SyntaxError).
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        bad = tmp_root / "src" / "pokazun" / "search" / "bad.py"
        bad.parent.mkdir(parents=True)
        bad.write_text("def broken(:\n", encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = run_scan(tmp_root)
        if rc == 1 and "syntax error" in buf.getvalue():
            print("self-test PASS: scan propagates syntax error")
        else:
            failures.append(f"scan syntax-error propagation: rc={rc} out={buf.getvalue()!r}")
            print("self-test FAIL: scan propagates syntax error")

    if failures:
        print(f"self-test FAIL: {len(failures)} case(s) failed")
        return 1
    print("self-test OK: all cases passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Boundary gate for aiogram imports in domain.")
    parser.add_argument("--self-test", action="store_true", help="run internal self-test")
    args = parser.parse_args(argv)
    if args.self_test:
        return run_self_test()
    return run_scan()


if __name__ == "__main__":
    sys.exit(main())
