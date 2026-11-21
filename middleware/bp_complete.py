"""Detección de JSON BP-Lite truncado o incompleto vs prompt — sin fabricar grafos.

El modelo emite el grafo; el middleware solo señala cortes sintácticos o huecos
semánticos para disparar un continue. Nunca inventa nodos.
"""

from __future__ import annotations

import json
import re
from typing import Any

_TRUNCATION_MSG = "JSON incompleto / truncado: la respuesta del modelo no es un objeto JSON completo"


_SALVAGE_MSG = (
    "El modelo cortó el JSON a medias; se aplican solo los nodos completos "
    "({kept} de {kept_plus}). Repite la petición si falta algún nodo."
)


def note_truncation() -> str:
    return _TRUNCATION_MSG


def note_salvage(kept: int, dropped: int) -> str:
    return _SALVAGE_MSG.format(kept=kept, kept_plus=kept + dropped)


def salvage_truncated_nodes(raw_text: str) -> dict[str, Any] | None:
    """
    Recupera el prefijo válido de un JSON BP-Lite cortado: graph_name + los nodos
    que cerraron su objeto. El nodo a medias se descarta (no se inventa nada).
    """
    import json
    import re

    text = raw_text or ""
    fence = re.search(r"```(?:json)?\s*([\s\S]*)", text, re.IGNORECASE)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start < 0:
        return None
    text = text[start:]

    name_match = re.search(r'"graph_name"\s*:\s*"([^"]*)"', text)
    if not name_match:
        return None

    nodes_at = text.find('"nodes"')
    if nodes_at < 0:
        return None
    array_at = text.find("[", nodes_at)
    if array_at < 0:
        return None

    nodes: list[dict[str, Any]] = []
    dropped = 0
    depth = 0
    obj_start = -1
    in_string = False
    escaped = False
    for idx in range(array_at + 1, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                obj_start = idx
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start >= 0:
                try:
                    node = json.loads(text[obj_start : idx + 1])
                except json.JSONDecodeError:
                    dropped += 1
                else:
                    if isinstance(node, dict):
                        nodes.append(node)
                obj_start = -1
        elif ch == "]" and depth == 0:
            break
    if depth > 0 or obj_start >= 0:
        dropped += 1

    if not nodes:
        return None
    return {
        "graph_name": name_match.group(1) or "Pygenesis_Graph",
        "nodes": nodes,
        "_salvaged_dropped": dropped,
    }


def is_syntactically_truncated(raw_text: str) -> bool:
    """True solo si hay llaves/corchetes desbalanceados (corte a medias)."""
    if not raw_text or not raw_text.strip():
        return False
    s = raw_text.strip()
    if "{" not in s:
        return False
    if s.count("{") > s.count("}"):
        return True
    if s.count("[") > s.count("]"):
        return True
    # Corte mid-token: termina en coma/colon/backslash tras haber abierto un objeto
    tail = s.rstrip()
    if '"graph_name"' in s and tail.endswith((",", ":", "\\")):
        return True
    return False


def graph_looks_incomplete(graph: dict[str, Any] | None, raw_text: str = "") -> bool:
    """Compat: truncado sintáctico o grafo ausente/sin nodos."""
    if is_syntactically_truncated(raw_text):
        return True
    if graph is None:
        return True
    nodes = graph.get("nodes")
    return not isinstance(nodes, list) or len(nodes) == 0


_KEY_TOKEN_RE = re.compile(
    r"(?:tecla|pulsar|pulsa|key)\s+(espacio|spacebar|space|[A-Za-z])\b",
    re.IGNORECASE,
)
_STRAFE_AD_RE = re.compile(
    r"\bA\b.{0,80}\bD\b|\bD\b.{0,80}\bA\b",
    re.IGNORECASE | re.DOTALL,
)
_QUOTED_RE = re.compile(r"[\"«']([^\"»']{1,64})[\"»']")
# Funciones que el pedido nombra. «sin Jump» no cuenta como pedido.
_NAMED_CALLS = (
    "AIMoveTo",
    "GetActorLocation",
    "SetActorLocation",
    "SetActorRotation",
    "GetPlayerCharacter",
    "GetPlayerPawn",
    "GetPlayerController",
    "LineTraceByChannel",
    "AddMovementInput",
    "DestroyActor",
    "LaunchCharacter",
    "Jump",
    "PrintString",
)


def _calls_asked(prompt: str, token: str) -> int:
    cleaned = re.sub(
        rf"\bsin\s+(?:el\s+|la\s+)?{re.escape(token)}\b",
        " ",
        prompt or "",
        flags=re.IGNORECASE,
    )
    return len(re.findall(rf"\b{re.escape(token)}\b", cleaned, flags=re.IGNORECASE))


_BRANCH_BOTH_RE = re.compile(
    r"\bbranch\b.{0,120}(?:\btrue\b|\bok\b).{0,80}(?:\bfalse\b|\bfail\b)"
    r"|\bsi\s+true\b|\bsi\s+false\b|\bthen\b.{0,40}\belse\b",
    re.IGNORECASE | re.DOTALL,
)


def _norm_key(token: str) -> str:
    t = (token or "").strip().lower()
    if t in ("espacio", "space", "spacebar"):
        return "SpaceBar"
    if len(t) == 1:
        return t.upper()
    return token.strip()


def _as_graph(blob: str | dict[str, Any] | None) -> dict[str, Any] | None:
    if isinstance(blob, dict):
        return blob
    if not isinstance(blob, str) or not blob.strip():
        return None
    text = blob.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start < 0:
        return None
    text = text[start:]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        salvaged = salvage_truncated_nodes(blob)
        return salvaged
    if isinstance(obj, dict):
        return obj
    return None


def node_count(blob: str | dict[str, Any] | None) -> int:
    g = _as_graph(blob)
    if not g:
        return 0
    nodes = g.get("nodes")
    return len(nodes) if isinstance(nodes, list) else 0


def missing_vs_prompt(
    user_prompt: str,
    graph_or_raw: str | dict[str, Any] | None,
) -> list[str]:
    """
    Huecos semánticos del grafo respecto al prompt (sin inventar nodos).
    Lista vacía = cubre lo pedido o no hay señales claras.
    """
    prompt = (user_prompt or "").strip()
    if not prompt:
        return []
    graph = _as_graph(graph_or_raw)
    if graph is None:
        return ["JSON ausente o ilegible"]
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return ["sin nodos"]

    gaps: list[str] = []
    # Salvage de un corte a medias: el nodo a medias cuenta como hueco aunque
    # los cerrados ya formen un grafo "válido".
    dropped = int(graph.get("_salvaged_dropped") or 0)
    if dropped > 0 or (
        isinstance(graph_or_raw, str) and is_syntactically_truncated(graph_or_raw)
    ):
        gaps.append("JSON truncado (nodo a medias)")
    names = [(n.get("type") or "", n.get("name") or "") for n in nodes if isinstance(n, dict)]
    input_keys = {name for typ, name in names if typ == "InputKey" and name}
    prints = [
        str((n.get("inputs") or {}).get("InString") or "")
        for n in nodes
        if isinstance(n, dict) and (n.get("name") or "") == "PrintString"
    ]
    has_delay = any(name == "Delay" for _, name in names)
    has_branch = any(typ == "Branch" or name == "Branch" for typ, name in names)
    branch_outs = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        if (n.get("type") or n.get("name")) == "Branch":
            branch_outs = dict(n.get("outputs") or {})
            break

    # Teclas pedidas
    wanted_keys: list[str] = []
    for m in _KEY_TOKEN_RE.finditer(prompt):
        k = _norm_key(m.group(1))
        if k and k not in wanted_keys:
            wanted_keys.append(k)
    pl = prompt.lower()
    if _STRAFE_AD_RE.search(prompt) and (
        "strafe" in pl
        or "addmovement" in pl
        or "izquierda" in pl
        or "derecha" in pl
        or "movement" in pl
    ):
        for k in ("A", "D"):
            if k not in wanted_keys:
                wanted_keys.append(k)
    for k in wanted_keys:
        if k not in input_keys:
            gaps.append(f"falta InputKey {k}")

    # Textos de PrintString entre comillas
    quoted = [q for q in _QUOTED_RE.findall(prompt) if q.strip()]
    # Evitar falsos positivos de teclas sueltas entre comillas tipo "F" si ya es key
    for q in quoted:
        if len(q) <= 2 and q.upper() in {"F", "W", "A", "S", "D", "E"}:
            continue
        if not any(q == p or q.lower() == p.lower() for p in prints):
            gaps.append(f'falta PrintString "{q}"')

    # Delay pedido
    if re.search(r"\bdelay\b|\bespera\b", pl) and not has_delay:
        gaps.append("falta Delay")

    # La misma función dos veces (patrulla: AIMoveTo, Delay, AIMoveTo) no se
    # cubre con un solo BeginPlay.
    for token in _NAMED_CALLS:
        asked = _calls_asked(prompt, token)
        if asked <= 0:
            continue
        key = token.lower()
        have = 0
        for _, name in names:
            blob = name.lower().replace(" ", "").replace("_", "")
            if blob == key or blob.startswith(key):
                have += 1
        if have < asked:
            gaps.append(f"falta {token} ({have}<{asked})")

    # Branch con ambas ramas
    if re.search(r"\bbranch\b", pl) and _BRANCH_BOTH_RE.search(prompt):
        if not has_branch:
            gaps.append("falta Branch")
        else:
            then_ok = any(k.lower() in ("then", "true", "truenodeid") for k in branch_outs)
            else_ok = any(k.lower() in ("else", "false", "falsenodeid") for k in branch_outs)
            if not then_ok:
                gaps.append("Branch sin rama then")
            if not else_ok:
                gaps.append("Branch sin rama else")
            # Dos prints distintos si el prompt trae dos literales
            if len([q for q in quoted if len(q) > 2]) >= 2 and len(prints) < 2:
                gaps.append("Branch: faltan las dos salidas PrintString")

    # Cadena mínima: BeginPlay + Delay + ≥2 prints → ≥4 nodos
    wants_begin = bool(
        re.search(r"beginplay|comenzar|al comenzar|al inicio", pl)
    )
    n_print_asked = len([q for q in quoted if len(q) > 2])
    min_nodes = 0
    if wanted_keys:
        # cada tecla + al menos una acción por tecla (salvo que solo pidan la tecla)
        min_nodes = max(min_nodes, len(wanted_keys) * 2)
    if wants_begin:
        min_nodes = max(min_nodes, 1)
    if has_branch or re.search(r"\bbranch\b", pl):
        # Event + Branch + 2 actions típico
        min_nodes = max(min_nodes, 4 if _BRANCH_BOTH_RE.search(prompt) else 3)
    if re.search(r"\bdelay\b|\bespera\b", pl):
        min_nodes = max(min_nodes, 1 + (1 if wants_begin else 0) + max(1, n_print_asked))
    elif n_print_asked >= 2 and wants_begin:
        min_nodes = max(min_nodes, 1 + n_print_asked)
    if min_nodes and len(nodes) < min_nodes:
        gaps.append(f"pocos nodos ({len(nodes)}<{min_nodes})")

    # Dedup conservando orden
    seen: set[str] = set()
    out: list[str] = []
    for g in gaps:
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out


def clean_partial_for_continue(raw_text: str) -> str:
    """
    Borrador limpio para el continue: solo nodos que cerraron, sin la basura
    del corte ("Print     …"). Así el modelo no re-engancha en espacios.
    """
    salvaged = salvage_truncated_nodes(raw_text)
    if salvaged is None:
        graph = _as_graph(raw_text)
        if graph is None:
            return (raw_text or "").strip()
        clean = {k: v for k, v in graph.items() if not str(k).startswith("_")}
        return json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
    clean = {k: v for k, v in salvaged.items() if not str(k).startswith("_")}
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"))


def _next_node_id(nodes: list[dict[str, Any]]) -> str:
    best = 0
    for n in nodes:
        m = re.search(r"(\d+)$", str(n.get("id") or ""))
        if m:
            best = max(best, int(m.group(1)))
    return f"node_{best + 1:02d}"


def _free_exec_source(nodes: list[dict[str, Any]]) -> tuple[str, str] | None:
    """(node_id, pin) del último nodo con un pin de ejecución libre."""
    known = {str(n.get("id")) for n in nodes}

    def _dest_missing(target: Any) -> bool:
        if not isinstance(target, str) or not target.strip():
            return True
        return target.split(".", 1)[0] not in known

    for n in reversed(nodes):
        nid = str(n.get("id") or "")
        typ = str(n.get("type") or "")
        outs = dict(n.get("outputs") or {})
        if typ == "Branch":
            for pin in ("then", "else"):
                if _dest_missing(outs.get(pin)):
                    return nid, pin
            continue
        pin = "Pressed" if typ == "InputKey" else "exec_out"
        if _dest_missing(outs.get(pin)):
            return nid, pin
    return None


_MOVE_DIR = {
    "W": [1.0, 0.0, 0.0],
    "S": [-1.0, 0.0, 0.0],
    "A": [0.0, -1.0, 0.0],
    "D": [0.0, 1.0, 0.0],
}


def _prompt_wants_movement(prompt: str) -> bool:
    pl = (prompt or "").lower()
    return bool(
        re.search(
            r"addmovement|strafe|adelante|atr[aá]s|izquierda|derecha|movementinput",
            pl,
        )
    )


def _set_out(nodes: list[dict[str, Any]], src_id: str, pin: str, dst_id: str) -> None:
    for i, n in enumerate(nodes):
        if str(n.get("id")) != src_id:
            continue
        outs = dict(n.get("outputs") or {})
        outs[pin] = f"{dst_id}.exec_in"
        nodes[i] = {**n, "outputs": outs}
        return


def _append_node(nodes: list[dict[str, Any]], node: dict[str, Any]) -> str:
    nodes.append(node)
    return str(node["id"])


def fill_obvious_prompt_gaps(
    graph_or_raw: str | dict[str, Any] | None,
    user_prompt: str,
) -> dict[str, Any] | None:
    """
    Cierra huecos obvios tras un corte del modelo:
    - PrintString con texto literal del prompt
    - InputKey huérfano → AddMovementInput si el prompt pide movimiento
    - InputKey pedido en el prompt y ausente (A/D strafe)
    No inventa grafos enteros desde cero.
    """
    graph = _as_graph(graph_or_raw)
    if graph is None:
        return None
    nodes = [dict(n) for n in (graph.get("nodes") or []) if isinstance(n, dict)]
    if not nodes:
        return None

    changed = False
    pl = (user_prompt or "").lower()

    # Quitar EventTick espurio si el usuario pidió teclas (no tick)
    if (
        re.search(r"tecla|pulsar|pulsa|strafe|inputkey", pl)
        and not re.search(r"\btick\b|cada frame|eventtick", pl)
    ):
        kept = [
            n
            for n in nodes
            if not (
                (n.get("type") == "Event" and n.get("name") == "EventTick")
                or (n.get("name") == "EventTick")
            )
        ]
        if len(kept) < len(nodes):
            nodes = kept
            changed = True

    # Teclas pedidas ausentes
    wanted_keys: list[str] = []
    for m in _KEY_TOKEN_RE.finditer(user_prompt or ""):
        k = _norm_key(m.group(1))
        if k and k not in wanted_keys:
            wanted_keys.append(k)
    if _STRAFE_AD_RE.search(user_prompt or "") and _prompt_wants_movement(user_prompt):
        for k in ("A", "D"):
            if k not in wanted_keys:
                wanted_keys.append(k)
    have_keys = {
        str(n.get("name"))
        for n in nodes
        if n.get("type") == "InputKey" and n.get("name")
    }
    for k in wanted_keys:
        if k in have_keys:
            continue
        new_id = _next_node_id(nodes)
        _append_node(
            nodes,
            {
                "id": new_id,
                "type": "InputKey",
                "name": k,
                "inputs": {},
                "outputs": {},
            },
        )
        have_keys.add(k)
        changed = True

    # InputKey con Pressed libre → AddMovementInput si el prompt lo pide
    if _prompt_wants_movement(user_prompt):
        # snapshot ids because we append
        for n in list(nodes):
            if n.get("type") != "InputKey":
                continue
            nid = str(n.get("id"))
            key = str(n.get("name") or "W")
            outs = dict(n.get("outputs") or {})
            target = outs.get("Pressed")
            dest_ok = (
                isinstance(target, str)
                and target.split(".", 1)[0]
                in {str(x.get("id")) for x in nodes}
            )
            if dest_ok:
                continue
            new_id = _next_node_id(nodes)
            direction = _MOVE_DIR.get(key, [1.0, 0.0, 0.0])
            _set_out(nodes, nid, "Pressed", new_id)
            _append_node(
                nodes,
                {
                    "id": new_id,
                    "type": "FunctionCall",
                    "name": "AddMovementInput",
                    "inputs": {
                        "exec_in": f"{nid}.Pressed",
                        "WorldDirection": direction,
                        "ScaleValue": 1.0,
                    },
                    "outputs": {},
                },
            )
            changed = True

    # PrintString con texto literal del prompt
    prints = {
        str((n.get("inputs") or {}).get("InString") or "")
        for n in nodes
        if (n.get("name") or "") == "PrintString"
    }
    quoted = [q for q in _QUOTED_RE.findall(user_prompt or "") if q.strip()]
    missing_texts = [
        q
        for q in quoted
        if not (len(q) <= 2 and q.upper() in {"F", "W", "A", "S", "D", "E"})
        and not any(q == p or q.lower() == p.lower() for p in prints)
    ]
    for text in missing_texts:
        link = _free_exec_source(nodes)
        if link is None:
            break
        src_id, pin = link
        new_id = _next_node_id(nodes)
        _set_out(nodes, src_id, pin, new_id)
        _append_node(
            nodes,
            {
                "id": new_id,
                "type": "FunctionCall",
                "name": "PrintString",
                "inputs": {"exec_in": f"{src_id}.{pin}", "InString": text},
                "outputs": {},
            },
        )
        changed = True

    # Re-cablear exec_in huérfanos a un pin libre anterior (Print→Delay sin outputs)
    by_id = {str(n.get("id")): n for n in nodes}
    for n in nodes:
        inns = dict(n.get("inputs") or {})
        exec_in = inns.get("exec_in")
        if not isinstance(exec_in, str) or "." not in exec_in:
            continue
        src_id, pin = exec_in.split(".", 1)
        src = by_id.get(src_id)
        if src is None:
            continue
        outs = dict(src.get("outputs") or {})
        if outs.get(pin) == exec_in or outs.get(pin) == f"{n.get('id')}.exec_in":
            continue
        if not outs.get(pin):
            outs[pin] = f"{n.get('id')}.exec_in"
            src["outputs"] = outs
            changed = True

    if not changed:
        # Aun sin cambios de topología, devolver grafo limpio si venía truncado
        if isinstance(graph_or_raw, str) and is_syntactically_truncated(graph_or_raw):
            out = {k: v for k, v in graph.items() if not str(k).startswith("_")}
            out["nodes"] = nodes
            return out
        return None
    out = {k: v for k, v in graph.items() if not str(k).startswith("_")}
    out["nodes"] = nodes
    return out


def finalize_bp_json(raw_text: str, user_prompt: str = "") -> str:
    """
    Cierra el JSON con los nodos que ya terminaron.
    No añade teclas, prints ni movimiento: los huecos los cubre un continue
    del modelo, no una plantilla. user_prompt se conserva por la firma.
    """
    _ = user_prompt
    raw = raw_text or ""
    clean = clean_partial_for_continue(raw)
    return clean or raw


def score_graph_candidate(
    user_prompt: str, blob: str | dict[str, Any] | None
) -> tuple[int, int, int]:
    """Mayor es mejor: (-gaps, node_count, -truncated)."""
    gaps = missing_vs_prompt(user_prompt, blob)
    trunc = (
        1
        if isinstance(blob, str) and is_syntactically_truncated(blob)
        else 0
    )
    return (-len(gaps), node_count(blob), -trunc)


def complete_if_incomplete(
    graph: dict[str, Any] | None,
    *,
    user_prompt: str = "",
    raw_text: str = "",
) -> dict[str, Any] | None:
    """
    Ya no inventa plantillas. Si el JSON está truncado → None.
    Si el grafo es usable → se devuelve tal cual (los huecos semánticos
    los resuelve el continue del job_runner, no este helper).
    """
    _ = user_prompt
    if is_syntactically_truncated(raw_text):
        return None
    return graph
