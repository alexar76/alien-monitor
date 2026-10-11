"""A map too big to send whole.

Measured on this codebase before the split: 5 005 nodes took 35 s to load, 15 005 ran at
the software renderer's floor, and 50 005 killed the browser process — not by drawing them
(the far field is one draw call) but by building fifty thousand objects for things the
camera cannot resolve. A hundred thousand hubs needs the payload to stop being the graph.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def node(nid, x=0.0, y=0.0, z=0.0, hop=0, group="core", parent=None):
    out = {
        "id": nid,
        "label": nid,
        "group": group,
        "hop": hop,
        "position": {"x": x, "y": y, "z": z},
        "metrics": {"capabilities": 3},
        "description": "x" * 200,  # the bulk a digest row must not carry
    }
    if parent:
        out["parent_id"] = parent
    return out


def federation(hub_count, children=2):
    """A synthetic federation: our own hub plus `hub_count` peers, each with children."""
    nodes = [node("hub"), node("federation", -2, 5, 1)]
    links = [{"source": "hub", "target": "federation"}]
    for i in range(hub_count):
        angle = (2 * math.pi * i) / max(1, hub_count)
        hx, hz = 40 * math.cos(angle), 40 * math.sin(angle)
        hid = f"peer-{i}"
        nodes.append(node(hid, hx, 0.0, hz, hop=1, group="peer_hub"))
        links.append({"source": "federation", "target": hid})
        for c in range(children):
            cid = f"{hid}-c{c}"
            nodes.append(node(cid, hx + 2.2 * (c + 1), 0.4, hz, hop=2,
                              group="peer_hub_node", parent=hid))
            links.append({"source": hid, "target": cid})
    return nodes, links


@pytest.fixture(autouse=True)
def _default_threshold(monkeypatch):
    monkeypatch.delenv("ALIEN_MAP_WINDOW_THRESHOLD", raising=False)
    monkeypatch.delenv("ALIEN_MAP_WINDOW_LIMIT", raising=False)


class TestASmallMapIsUntouched:
    """The split removes a ceiling. It must not add a round trip to a map of sixty nodes."""

    def test_the_tick_still_carries_everything(self):
        from map_window import should_window, tick_payload

        nodes, links = federation(12)
        state = {"nodes": nodes, "links": links, "tick": 3}
        assert should_window(nodes) is False
        assert tick_payload(state) is state
        assert "map" not in tick_payload(state)


class TestABigMapShipsAPointer:
    def test_the_tick_drops_to_the_local_ecosystem(self):
        from map_window import tick_payload

        nodes, links = federation(1000)          # 3002 nodes
        payload = tick_payload({"nodes": nodes, "links": links})
        assert payload["map"]["windowed"] is True
        assert payload["map"]["total"] == len(nodes)
        # Only hop 0 rides the tick — everything this deployment actually IS.
        assert {n["id"] for n in payload["nodes"]} == {"hub", "federation"}
        assert payload["links"] == [{"source": "hub", "target": "federation"}]

    def test_a_link_with_one_end_off_the_tick_is_not_shipped(self):
        from map_window import tick_payload

        nodes, links = federation(1000)
        payload = tick_payload({"nodes": nodes, "links": links})
        ids = {n["id"] for n in payload["nodes"]}
        for link in payload["links"]:
            assert link["source"] in ids and link["target"] in ids


class TestTheDigest:
    def test_a_row_is_five_values_and_no_prose(self):
        from map_window import build_digest

        nodes, _links = federation(3)
        page = build_digest(nodes)
        assert page["total"] == len(nodes)
        for row in page["rows"]:
            assert len(row) == 5
            nid, x, y, z, kind = row
            assert isinstance(nid, str) and kind in (0, 1, 2, 3)
            assert all(isinstance(v, float) for v in (x, y, z))
        # The 200-character description each node carries is not in it.
        assert "xxxx" not in str(page["rows"])

    def test_it_pages(self):
        from map_window import build_digest

        nodes, _links = federation(500)          # 1502 nodes
        seen: list[str] = []
        cursor = 0
        pages = 0
        while True:
            page = build_digest(nodes, cursor=cursor, limit=400)
            seen.extend(row[0] for row in page["rows"])
            pages += 1
            if page["next_cursor"] is None:
                break
            cursor = page["next_cursor"]
            assert pages < 20, "paging did not terminate"
        assert seen == [n["id"] for n in nodes]

    def test_the_epoch_moves_when_the_chart_does_and_not_when_a_metric_does(self):
        from map_window import digest_epoch

        nodes, _links = federation(20)
        before = digest_epoch(nodes)
        nodes[5]["metrics"]["capabilities"] = 999
        nodes[5]["status"] = "active"
        assert digest_epoch(nodes) == before, "a metric tick must not cost a re-fetch"

        moved = [dict(n) for n in nodes]
        moved[5] = dict(moved[5], position={"x": 99.0, "y": 0.0, "z": 0.0})
        assert digest_epoch(moved) != before

    def test_one_hub_arriving_as_another_leaves_still_changes_the_epoch(self):
        """A count would miss this, which is why the epoch is a hash of identity."""
        from map_window import digest_epoch

        nodes, _links = federation(10)
        swapped = list(nodes)
        swapped[-1] = node("newcomer", 41.0, 0.0, 0.0, hop=1, group="peer_hub")
        assert len(swapped) == len(nodes)
        assert digest_epoch(swapped) != digest_epoch(nodes)


class TestTheWindow:
    def test_it_returns_what_is_near_and_stops(self):
        from map_window import select_window, window_limit

        nodes, links = federation(2000)
        got = select_window(nodes, links, center=(40.0, 0.0, 0.0), radius=25.0)
        assert len(got["nodes"]) <= window_limit()
        assert got["nodes"], "a window over a populated region cannot be empty"

    def test_it_never_returns_a_dangling_link(self):
        from map_window import select_window

        nodes, links = federation(400)
        got = select_window(nodes, links, center=(40.0, 0.0, 0.0), radius=30.0)
        ids = {n["id"] for n in got["nodes"]}
        for link in got["links"]:
            assert link["source"] in ids and link["target"] in ids

    def test_a_focused_hub_comes_back_with_its_constellation(self):
        """Clicking a distant star must not open a card with nothing behind it."""
        from map_window import select_window

        nodes, links = federation(2000, children=4)
        far = "peer-1500"
        got = select_window(
            nodes, links, center=(0.0, 0.0, 0.0), radius=1.0, include_ids=[far],
        )
        ids = {n["id"] for n in got["nodes"]}
        assert far in ids
        assert {f"{far}-c{i}" for i in range(4)} <= ids, "a sun arrived without its planets"

    def test_a_hundred_thousand_nodes_still_answer_in_one_bounded_payload(self):
        from map_window import build_digest, select_window, tick_payload, window_limit

        nodes, links = federation(33333, children=2)   # 100 001 nodes
        assert len(nodes) > 100_000

        tick = tick_payload({"nodes": nodes, "links": links})
        assert len(tick["nodes"]) == 2, "the tick must not grow with the federation"

        page = build_digest(nodes, cursor=0, limit=4000)
        assert len(page["rows"]) == 4000 and page["total"] == len(nodes)

        got = select_window(nodes, links, center=(40.0, 0.0, 0.0), radius=20.0)
        assert len(got["nodes"]) <= window_limit()
