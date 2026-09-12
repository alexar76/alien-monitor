"""Tests for multi-instance ARGUS roster (Factory Products pattern)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from argus_roster import (
    apply_roster_to_node,
    clear_roster,
    counts,
    get_instance,
    heartbeat,
    list_instances,
    note_run,
    seed_demo_instances,
)


def setup_function():
    clear_roster()


def test_heartbeat_registers_and_counts_active():
    rec = heartbeat(
        {
            "instance_id": "argus-alice-01",
            "display_name": "Alice",
            "wallet": "0x1111111111111111111111111111111111111111",
            "economy": "off",
            "version": "0.3.0",
        }
    )
    assert rec is not None
    # Wallet-derived id (stable across live/uni containers).
    assert rec["instance_id"].startswith("argus-")
    assert rec["instance_id"] != "argus-alice-01"
    assert rec["status"] == "active"
    c = counts()
    assert c["active"] == 1
    assert c["total"] == 1


def test_list_search_sort_and_cursor():
    for i in range(5):
        heartbeat(
            {
                "instance_id": f"argus-user-{i:02d}",
                "display_name": f"User {i}",
                "wallet": f"0x{'%038d' % i}ab",
                "economy": "on" if i % 2 == 0 else "off",
            }
        )
    page1 = list_instances(limit=2, sort="name")
    assert page1["count"] == 2
    assert page1["total"] == 5
    assert page1["has_more"] is True
    page2 = list_instances(limit=2, sort="name", cursor=page1["next_cursor"])
    assert page2["count"] == 2
    ids = {r["instance_id"] for r in page1["instances"] + page2["instances"]}
    assert len(ids) == 4

    found = list_instances(q="user 3")
    assert found["count"] == 1
    assert found["instances"][0]["display_name"] == "User 3"


def test_note_run_derives_id_from_wallet():
    run = {
        "id": "run_abc",
        "goal": "test",
        "beats": [],
        "spendUsd": 0.05,
        "receiptHash": "0xhash",
        "signer": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    }
    rec = note_run({"signer": run["signer"], "spendUsd": 0.05}, run)
    assert rec is not None
    assert rec["instance_id"].startswith("argus-")
    detail = get_instance(rec["instance_id"])
    assert detail is not None
    assert detail["has_run"] is True
    assert detail["last_run"]["id"] == "run_abc"


def test_apply_roster_updates_metrics_not_label():
    seed_demo_instances(2)
    node = {"id": "argus", "label": "ARGUS-3", "metrics": {}, "status": "offline"}
    apply_roster_to_node(node)
    assert node["label"] == "ARGUS-3"
    assert node["metrics"]["instances_total"] == 2
    assert node["status"] == "active"


def test_invalid_id_rejected():
    assert heartbeat({"instance_id": "ab"}) is None
    assert heartbeat({"instance_id": "bad id!"}) is None


def test_live_and_uni_same_wallet_coalesce():
    """Factory live + Factory-UNI → one fleet agent with two mode/wallet marks."""
    wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    heartbeat(
        {
            "instance_id": "argus-legacy-live",
            "display_name": "Factory",
            "wallet": wallet,
            "mode": "live",
            "economy": "on",
            "host": "factory.ams-1",
        }
    )
    heartbeat(
        {
            "instance_id": "argus-legacy-uni",
            "display_name": "Factory-UNI",
            "wallet": wallet,
            "mode": "uni",
            "economy": "on",
            "host": "factory.ams-1",
        }
    )
    c = counts()
    assert c["total"] == 1
    assert c["active"] == 1
    page = list_instances()
    assert page["count"] == 1
    row = page["instances"][0]
    assert row["display_name"] == "Factory"
    assert set(row["modes"]) == {"live", "uni"}
    assert len(row["wallets"]) == 2
    chains = {w["chain"] for w in row["wallets"]}
    assert chains == {"live", "uni"}


def test_two_wallets_two_agents():
    heartbeat(
        {
            "display_name": "Factory",
            "wallet": "0x1111111111111111111111111111111111111111",
            "mode": "live",
            "economy": "on",
        }
    )
    heartbeat(
        {
            "display_name": "Server-2",
            "wallet": "0x2222222222222222222222222222222222222222",
            "mode": "live",
            "economy": "on",
        }
    )
    assert counts()["total"] == 2
