"""The monitor's mirrored WARDEN ruleset version must match the package.

`warden_status.RULESET_VERSION` exists because the monitor is Python and the firewall is TypeScript,
so the version shown on the node is a hand copy. That copy went stale within hours of being written:
the package shipped ruleset v4 and the node kept saying v3, which is worse than showing nothing —
a scan version is exactly the kind of fact a viewer would quote.

The monorepo holds both sides, so the drift is checkable here even though the package ships
separately.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

PACKAGE_SOURCE = ROOT.parent / "warden" / "src" / "static-scan.ts"


def test_the_mirrored_version_matches_the_package():
    if not PACKAGE_SOURCE.is_file():  # pragma: no cover - satellite checkouts lack the package
        pytest.skip("warden/src/static-scan.ts is not in this checkout")
    source = PACKAGE_SOURCE.read_text(encoding="utf-8")
    m = re.search(r'STATIC_SCAN_RULESET_VERSION = "([^"]+)"', source)
    assert m, "could not read STATIC_SCAN_RULESET_VERSION from the package"

    from warden_status import RULESET_VERSION

    assert RULESET_VERSION == m.group(1), (
        f"the monitor shows ruleset v{RULESET_VERSION} on the WARDEN node while the package ships "
        f"v{m.group(1)} — update warden_status.RULESET_VERSION"
    )
