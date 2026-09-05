"""
Alien Monitor AI — multi-provider LLM + live ecosystem state in the prompt.
Uses the same provider ids / YAML shape as aicom (data/config/model_providers.yaml).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import yaml

_MONITOR_ROOT = Path(__file__).resolve().parent.parent
_AICOM_ROOT = _MONITOR_ROOT.parent

DEFAULT_PROVIDER = "deepseek_api"
DEFAULT_MODEL_HEAVY = "deepseek-v4-pro"
DEFAULT_MODEL_LIGHT = "deepseek-v4-flash"

LOCALE_INSTRUCTIONS: dict[str, str] = {
    "en": "Reply in English.",
    "ru": "Отвечай на русском языке.",
    "es": "Responde en español.",
}

LOCALE_NAMES: dict[str, str] = {
    "en": "English",
    "ru": "Russian",
    "es": "Spanish",
}

EMPTY_QUESTION: dict[str, str] = {
    "en": "Please ask a question about the AIMarket ecosystem.",
    "ru": "Задайте вопрос об экосистеме AIMarket.",
    "es": "Haz una pregunta sobre el ecosistema AIMarket.",
}

_config_cache: dict[str, Any] | None = None


def normalize_locale(raw: str) -> str:
    code = (raw or "en").strip().lower()[:2]
    return code if code in LOCALE_INSTRUCTIONS else "en"


def detect_question_locale(question: str) -> str | None:
    """Guess language from user text (Latin / Cyrillic / Spanish markers)."""
    text = (question or "").strip()
    if not text:
        return None
    cyrillic = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    latin = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    lower = text.lower()
    spanish_markers = sum(1 for c in lower if c in "áéíóúñü¿¡")
    spanish_words = ("qué", "cómo", "cuál", "dónde", "por qué", "cuánto", "cuáles")
    if cyrillic >= 2 and cyrillic >= latin:
        return "ru"
    if spanish_markers >= 1 or any(w in lower for w in spanish_words):
        return "es"
    if latin >= 2:
        return "en"
    return None


def resolve_response_locale(question: str, ui_locale: str) -> str:
    """Prefer the question language; fall back to the UI locale."""
    ui = normalize_locale(ui_locale)
    detected = detect_question_locale(question)
    return detected or ui


def _config_paths() -> list[Path]:
    custom = os.getenv("ALIEN_LLM_CONFIG", "").strip()
    if custom:
        return [Path(custom)]
    return [
        _AICOM_ROOT / "data" / "config" / "model_providers.yaml",
        _MONITOR_ROOT / "config" / "model_providers.yaml",
        _MONITOR_ROOT / "config" / "model_providers.example.yaml",
    ]


def load_providers_config() -> dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    for path in _config_paths():
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                _config_cache = yaml.safe_load(f) or {}
            return _config_cache

    _config_cache = {
        "default_provider": DEFAULT_PROVIDER,
        "providers": {
            DEFAULT_PROVIDER: {
                "api_key_env": "DEEPSEEK_API_KEY",
                "base_url": "https://api.deepseek.com/v1",
                "enabled": True,
                "models": {"heavy": DEFAULT_MODEL_HEAVY, "light": DEFAULT_MODEL_LIGHT},
                "provider_type": "openai_compatible",
            },
        },
    }
    return _config_cache


def _resolve_api_key(pconf: dict) -> str:
    if pconf.get("api_key"):
        return str(pconf["api_key"])
    env_name = pconf.get("api_key_env")
    if env_name:
        return os.environ.get(str(env_name), "")
    return ""



def resolve_default_provider() -> str:
    """Which provider actually answers, not which one the file names.

    The shipped config names `deepseek_api`, and a deployment without
    `DEEPSEEK_API_KEY` then answered every question with "empty answer" — a
    configured default that cannot be called is not a default. Order:

      1. ``ALIEN_AI_PROVIDER`` — the operator pinning one on purpose.
      2. the config's ``default_provider``, IF its key resolves.
      3. the first provider that is actually available.
    """
    cfg = load_providers_config()
    providers = cfg.get("providers") or {}

    pinned = os.getenv("ALIEN_AI_PROVIDER", "").strip()
    if pinned and isinstance(providers.get(pinned), dict):
        return pinned

    named = cfg.get("default_provider") or DEFAULT_PROVIDER
    pconf = providers.get(named)
    if isinstance(pconf, dict) and _resolve_api_key(pconf):
        return named

    for candidate in list_providers()["providers"]:
        if candidate.get("available"):
            return str(candidate["id"])
    return named


def list_providers() -> dict[str, Any]:
    """Providers available for the monitor AI (enabled + has API key or local)."""
    cfg = load_providers_config()
    default = cfg.get("default_provider") or DEFAULT_PROVIDER
    pinned = os.getenv("ALIEN_AI_PROVIDER", "").strip()
    if pinned and isinstance((cfg.get("providers") or {}).get(pinned), dict):
        default = pinned
    out: list[dict[str, Any]] = []

    for name, pconf in (cfg.get("providers") or {}).items():
        if not isinstance(pconf, dict):
            continue
        if pconf.get("enabled") is False:
            continue
        ptype = pconf.get("provider_type", "openai_compatible")
        if ptype == "local_ollama":
            # Ollama uses native API — skip for monitor chat unless wired later
            continue
        api_key = _resolve_api_key(pconf)
        if ptype != "openai_compatible" and ptype != "anthropic" and not api_key:
            continue
        if ptype == "openai_compatible" and pconf.get("api_key_env") and not api_key:
            # key missing in env — still list but mark unavailable
            available = False
        else:
            available = bool(api_key) or pconf.get("api_key_env") is None

        models = pconf.get("models") or {}
        out.append({
            "id": name,
            "provider_type": ptype,
            "base_url": pconf.get("base_url", ""),
            "models": {
                "heavy": models.get("heavy", DEFAULT_MODEL_HEAVY),
                "light": models.get("light", DEFAULT_MODEL_LIGHT),
            },
            "available": available,
            "is_default": name == default,
        })

    out.sort(key=lambda x: (not x["is_default"], x["id"]))
    return {
        "default_provider": default,
        "default_model": DEFAULT_MODEL_HEAVY,
        "providers": out,
    }


def build_live_context(state: dict | None, mode: str, selected_node_id: str | None = None) -> str:
    """Compact JSON snapshot for the system prompt — tick, summary, nodes, recent activity."""
    if not state:
        return json.dumps(
            {"monitor_mode": mode, "note": "No live state snapshot yet — answers use static ecosystem knowledge only."},
            ensure_ascii=False,
        )

    summary = state.get("summary") or {}
    nodes_in = state.get("nodes") or []
    priority_ids: tuple[str, ...] = (
        "hub", "factory", "factory_agents", "mesh", "bridges", "themis",
        "hephaestus", "basanos",
        "skopos", "metis", "dioscuri",
        "helios", "argus",
        "momus", "treasury", "logos", "gaia", "atlas", "theoros", "platon", "lumen",
        "acex", "federation", "lottery", "plugins", "desktop_apps",
        # Competing lab galaxy — keep these ahead of the product flood so the assistant
        # always "sees" the second Hub when answering about federation / hunt / use-cases.
        "competing_hub", "signal_hunt_hub", "signal_hunt", "use_cases",
    )
    # Nodes tagged galaxy=* jump the queue automatically — future lab peers need no edit.
    extra_galaxy = tuple(
        str(n["id"])
        for n in nodes_in
        if isinstance(n, dict) and n.get("galaxy") and n.get("id")
        and str(n["id"]) not in priority_ids
    )
    priority_ids = priority_ids + extra_galaxy
    seen: set[str] = set()
    ordered: list[dict] = []
    by_id = {n.get("id"): n for n in nodes_in if isinstance(n, dict) and n.get("id")}
    for pid in priority_ids:
        if pid in by_id:
            ordered.append(by_id[pid])
            seen.add(pid)
    for n in nodes_in:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        if nid and nid not in seen:
            ordered.append(n)
            seen.add(nid)
    # The cap used to silently drop everything past the 48th node, and the priority list did not
    # include the newest satellites — so the assistant answered that MOMUS "is not in the ecosystem"
    # when it simply could not see it. A truncated list that does not say it is truncated turns
    # "I cannot see it" into "it does not exist", which is the one thing an assistant must never do.
    # The cap stays (a prompt has a budget) but the omission is now stated in the payload below.
    # A universe run seeds ~50 core entities and materialises up to
    # ALIEN_MAX_PRODUCT_ENTITIES (400 by default) products on top, so a 64-node
    # window showed the assistant a seventh of the map and it answered as if the
    # rest were not there. Measured cost of carrying the whole map instead: about
    # 130 characters per node, so 1000 nodes is ~130 KB of live context — inside
    # the window of the models this talks to, and more than double what the
    # universe can currently create (50 core + 400 products). Lower it via env
    # only for a genuinely small-context model.
    NODE_BUDGET = max(64, int(os.environ.get("ALIEN_AI_NODE_BUDGET", "1000")))
    omitted = max(0, len(ordered) - NODE_BUDGET)
    nodes_out = []
    for n in ordered[:NODE_BUDGET]:
        if not isinstance(n, dict):
            continue
        entry: dict[str, Any] = {
            "id": n.get("id"),
            "label": n.get("label"),
            "group": n.get("group"),
            "status": n.get("status"),
            "metrics": n.get("metrics") or {},
        }
        if n.get("galaxy"):
            entry["galaxy"] = n.get("galaxy")
        if n.get("url"):
            entry["url"] = n.get("url")
        if n.get("description") and (
            (selected_node_id and n.get("id") == selected_node_id) or n.get("galaxy")
        ):
            entry["description"] = n.get("description")
        if selected_node_id and n.get("id") == selected_node_id:
            entry["selected"] = True
            if n.get("description"):
                entry["description"] = n.get("description")
            if n.get("children"):
                entry["children"] = n.get("children")
        nodes_out.append(entry)

    events = (state.get("events") or [])[-8:]
    transactions = (state.get("transactions") or [])[-8:]
    channels = (state.get("channels") or [])[-5:]

    galaxies: dict[str, list[str]] = {}
    for n in ordered:
        g = n.get("galaxy")
        nid = n.get("id")
        if g and nid:
            galaxies.setdefault(str(g), []).append(str(nid))

    payload: dict[str, Any] = {
        "monitor_mode": mode,
        "tick": state.get("tick", summary.get("tick")),
        "ts": state.get("ts"),
        "summary": summary,
        "scenario": state.get("scenario"),
        "nodes": nodes_out,
        # Stated explicitly so the model can say "I can see 64 of 71 nodes" instead of denying that
        # the missing one exists.
        "nodes_total": len(ordered),
        "nodes_omitted": omitted,
        # Auto catalog of secondary galaxies (competing lab, …) — no prompt edit required.
        "galaxies": galaxies,
        "recent_events": events,
        "recent_transactions": transactions,
        "open_channels_sample": channels,
        "funding_events_recent": (state.get("funding_events") or [])[-3:],
    }
    if selected_node_id:
        payload["selected_node_id"] = selected_node_id

    return json.dumps(payload, ensure_ascii=False, default=str)


def build_system_prompt(
    ecosystem_context: str,
    locale: str,
    live_context: str,
) -> str:
    lang = LOCALE_NAMES.get(locale, "English")
    locale_rule = LOCALE_INSTRUCTIONS.get(locale, LOCALE_INSTRUCTIONS["en"])
    return (
        ecosystem_context
        + "\n\n## LIVE MONITOR SNAPSHOT (authoritative for current tick/metrics)\n"
        + "Use these values when the user asks about «now», current mode, metrics, nodes, or activity.\n"
        + live_context
        + "\n\n## SECONDARY GALAXIES (mandatory when present)\n"
        + "If the LIVE snapshot includes `galaxies` (e.g. `competing`), treat those nodes as a "
          "real second Hub galaxy — far from the primary cloud. When the user asks about the "
          "competing lab, Signal Hunt, use-cases portal, or «вторая галактика», answer from "
          "those nodes' labels/urls/descriptions and invite them to «show / покажи» the node "
          "so the map focuses. Never claim they are absent if they appear under `galaxies` "
          "or in `nodes`.\n"
        + "\n\n## THE SNAPSHOT IS A WINDOW, NOT THE WORLD (mandatory)\n"
        + "`nodes` is capped: `nodes_total` is how many exist and `nodes_omitted` is how many "
          "were left out of this prompt. NEVER answer that a component does not exist, is not "
          "registered, or is not part of the ecosystem merely because it is absent from `nodes`. "
          "If you cannot find something the user names, say you cannot see it in this snapshot "
          "and that omitted nodes exist — then answer from the COMPONENT REGISTRY above, which "
          "lists every satellite. Denying the existence of a component that is deployed and "
          "documented is the single worst answer you can give: it reads as authoritative and is "
          "simply false.\n"
        + "\n\n## RESPONSE LANGUAGE (mandatory)\n"
        + f"Write your entire answer in {lang} only. {locale_rule} "
        + "Do not switch languages mid-answer.\n"
        + "When citing numbers, prefer the LIVE MONITOR SNAPSHOT. "
        + "If monitor_mode is test, note that metrics are simulated."
    )


async def generate_answer(
    *,
    question: str,
    locale: str,
    system_prompt: str,
    provider_id: str | None = None,
    model_role: str = "heavy",
) -> tuple[str, dict[str, Any]]:
    """
    Call configured LLM provider. Returns (answer_text, meta).
    """
    cfg = load_providers_config()
    providers = cfg.get("providers") or {}
    pid = provider_id or resolve_default_provider()
    pconf = providers.get(pid)
    if not isinstance(pconf, dict):
        pid = resolve_default_provider()
        pconf = providers.get(pid) or {}
    if not _resolve_api_key(pconf) and pconf.get("api_key_env"):
        # The caller asked for a provider this deployment cannot reach. Answering with
        # somebody that can beats answering with nothing.
        fallback = resolve_default_provider()
        if fallback != pid and isinstance(providers.get(fallback), dict):
            pid, pconf = fallback, providers[fallback]

    role = model_role if model_role in ("heavy", "light") else "heavy"
    models = pconf.get("models") or {}
    model = models.get(role) or models.get("heavy") or DEFAULT_MODEL_HEAVY
    api_key = _resolve_api_key(pconf)
    ptype = pconf.get("provider_type", "openai_compatible")
    base_url = (pconf.get("base_url") or "https://api.deepseek.com/v1").rstrip("/")
    max_tokens = int((pconf.get("capabilities") or {}).get("max_tokens") or 1024)
    max_tokens = min(max_tokens, 4096)

    meta = {"provider": pid, "model": model, "model_role": role}

    if ptype == "anthropic":
        if not api_key:
            raise RuntimeError(f"Provider {pid}: missing API key")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{base_url}/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": question}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            blocks = data.get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            return text.strip(), meta

    # openai_compatible (DeepSeek, Groq, Together, LM Studio, …)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "max_tokens": max_tokens,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        return text.strip(), meta


def any_provider_configured() -> bool:
    listed = list_providers()["providers"]
    return any(p.get("available") for p in listed)
