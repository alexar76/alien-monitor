"""Does every hub the federation reports actually reach the map?

Written because a hub did not, three times over, and each time the failure was silent: the
node was discovered correctly, merged correctly, served correctly — and then simply was not
on screen. Nothing logged, nothing errored, and the only way to notice was for a person to
look at a picture and say "where is it".

A federation that grows by strangers knocking cannot be audited by looking at pictures. So
this walks the same path the data walks and reports, per discovered node, whether it survived
and — when it did not — which of the four gates ate it:

  fold        a canonical rule mapped it onto an existing map node (correct, and named)
  collision   its id already existed in the static shelf, so the merge skipped it
  orphan      it names a parent that is not on the map, so it can never be revealed
  lost        it passed the merge and is not in the graph — a real defect, no known cause

`orphan` and `lost` are defects. `fold` and `collision` are design, and are reported anyway,
because "correct" and "invisible" have been the same thing here often enough that a reader
deserves to see the whole ledger rather than only the exceptions.
"""

from __future__ import annotations

from typing import Any


def audit(nodes: list[dict[str, Any]], disc: dict[str, Any],
          static_ids: set[str], folded: dict[str, str]) -> dict[str, Any]:
    """Compare what discovery found against what the merged graph carries."""
    by_id = {str(n.get("id")): n for n in nodes if n.get("id")}
    rows: list[dict[str, Any]] = []
    for dn in disc.get("nodes") or []:
        if not isinstance(dn, dict):
            continue
        nid = str(dn.get("id") or "")
        label = str(dn.get("label") or nid)[:80]
        parent = str(dn.get("parent_id") or "")
        if nid in by_id and nid not in static_ids:
            verdict, why = "on_map", ""
        elif nid in folded:
            verdict, why = "fold", "canonical rule -> %s" % folded[nid]
        elif nid in static_ids:
            verdict, why = "collision", "id already in the static shelf"
        else:
            verdict, why = "lost", "passed discovery, absent from the merged graph"
        if verdict == "on_map" and parent and parent not in by_id:
            verdict, why = "orphan", "parent %s is not on the map" % parent
        rows.append({"id": nid, "label": label, "group": str(dn.get("group") or ""),
                     "hop": dn.get("hop"), "parent_id": parent or None,
                     "verdict": verdict, "why": why})
    defects = [r for r in rows if r["verdict"] in ("lost", "orphan")]
    return {
        "discovered": len(rows),
        "on_map": sum(1 for r in rows if r["verdict"] == "on_map"),
        "folded": sum(1 for r in rows if r["verdict"] == "fold"),
        "collisions": sum(1 for r in rows if r["verdict"] == "collision"),
        "defects": len(defects),
        "ok": not defects,
        "rows": rows,
        "note": ("Every hub discovered should be either on_map or explicitly folded. "
                 "`lost` and `orphan` are defects: a peer that knocked, passed an assay and "
                 "is served by the hub, yet cannot appear to anybody looking at the map."),
    }
