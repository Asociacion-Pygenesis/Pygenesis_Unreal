"""Clasificación de aliases LLM → type/name canónicos BP-Lite.

Clasifica con type/name/id; io_blob solo como pista secundaria mínima (claves de pin).
"""

from __future__ import annotations

import re
from typing import Any

from middleware.bp_normalize.pins import io_type_hint_blob


def classify_node(raw: dict[str, Any], *, graph_name: str = "") -> dict[str, str]:
    raw_type = raw.get("type")
    ntype = str(raw_type if raw_type is not None else "") or "FunctionCall"
    nname = str(raw.get("name") or "").strip()
    nid = str(raw.get("id") or "").strip()
    if not nname:
        if nid and nid.lower() not in {"node", "none", "null"} and not re.match(
            r"^node_?\d+$", nid, re.I
        ):
            nname = nid
        else:
            nname = ntype if ntype not in {"", "None", "null"} else "Node"

    # Primario: type / name / id — no valores de pines (evita Delay/Branch por cables)
    identity = f"{ntype} {nname} {nid}".lower().replace(" ", "").replace("_", "")
    pin_keys = io_type_hint_blob(raw.get("inputs"), raw.get("outputs"))
    # Pista secundaria mínima: solo si identity no alcanza (p.ej. InString → Print)
    low = identity
    title = (graph_name or "").lower().replace(" ", "")

    key_letter = _detect_key_letter(raw, ntype, nname, identity)

    if (
        "eventinput" in low
        or ntype.lower() in {"eventinputnode", "eventinput", "inputeventnode"}
    ):
        if any(x in title for x in ("launch", "space", "jump", "espacio")):
            return {"type": "InputKey", "name": "SpaceBar"}
        if "beginplay" in low:
            return {"type": "Event", "name": "EventBeginPlay"}
        return {"type": "InputKey", "name": key_letter or "F"}

    if "eventtick" in low or low in {"tick", "receivetick"}:
        return {"type": "Event", "name": "EventTick"}
    if "beginplay" in low and "eventinput" not in low:
        return {"type": "Event", "name": "EventBeginPlay"}
    if any(
        x in low
        for x in (
            "actorbeginoverlap",
            "beginoverlap",
            "getalloverlapping",
            "getoverlappingactors",
            "overlappingactors",
        )
    ):
        return {"type": "Event", "name": "EventActorBeginOverlap"}
    if "actorendoverlap" in low or "endoverlap" in low:
        return {"type": "Event", "name": "EventActorEndOverlap"}
    if "actorhit" in low or low.endswith("eventhit"):
        return {"type": "Event", "name": "EventHit"}
    if "destroyactor" in low or ("destroy" in low and "actor" in low):
        return {"type": "FunctionCall", "name": "DestroyActor"}
    if "launch" in low and "character" in low:
        return {"type": "FunctionCall", "name": "LaunchCharacter"}
    if "addmovementinput" in low or "addmovement" in low:
        return {"type": "FunctionCall", "name": "AddMovementInput"}
    # Delay/Branch: solo por type/name/id (nunca por valores de pines)
    if "delay" in identity or ntype.lower() in {"delay", "delaynode"}:
        return {"type": "FunctionCall", "name": "Delay"}
    if "branch" in identity or ntype.lower() in {"branch", "if", "ifthenelse"}:
        return {"type": "Branch", "name": "Branch"}

    if (
        "inputkeyevent" in low
        or "inputkeynode" in low
        or "eventinputkey" in low
        or ntype.lower()
        in {
            "inputkey",
            "inputkeynode",
            "inputkeyeventnode",
            "inputkeyevent",
            "keyevent",
            "eventinputkeynode",
        }
    ):
        return {"type": "InputKey", "name": key_letter or "F"}

    if key_letter and (
        "trigger" in low
        or "pressed" in pin_keys
        or "inputkey" in low
        or ntype.lower() in {"inputkey", "eventtriggernode", "key"}
    ):
        return {"type": "InputKey", "name": key_letter}

    if "inputkey" in low or "spacebar" in low or low in {"space", "teclaespacio"}:
        return {"type": "InputKey", "name": "SpaceBar"}

    # Event_InputAction_F / InputAction_W / Spacebar (dialecto Ollama)
    m_ia = re.search(
        r"inputaction[_]?([a-z0-9]+)|eventinputaction[_]?([a-z0-9]+)",
        identity,
        re.I,
    )
    if m_ia or "inputaction" in low:
        tok = (m_ia.group(1) or m_ia.group(2) or "").lower() if m_ia else ""
        if tok in {"spacebar", "space", "jump"} or "jump" in low or "space" in low:
            return {"type": "InputKey", "name": "SpaceBar"}
        if len(tok) == 1 and tok.isalpha():
            return {"type": "InputKey", "name": tok.upper()}
        m_kn = re.search(r"\b([A-Za-z])\s*key\b", nname, re.I)
        if m_kn:
            return {"type": "InputKey", "name": m_kn.group(1).upper()}
        if key_letter:
            return {"type": "InputKey", "name": key_letter}
        m_path = re.search(r"inputactions[./]([a-z])\b", low)
        if m_path:
            return {"type": "InputKey", "name": m_path.group(1).upper()}
        return {"type": "InputKey", "name": "F"}

    if low.startswith("input") and "jump" in low:
        return {"type": "InputKey", "name": "SpaceBar"}

    if ntype.lower() == "launchcharacter" or nname.lower().replace(" ", "") == "launchcharacter":
        return {"type": "FunctionCall", "name": "LaunchCharacter"}

    if "printstring" in identity or ntype.lower() in {
        "printstring",
        "printstringnode",
        "functioncall printstring",
    }:
        return {"type": "FunctionCall", "name": "PrintString"}
    if "instring" in pin_keys or ("print" in identity and "string" in identity):
        return {"type": "FunctionCall", "name": "PrintString"}

    if "functioncall" in low.replace(" ", "") or "functioncallnode" in low:
        nid_l = nid.lower().replace(" ", "").replace("_", "")
        if "destroy" in low or "destroyactor" in nid_l:
            return {"type": "FunctionCall", "name": "DestroyActor"}
        if "launch" in low or "launchcharacter" in nid_l:
            return {"type": "FunctionCall", "name": "LaunchCharacter"}
        if "addmovement" in low or "addmovementinput" in nid_l:
            return {"type": "FunctionCall", "name": "AddMovementInput"}
        if "delay" in identity or nid_l == "delay":
            return {"type": "FunctionCall", "name": "Delay"}
        if "print" in identity or "instring" in pin_keys:
            return {"type": "FunctionCall", "name": "PrintString"}
        if nname.lower() in {"node", "null", "none", "functioncallnode", "functioncall", ""}:
            return {"type": "FunctionCall", "name": "PrintString"}
        return {"type": "FunctionCall", "name": nname}

    if "eventgraphnode" in low or (("event" in low or "trigger" in low) and "beginplay" in low):
        return {"type": "Event", "name": "EventBeginPlay"}
    if "eventtrigger" in low or (("event" in low or "trigger" in low) and "key" in low):
        return {"type": "InputKey", "name": key_letter or "F"}
    if "event" in low or "trigger" in low:
        if not nname or nname.lower() in {"node", "eventgraphnode", "event"}:
            nname = "EventBeginPlay" if "beginplay" in low else "PygenesisEvent"
        return {"type": "Event", "name": nname}
    if "linetrace" in low:
        return {"type": "FunctionCall", "name": "LineTraceByChannel"}
    if "variable" in low and "set" in low:
        return {"type": "VariableSet", "name": nname or "VariableSet"}
    if "variable" in low and "get" in low:
        return {"type": "VariableGet", "name": nname or "VariableGet"}

    return {"type": ntype, "name": nname}


def _detect_key_letter(
    raw: dict[str, Any], ntype: str, nname: str, low: str
) -> str | None:
    if (
        "inputkeynode" in low
        or "inputkeyevent" in low
        or ntype.lower()
        in {
            "inputkey",
            "inputkeynode",
            "inputkeyeventnode",
            "inputkeyevent",
            "keyevent",
        }
    ):
        raw_name = str(raw.get("name") or "").strip()
        if raw_name.replace(" ", "").lower() in {"spacebar", "space"}:
            return "SpaceBar"
        if len(raw_name) == 1 and raw_name.isalpha():
            return raw_name.upper()
        n_key = re.search(r"\b([a-z])\s*key\b", raw_name.lower())
        if n_key:
            return n_key.group(1).upper()
        if "space" in raw_name.lower():
            return "SpaceBar"
        outs = raw.get("outputs") or {}
        if isinstance(outs, dict):
            for ok in outs.keys():
                if len(str(ok)) == 1 and str(ok).isalpha():
                    return str(ok).upper()
        return "F"

    if "inputkey" not in low:
        key_m = re.search(
            r"(?:^|[^a-z])([a-z])key(?:pressed)?|(?:key|tecla)([a-z])(?:[^a-z]|$)",
            low,
        )
        if key_m:
            return (key_m.group(1) or key_m.group(2) or "").upper() or None
        if re.search(r"\bfkey\b|fkeypressed|[^\w]fkey", low):
            return "F"
    return None
