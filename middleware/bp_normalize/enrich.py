"""Cableado solo de nodos huérfanos — no reescribe cables del modelo."""

from __future__ import annotations

from middleware.bp_models import BPGraph, BPNode
from middleware.bp_normalize.pins import _PIN_REF_RE, clean_pin_map


def _node_ids(nodes: list[BPNode]) -> set[str]:
    return {n.id for n in nodes}


def _has_useful_exec_in(n: BPNode, known: set[str]) -> bool:
    inns = n.inputs or {}
    for k, v in inns.items():
        kl = str(k).lower().replace(" ", "")
        if kl not in {"exec_in", "execute", "exec"} and "exec" not in kl:
            # también aceptar refs en cualquier input si apunta a id del grafo
            if isinstance(v, str) and _PIN_REF_RE.match(v):
                src = v.split(".", 1)[0]
                if src in known and src != n.id:
                    return True
            continue
        if isinstance(v, str) and v.strip():
            src = v.split(".", 1)[0] if "." in v else v
            if src == n.id:
                # Autorreferencia del modelo: no es cable, es ruido
                continue
            if src in known or _PIN_REF_RE.match(v):
                return True
    return False


def _has_useful_exec_out(n: BPNode, known: set[str]) -> bool:
    outs = n.outputs or {}
    if not outs:
        return False
    for v in outs.values():
        if not isinstance(v, str) or not v.strip():
            continue
        dst = v.split(".", 1)[0]
        if dst == n.id:
            continue
        if _PIN_REF_RE.match(v):
            if dst in known:
                return True
        elif dst in known:
            return True
    return False


def _is_entry(n: BPNode) -> bool:
    t = n.type.lower()
    blob = f"{t}{n.name}".lower().replace(" ", "")
    return (
        t == "inputkey"
        or "inputaction" in blob
        or t == "event"
        or "beginplay" in blob
        or "customevent" in blob
    )


def _is_orphan(n: BPNode, known: set[str]) -> bool:
    """Sin exec_in útil ni outputs con refs a ids del grafo."""
    if _is_entry(n):
        # Entry sin salida cableada cuenta como huérfano de cableado
        return not _has_useful_exec_out(n, known)
    has_in = _has_useful_exec_in(n, known)
    has_out = _has_useful_exec_out(n, known)
    return not has_in and not has_out


def _out_pin_for(n: BPNode) -> str:
    t = n.type.lower()
    blob = f"{t}{n.name}".lower().replace(" ", "")
    if t == "inputkey" or "inputkey" in blob:
        return "Pressed"
    if t == "branch" or "branch" in blob:
        return "then"
    return "exec_out"


def enrich_graph(graph: BPGraph) -> BPGraph:
    """
    Si un nodo ya tiene exec_in / outputs con refs a ids del grafo → no tocar.
    Auto-cable solo cadenas de huérfanos (orden de aparición).
    """
    nodes = list(graph.nodes)
    known = _node_ids(nodes)

    # Limpiar basura de outputs sin pisar pines válidos del modelo
    cleaned: list[BPNode] = []
    for n in nodes:
        outs = clean_pin_map(dict(n.outputs or {}), is_outputs=True)
        inns = dict(n.inputs or {})
        cleaned.append(n.model_copy(update={"inputs": inns, "outputs": outs}))
    nodes = cleaned
    known = _node_ids(nodes)

    # Si TODOS los no-entry ya tienen cables útiles, no reordenar
    non_entries = [n for n in nodes if not _is_entry(n)]
    if non_entries and all(
        _has_useful_exec_in(n, known) or _has_useful_exec_out(n, known)
        for n in non_entries
    ):
        # Entries con salida ya cableada: dejar tal cual
        return BPGraph(graph_name=graph.graph_name, nodes=nodes)

    orphans = [n for n in nodes if _is_orphan(n, known)]
    if len(orphans) < 2:
        return BPGraph(graph_name=graph.graph_name, nodes=nodes)

    # Cadena lineal solo entre huérfanos consecutivos en el orden original
    by_id = {n.id: n for n in nodes}
    orphan_ids = [n.id for n in orphans]

    for i in range(len(orphan_ids) - 1):
        src_id, dst_id = orphan_ids[i], orphan_ids[i + 1]
        src, dst = by_id[src_id], by_id[dst_id]
        # No tocar si ya no son huérfanos tras cables previos
        if not _is_orphan(src, known) and not _is_orphan(dst, known):
            continue
        src_blob = f"{src.type}{src.name}".lower().replace(" ", "")
        dst_blob = f"{dst.type}{dst.name}".lower().replace(" ", "")
        if "addmovementinput" in src_blob and "addmovementinput" in dst_blob:
            continue
        pin = _out_pin_for(src)
        src_outs = dict(src.outputs or {})
        # No sobrescribir si ya hay clave de exec válida
        if any(
            str(k).lower().replace(" ", "")
            in {"pressed", "released", "exec_out", "execout", "then", "else", "completed"}
            and isinstance(v, str)
            and v.strip()
            for k, v in src_outs.items()
        ):
            continue
        dst_inns = dict(dst.inputs or {})
        if dst_inns.get("exec_in"):
            continue
        src_outs[pin] = f"{dst.id}.exec_in"
        dst_inns["exec_in"] = f"{src.id}.{pin}"
        src = src.model_copy(update={"outputs": src_outs})
        dst = dst.model_copy(update={"inputs": dst_inns})
        by_id[src_id] = src
        by_id[dst_id] = dst

    nodes = [by_id[n.id] for n in nodes]
    return BPGraph(graph_name=graph.graph_name, nodes=nodes)
