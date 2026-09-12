"""Answering from the graph that is on screen, rather than from a list somebody wrote down.

The offline assistant (no LLM key configured) used to end at a hand-written give-up line
naming SKOPOS, Metis, THEMIS, DIOSCURI, MOMUS, contracts, plugins, mesh and ACEX. On the
deployment those names belong to that is merely unhelpful. On any OTHER deployment it is
wrong: `monitor.attestedmemory.net` answered "ask about the hub, SKOPOS, Metis…" to «где
аттестед мемори?» — advertising a stranger's components while its own hub, its Memory
Market and its Provenance Ledger sat on the map three nodes away.

So the fallback reads the map. Everything here takes the live snapshot and describes what is
actually in it: what a node is, whose constellation it sits in, what it is wired to, and —
when nothing matches — what this particular map does contain, by name.
"""

from __future__ import annotations

from typing import Any

#: Human names for the groups the graph uses, per locale. A group with no entry is named by
#: its own key rather than dropped: an unnamed kind of node is still a fact about the map.
_GROUP_NAMES: dict[str, dict[str, str]] = {
    "en": {
        "core": "core service", "peer_hub": "federated hub", "pending_hub": "unapproved hub",
        "peer_hub_provider": "provider in a hub's own ecosystem",
        "peer_hub_node": "peer of a federated hub", "oracle": "oracle",
        "security": "security component", "contract": "on-chain contract",
        "chain": "blockchain network", "network": "network service", "sdk": "SDK",
        "client": "client", "economy": "economic actor", "cluster": "product catalogue",
        "agent": "agent", "infra": "infrastructure", "observability": "observability",
        "cognition": "cognition layer", "physical": "physical-world gateway",
        "community": "community agent", "media": "media", "studio": "studio",
        "crypto": "crypto service", "factory_product": "shipped product",
    },
    "ru": {
        "core": "базовый сервис", "peer_hub": "федеративный хаб",
        "pending_hub": "неодобренный хаб",
        "peer_hub_provider": "провайдер в экосистеме своего хаба",
        "peer_hub_node": "пир федеративного хаба", "oracle": "оракул",
        "security": "компонент безопасности", "contract": "он-чейн контракт",
        "chain": "блокчейн-сеть", "network": "сетевой сервис", "sdk": "SDK",
        "client": "клиент", "economy": "экономический актор",
        "cluster": "каталог продуктов", "agent": "агент",
        "infra": "инфраструктура", "observability": "наблюдаемость",
        "cognition": "слой мышления", "physical": "шлюз физического мира",
        "community": "community-агент", "media": "медиа", "studio": "студия",
        "crypto": "крипто-сервис", "factory_product": "выпущенный продукт",
    },
    "es": {
        "core": "servicio base", "peer_hub": "hub federado",
        "pending_hub": "hub no aprobado",
        "peer_hub_provider": "proveedor del ecosistema de su hub",
        "peer_hub_node": "par de un hub federado", "oracle": "oráculo",
        "security": "componente de seguridad", "contract": "contrato on-chain",
        "chain": "red blockchain", "network": "servicio de red", "sdk": "SDK",
        "client": "cliente", "economy": "actor económico",
        "cluster": "catálogo de productos", "agent": "agente",
        "infra": "infraestructura", "observability": "observabilidad",
    },
}

#: Groups worth naming in an overview, most structural first. Everything else is counted.
#: This deployment's OWN ecosystem comes before the hubs it federates with: the question
#: that produced this module was «где мемори маркет?» on a map whose overview named seven
#: foreign hubs and then said "providers — 4" without naming the one being asked about.
_OVERVIEW_ORDER = (
    "core", "peer_hub_provider", "peer_hub", "peer_hub_node", "pending_hub",
    "oracle", "security", "economy", "contract", "chain", "network", "cluster",
)

_MAX_NEIGHBOURS = 6
_MAX_OVERVIEW_NAMES = 12
_MAX_METRICS = 4


def group_name(group: str, locale: str = "en") -> str:
    table = _GROUP_NAMES.get(locale) or _GROUP_NAMES["en"]
    return table.get(group) or _GROUP_NAMES["en"].get(group) or (group or "node").replace("_", " ")


def _ru_nodes_word(count: int) -> str:
    """«1 узел» / «2 узла» / «21 узел» — the count is read aloud, so it has to agree."""
    tail_two, tail = count % 100, count % 10
    if 11 <= tail_two <= 14:
        return "узлов"
    if tail == 1:
        return "узел"
    if 2 <= tail <= 4:
        return "узла"
    return "узлов"


def _nodes(state: dict | None) -> list[dict[str, Any]]:
    if not isinstance(state, dict):
        return []
    return [n for n in (state.get("nodes") or []) if isinstance(n, dict) and n.get("id")]


def _label(node: dict[str, Any]) -> str:
    return str(node.get("label") or node.get("id") or "node")


def neighbours(state: dict | None, node_id: str) -> list[tuple[str, str]]:
    """(label, edge label) for everything wired to this node, nearest relationships first.

    The links are what makes this a map rather than a list, and they are the half the
    assistant never looked at: "where is X" is answered by what X is attached to.
    """
    by_id = {str(n["id"]): n for n in _nodes(state)}
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for link in (state or {}).get("links") or []:
        if not isinstance(link, dict):
            continue
        src, tgt = str(link.get("source") or ""), str(link.get("target") or "")
        other = tgt if src == node_id else (src if tgt == node_id else "")
        if not other or other in seen:
            continue
        seen.add(other)
        peer = by_id.get(other)
        if peer is None:
            continue
        out.append((_label(peer), str(link.get("label") or link.get("kind") or "").strip()))
    return out


def _metric_text(node: dict[str, Any]) -> str:
    metrics = node.get("metrics")
    if not isinstance(metrics, dict):
        return ""
    parts = [
        f"{key}={value}"
        for key, value in metrics.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return ", ".join(parts[:_MAX_METRICS])


def describe_node(state: dict | None, node_id: str, locale: str = "en") -> str:
    """Where a node sits in the live graph, in one paragraph. Empty when it is not there."""
    node = next((n for n in _nodes(state) if str(n["id"]) == str(node_id)), None)
    if node is None:
        return ""
    by_id = {str(n["id"]): n for n in _nodes(state)}
    label = _label(node)
    kind = group_name(str(node.get("group") or ""), locale)
    status = str(node.get("status") or "unknown")
    parent = by_id.get(str(node.get("parent_id") or ""))
    hub_ref = node.get("hub") if isinstance(node.get("hub"), dict) else None
    owner = _label(parent) if parent is not None else str((hub_ref or {}).get("label") or "")
    # A hub's own `hub` back-reference points at itself, and it carries the label the
    # topology was BUILT with — so the primary hub, renamed from its own /.well-known,
    # introduced itself as living in the system of its former name.
    if owner == label or str((hub_ref or {}).get("id") or "") == str(node.get("id") or ""):
        owner = ""
    wired = neighbours(state, str(node_id))
    metrics = _metric_text(node)
    url = str(node.get("url") or node.get("url_internal") or "").strip()
    description = str(node.get("description") or "").strip()
    if description and description[-1] not in ".!?…":
        description += "."

    def wired_text(joiner: str) -> str:
        if not wired:
            return ""
        return joiner.join(
            f"{name} ({edge})" if edge else name for name, edge in wired[:_MAX_NEIGHBOURS]
        )

    if locale == "ru":
        bits = [f"**{label}** — {kind} на текущей карте, статус: {status}."]
        if owner:
            bits.append(f"Живёт в системе **{owner}**.")
        if description:
            bits.append(description)
        if wired:
            bits.append(f"Связан с: {wired_text(', ')}.")
        if metrics:
            bits.append(f"Метрики: {metrics}.")
        if url:
            bits.append(f"Адрес: {url}")
        bits.append("Найдено обходом живого графа, без статического списка.")
        return " ".join(bits)
    if locale == "es":
        bits = [f"**{label}** — {kind} en el mapa actual, estado: {status}."]
        if owner:
            bits.append(f"Vive en el sistema de **{owner}**.")
        if description:
            bits.append(description)
        if wired:
            bits.append(f"Conectado con: {wired_text(', ')}.")
        if metrics:
            bits.append(f"Métricas: {metrics}.")
        if url:
            bits.append(f"Dirección: {url}")
        bits.append("Encontrado recorriendo el grafo en vivo, sin lista estática.")
        return " ".join(bits)
    bits = [f"**{label}** — {kind} on the current map, status: {status}."]
    if owner:
        bits.append(f"It lives in **{owner}**'s system.")
    if description:
        bits.append(description)
    if wired:
        bits.append(f"Wired to: {wired_text(', ')}.")
    if metrics:
        bits.append(f"Metrics: {metrics}.")
    if url:
        bits.append(f"Address: {url}")
    bits.append("Found by walking the live graph, with no static allowlist.")
    return " ".join(bits)


def graph_overview(state: dict | None, locale: str = "en") -> str:
    """What THIS map holds, by name — the answer when no node matched the question.

    Replaces a hardcoded product list that was only ever right on one deployment.
    """
    nodes = _nodes(state)
    if not nodes:
        return ""
    by_group: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        by_group.setdefault(str(node.get("group") or "other"), []).append(node)

    own_hub = next((n for n in nodes if str(n["id"]) == "hub"), None)
    lines: list[str] = []
    named = 0
    for group in _OVERVIEW_ORDER:
        members = by_group.get(group)
        if not members:
            continue
        labels = sorted({_label(n) for n in members})
        room = max(0, _MAX_OVERVIEW_NAMES - named)
        if room <= 0:
            lines.append(f"{group_name(group, locale)} — {len(labels)}")
            continue
        shown = labels[:room]
        named += len(shown)
        more = len(labels) - len(shown)
        text = ", ".join(shown) + (f" (+{more})" if more > 0 else "")
        lines.append(f"{group_name(group, locale)}: {text}")
    counted = len(nodes)
    body = "; ".join(lines)
    hub_label = _label(own_hub) if own_hub is not None else ""

    if locale == "ru":
        head = f"На этой карте {counted} {_ru_nodes_word(counted)}"
        head += f", центральный — **{hub_label}**. " if hub_label else ". "
        return head + body + ". Спросите про любой из них по имени — я найду его в живом графе."
    if locale == "es":
        head = f"Este mapa tiene {counted} nodos"
        head += f"; el central es **{hub_label}**. " if hub_label else ". "
        return head + body + ". Pregunta por cualquiera por su nombre."
    head = f"This map has {counted} nodes"
    head += f"; the one at the centre is **{hub_label}**. " if hub_label else ". "
    return head + body + ". Ask about any of them by name — I resolve it against the live graph."
