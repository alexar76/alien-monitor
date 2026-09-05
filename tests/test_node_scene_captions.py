"""Every node-scene caption must exist in every locale.

A scene whose ``captionKey`` is missing from a locale does not fail loudly — i18next falls back to
the key itself, so the panel renders ``nodeDetail.scene.warden`` as its caption and only someone
reading that language ever sees it. The registry is TypeScript and the locales are JSON, so nothing
else checks the pair.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "frontend" / "src" / "nodeScenes" / "resolve.ts"
LOCALES = ROOT / "frontend" / "src" / "i18n" / "locales"
LANGS = ("en", "ru", "es", "fr", "zh")


def _caption_keys() -> dict[str, str]:
    text = REGISTRY.read_text(encoding="utf-8")
    body = text.split("NODE_SCENE_REGISTRY", 1)[1]
    # `id: { ... captionKey: 'nodeDetail.scene.id' ... }` — one entry per scene.
    return dict(re.findall(r"\n  ([a-z_]+): \{[^}]*?captionKey: '([^']+)'", body, re.S))


def _lookup(data: dict, dotted: str):
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def test_the_registry_is_readable():
    keys = _caption_keys()
    assert keys, "no captionKey found — did NODE_SCENE_REGISTRY change shape?"
    # The scene added with the WARDEN node; a canary for the parse above.
    assert keys.get("warden") == "nodeDetail.scene.warden"


@pytest.mark.parametrize("lang", LANGS)
def test_every_card_description_is_translated(lang):
    """`nodeDetail.desc.<id>` is optional per node — but a node that has one in ANY locale must have
    it in all of them, or that language silently falls back to the backend's English paragraph."""
    per_lang = {
        l: set(json.loads((LOCALES / f"{l}.json").read_text(encoding="utf-8"))["nodeDetail"]["desc"])
        for l in LANGS
    }
    everywhere = set.union(*per_lang.values())
    assert per_lang[lang] == everywhere, (
        f"{lang}.json card descriptions differ from the others: "
        f"missing {sorted(everywhere - per_lang[lang])}"
    )


@pytest.mark.parametrize("lang", LANGS)
def test_every_scene_caption_is_translated(lang):
    data = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    missing = {
        scene: key for scene, key in _caption_keys().items() if not isinstance(_lookup(data, key), str)
    }
    assert not missing, f"{lang}.json is missing scene captions: {missing}"
