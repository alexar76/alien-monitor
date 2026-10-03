"""Peer health probing follows the peer shape learned from well-known."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from hub_discovery import _health_url  # noqa: E402


def test_aimarket_hub_uses_the_protocol_health_endpoint():
    assert _health_url(
        "https://independentai.network/hub/", is_hub=True,
    ) == "https://independentai.network/hub/ai-market/v2/health"


def test_capability_service_keeps_the_service_health_endpoint():
    assert _health_url(
        "https://memory.attestedmemory.net/", is_hub=False,
    ) == "https://memory.attestedmemory.net/api/health"
