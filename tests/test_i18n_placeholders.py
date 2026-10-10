"""Every placeholder in the monitor's locales uses the syntax the i18n layer interpolates.

frontend/src/i18n/context.tsx replaces {{name}} only. A string written with {name} reaches the
screen verbatim — the Hestia card showed "{running} running · {ours} ours · {third} third-party"
in all five languages until 2026-10-04.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

LOCALES = Path(__file__).resolve().parent.parent / "frontend" / "src" / "i18n" / "locales"
SINGLE = re.compile(r"(?<!\{)\{[A-Za-z_]+\}(?!\})")


def _strings(node, path=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}.{key}" if path else key)
    elif isinstance(node, str):
        yield path, node


def test_no_single_brace_placeholders():
    offenders = []
    for locale in sorted(LOCALES.glob("*.json")):
        for path, text in _strings(json.loads(locale.read_text(encoding="utf-8"))):
            if SINGLE.search(text):
                offenders.append(f"{locale.stem}:{path}")
    assert offenders == [], offenders


def test_the_interpolation_syntax_is_still_double_braces():
    context = (LOCALES.parent / "context.tsx").read_text(encoding="utf-8")
    assert "\\{\\{(\\w+)\\}\\}" in context
