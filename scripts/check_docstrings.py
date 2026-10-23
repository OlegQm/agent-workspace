"""Check that every project Python module and definition has a docstring."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterable
from pathlib import Path

EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "data",
    "node_modules",
    "venv",
}
DOCUMENTED_NODES = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def python_files(root: Path) -> Iterable[Path]:
    """Yield Python source files that belong to the project."""
    for path in sorted(root.rglob("*.py")):
        if not any(part in EXCLUDED_PARTS for part in path.parts):
            yield path


def missing_docstrings(path: Path) -> list[str]:
    """Return descriptions of missing docstrings in one Python file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    missing: list[str] = []
    if ast.get_docstring(tree, clean=False) is None:
        missing.append("module")

    for node in ast.walk(tree):
        if isinstance(node, DOCUMENTED_NODES) and ast.get_docstring(node, clean=False) is None:
            kind = type(node).__name__.removesuffix("Def").lower()
            missing.append(f"{kind} {node.name} (line {node.lineno})")
    return missing


def main(argv: list[str] | None = None) -> int:
    """Report missing docstrings and return a shell-compatible status code."""
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0] if args else ".").resolve()
    failures: list[tuple[Path, str]] = []

    for path in python_files(root):
        try:
            failures.extend((path, item) for item in missing_docstrings(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            failures.append((path, f"could not parse file: {exc}"))

    for path, description in failures:
        print(f"{path.relative_to(root)}: {description}")

    if failures:
        print(f"Docstring check failed with {len(failures)} issue(s).")
        return 1

    print("Docstring check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
