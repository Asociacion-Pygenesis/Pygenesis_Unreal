"""Adapta el dialecto compacto del modelo (estilo Ollama) al BP-Lite canónico.

Ejemplo nativo del GGUF / Ollama:
{"graph_name":"FKeyInteraction","nodes":[
  {"id":"1","type":"Event_InputAction_F","name":"","inputs":[],"outputs":[]},
  {"id":"2","type":"PrintString","name":"Interactuando","inputs":["1"],"outputs":[]}
]}
"""

from __future__ import annotations

import re
from typing import Any

from middleware.bp_normalize.pins import norm_node_id

_INPUT_ACTION_RE = re.compile(
    r"(?:event[_ ]?)?inputaction[_ ]?(spacebar|space|jump|[a-z0-9]+)",
    re.IGNORECASE,
)
_DELAY_DUR_RE = re.compile(
    r"delay[_\s-]*(?:0*)?([0-9]+(?:\.[0-9]+)?)\s*(?:s|sec|secs|second)?",
    re.IGNORECASE,
)


def _as_id(raw: Any, idx: int) -> str:
    return norm_node_id(raw, idx)


#    el token tras InputAction suele ser relleno ("Node", "Pressed"), no la tecla
_KEY_FILLER = {
    "node",
    "nodes",
    "key",
    "keys",
    "pressed",
    "released",
    "event",
    "events",
    "action",
    "actions",
    "input",
    "trigger",
}


def _key_from_tokens(blob: str) -> str | None:
    """'InputActionNode W Key Pressed' → 'W'; 'Tecla F' → 'F'."""
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", blob) if t]
    for token in tokens:
        low = token.lower()
        if low in {"spacebar", "space", "jump", "espacio"}:
            return "SpaceBar"
        if len(token) == 1 and token.isalpha():
            return token.upper()
    # Patrón "<L>Key" / "Key<L>" pegado
    m = re.search(r"\b([A-Za-z])\s*key\b|\bkey\s*([A-Za-z])\b", blob, re.IGNORECASE)
    if m:
        return (m.group(1) or m.group(2)).upper()
    return None


def _extract_input_action_key(ntype: str, nname: str) -> str | None:
    """Event_InputAction_F / InputAction_W / …_Spacebar → tecla canónica.

    Solo si el nodo es una tecla o una input action. Un FunctionCall llamado
    Jump no es la tecla Espacio.
    """
    compact = f"{ntype} {nname}".lower().replace(" ", "").replace("_", "").replace("-", "")
    if "inputaction" not in compact and "inputkey" not in compact and "tecla" not in compact:
        return None
    blob = f"{ntype} {nname}".replace("-", "_")
    m = _INPUT_ACTION_RE.search(blob.replace(" ", "_"))
    if not m:
        # type literal Event_InputAction_F
        m2 = re.search(r"inputaction[_]?([a-z0-9]+)", blob.replace(" ", ""), re.I)
        key = m2.group(1).lower() if m2 else ""
    else:
        key = m.group(1).lower()

    if key in {"spacebar", "space", "jump", "espacio"}:
        return "SpaceBar"
    if len(key) == 1 and key.isalpha():
        return key.upper()
    if key and key not in _KEY_FILLER and key.isalpha() and len(key) <= 3:
        return key.capitalize()
    # "InputActionNode" + name "W Key Pressed": la tecla está en los tokens
    return _key_from_tokens(blob)


def _canonicalize_type_name(ntype: str, nname: str) -> tuple[str, str, dict[str, Any]]:
    """Devuelve (type, name, extra_inputs) canónicos."""
    extra: dict[str, Any] = {}
    low = f"{ntype} {nname}".lower().replace(" ", "").replace("_", "")
    raw_type = ntype
    raw_name = nname

    key = _extract_input_action_key(ntype, nname)
    if key or "inputaction" in low:
        # Sin tecla reconocida, conservar el name original: classify_node aún
        # puede sacarla ("W Key Pressed") en vez de caer en una F inventada.
        return "InputKey", key or raw_name or "F", extra

    if "printstring" in low or "print string" in f"{ntype} {nname}".lower() or ntype.lower() in {
        "printstring",
        "print",
    }:
        return "FunctionCall", "PrintString", extra

    if "addmovement" in low or "add movement input" in f"{ntype} {nname}".lower():
        blob = f"{ntype} {nname}".lower()
        if "left" in blob or "izquierda" in blob or "strafeleft" in low:
            extra["WorldDirection"] = [0.0, -1.0, 0.0]
        elif "right" in blob or "derecha" in blob or "straferight" in low:
            extra["WorldDirection"] = [0.0, 1.0, 0.0]
        elif "back" in blob or "atrás" in blob or "atras" in blob or "backward" in blob:
            extra["WorldDirection"] = [-1.0, 0.0, 0.0]
        else:
            # Forward / adelante / default
            extra["WorldDirection"] = [1.0, 0.0, 0.0]
        if "ScaleValue" not in extra:
            extra["ScaleValue"] = 1.0
        return "FunctionCall", "AddMovementInput", extra

    if "launch" in low and "character" in low:
        return "FunctionCall", "LaunchCharacter", extra

    if "destroy" in low and "actor" in low:
        return "FunctionCall", "DestroyActor", extra

    if "delay" in low or ntype.lower().startswith("delay"):
        dur = None
        for src in (ntype, nname, f"{ntype}_{nname}"):
            m = _DELAY_DUR_RE.search(src.replace(" ", ""))
            if not m:
                m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*s", src, re.I)
            if m:
                try:
                    dur = float(m.group(1))
                    # Delay_02Sec → 2.0 si el modelo puso 02
                    if dur >= 10 and "sec" in src.lower().replace(" ", ""):
                        # 02 as two digits meaning 2? Delay_02Sec group is 02 → 2.0
                        pass
                    break
                except ValueError:
                    dur = None
        # Delay_02Sec → group "02" → 2.0; Delay_2s → 2.0
        if dur is not None and dur == int(dur) and dur >= 10 and dur < 100:
            # 02 parsed as 2? float("02") is 2.0 already in Python
            pass
        if dur is None:
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", nname or ntype)
            if m:
                try:
                    dur = float(m.group(1))
                except ValueError:
                    dur = 1.0
        extra["Duration"] = float(dur if dur is not None else 1.0)
        return "FunctionCall", "Delay", extra

    if "beginplay" in low:
        return "Event", "EventBeginPlay", extra

    if "beginoverlap" in low or "actorbeginoverlap" in low or (
        "overlap" in low and "event" in low and "end" not in low
    ):
        return "Event", "EventActorBeginOverlap", extra

    if "branch" in low:
        return "Branch", "Branch", extra

    if "inputkey" in low or ntype.lower() == "inputkey":
        k = key or (raw_name.upper() if len(raw_name) == 1 else None) or "F"
        if raw_name.replace(" ", "").lower() in {"spacebar", "space"}:
            k = "SpaceBar"
        return "InputKey", k, extra

    return raw_type, raw_name, extra


def _source_out_pin(src_type: str, src_name: str) -> str:
    """Pin de salida según tipo origen: InputKey→Pressed, Event→exec_out."""
    low = f"{src_type} {src_name}".lower().replace(" ", "").replace("_", "")
    if (
        src_type.lower() == "inputkey"
        or "inputkey" in low
        or "inputaction" in low
    ):
        return "Pressed"
    if "branch" in low or src_type.lower() == "branch":
        return "exec_out"
    return "exec_out"


def _has_valid_output_keys(outputs: dict[str, Any]) -> bool:
    for k, v in (outputs or {}).items():
        if v in (None, ""):
            continue
        kl = str(k).lower().replace(" ", "")
        if kl in {
            "pressed",
            "released",
            "exec_out",
            "execout",
            "then",
            "else",
            "completed",
            "returnvalue",
        }:
            return True
        if isinstance(v, str) and "." in v:
            return True
    return False


def coerce_model_dialect(data: dict[str, Any]) -> dict[str, Any]:
    """Convierte ids cortos + inputs[] + dialecto Ollama → pines UE canónicos."""
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return data

    listish = False
    for n in raw_nodes:
        if not isinstance(n, dict):
            continue
        inn = n.get("inputs")
        out = n.get("outputs")
        if isinstance(inn, list) or isinstance(out, list):
            listish = True
            break
        tid = str(n.get("id") or "")
        if tid.isdigit() or re.fullmatch(r"\d+", tid):
            listish = True
            break
        # Tipos Ollama con espacios / InputAction aunque ids ya sean node_XX
        t = str(n.get("type") or "")
        if "InputAction" in t or " " in t or t.startswith("Event_"):
            listish = True
            break
    if not listish:
        # Aun sin listish, canonicalizar aliases sueltos (Destroy Actor, etc.)
        changed = False
        out_fix: list[dict[str, Any]] = []
        for idx, n in enumerate(raw_nodes, start=1):
            if not isinstance(n, dict):
                continue
            ntype, nname, extra = _canonicalize_type_name(
                str(n.get("type") or ""), str(n.get("name") or "").strip()
            )
            if ntype != n.get("type") or nname != n.get("name"):
                changed = True
            inns = dict(n.get("inputs") or {})
            for k, v in extra.items():
                inns.setdefault(k, v)
            out_fix.append({**n, "type": ntype, "name": nname, "inputs": inns})
        if changed:
            return {**data, "nodes": out_fix}
        return data

    id_map: dict[str, str] = {}
    for idx, n in enumerate(raw_nodes, start=1):
        if not isinstance(n, dict):
            continue
        old = str(n.get("id") or idx)
        id_map[old] = _as_id(old if not old.isdigit() else old, idx)
        id_map[str(idx)] = id_map[old]

    meta: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for idx, n in enumerate(raw_nodes, start=1):
        if not isinstance(n, dict):
            continue
        old_id = str(n.get("id") or idx)
        ntype, nname, extra = _canonicalize_type_name(
            str(n.get("type") or ""), str(n.get("name") or "").strip()
        )
        meta[old_id] = (ntype, nname, extra)
        meta[str(idx)] = (ntype, nname, extra)

    out_nodes: list[dict[str, Any]] = []
    for idx, n in enumerate(raw_nodes, start=1):
        if not isinstance(n, dict):
            continue
        old_id = str(n.get("id") or idx)
        nid = id_map.get(old_id, _as_id(old_id, idx))
        ntype, nname, extra = meta.get(
            old_id, (str(n.get("type") or ""), str(n.get("name") or "").strip(), {})
        )

        inputs: dict[str, Any] = {}
        outputs: dict[str, Any] = {}

        raw_in = n.get("inputs")
        parent_ids: list[str] = []
        if isinstance(raw_in, list):
            for item in raw_in:
                if isinstance(item, (str, int)):
                    parent_ids.append(str(item))
                elif isinstance(item, dict) and "id" in item:
                    parent_ids.append(str(item["id"]))
        elif isinstance(raw_in, dict):
            inputs.update(raw_in)

        if parent_ids:
            parent_old = parent_ids[0]
            src = id_map.get(parent_old, _as_id(parent_old, 0))
            src_type, src_name, _ = meta.get(parent_old, ("", "", {}))
            pin = _source_out_pin(src_type, src_name)
            inputs["exec_in"] = f"{src}.{pin}"

        for k, v in extra.items():
            inputs.setdefault(k, v)

        raw_name = str(n.get("name") or "").strip()
        if ntype == "FunctionCall" and nname == "PrintString":
            if raw_name and raw_name.lower().replace(" ", "") not in {
                "printstring",
                "print",
                "node",
                "print string",
            }:
                if "instring" not in {k.lower() for k in inputs}:
                    inputs["InString"] = raw_name
        elif ntype == "FunctionCall" and nname == "Delay":
            if "Duration" not in inputs:
                inputs["Duration"] = 1.0

        raw_out = n.get("outputs")
        if isinstance(raw_out, dict):
            outputs.update(raw_out)

        out_nodes.append(
            {
                "id": nid,
                "type": ntype,
                "name": nname,
                "inputs": inputs,
                "outputs": outputs,
            }
        )

    by_id = {n["id"]: n for n in out_nodes}
    for n in out_nodes:
        exec_in = (n.get("inputs") or {}).get("exec_in")
        if not isinstance(exec_in, str) or "." not in exec_in:
            continue
        src_id, src_pin = exec_in.split(".", 1)
        src = by_id.get(src_id)
        if src is None:
            continue
        src_outs = src.setdefault("outputs", {})
        if _has_valid_output_keys(src_outs):
            continue
        if str(src.get("type", "")).lower() == "branch":
            continue
        src_outs[src_pin] = f"{n['id']}.exec_in"

    return {
        "graph_name": data.get("graph_name") or "BP_Graph",
        "nodes": out_nodes,
    }
