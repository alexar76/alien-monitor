"""Colour has to mean something, and a meaning is not one colour.

Two flat universes, in order. First purple: every federated node that was not a hub fell to
`#a64dff`, so three unrelated services under one hub were identical and a second operator's
satellites would have been that same purple. Then grey: the fix gave everything undeclared
one slate, which is the same defect wearing a different hue.

What the map needs is both — a family you can recognise at a glance, and a node you can tell
apart inside it. So a family owns a narrow ARC of hue and a node picks its shade from its own
id; and a node that declared nothing takes a vivid hue from the space BETWEEN the arcs, which
asserts no family while still being a colour worth looking at.
"""

from __future__ import annotations

import colorsys
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def hue_of(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    r, g, b = (int(raw[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[0] * 360.0


def saturation_of(hex_color: str) -> float:
    raw = hex_color.lstrip("#")
    r, g, b = (int(raw[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)[2]


def in_arc(hue: float, base: float, spread: float) -> bool:
    delta = abs((hue - base + 180.0) % 360.0 - 180.0)
    return delta <= spread + 0.6  # rounding to 8-bit channels costs a fraction of a degree


class TestColourSaysWhatAThingDoes:
    @pytest.mark.parametrize(
        "label,categories,family",
        [
            ("ATLAS", ["iot", "sensors", "geospatial"], "physical"),
            ("GAIA", ["iot", "sensors", "physical-data", "weather"], "physical"),
            ("MOMUS", ["security", "red-team", "audit"], "security"),
            ("THEMIS", ["security", "procurement", "admission"], "security"),
            ("BASANOS", ["security", "solidity", "assurance"], "security"),
            ("LOGOS", ["analytics", "federation", "observability"], "observability"),
            ("SKOPOS", ["observability", "security", "fleet"], "observability"),
            ("oracle family", ["oracle", "consensus", "sampling"], "oracle"),
        ],
    )
    def test_a_real_peer_lands_in_its_family_arc(self, label, categories, family):
        from node_palette import FAMILY_BANDS, color_for

        base, spread, _s, _l = FAMILY_BANDS[family]
        got = color_for("peer_hub", categories, node_id=label)
        assert in_arc(hue_of(got), base, spread), f"{label} {got} is outside {family}"

    def test_the_first_category_wins(self):
        """SKOPOS says observability, security, fleet — an observability service that also
        mentions security. Scoring by overlap would have filed it under security."""
        from node_palette import family_for

        assert family_for(["observability", "security", "fleet"]) == "observability"
        assert family_for(["security", "observability"]) == "security"

    def test_a_service_is_the_same_family_whoever_runs_it(self):
        from node_palette import FAMILY_BANDS, color_for

        base, spread, _s, _l = FAMILY_BANDS["physical"]
        for owner in ("peer_hub", "peer_hub_provider", "peer_hub_node"):
            got = color_for(owner, ["iot"], node_id=f"{owner}:x")
            assert in_arc(hue_of(got), base, spread)


class TestAFamilyIsNotOneColour:
    def test_twelve_siblings_are_twelve_shades(self):
        """The grey universe in one assertion: twelve security services under one hub used
        to be one crimson repeated, and a reader could not tell which one they clicked."""
        from node_palette import color_for

        shades = {color_for("peer_hub", ["security"], node_id=f"sec-{i}") for i in range(12)}
        assert len(shades) >= 8, "a family collapsed back into one colour"

    def test_but_they_still_read_as_one_family(self):
        from node_palette import FAMILY_BANDS, color_for

        base, spread, _s, _l = FAMILY_BANDS["security"]
        for i in range(30):
            got = color_for("peer_hub", ["security"], node_id=f"sec-{i}")
            assert in_arc(hue_of(got), base, spread)

    def test_a_shade_never_moves(self):
        """Keyed on a stable digest, not `hash()`: Python salts str hashing per process, so
        the map would have re-coloured itself on every restart."""
        from node_palette import color_for

        first = color_for("peer_hub_provider", ["oracle"], node_id="provider:hub:kova")
        again = color_for("peer_hub_provider", ["oracle"], node_id="provider:hub:kova")
        assert first == again
        assert first != color_for("peer_hub_provider", ["oracle"], node_id="provider:hub:aegis")


class TestUndeclaredIsColourfulButClaimsNothing:
    def test_three_unnamed_providers_are_three_colours(self):
        from node_palette import color_for

        ids = ["provider:hub:kova-gateway", "provider:hub:aegis-independent",
               "provider:hub:independentai"]
        got = {color_for("peer_hub_provider", [], node_id=i) for i in ids}
        assert len(got) == 3, "the grey universe is back"

    def test_it_never_lands_inside_a_family_arc(self):
        """A colour inside a family's arc means that family. Nothing undeclared may sit
        there, or the map starts asserting categories nobody published."""
        from node_palette import FAMILY_BANDS, color_for

        for i in range(200):
            hue = hue_of(color_for("peer_hub_provider", [], node_id=f"unknown-{i}"))
            for family, (base, spread, _s, _l) in FAMILY_BANDS.items():
                assert not in_arc(hue, base, spread), f"unknown-{i} impersonates {family}"

    def test_it_is_not_grey(self):
        from node_palette import color_for

        for i in range(20):
            assert saturation_of(color_for("peer_hub_provider", [], node_id=f"u{i}")) > 0.4


class TestAHubIsStillAHub:
    def test_a_hub_that_declares_nothing_stays_hub_cyan(self):
        """modelmarket.dev, Signal Hunt Hub — real federation hubs, no capability
        categories. Their identity IS being a hub, so that is what the colour says."""
        from node_palette import STRUCTURAL_COLORS, color_for

        assert color_for("peer_hub", [], node_id="mm") == STRUCTURAL_COLORS["peer_hub"]
        assert color_for("peer_hub", [], role="hub", node_id="x") == STRUCTURAL_COLORS["peer_hub"]

    def test_a_stranger_keeps_the_amber_of_a_stranger(self):
        from node_palette import STRUCTURAL_COLORS, color_for

        assert color_for("pending_hub", ["oracle"]) == STRUCTURAL_COLORS["pending_hub"]
        assert color_for("pending_hub_node", []) == STRUCTURAL_COLORS["pending_hub_node"]


class TestBothMapsAgree:
    def test_the_live_and_uni_paths_stamp_the_same_colour(self):
        """The original defect in one assertion: one node, two of our maps, two colours."""
        from node_palette import color_for

        live = color_for("peer_hub_provider", ["payments"], node_id="provider:h:kova")
        uni = color_for("peer_hub_provider", ["payments"], role="", node_id="provider:h:kova")
        assert live == uni


class TestSiblingsNeverBunch:
    """Three providers under one hub came back as three magentas within thirty degrees.

    A hash is uniform but not spread — three samples are allowed to land together — and on
    the live map they did. Children of a hub are therefore walked by the golden angle from a
    per-hub starting point, which cannot bunch at any count.
    """

    def test_a_hubs_children_are_spread_apart(self):
        from node_palette import color_for

        for count in (2, 3, 5, 8):
            hues = sorted(
                hue_of(color_for("peer_hub_provider", [], node_id=f"c{i}",
                                 sibling=i, sibling_seed="hub-a"))
                for i in range(count)
            )
            gaps = [b - a for a, b in zip(hues, hues[1:])]
            assert min(gaps) > 12.0, f"{count} siblings bunched: {hues}"

    def test_two_hubs_do_not_get_the_same_run_of_colours(self):
        from node_palette import color_for

        def run(hub):
            return [color_for("peer_hub_provider", [], node_id=f"{hub}:{i}",
                              sibling=i, sibling_seed=hub) for i in range(3)]

        assert run("hub-a") != run("hub-b")

    def test_the_run_is_still_stable(self):
        from node_palette import color_for

        first = [color_for("peer_hub_provider", [], node_id=f"x{i}", sibling=i,
                           sibling_seed="h") for i in range(4)]
        again = [color_for("peer_hub_provider", [], node_id=f"x{i}", sibling=i,
                           sibling_seed="h") for i in range(4)]
        assert first == again

    def test_spread_siblings_still_respect_their_family(self):
        from node_palette import FAMILY_BANDS, color_for

        base, spread, _s, _l = FAMILY_BANDS["security"]
        for i in range(10):
            got = color_for("peer_hub_node", ["security"], node_id=f"s{i}",
                            sibling=i, sibling_seed="h")
            assert in_arc(hue_of(got), base, spread)
