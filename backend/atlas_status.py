"""Poll ATLAS for the Alien Monitor ``atlas`` node.

Best-effort and offline-safe: if ATLAS is unreachable the node shows ``offline``
and the rest of the monitor is unaffected.

Reads (no auth):

    GET /health           → ok / version / station count
    GET /api/v1/monitor   → slim stations + embed/map URLs for the detail panel
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_ATLAS_URL = "https://atlas.modelmarket.dev"
DEFAULT_PUBLIC_ATLAS_URL = "https://atlas.modelmarket.dev"
# atlas/ is a satellite: it is rsync-excluded from the public alexar76/aicom
# mirror, so the monorepo path 404s. Point at the satellite repo like GAIA /
# METIS / SKOPOS do.
DEFAULT_ATLAS_GITHUB_URL = "https://github.com/alexar76/atlas"


def atlas_poll_url() -> str:
    return (
        os.environ.get("ALIEN_ATLAS_URL")
        or os.environ.get("ATLAS_URL")
        or DEFAULT_ATLAS_URL
    ).rstrip("/")


def atlas_public_url() -> str:
    return (
        os.environ.get("ALIEN_PUBLIC_ATLAS_URL")
        or os.environ.get("ATLAS_PUBLIC_URL")
        or DEFAULT_PUBLIC_ATLAS_URL
    ).rstrip("/")


def atlas_links() -> dict[str, str]:
    github = (
        os.environ.get("ALIEN_ATLAS_GITHUB_URL")
        or os.environ.get("ATLAS_GITHUB_URL")
        or DEFAULT_ATLAS_GITHUB_URL
    ).rstrip("/")
    public = atlas_public_url()
    return {
        "landing": public,
        "embed": f"{public}/embed",
        "github": github,
        "docs": f"{github}#readme",
    }


def fetch_atlas_status_sync(
    *, base_url: str | None = None, timeout: float = 4.0
) -> dict[str, Any] | None:
    root = (base_url or atlas_poll_url()).rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            h = client.get(f"{root}/health")
            if h.status_code != 200:
                return None
            health = h.json()
            if not isinstance(health, dict):
                return None
            monitor: dict[str, Any] = {}
            try:
                r = client.get(f"{root}/api/v1/monitor")
                if r.status_code == 200:
                    body = r.json()
                    if isinstance(body, dict):
                        monitor = body
            except Exception:
                monitor = {}
            return {"health": health, "monitor": monitor}
    except Exception:
        return None


def _live_payload(health: dict[str, Any], monitor: dict[str, Any]) -> dict[str, Any]:
    stations = monitor.get("stations") if isinstance(monitor.get("stations"), list) else []
    quakes = monitor.get("quakes") if isinstance(monitor.get("quakes"), list) else []
    live_n = int(monitor.get("live") or sum(1 for s in stations if isinstance(s, dict) and s.get("live")))
    sim_n = int(monitor.get("sim") or sum(1 for s in stations if isinstance(s, dict) and s.get("mode") == "sim"))
    return {
        "version": monitor.get("version") or health.get("version"),
        "service": "atlas",
        "status": monitor.get("status") or health.get("status"),
        "stale": bool(monitor.get("stale") or health.get("stale")),
        "station_count": int(monitor.get("station_count") or health.get("stations") or len(stations)),
        "online": int(monitor.get("online") or 0),
        "live": live_n,
        "sim": sim_n,
        "quake_count": int(monitor.get("quake_count") or len(quakes)),
        "layers": monitor.get("layers") if isinstance(monitor.get("layers"), list) else [],
        "embed_url": str(monitor.get("embed_url") or atlas_links()["embed"]),
        "map_url": str(monitor.get("map_url") or atlas_public_url()),
        # Match ATLAS monitor_station_limit (default 24) so river/marine pins survive.
        "stations": stations[:24],
        "quakes": quakes[:6],
    }


def apply_atlas_to_nodes(
    nodes: list[dict],
    status: dict[str, Any] | None,
    *,
    public_url: str | None = None,
) -> None:
    node = next((n for n in nodes if n.get("id") == "atlas"), None)
    if not node:
        return

    node["url"] = public_url or atlas_public_url()
    node["links"] = atlas_links()

    if not status:
        node["status"] = "offline"
        node.pop("atlas_live", None)
        node["metrics"] = {"stations": 0, "online": 0, "quakes": 0}
        return

    health = status.get("health") or {}
    monitor = status.get("monitor") or {}
    payload = _live_payload(health, monitor)
    ok = bool(health.get("ok")) or payload["station_count"] > 0
    node["status"] = "active" if ok else "idle"
    node["atlas_live"] = payload
    node["metrics"] = {
        "stations": payload["station_count"],
        "online": payload["online"],
        "live": payload.get("live", 0),
        "sim": payload.get("sim", 0),
        "quakes": payload["quake_count"],
    }


def apply_atlas_graph(nodes: list[dict], *, mode: str = "real") -> None:
    _ = mode
    status = fetch_atlas_status_sync()
    apply_atlas_to_nodes(nodes, status, public_url=atlas_public_url())


def atlas_demo_stations() -> list[dict[str, Any]]:
    return [
        {
            "id": "om-wx-01",
            "layer": "weather",
            "label": "Open-Meteo Weather",
            "place": "Berlin",
            "online": True,
            "mode": "live",
            "live": True,
            "source": "https://open-meteo.com",
            "lat": 52.52,
            "lon": 13.41,
            "headline": "22.0 °C",
            "values": {"temperature_c": 22.0},
        },
        {
            "id": "ws-01",
            "layer": "weather",
            "label": "Weather Sim A",
            "place": "GAIA demo campus (sim)",
            "online": True,
            "mode": "sim",
            "live": False,
            "source": None,
            "lat": 46.95,
            "lon": 7.45,
            "headline": "19.0 °C",
            "values": {"temperature_c": 19.0},
        },
        {
            "id": "usgs-quake-01",
            "layer": "quake",
            "label": "USGS Earthquake",
            "place": "Latest event",
            "online": True,
            "mode": "live",
            "live": True,
            "source": "https://earthquake.usgs.gov",
            "lat": 29.0,
            "lon": 94.7,
            "headline": "M 5.0",
            "values": {"magnitude": 5.0, "latitude": 29.0, "longitude": 94.7},
        },
        {
            "id": "noaa-tide-01",
            "layer": "tide",
            "label": "NOAA Tide",
            "place": "The Battery, NYC",
            "online": True,
            "mode": "live",
            "live": True,
            "source": "https://api.tidesandcurrents.noaa.gov",
            "lat": 40.7,
            "lon": -74.01,
            "headline": "0.150 m",
            "values": {"water_level_m": 0.15},
        },
        {
            "id": "usgs-river-01",
            "layer": "river",
            "label": "USGS River · Potomac",
            "place": "Potomac River, MD/DC",
            "online": True,
            "mode": "live",
            "live": True,
            "source": "https://waterservices.usgs.gov",
            "lat": 38.9495,
            "lon": -77.1275,
            "headline": "999 m³/s",
            "values": {"discharge_m3s": 999.0, "gage_height_m": 1.65},
        },
        {
            "id": "ndbc-01",
            "layer": "marine",
            "label": "NDBC Buoy 44025",
            "place": "New York Bight",
            "online": True,
            "mode": "live",
            "live": True,
            "source": "https://www.ndbc.noaa.gov",
            "lat": 40.251,
            "lon": -73.164,
            "headline": "1.40 m waves",
            "values": {"wave_height_m": 1.4, "sst_c": 21.4},
        },
        {
            "id": "om-marine-01",
            "layer": "marine",
            "label": "Open-Meteo Marine",
            "place": "New York Harbor",
            "online": True,
            "mode": "live",
            "live": True,
            "source": "https://open-meteo.com",
            "lat": 40.70,
            "lon": -74.01,
            "headline": "1.25 m waves",
            "values": {"wave_height_m": 1.25, "sst_c": 20.8},
        },
    ]


def fill_atlas_sim_node(node: dict) -> None:
    stations = atlas_demo_stations()
    live_n = sum(1 for s in stations if s.get("live"))
    sim_n = sum(1 for s in stations if s.get("mode") == "sim")
    node["url"] = atlas_public_url()
    node["links"] = atlas_links()
    node["status"] = "active"
    node["atlas_live"] = {
        "version": "0.1.0",
        "service": "atlas",
        "status": "ok",
        "stale": False,
        "station_count": len(stations),
        "online": len(stations),
        "live": live_n,
        "sim": sim_n,
        "quake_count": 1,
        "layers": ["weather", "quake", "tide", "river", "marine"],
        "embed_url": atlas_links()["embed"],
        "map_url": atlas_public_url(),
        "stations": stations,
        "quakes": [
            {
                "id": "q-demo",
                "lat": 29.0,
                "lon": 94.7,
                "magnitude": 5.0,
                "depth_km": 10.0,
                "place": "demo",
            }
        ],
    }
    node["metrics"] = {
        "stations": len(stations),
        "online": len(stations),
        "live": live_n,
        "sim": sim_n,
        "quakes": 1,
    }
