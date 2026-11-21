"""Reparación de cableado que el modelo deja a medias.

El modelo acierta los nodos y falla los enlaces: salta ids (node_03 → node_05),
nombra las ramas del Branch a su manera (TrueNodeID) y deja el último nodo
suelto. Antes esos nodos se perdían en el prune; aquí se reconectan.
"""

from __future__ import annotations

import re
from typing import Any

from middleware.bp_models import BPGraph, BPNode
from middleware.bp_normalize.identity import node_blob as _blob

_EXEC_OUT_KEYS = {
    "pressed",
    "released",
    "exec_out",
    "execout",
    "then",
    "else",
    "completed",
}

_TRUE_PIN_RE = re.compile(r"^(?:true|then|truenodeid|true_id|trueid|on_?true)$", re.I)
_FALSE_PIN_RE = re.compile(r"^(?:false|else|falsenodeid|false_id|falseid|on_?false)$", re.I)

_PROMPT_SECONDS_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:s\b|seg\b|segs\b|segundos?\b|sec\b|secs\b|seconds?\b)",
    re.IGNORECASE,
)


def _is_entry(n: BPNode) -> bool:
    t = n.type.lower()
    b = _blob(n)
    return t in {"inputkey", "event"} or "inputaction" in b or "beginplay" in b


def _is_branch(n: BPNode) -> bool:
    return n.type.lower() == "branch" or "branch" in _blob(n)


def _is_movement(n: BPNode) -> bool:
    return "addmovementinput" in _blob(n)


def _ref_target(value: Any) -> str | None:
    """'node_03.exec_in' → 'node_03'. Ids desnudos ('3') se normalizan antes."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.split(".", 1)[0].strip() or None


def _out_pin_for(n: BPNode) -> str:
    t = n.type.lower()
    if t == "inputkey" or "inputkey" in _blob(n):
        return "Pressed"
    return "exec_out"


def _canonical_branch_outputs(node: BPNode) -> BPNode:
    """TrueNodeID/true_id/True → then; FalseNodeID/false_id/False → else."""
    outs = dict(node.outputs or {})
    renamed: dict[str, Any] = {}
    for key, value in outs.items():
        k = str(key).strip()
        if _TRUE_PIN_RE.match(k):
            renamed.setdefault("then", value)
        elif _FALSE_PIN_RE.match(k):
            renamed.setdefault("else", value)
        else:
            renamed[k] = value
    if renamed == outs:
        return node
    return node.model_copy(update={"outputs": renamed})


def _normalized_refs(node: BPNode, known: set[str]) -> BPNode:
    """Ids desnudos o numéricos en los cables → node_XX existente."""
    def fix(value: Any, default_pin: str) -> Any:
        if not isinstance(value, str) or not value.strip():
            return value
        raw = value.strip()
        target, _, pin = raw.partition(".")
        target = target.strip()
        if target.isdigit():
            target = f"node_{int(target):02d}"
        if target not in known:
            return value if target == raw else f"{target}.{pin or default_pin}"
        return f"{target}.{pin or default_pin}"

    inputs = {
        k: (fix(v, "exec_in") if "exec" in str(k).lower() else v)
        for k, v in (node.inputs or {}).items()
    }
    outputs = {
        k: (fix(v, "exec_in") if str(k).lower().replace(" ", "") in _EXEC_OUT_KEYS else v)
        for k, v in (node.outputs or {}).items()
    }
    return node.model_copy(update={"inputs": inputs, "outputs": outputs})


_DATA_EXEC_PINS = {
    "exec_in",
    "exec_out",
    "execute",
    "then",
    "else",
    "pressed",
    "released",
}


def _bad_data_ref(value: Any, known: set[str]) -> bool:
    """Un pin de dato no puede apuntar a un id ausente ni a un pin de ejecución."""
    if not isinstance(value, str):
        return False
    raw = value.strip()
    if not re.match(r"^node_\d+(?:\..+)?$", raw, re.I):
        return False
    target, _, pin = raw.partition(".")
    if target not in known:
        return True
    return pin.lower() in _DATA_EXEC_PINS


def _drop_self_and_dangling(node: BPNode, known: set[str]) -> BPNode:
    """Quita autorreferencias y cables a ids que el modelo nunca emitió."""
    inputs: dict[str, Any] = {}
    for k, v in (node.inputs or {}).items():
        if "exec" in str(k).lower():
            target = _ref_target(v)
            if target is not None and (target == node.id or target not in known):
                continue
        elif _bad_data_ref(v, known):
            continue
        inputs[k] = v

    outputs: dict[str, Any] = {}
    for k, v in (node.outputs or {}).items():
        if str(k).lower().replace(" ", "") in _EXEC_OUT_KEYS:
            target = _ref_target(v)
            if target is not None and (target == node.id or target not in known):
                continue
        outputs[k] = v
    return node.model_copy(update={"inputs": inputs, "outputs": outputs})


def _wired_in(node: BPNode) -> bool:
    for k, v in (node.inputs or {}).items():
        if "exec" in str(k).lower() and _ref_target(v):
            return True
    return False


def _free_exec_pins(node: BPNode) -> list[str]:
    """Pines de salida de ejecución sin destino."""
    outs = node.outputs or {}
    if _is_branch(node):
        return [pin for pin in ("then", "else") if not _ref_target(outs.get(pin))]
    pin = _out_pin_for(node)
    for key, value in outs.items():
        if str(key).lower().replace(" ", "") in _EXEC_OUT_KEYS and _ref_target(value):
            return []
    return [pin]


def _feeding_branch(node: BPNode, by_id: dict[str, BPNode]) -> BPNode | None:
    """Branch del que cuelga este nodo, si es que cuelga de una rama."""
    exec_in = (node.inputs or {}).get("exec_in")
    target = _ref_target(exec_in)
    if not target:
        return None
    src = by_id.get(target)
    if src is not None and _is_branch(src):
        return src
    return None


def _reconnect_orphans(nodes: list[BPNode]) -> list[BPNode]:
    """Cada nodo sin exec_in se engancha a un pin de ejecución libre anterior."""
    by_id = {n.id: n for n in nodes}
    order = [n.id for n in nodes]

    def link(src_id: str, pin: str, dst_id: str) -> None:
        src, dst = by_id[src_id], by_id[dst_id]
        outs = dict(src.outputs or {})
        outs[pin] = f"{dst_id}.exec_in"
        inns = dict(dst.inputs or {})
        inns["exec_in"] = f"{src_id}.{pin}"
        by_id[src_id] = src.model_copy(update={"outputs": outs})
        by_id[dst_id] = dst.model_copy(update={"inputs": inns})

    for position, dst_id in enumerate(order):
        dst = by_id[dst_id]
        if _is_entry(dst) or _wired_in(dst):
            continue

        # "si true imprime OK, si false FAIL": dos nodos iguales seguidos, el
        # primero ya en then → el segundo va al else, no en cadena tras el primero.
        if position > 0:
            prev = by_id[order[position - 1]]
            branch = _feeding_branch(prev, by_id)
            if (
                branch is not None
                and prev.type == dst.type
                and prev.name == dst.name
                and _free_exec_pins(branch)
            ):
                link(branch.id, _free_exec_pins(branch)[0], dst_id)
                continue

        # Si no, el nodo anterior más cercano que tenga un pin de ejecución libre
        source = None
        pin = None
        for candidate_id in reversed(order[:position]):
            candidate = by_id[candidate_id]
            # A y D son dos acciones. Un AddMovementInput no dispara al otro.
            if _is_movement(dst) and _is_movement(candidate):
                continue
            free = _free_exec_pins(candidate)
            if free:
                source, pin = candidate, free[0]
                break
        if source is None or pin is None:
            continue
        link(source.id, pin, dst_id)

    return [by_id[i] for i in order]


def _unchain_branch_siblings(nodes: list[BPNode]) -> list[BPNode]:
    """Si then y else ya apuntan a dos nodos, quita el cable extra de uno al otro."""
    by_id = {n.id: n for n in nodes}
    for n in nodes:
        if not _is_branch(n):
            continue
        outs = n.outputs or {}
        ends = {
            _ref_target(outs.get("then")),
            _ref_target(outs.get("else")),
        }
        ends.discard(None)
        if len(ends) < 2:
            continue
        for src_id in list(ends):
            src = by_id.get(src_id or "")
            if src is None:
                continue
            new_outs = {
                k: v
                for k, v in (src.outputs or {}).items()
                if _ref_target(v) not in ends or _ref_target(v) == src_id
            }
            if new_outs != (src.outputs or {}):
                by_id[src_id] = src.model_copy(update={"outputs": new_outs})
        for pin, key in (("then", "then"), ("else", "else")):
            dst_id = _ref_target(outs.get(pin))
            dst = by_id.get(dst_id or "")
            if dst is None:
                continue
            inns = dict(dst.inputs or {})
            src = _ref_target(inns.get("exec_in"))
            if src in ends and src != n.id:
                inns["exec_in"] = f"{n.id}.{key}"
                by_id[dst_id] = dst.model_copy(update={"inputs": inns})
    return [by_id[n.id] for n in nodes]


_PURE_CALLS = {
    "getactorlocation",
    "getactorrotation",
    "getplayercharacter",
    "getplayerpawn",
    "getplayercontroller",
}


def _is_pure_call(node: BPNode) -> bool:
    return _blob(node) in _PURE_CALLS or any(name in _blob(node) for name in _PURE_CALLS)


def _ref_pin(value: Any) -> str | None:
    if not isinstance(value, str) or "." not in value:
        return None
    return value.split(".", 1)[1].strip() or None


def _pure_successor_id(node: BPNode, outs: dict[str, Any], nodes: list[BPNode]) -> str | None:
    """El nodo de acción que sigue a un puro, aunque el modelo cruce exec y ReturnValue."""
    for key in ("exec_out", "ReturnValue"):
        target = _ref_target(outs.get(key))
        if target and target != node.id:
            return target
    for other in nodes:
        if other.id == node.id or _is_pure_call(other):
            continue
        if _ref_target((other.inputs or {}).get("exec_in")) == node.id:
            return other.id
    return None


def _bypass_pure_nodes(nodes: list[BPNode]) -> list[BPNode]:
    """Un GetActorLocation no tiene exec. La cadena lo salta y el ReturnValue alimenta el dato."""
    by_id = {n.id: n for n in nodes}
    for node in nodes:
        if not _is_pure_call(node):
            continue
        inns = dict(node.inputs or {})
        outs = dict(node.outputs or {})
        pred_id = _ref_target(inns.get("exec_in"))
        succ_id = _pure_successor_id(node, outs, nodes)
        pred = by_id.get(pred_id or "")
        succ = by_id.get(succ_id or "")
        if (
            pred is not None
            and succ is not None
            and pred_id != succ_id
            and not _is_pure_call(succ)
        ):
            pred_pin = "exec_out"
            pred_outs = dict(pred.outputs or {})
            for key, value in pred_outs.items():
                if _ref_target(value) == node.id:
                    pred_pin = str(key)
                    pred_outs[key] = f"{succ_id}.exec_in"
            succ_inns = dict(succ.inputs or {})
            # exec_in vacío, o apuntando al puro (también a su ReturnValue).
            if _ref_target(succ_inns.get("exec_in")) in {None, node.id}:
                succ_inns["exec_in"] = f"{pred_id}.{pred_pin}"
            data_pin = "InString" if "printstring" in _blob(succ) else None
            if data_pin is None:
                for key in succ_inns:
                    if "exec" not in str(key).lower():
                        data_pin = str(key)
                        break
            current = succ_inns.get(data_pin) if data_pin else None
            if data_pin and not (isinstance(current, str) and current.startswith("node_") and _ref_pin(current) not in _DATA_EXEC_PINS):
                # Solo en el pin de entrada. Si el ReturnValue repite el mismo
                # destino, el applier lo cablea dos veces y Unreal inserta dos
                # conversores (Character → String crea dos GetDisplayName).
                succ_inns[data_pin] = f"{node.id}.ReturnValue"
            by_id[pred_id] = pred.model_copy(update={"outputs": pred_outs})
            by_id[succ_id] = succ.model_copy(update={"inputs": succ_inns})
        inns.pop("exec_in", None)
        outs.pop("exec_out", None)
        ret = outs.get("ReturnValue")
        ret_pin = (_ref_pin(ret) or "").lower()
        if not isinstance(ret, str) or not ret.startswith("node_") or ret_pin in _DATA_EXEC_PINS:
            outs.pop("ReturnValue", None)
        by_id[node.id] = node.model_copy(update={"inputs": inns, "outputs": outs})
    return [by_id[n.id] for n in nodes]


def _unchain_movement_siblings(nodes: list[BPNode]) -> list[BPNode]:
    """Dos AddMovementInput no se encadenan: cada uno espera su tecla."""
    by_id = {n.id: n for n in nodes}
    movement_ids = {n.id for n in nodes if _is_movement(n)}
    for node in nodes:
        if node.id not in movement_ids:
            continue
        current = by_id[node.id]
        inns = dict(current.inputs or {})
        src_id = _ref_target(inns.get("exec_in"))
        if src_id not in movement_ids:
            continue
        inns.pop("exec_in", None)
        by_id[node.id] = current.model_copy(update={"inputs": inns})
        src = by_id[src_id]
        outs = {
            key: value
            for key, value in (src.outputs or {}).items()
            if _ref_target(value) != node.id
        }
        by_id[src_id] = src.model_copy(update={"outputs": outs})
    return [by_id[n.id] for n in nodes]


def _fix_delay_durations(nodes: list[BPNode], user_prompt: str) -> list[BPNode]:
    """Duration=1e-06 es ruido del modelo: usar los segundos del prompt."""
    prompt_seconds: float | None = None
    match = _PROMPT_SECONDS_RE.search(user_prompt or "")
    if match:
        try:
            prompt_seconds = float(match.group(1).replace(",", "."))
        except ValueError:
            prompt_seconds = None

    out: list[BPNode] = []
    for n in nodes:
        if "delay" not in _blob(n):
            out.append(n)
            continue
        inputs = dict(n.inputs or {})
        try:
            duration = float(inputs.get("Duration", 1.0))
        except (TypeError, ValueError):
            duration = 1.0
        if duration < 0.01 or duration > 3600:
            duration = prompt_seconds if prompt_seconds else 1.0
        inputs["Duration"] = float(duration)
        out.append(n.model_copy(update={"inputs": inputs}))
    return out


def repair_graph(graph: BPGraph, user_prompt: str = "") -> BPGraph:
    nodes = [
        _canonical_branch_outputs(n) if _is_branch(n) else n for n in graph.nodes
    ]
    known = {n.id for n in nodes}
    nodes = [_normalized_refs(n, known) for n in nodes]
    nodes = [_drop_self_and_dangling(n, known) for n in nodes]
    nodes = _bypass_pure_nodes(nodes)
    nodes = _reconnect_orphans(nodes)
    nodes = _unchain_branch_siblings(nodes)
    nodes = _unchain_movement_siblings(nodes)
    nodes = _fix_delay_durations(nodes, user_prompt)
    return BPGraph(graph_name=graph.graph_name, nodes=nodes)
