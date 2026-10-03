"""Signal Hunt sidebar reads Hub federation stats (capabilities / peers / trust)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from competing_lab_layers import (  # noqa: E402
    apply_competing_lab_sim_metrics,
    enrich_competing_lab_nodes,
    signal_hunt_hub_node_spec,
    signal_hunt_node_spec,
)


def test_sim_metrics_fill_signal_hunt_card_fields():
    nodes = [signal_hunt_hub_node_spec(), signal_hunt_node_spec()]
    apply_competing_lab_sim_metrics(nodes, tick=10)
    game = next(n for n in nodes if n["id"] == "signal_hunt")
    hub = next(n for n in nodes if n["id"] == "signal_hunt_hub")
    assert game["metrics"]["capabilities"] == hub["metrics"]["capabilities"]
    assert game["metrics"]["peers"] == hub["metrics"]["peers"]
    assert game["metrics"]["trust_score"] == hub["metrics"]["trust_score"]
    assert game["metrics"]["capabilities"] not in (None, "")
    assert game["metrics"]["peers"] not in (None, "")


class _Resp:
    def __init__(self, status: int, payload: dict):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, routes: dict[str, _Resp]):
        self.routes = routes

    async def get(self, url: str, follow_redirects: bool = False):  # noqa: ARG002
        for needle, resp in self.routes.items():
            if needle in url:
                return resp
        return _Resp(404, {})

    async def aclose(self):
        return None


def test_live_enrich_copies_hub_stats_onto_game_ball():
    nodes = [signal_hunt_hub_node_spec(), signal_hunt_node_spec()]
    client = _FakeClient(
        {
            "/ai-market/v2/federation/peers": _Resp(
                200,
                {
                    "peers": [
                        {
                            "name": "Signal Hunt Hub",
                            "url": "https://hunt.modelmarket.dev",
                            "trust_score": 0.2685,
                            "capabilities_count": 5,
                        }
                    ]
                },
            ),
            "/ai-market/v2/stats/live": _Resp(
                200,
                {
                    "summary": {
                        "peers_count": 4,
                        "offerable_capabilities_count": 75,
                        "real_local_capabilities_count": 5,
                    }
                },
            ),
            "https://hunt.modelmarket.dev": _Resp(200, {}),
        }
    )

    asyncio.run(
        enrich_competing_lab_nodes(
            nodes,
            primary_hub_url="https://modelmarket.dev",
            client=client,
        )
    )
    game = next(n for n in nodes if n["id"] == "signal_hunt")
    hub = next(n for n in nodes if n["id"] == "signal_hunt_hub")
    assert hub["metrics"]["capabilities"] == 75
    assert hub["metrics"]["peers"] == 4
    assert hub["metrics"]["trust_score"] == 0.2685
    assert game["metrics"]["capabilities"] == 75
    assert game["metrics"]["peers"] == 4
    assert game["metrics"]["trust_score"] == 0.2685
    assert game["metrics"]["local_capabilities"] == 5
