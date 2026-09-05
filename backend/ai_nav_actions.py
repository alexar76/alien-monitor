"""Detect map-navigation intents from AI chat questions."""

from __future__ import annotations

import re
from typing import Any

# Core nodes the monitor can focus — aliases cover the five base locales
# (en / ru / es / fr / zh) plus common transliterations.
NODE_ALIASES: dict[str, tuple[str, ...]] = {
    "skopos": (
        "skopos", "σκοπός", "скопос", "скopos", "skopós", "斯科波斯",
    ),
    "metis": (
        "metis", "μῆτις", "метис", "μητις", "métis", "墨提斯", "梅蒂斯",
    ),
    "dioscuri": (
        "dioscuri", "диоскур", "castor", "pollux", "mnemosyne",
        "dioscures", "dioskouroi", "狄奥斯库里", "狄奧斯庫里",
    ),
    "helios": (
        "helios", "гелиос", "helios agent", "hélios", "helíos",
        "赫利俄斯", "赫利奥斯",
    ),
    # RU short names ending in -я need accusative -ю too ("покажи гею").
    "gaia": (
        "gaia", "gaïa",
        "гайя", "гайю", "гея", "гею", "геи",
        "iot", "айот", "датчик", "сенсор", "sensor", "capteur", "传感器", "感測器",
        "盖亚", "蓋亞", "盖娅", "蓋婭",
    ),
    "atlas": (
        "atlas", "атлас", "атласа", "атласе",
        "sensor map", "карта датчик", "carte capteur", "mapa sensor",
        "атлас карта", "阿特拉斯",
    ),
    "theoros": (
        "theoros", "теорос", "the canon", "the-canon", "théoros", "特奥罗斯", "特奧羅斯",
    ),
    "argus": (
        "argus", "аргус", "argus-3", "argus3", "阿格斯",
    ),
    # "покажи агентов фабрики" must focus the roster, not the factory itself.
    "factory_agents": (
        "factory agents", "factory-agents", "агенты фабрики", "агентов фабрики",
        "агенты", "агентов", "агента фабрики", "shipped agents", "agent roster",
        "реестр агентов", "agentes de la fábrica", "agents de l'usine",
        "工厂代理", "工廠代理", "代理名册",
    ),
    "hub": (
        "hub", "хаб", "aimarket hub", "aimarket", "concentrateur", "中枢", "中樞", "枢纽",
    ),
    "factory": (
        "factory", "фабрик", "ai-factory", "ai factory", "usine", "fabrique",
        "工厂", "工廠", "人工智能工厂",
    ),
    "mesh": (
        "mesh", "service mesh", "меш", "ai service mesh", "maillage", "服务网格", "服務網格",
    ),
    "acex": ("acex",),
    "federation": (
        "federation", "федерац", "fédération", "federación", "联邦", "聯盟",
    ),
    "lottery": (
        "lottery", "лотере", "loterie", "lotería", "彩票", "抽奖",
    ),
    "plugins": (
        "plugins", "плагин", "greffons", "插件",
    ),
    "desktop_apps": (
        "desktop", "десктоп", "flutter apps", "bureau", "桌面",
    ),
    "platon": (
        "platon", "платон", "umbral", "platon", "柏拉图", "柏拉圖",
    ),
    "lumen": (
        "lumen", "люmen", "репутац", "réputation", "声誉", "聲譽",
    ),
    # MOMUS and Treasury were absent here, so "где момус?" matched nothing and the map never
    # focused — while the answer separately claimed the node did not exist. Two different gaps
    # producing one confusing experience.
    # WARDEN is the node with no host, and it was missing here for the same reason it was
    # missing from the graph: nothing about it has an address. "где варден?" has to move the
    # camera like every other name a viewer can say.
    "warden": (
        "warden", "варден", "вардена", "вардене", "вардену", "уорден",
        "mcp firewall", "mcp-файрвол", "файрвол", "firewall",
        "cortafuegos", "pare-feu", "防火墙", "aimarket/warden",
    ),
    "momus": (
        "momus", "μῶμος", "момус", "момос", "мом",
        # Multi-word Russian phrases need their cases spelled out: _alias_forms derives declensions
        # for a single trailing -а/-я, not for an adjective agreeing with its noun.
        "red team", "красная команда", "красную команду", "красной команды",
        "equipo rojo", "équipe rouge",
        "红队", "紅隊", "адверсар", "adversarial audit", "auditoría adversaria",
    ),
    # LOGOS repeated the MOMUS gap exactly: "где логос?" matched nothing, the map never
    # focused, and the answer separately claimed the component did not exist — so the user
    # was told twice, in two different ways, that a deployed node was not there.
    "logos": (
        "logos", "логос", "логоса", "логосе", "логосу", "лог0с",
        "analytics engine", "аналитический движок", "аналитика федерации",
        "motor de analítica", "moteur d'analytique", "moteur analytique",
        "联邦分析", "分析引擎", "аномал", "anomaly detection",
        "detección de anomalías", "détection d'anomalies",
    ),
    "treasury": (
        "treasury", "трезури", "трежери", "казна", "казну", "казны", "казне",
        "tesorería", "tesoreria", "trésorerie", "tresorerie", "金库", "金庫", "資金庫",
        "bounty", "вознагражден", "recompensa", "prime", "赏金", "賞金",
    ),
    # The third paid invoke channel. Two Russian words are in real use for it — the loanword
    # "бридж" and the native "мост" — and both need their cases spelled out: _alias_forms only
    # derives declensions for a single trailing -а/-я, so masculine plurals ("мосты", "мостов")
    # and the loanword's plural ("бриджи") are not reachable from the nominative stem. The
    # framework names are aliases too, because "langchain tools" is how a viewer who does not
    # know the product name will ask for it.
    "bridges": (
        "bridges", "aimarket-bridges", "aimarket bridges", "bridge",
        "бридж", "бриджи", "бриджей", "бриджах", "бриджами",
        "мост", "мосты", "мостов", "мосту", "мостам", "мостами",
        "puente", "puentes", "pont", "ponts", "桥", "橋", "桥接", "橋接",
        "langchain", "langgraph", "crewai", "autogen",
    ),
    "hephaestus": (
        "hephaestus", "hephaistos", "forge", "studio", "the forge", "graph builder",
        "pipeline builder", "blueprint", "cost estimate", "bill of materials", "bom",
        "гефест", "гефеста", "кузница", "кузницу", "кузнице", "студия", "студию",
        "конструктор", "конструктор графов", "смета", "смету", "смета графа",
        "цепочка возможностей", "спецификация счёта",
        "fragua", "estudio", "presupuesto", "forja",
        "forge visuelle", "atelier", "devis",
        "锻造", "工坊", "图形编排", "成本预估",
    ),
    "themis": (
        "themis", "supply-chain-auditor", "supply chain auditor",
        "THEMIS", "admission gate", "admission", "sca auditor",
        "темис", "темида", "допуск", "шлюз допуска", "допуск публикации",
        "аудитор цепочки поставок", "аудит цепочки поставок", "контур допуска",
        "аудитор агентов", "проверка агента",
        "auditor de cadena de suministro", "puerta de admisión", "admisión",
        "auditeur de chaîne d’approvisionnement", "contrôle d’admission", "admission",
        "供应链审计器", "智能体供应链", "准入门", "发布准入",
    ),
    # The touchstone. "камень" and "пробирный камень" are how a Russian speaker asks
    # for it by meaning rather than by name, and both need their cases spelled out:
    # _alias_forms only derives declensions for a single trailing -а/-я, so a masculine
    # noun with an agreeing adjective is unreachable from the nominative stem.
    "basanos": (
        "basanos", "βάσανος", "basanos.modelmarket.dev",
        "touchstone", "assurance pack", "contract assurance", "solidity audit",
        "lydian", "lydian touchstone",
        "базанос", "басанос", "базаноса", "базаносе",
        "пробирный камень", "пробирного камня", "пробирном камне",
        "камень", "камня", "камне",
        "аудит контрактов", "аудит солидити", "проверка контрактов",
        "пакет гарантий", "assurance-пакет",
        "piedra de toque", "auditoría de contratos", "paquete de garantía",
        "pierre de touche", "audit de contrats", "pack d'assurance",
        "试金石", "合约审计", "保证包", "吕底亚试金石",
    ),
}

# Five base locales: en / ru / es / fr / zh (stems — substring match).
NAV_VERBS = (
    # en
    "show", "open", "find", "zoom", "focus", "fly", "navigate", "go to", "take me",
    "center", "highlight", "select", "display", "bring",
    # ru
    # "сфокус" alone matches "сфокусируйся" but NOT "фокус на X" — the plainest way
    # a Russian speaker asks for exactly this action.
    "покаж", "найди", "открой", "перейди", "сфокус", "фокус", "центр", "выведи",
    # es
    "muéstr", "muestr", "encuentr", "abre", "naveg", "enfoc", "centr",
    # fr
    "montre", "montr", "ouvre", "trouv", "navigu", "affich", "amène", "amene",
    "sélectionn", "selectionn", "survole", "vole vers", "emmène", "emmene",
    # zh (simplified + common traditional)
    "显示", "顯示", "打开", "打開", "找到", "飞到", "飛到", "聚焦", "导航", "導航",
    "带我", "帶我", "看看", "定位",
)

# "where is X" markers — paired with a node match (no verb required).
WHERE_MARKERS = (
    "where", "где",
    "dónde", "donde",
    "où",
    "哪里", "哪兒", "哪儿", "在哪", "何处", "何處",
)

CORE_GRAPH_NODES = frozenset(NODE_ALIASES.keys()) | {
    "ethereum", "solana", "evm_escrow", "solana_escrow", "nft_contract",
    "sdk_dart", "sdk_typescript", "sdk_rust", "cli", "widget",
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


_CYRILLIC_TO_LATIN = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
})


def _latinize(text: str) -> str:
    """Comparable form for a Cyrillic spelling of a newly discovered Latin label."""
    return _normalize(text).translate(_CYRILLIC_TO_LATIN)


def _alias_forms(alias: str) -> tuple[str, ...]:
    """Expand short RU aliases with common case endings.

    Substring match works for stems ("метис" ⊂ "метиса"), but names ending in
    -я/-а change the final letter in accusative ("гея" → "гею"), so nominative
    is not a prefix. Keep this tiny — no full morphology.
    """
    forms = [alias]
    if len(alias) < 3:
        return tuple(forms)
    last = alias[-1]
    stem = alias[:-1]
    if last == "я":
        forms.extend((stem + "ю", stem + "и", stem + "ей", stem + "ею"))
    elif last == "а" and not alias.isascii():
        forms.extend((stem + "у", stem + "ы", stem + "е"))
    return tuple(dict.fromkeys(forms))


def _match_node(question: str, state: dict | None = None) -> str | None:
    """Resolve a node id from the question.

    Prefer static NODE_ALIASES (multilingual nicknames), then fall back to any
    live graph node id/label so newly seeded spheres (competing lab galaxy,
    hub-discovered peers, factory products) are focusable without editing
    aliases by hand.
    """
    q = _normalize(question)
    best: tuple[int, str] | None = None
    for node_id, aliases in NODE_ALIASES.items():
        for alias in aliases:
            for form in _alias_forms(alias):
                if form in q:
                    score = len(form)
                    if best is None or score > best[0]:
                        best = (score, node_id)
                    break
    live = _match_live_node(q, state)
    if live is not None:
        live_score, live_id = live
        if best is None or live_score > best[0]:
            best = (live_score, live_id)
    return best[1] if best else None


def _match_live_node(q: str, state: dict | None) -> tuple[int, str] | None:
    """Longest substring match against live node ids and labels."""
    if not state:
        return None
    q_latin = _latinize(q)
    best: tuple[int, str] | None = None
    for n in state.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        if not nid:
            continue
        candidates = [nid, nid.replace("_", " "), nid.replace("-", " ")]
        label = str(n.get("label") or "").strip()
        if label:
            candidates.append(label)
            # Drop decorative separators so "Competing Lab Hub" still matches
            # questions that omit the middle word.
            candidates.append(re.sub(r"[·•|/]+", " ", label))
        for raw in candidates:
            form = _normalize(raw)
            if len(form) < 3:
                continue
            if form in q or form in q_latin:
                score = len(form)
                # Prefer exact id hits slightly over longer but fuzzy labels when
                # equal length; otherwise longest wins (same as aliases).
                if best is None or score > best[0]:
                    best = (score, nid)
    return best


def match_live_node_id(question: str, state: dict | None = None) -> str | None:
    """Public data-driven resolver used by both map actions and offline answers."""
    match = _match_live_node(_normalize(question), state)
    return match[1] if match else None


def _has_nav_intent(question: str, state: dict | None = None) -> bool:
    q = _normalize(question)
    if any(v in q for v in NAV_VERBS):
        return True
    # "where is skopos" / "где skopos" / "où est gaia" / "盖亚在哪里"
    if any(m in q for m in WHERE_MARKERS) and _match_node(q, state):
        return True
    return False


def resolve_nav_actions(question: str, state: dict | None = None) -> list[dict[str, Any]]:
    """Return client actions (e.g. focus_node) when the user asks to show a map node.

    Matching is dual-source: curated NODE_ALIASES plus every node currently in
    ``state["nodes"]``. That second path is what makes a newly deployed galaxy
    (or any discovered peer) focusable the moment it appears on the graph —
    no alias PR required.
    """
    node_id = _match_node(question, state)
    if not node_id or not _has_nav_intent(question, state):
        return []

    if state:
        ids = {n.get("id") for n in (state.get("nodes") or []) if isinstance(n, dict)}
        if ids and node_id not in ids and node_id not in CORE_GRAPH_NODES:
            return []

    focus_id = node_id
    if node_id == "theoros":
        focus_id = "dioscuri"

    return [{"type": "focus_node", "node_id": focus_id, "requested_id": node_id}]


def nav_focus_label(node_id: str, locale: str = "en") -> str:
    # Product names stay Latin across the five base locales.
    labels = {
        "skopos": "SKOPOS",
        "metis": "METIS",
        "dioscuri": "DIOSCURI",
        "helios": "HELIOS",
        "gaia": "GAIA",
        "atlas": "ATLAS",
        "momus": "MOMUS",
        "warden": "WARDEN",
        "treasury": "Treasury",
        "logos": "LOGOS",
        "bridges": "Bridges",
        "hephaestus": "HEPHAESTUS",
        "themis": "THEMIS",
        "basanos": "BASANOS",
        "theoros": "THEOROS",
        "argus": "ARGUS",
        "factory_agents": "Agents",
        "hub": "AIMarket Hub",
        "factory": "AI-Factory",
        "competing_hub": "Competing Lab Hub",
        "signal_hunt_hub": "Signal Hunt Hub",
        "signal_hunt": "Signal Hunt",
        "use_cases": "Use Cases Portal",
    }
    return labels.get(node_id, node_id.upper())


def append_nav_hint(answer: str, actions: list[dict[str, Any]], locale: str) -> str:
    if not actions or not answer:
        return answer
    focus = next((a for a in actions if a.get("type") == "focus_node"), None)
    if not focus:
        return answer
    node_id = str(focus.get("node_id") or "")
    if not node_id:
        return answer
    label = nav_focus_label(node_id, locale)
    lower = answer.lower()
    if node_id in lower or label.lower() in lower:
        return answer
    hints = {
        "ru": f"\n\nОткрываю **{label}** на 3D-карте — камера переместится к узлу, панель с деталями развернётся.",
        "es": f"\n\nAbriendo **{label}** en el mapa 3D — la cámara se centra y el panel de detalles se despliega.",
        "fr": f"\n\nJ’ouvre **{label}** sur la carte 3D — la caméra se centre et le panneau de détails s’ouvre.",
        "zh": f"\n\n正在 3D 地图上打开 **{label}** — 镜头将飞向该节点并展开详情面板。",
        "en": f"\n\nOpening **{label}** on the 3D map — flying the camera there and expanding the detail panel.",
    }
    return answer + hints.get(locale, hints["en"])
