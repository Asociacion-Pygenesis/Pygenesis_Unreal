"""Nombres de asset BP-Lite derivados del prompt / nodos (evita todo = BP-Lite)."""

from __future__ import annotations

import re
from typing import Any

_GENERIC = {
    "bp-lite",
    "bp_lite",
    "bplite",
    "bp",
    "pygenesis_graph",
    "pygenesis",
    "graph",
    "blueprint",
    "unreal_imported_graph",
    "node",
}


def _slug(s: str, *, max_len: int = 48) -> str:
    s = re.sub(r"[^\w\-]+", "_", (s or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    return (s or "BP_Graph")[:max_len]


def is_generic_graph_name(name: str) -> bool:
    n = (name or "").strip().lower().replace(" ", "").replace("-", "_")
    return not n or n in _GENERIC or n.startswith("bp_lite") or n == "bp_lite_beginplay"


def infer_graph_name(
    *,
    user_prompt: str = "",
    graph: dict[str, Any] | None = None,
    fallback: str = "BP_Graph",
) -> str:
    """Nombre corto y único a partir de la cadena de nodos o del prompt."""
    nodes = (graph or {}).get("nodes") or []
    names = [str(n.get("name") or "") for n in nodes]
    types = [str(n.get("type") or "") for n in nodes]
    blob = " ".join(names + types).lower().replace(" ", "")

    intent = (user_prompt or "").lower()

    # Cadenas conocidas
    prints = [
        (n.get("inputs") or {}).get("InString")
        for n in nodes
        if str(n.get("name", "")).replace(" ", "").lower() == "printstring"
    ]
    prints = [p for p in prints if isinstance(p, str) and p.strip()]

    if "launchcharacter" in blob or "launchcharacter" in intent.replace(" ", ""):
        return "JumpOnSpace"
    if "addmovementinput" in blob:
        key = next(
            (
                str(n.get("name"))
                for n in nodes
                if str(n.get("type", "")).lower() == "inputkey"
            ),
            "Move",
        )
        return _slug(f"MoveOn{key}")
    if "branch" in blob:
        return "BranchBeginPlay"
    if "destroyactor" in blob:
        return "BeginPlayDestroy"
    if len(prints) >= 2 and any("delay" in str(n.get("name", "")).lower() for n in nodes):
        a, b = _slug(prints[0], max_len=12), _slug(prints[1], max_len=12)
        return _slug(f"BP_{a}_{b}")
    if any("delay" in str(n.get("name", "")).lower() for n in nodes) and prints:
        return _slug(f"BP_Delay_{prints[0]}")
    if prints:
        key = next(
            (
                str(n.get("name"))
                for n in nodes
                if str(n.get("type", "")).lower() == "inputkey"
            ),
            "",
        )
        if key:
            return _slug(f"BP_{key}_{prints[0]}")
        return _slug(f"BP_{prints[0]}")
    if any("beginplay" in str(n.get("name", "")).lower() for n in nodes):
        return "BP_BeginPlay"

    # Desde prompt: primeras palabras útiles
    m = re.search(
        r"(?:blueprint|crea|crear|monta)[:\s]+(.+)$",
        user_prompt or "",
        re.I | re.S,
    )
    bit = (m.group(1) if m else user_prompt or "")[:60]
    bit = re.sub(r"[→\->]+", "_", bit)
    bit = re.sub(r'["\']', "", bit)
    slug = _slug(bit, max_len=40)
    if slug.lower() in _GENERIC or len(slug) < 3:
        return fallback
    if not slug.upper().startswith("BP"):
        slug = f"BP_{slug}"
    return slug


def ensure_distinct_graph_name(
    graph: dict[str, Any],
    *,
    user_prompt: str = "",
) -> dict[str, Any]:
    """Si graph_name es genérico (BP-Lite), sustituye por uno descriptivo."""
    current = str(graph.get("graph_name") or "")
    if not is_generic_graph_name(current):
        # Aun así sanitizar
        graph = {**graph, "graph_name": _slug(current)}
        return graph
    inferred = infer_graph_name(user_prompt=user_prompt, graph=graph)
    return {**graph, "graph_name": inferred}
