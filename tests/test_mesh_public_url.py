"""The AI Service Mesh card links to the mesh's public edge, not to the poll URL (:8090)."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import factory_products  # noqa: E402
from factory_products import DEFAULT_PUBLIC_MESH_URL, mesh_public_url  # noqa: E402


def test_a_loopback_poll_url_never_reaches_the_card(monkeypatch) -> None:
    monkeypatch.delenv("ALIEN_PUBLIC_MESH_URL", raising=False)
    for poll in ("http://localhost:8090", "http://127.0.0.1:8090/", ""):
        monkeypatch.setenv("MESH_URL", poll)
        assert mesh_public_url() == DEFAULT_PUBLIC_MESH_URL


def test_an_explicit_or_routable_url_wins(monkeypatch) -> None:
    monkeypatch.setenv("MESH_URL", "http://localhost:8090")
    monkeypatch.setenv("ALIEN_PUBLIC_MESH_URL", "https://mesh.example.org/")
    assert mesh_public_url() == "https://mesh.example.org"
    monkeypatch.delenv("ALIEN_PUBLIC_MESH_URL")
    monkeypatch.setenv("MESH_URL", "https://service-mesh.example.net")
    assert mesh_public_url() == "https://service-mesh.example.net"


def test_the_mesh_node_uses_it(monkeypatch) -> None:
    monkeypatch.setenv("MESH_URL", "http://localhost:8090")
    monkeypatch.delenv("ALIEN_PUBLIC_MESH_URL", raising=False)
    import main

    nodes, _ = main.build_topology()
    mesh = next(n for n in nodes if n["id"] == "mesh")
    assert mesh["url"] == DEFAULT_PUBLIC_MESH_URL
    assert factory_products.DEFAULT_PUBLIC_MESH_URL.startswith("https://")
