#!/usr/bin/env python3
"""The endpoint map of docs/book/src/reference/endpoints.md.

Built from the ``METHOD /path`` that each public method's docstring names.

    python3 scripts/endpoint-map.py           # print the table
    python3 scripts/endpoint-map.py --write   # replace the table in the page
    python3 scripts/endpoint-map.py --check   # fail if the page is stale (CI)
"""

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src/zeroclaw_client"
PAGE = ROOT / "docs/book/src/reference/endpoints.md"
HEADER = "| Method | Path | Module | Function |"
ROUTE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS) (/[^\s)?,;`]*)")


def table() -> str:
    rows = set()
    for file in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            for fn in cls.body:
                if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if fn.name.startswith("_"):
                    continue
                doc = " ".join((ast.get_docstring(fn) or "").split())
                for method, path in ROUTE.findall(doc):
                    rows.add((path.rstrip("."), method, file.name, f"{cls.name}.{fn.name}"))
    lines = [HEADER, "|---|---|---|---|"]
    lines += [f"| `{m}` | `{p}` | `{f}` | `{fn}` |" for p, m, f, fn in sorted(rows)]
    return "\n".join(lines) + "\n"


def page_with(new_table: str) -> str:
    text = PAGE.read_text(encoding="utf-8")
    return text[: text.index(HEADER)] + new_table


if __name__ == "__main__":
    generated = table()
    if "--write" in sys.argv:
        PAGE.write_text(page_with(generated), encoding="utf-8")
    elif "--check" in sys.argv:
        if PAGE.read_text(encoding="utf-8") != page_with(generated):
            sys.exit("docs/book/src/reference/endpoints.md is stale: run endpoint-map.py --write")
    else:
        sys.stdout.write(generated)
