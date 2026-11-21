"""Normalización BP-Lite por registro (sin plantillas forced)."""

from __future__ import annotations

from typing import Any

from middleware.bp_models import BPGraph, BPNode, parse_bp_graph
from middleware.bp_normalize.classify import classify_node
from middleware.bp_normalize.dialect import coerce_model_dialect
from middleware.bp_normalize.enrich import enrich_graph
from middleware.bp_normalize.pins import as_pin_map, clean_pin_map, norm_node_id
from middleware.bp_normalize.prune import prune_graph_junk
from middleware.bp_normalize.registry import apply_normalizers
from middleware.bp_normalize.repair import repair_graph


def normalize_graph(
    data: dict[str, Any], *, user_prompt: str = ""
) -> dict[str, Any]:
    """
    Pipeline: dialecto → clasificar → normalizadores → prune → reparar → cableado.

    El prune va antes de reparar: así la basura del modelo (un Print que repite
    la velocidad del Launch) se descarta en vez de acabar cableada, y lo que
    sobrevive se reconecta.
    """
    data = coerce_model_dialect(dict(data))
    raw_nodes = data.get("nodes") or []
    staged: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_nodes, start=1):
        if not isinstance(raw, dict):
            continue
        if not raw.get("id") and not raw.get("type") and not raw.get("name"):
            continue
        nid = norm_node_id(raw.get("id"), idx)
        classified = classify_node(raw, graph_name=str(data.get("graph_name") or ""))
        staged.append(
            {
                "id": nid,
                "type": classified["type"],
                "name": classified["name"],
                "inputs": clean_pin_map(
                    as_pin_map(raw.get("inputs")), is_outputs=False
                ),
                "outputs": clean_pin_map(
                    as_pin_map(raw.get("outputs")), is_outputs=True
                ),
            }
        )
        # Preservar InString/Duration ya resueltos por dialecto
        inns = staged[-1]["inputs"]
        for k, v in (raw.get("inputs") or {}).items():
            if k not in inns and v not in (None, ""):
                inns[k] = v

    if not staged:
        raise ValueError("nodes vacío tras filtrar")

    staged = _dedupe_staged_nodes(staged)

    draft = {
        "graph_name": data.get("graph_name") or "Pygenesis_Graph",
        "nodes": staged,
    }
    graph = parse_bp_graph(draft)
    nodes = apply_normalizers(list(graph.nodes), graph_name=graph.graph_name)
    pruned = prune_graph_junk(
        BPGraph(graph_name=graph.graph_name, nodes=nodes), user_prompt=user_prompt
    )
    repaired = repair_graph(pruned, user_prompt=user_prompt)
    enriched = enrich_graph(repaired)
    return enriched.to_dict()


def _dedupe_staged_nodes(staged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Elimina ids duplicados (copia idéntica) o renombra el segundo choque."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    used = {str(n.get("id")) for n in staged if n.get("id")}

    def _free_id() -> str:
        k = 1
        while f"node_{k:02d}" in used or f"node_{k:02d}" in seen:
            k += 1
        nid = f"node_{k:02d}"
        used.add(nid)
        return nid

    for n in staged:
        nid = str(n.get("id") or "")
        if not nid:
            n = {**n, "id": _free_id()}
            out.append(n)
            seen.add(n["id"])
            continue
        if nid not in seen:
            seen.add(nid)
            out.append(n)
            continue
        # Mismo id otra vez: si es copia equivalente, descartar
        prev = next(x for x in out if x["id"] == nid)
        same = (
            prev.get("type") == n.get("type")
            and prev.get("name") == n.get("name")
            and prev.get("inputs") == n.get("inputs")
        )
        if same:
            continue
        n = {**n, "id": _free_id()}
        seen.add(n["id"])
        out.append(n)
    return out
