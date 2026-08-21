"""GAIA panel device picking — LIVE relays must not vanish behind the mesh."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from gaia_status import _live_payload, _pick_devices_for_panel, _sanitize_devices


def test_pick_devices_prefers_live_over_mesh():
    devices = []
    for i in range(40):
        devices.append(
            {
                "id": f"om-wx-{i}",
                "live": True,
                "online": True,
                "source": "https://open-meteo.com",
            }
        )
    devices.append(
        {
            "id": "ws-01",
            "live": False,
            "online": True,
            "source": None,
        }
    )
    devices.extend(
        [
            {
                "id": "firms-fire-01",
                "live": True,
                "online": True,
                "source": "https://firms.modaps.eosdis.nasa.gov",
            },
            {
                "id": "safecast-01",
                "live": True,
                "online": True,
                "source": "https://api.safecast.org",
            },
            {
                "id": "cybernews-jam-01",
                "live": True,
                "online": True,
                "source": "https://www.cybernews.space",
            },
        ]
    )
    picked = _pick_devices_for_panel(devices, limit=20)
    top = [d["id"] for d in picked[:3]]
    assert set(top) == {"firms-fire-01", "safecast-01", "cybernews-jam-01"}
    assert all(d["live"] for d in picked)
    assert "ws-01" not in {d["id"] for d in picked}


def test_default_limit_is_unlimited(monkeypatch):
    monkeypatch.delenv("ALIEN_GAIA_DEVICE_LIST_LIMIT", raising=False)
    devices = [{"id": f"d-{i}", "live": True, "online": True, "source": "x"} for i in range(200)]
    picked = _pick_devices_for_panel(devices)
    assert len(picked) == 200


def test_env_limit_caps_list(monkeypatch):
    monkeypatch.setenv("ALIEN_GAIA_DEVICE_LIST_LIMIT", "10")
    devices = [{"id": f"d-{i}", "live": True, "online": True, "source": "x"} for i in range(50)]
    devices.append({"id": "firms-fire-01", "live": True, "online": True, "source": "x"})
    picked = _pick_devices_for_panel(devices)
    assert len(picked) == 10
    assert picked[0]["id"] == "firms-fire-01"


def test_sanitize_marks_source_as_live():
    raw = [
        {
            "device_id": "firms-fire-01",
            "model": "GAIA-FIRE",
            "fields": {"brightness_k": "K"},
            "source": "https://firms.modaps.eosdis.nasa.gov (NASA FIRMS)",
            "online": True,
        },
        {
            "device_id": "ws-01",
            "model": "sim",
            "fields": {"temperature_c": "cel"},
            "source": None,
            "online": True,
        },
    ]
    out = _sanitize_devices(raw)
    assert out[0]["live"] is True
    assert out[1]["live"] is False
    payload = _live_payload({"devices": 2, "status": "ok"}, out)
    assert payload["live_relays"] == 1
    assert payload["devices"][0]["id"] == "firms-fire-01"
