"""Current product names for display; observed identities and signed data stay verbatim."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

SYMMARTYS_ALIASES = ("symmartys", "симартис", "симмартис", "συμμάρτυς", "emporion", "эмпорион")
_FORMER_BRAND = re.compile(r"(?<![\w./:@-])(?:emporion|эмпорион|емпорион)(?![\w./:@-])", re.IGNORECASE)


def symmartys_identity_url(value: str) -> str | None:
    """One observed provider behind its old and new first-party addresses.

    This is an address alias, never a label claim. Paths belonging to other
    services on the same host do not acquire this identity.
    """
    try:
        url = urlsplit(str(value or ""))
        if url.scheme not in {"https", "http"} or url.query or url.fragment:
            return None
        if url.port not in {None, 443 if url.scheme == "https" else 80}:
            return None
        path = url.path.rstrip("/")
        if (url.hostname in {"emporion.modelmarket.dev", "symmartys.modelmarket.dev"} and not path) or (
            url.hostname == "modelmarket.dev" and path in {"/providers/emporion", "/providers/symmartys"}
        ):
            return "https://modelmarket.dev/providers/symmartys"
    except ValueError:
        pass
    return None


def current_product_label(value: str) -> str:
    """Replace the human brand only, never URLs, capability ids or package names."""
    return _FORMER_BRAND.sub("SYMMARTYS", value)


def is_symmartys_node(node: dict[str, Any]) -> bool:
    """Match this ecosystem's provider by identity/address, never a stranger's label."""
    if str(node.get("id") or "") in {"emporion", "symmartys"} or str(
        node.get("canonical_id") or ""
    ) in {"emporion", "symmartys"}:
        return True
    try:
        url = urlsplit(str(node.get("url") or ""))
        return url.hostname in {"emporion.modelmarket.dev", "symmartys.modelmarket.dev"} or (
            url.hostname == "modelmarket.dev" and url.path.rstrip("/") in {
                "/providers/emporion", "/providers/symmartys"
            }
        )
    except ValueError:
        return False


def node_display_label(node: dict[str, Any]) -> str:
    label = str(node.get("label") or node.get("id") or "node")
    return current_product_label(label) if is_symmartys_node(node) else label


def node_display_description(node: dict[str, Any]) -> str:
    description = str(node.get("description") or "")
    return current_product_label(description) if is_symmartys_node(node) else description


def symmartys_question(question: str) -> str:
    """Both names resolve to the current brand in natural-language registry matching."""
    return re.sub(r"\b(?:emporion|эмпорион|емпорион|симартис|симмартис|συμμάρτυς)\b", "symmartys", question, flags=re.IGNORECASE)
