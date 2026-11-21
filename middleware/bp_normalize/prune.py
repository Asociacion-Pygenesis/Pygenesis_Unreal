"""Limpieza de basura del modelo sin secuestrar la intención.

- PrintString huérfano si el prompt no pide imprimir.
- BeginPlay espurio en grafos solo-tecla.
- Pines basura en outputs de LaunchCharacter.
"""

from __future__ import annotations

import re
from typing import Any

from middleware.bp_models import BPGraph, BPNode
from middleware.bp_normalize.identity import node_blob as _blob

_PRINT_INTENT_RE = re.compile(
    r"\b(?:printstring|imprime|imprimir|muestra|mostrar|texto\s+en\s+pantalla|"
    r"en\s+pantalla|hola|mundo|listo|overlap|interactuando|interactuar)\b",
    re.IGNORECASE,
)
_KEY_ONLY_RE = re.compile(
    r"\b(?:tecla|pulsar|espacio|spacebar|inputkey|addmovement|strafe|"
    r"launchcharacter|saltar|adelante|izquierda|derecha)\b",
    re.IGNORECASE,
)
_BEGINPLAY_INTENT_RE = re.compile(
    r"\b(?:beginplay|al\s+comenzar|al\s+inicio|al\s+empezar|destruye|"
    r"destroyactor|delay)\b",
    re.IGNORECASE,
)
_BRANCH_INTENT_RE = re.compile(
    r"\bbranch\b|\bsi\s+(?:true|false|verdadero|falso)\b|\bif\b.{0,40}\belse\b",
    re.IGNORECASE | re.DOTALL,
)

_LAUNCH_JUNK_OUT = {
    "speedz",
    "velocityscale",
    "velocity",
    "vector3d",
    "speed",
    "comments",
}
_LAUNCH_DATA_PINS = {
    "launchvelocity",
    "xyoverride",
    "zoverride",
    "bxyoverride",
    "bzoverride",
}
_JUMP_WORD_RE = re.compile(r"\bjump\b", re.IGNORECASE)
_FORBID_LAUNCH_RE = re.compile(r"\bsin\s+launch\s*character\b", re.IGNORECASE)
_ASK_LAUNCH_RE = re.compile(r"\blaunch\s*character\b", re.IGNORECASE)


def _is_print(n: BPNode) -> bool:
    return "printstring" in _blob(n)


def _is_beginplay(n: BPNode) -> bool:
    b = _blob(n)
    return "beginplay" in b or (
        n.type.lower() == "event" and "beginplay" in n.name.lower().replace(" ", "")
    )


def _is_branch(n: BPNode) -> bool:
    return n.type.lower() == "branch" or n.name.lower() == "branch"


def _refs_any(value: Any, ids: set[str]) -> bool:
    if not isinstance(value, str):
        return False
    head = value.split(".", 1)[0]
    return head in ids


def _is_tick(n: BPNode) -> bool:
    name = n.name.lower().replace(" ", "")
    return (n.type.lower() == "event" and "tick" in name) or name == "eventtick"


def _drop_ids(nodes: list[BPNode], dropped: set[str]) -> list[BPNode]:
    if not dropped:
        return nodes
    kept: list[BPNode] = []
    for n in nodes:
        if n.id in dropped:
            continue
        inns = {
            k: v
            for k, v in (n.inputs or {}).items()
            if not _refs_any(v, dropped)
        }
        outs = {
            k: v
            for k, v in (n.outputs or {}).items()
            if not _refs_any(v, dropped)
        }
        kept.append(n.model_copy(update={"inputs": inns, "outputs": outs}))
    return kept


def _is_input_entry(n: BPNode) -> bool:
    t = n.type.lower()
    b = _blob(n)
    return t == "inputkey" or "inputaction" in b or "inputkey" in b


def _has_exec_in(n: BPNode) -> bool:
    inns = n.inputs or {}
    v = inns.get("exec_in") or inns.get("execute")
    return isinstance(v, str) and bool(v.strip())


def _prompt_wants_print(prompt: str) -> bool:
    return bool(_PRINT_INTENT_RE.search(prompt or ""))


def _prompt_is_key_driven(prompt: str) -> bool:
    p = prompt or ""
    if not _KEY_ONLY_RE.search(p):
        return False
    # Si también pide BeginPlay/Destroy/Delay explícito, no es solo-tecla
    if _BEGINPLAY_INTENT_RE.search(p) and not re.search(
        r"\b(?:tecla|pulsar|espacio|space)\b", p, re.I
    ):
        return False
    return True


def _prompt_wants_jump_not_launch(prompt: str) -> bool:
    """Jump pedido y LaunchCharacter no. «sin LaunchCharacter» cuenta como prohibido."""
    if not _JUMP_WORD_RE.search(prompt or ""):
        return False
    if _FORBID_LAUNCH_RE.search(prompt):
        return True
    return _ASK_LAUNCH_RE.search(prompt) is None


def _launch_to_jump(node: BPNode) -> BPNode:
    if "launchcharacter" not in _blob(node):
        return node
    inns = {
        k: v
        for k, v in (node.inputs or {}).items()
        if str(k).lower().replace("_", "") not in _LAUNCH_DATA_PINS
    }
    return node.model_copy(
        update={"type": "FunctionCall", "name": "Jump", "inputs": inns}
    )


def prune_graph_junk(graph: BPGraph, user_prompt: str = "") -> BPGraph:
    nodes = list(graph.nodes)
    prompt = user_prompt or ""

    # 0) El entrenamiento empuja Espacio → LaunchCharacter. Si el pedido nombra
    # Jump y no pide LaunchCharacter, el nodo es Jump y no lleva velocidad.
    if prompt.strip() and _prompt_wants_jump_not_launch(prompt):
        nodes = [_launch_to_jump(n) for n in nodes]

    # 1) Launch: limpiar outputs basura
    cleaned: list[BPNode] = []
    for n in nodes:
        if "launchcharacter" in _blob(n):
            outs = {
                k: v
                for k, v in (n.outputs or {}).items()
                if str(k).lower().replace(" ", "") not in _LAUNCH_JUNK_OUT
                and v not in (None, "")
            }
            cleaned.append(n.model_copy(update={"outputs": outs}))
        else:
            cleaned.append(n)
    nodes = cleaned

    # 2) Print huérfano si el prompt no pide imprimir.
    # Sin prompt no hay evidencia de basura: perder un nodo pedido es peor que
    # dejar uno de más, así que solo se poda cuando sabemos qué pidió el usuario.
    if prompt.strip() and not _prompt_wants_print(prompt):
        keep: list[BPNode] = []
        for n in nodes:
            if _is_print(n) and not _has_exec_in(n):
                continue
            keep.append(n)
        nodes = keep

    # 3b) Branch que el prompt no pidió (p.ej. A/D strafe no es un if/else).
    # Las teclas son entradas independientes; un Branch entre ellas es basura.
    if prompt.strip() and not _BRANCH_INTENT_RE.search(prompt):
        nodes = _drop_ids(nodes, {n.id for n in nodes if _is_branch(n)})

    # 3c) EventTick solo si el usuario lo pide. "sin EventTick" no cuenta.
    # Delante de una tecla el cable no tiene pin de entrada y el nodo queda huérfano.
    wants_tick = bool(
        re.search(r"\beventtick\b|\btick\b|cada\s+frame|por\s+frame", prompt, re.I)
    ) and not re.search(r"\bsin\s+(?:el\s+)?(?:event\s*)?tick\b", prompt, re.I)
    if prompt.strip() and not wants_tick:
        nodes = _drop_ids(nodes, {n.id for n in nodes if _is_tick(n)})

    # 3) BeginPlay espurio en grafos solo-tecla con InputKey
    if _prompt_is_key_driven(prompt) and any(_is_input_entry(n) for n in nodes):
        # No pedir BeginPlay en el prompt (o es launch/move por tecla)
        if not re.search(r"\bbeginplay\b", prompt, re.I) and not re.search(
            r"\bal\s+comenzar\b", prompt, re.I
        ):
            nodes = [n for n in nodes if not _is_beginplay(n)]

    if not nodes:
        return graph
    return BPGraph(graph_name=graph.graph_name, nodes=nodes)
