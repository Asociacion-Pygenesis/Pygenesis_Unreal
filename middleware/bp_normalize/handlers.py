"""Normalizadores concretos por tipo de nodo UE."""

from __future__ import annotations

import re

from middleware.bp_models import BPNode
from middleware.bp_normalize.pins import clean_pin_map
from middleware.bp_normalize.registry import normalizer

_REGISTERED = False


def ensure_registered() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    _REGISTERED = True
    # Los decoradores de abajo se ejecutan al importar este módulo.
    # ensure_registered solo garantiza el import una vez.


def _blob(n: BPNode) -> str:
    return f"{n.type}{n.name}".lower().replace(" ", "").replace("_", "")


@normalizer(lambda n: "launchcharacter" in _blob(n), name="LaunchCharacter")
def normalize_launch(node: BPNode) -> BPNode:
    inputs = dict(node.inputs or {})
    # Velocity_X/Y/Z → LaunchVelocity
    if "LaunchVelocity" not in inputs:
        if all(k in inputs for k in ("Velocity_X", "Velocity_Y", "Velocity_Z")):
            try:
                inputs["LaunchVelocity"] = [
                    float(inputs.pop("Velocity_X")),
                    float(inputs.pop("Velocity_Y")),
                    float(inputs.pop("Velocity_Z")),
                ]
            except (TypeError, ValueError):
                pass
        elif "Velocity_Y" in inputs and "LaunchVelocity" not in inputs:
            # Modelo raro: Velocity_Y=700 como impulso vertical
            try:
                z = float(inputs.get("Velocity_Y", 700))
                x = float(inputs.get("Velocity_X", 0))
                inputs["LaunchVelocity"] = [x, 0.0, z if z else 700.0]
            except (TypeError, ValueError):
                inputs["LaunchVelocity"] = [0.0, 0.0, 700.0]
            for k in list(inputs):
                if k.startswith("Velocity_") or k.startswith("XYOverride_"):
                    inputs.pop(k, None)
        elif "TargetLocation" in inputs:
            inputs.pop("TargetLocation", None)

    lv = inputs.get("LaunchVelocity")
    # Nombre tipo "Saltar con velocidad 700" → Z
    if not isinstance(lv, list) or len(lv) < 3:
        m = re.search(
            r"(?:velocidad|velocity|speed)\s*[:=]?\s*\(?\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)",
            node.name or "",
            re.I,
        )
        if m:
            try:
                lv = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
            except ValueError:
                lv = None
        if not isinstance(lv, list):
            m2 = re.search(
                r"(?:velocidad|velocity|speed)\s*[:=]?\s*([-\d.]+)",
                node.name or "",
                re.I,
            )
            if m2:
                try:
                    lv = [0.0, 0.0, float(m2.group(1))]
                except ValueError:
                    lv = None
    if isinstance(lv, str):
        parts = [p.strip() for p in lv.strip("[]()").split(",")]
        try:
            lv = [float(parts[i]) if i < len(parts) else 0.0 for i in range(3)]
        except ValueError:
            lv = [0.0, 0.0, 700.0]
    if not isinstance(lv, list) or len(lv) < 3:
        lv = [0.0, 0.0, 700.0]
    else:
        try:
            lv = [float(lv[0]), float(lv[1]), float(lv[2])]
        except (TypeError, ValueError):
            lv = [0.0, 0.0, 700.0]
    # Convención salto: Z positivo
    if lv[2] == 0.0 and lv[1] != 0.0 and lv[0] == 0.0:
        lv = [0.0, 0.0, abs(float(lv[1]))]
    inputs["LaunchVelocity"] = lv
    inputs["XYOverride"] = bool(inputs.get("XYOverride", True))
    inputs["ZOverride"] = bool(inputs.get("ZOverride", True))
    for junk in (
        "Velocity_X",
        "Velocity_Y",
        "Velocity_Z",
        "XYOverride_Z",
        "TargetLocation",
    ):
        inputs.pop(junk, None)
    return node.model_copy(
        update={
            "type": "FunctionCall",
            "name": "LaunchCharacter",
            "inputs": inputs,
            "outputs": clean_pin_map(node.outputs or {}, is_outputs=True),
        }
    )


@normalizer(lambda n: "printstring" in _blob(n), name="PrintString")
def normalize_print(node: BPNode) -> BPNode:
    inputs = dict(node.inputs or {})
    if "InString" not in inputs or inputs.get("InString") in (None, ""):
        for alt in ("String", "In String", "Message", "Text", "Value"):
            if alt in inputs and inputs[alt] not in (None, ""):
                inputs["InString"] = inputs.pop(alt)
                break
            inputs.pop(alt, None)
    msg = inputs.get("InString")
    if isinstance(msg, list) and msg:
        msg = msg[0]
    if isinstance(msg, str):
        msg = msg.strip().strip('"').strip("'")
    inputs["InString"] = msg if isinstance(msg, str) else ("" if msg is None else str(msg))
    inputs.pop("Duration", None)  # basura si venía en Print
    return node.model_copy(
        update={"type": "FunctionCall", "name": "PrintString", "inputs": inputs}
    )


@normalizer(lambda n: n.name.lower() == "delay" or "delay" in _blob(n), name="Delay")
def normalize_delay(node: BPNode) -> BPNode:
    inputs = dict(node.inputs or {})
    if "Duration" not in inputs or inputs.get("Duration") in (None, ""):
        for alt in ("DurationIn", "duration", "Time", "Seconds"):
            if alt in inputs and inputs[alt] not in (None, ""):
                try:
                    inputs["Duration"] = float(inputs.pop(alt))
                except (TypeError, ValueError):
                    inputs["Duration"] = inputs.pop(alt)
                break
    try:
        inputs["Duration"] = float(inputs.get("Duration", 1.0))
    except (TypeError, ValueError):
        inputs["Duration"] = 1.0
    return node.model_copy(
        update={"type": "FunctionCall", "name": "Delay", "inputs": inputs}
    )


@normalizer(lambda n: "addmovementinput" in _blob(n), name="AddMovementInput")
def normalize_move(node: BPNode) -> BPNode:
    # El pin real de APawn::AddMovementInput es "WorldDirection": cualquier otro
    # alias hace que FindPin falle en el applier y el vector quede en (0,0,0).
    inputs = dict(node.inputs or {})
    if "WorldDirection" not in inputs:
        for alt in ("WorldDirectionVector", "Direction", "Dir", "Vector"):
            if alt in inputs and inputs[alt] not in (None, ""):
                val = inputs.pop(alt)
                if isinstance(val, list) and len(val) >= 3:
                    try:
                        inputs["WorldDirection"] = [
                            float(val[0]),
                            float(val[1]),
                            float(val[2]),
                        ]
                    except (TypeError, ValueError):
                        pass
                elif isinstance(val, str):
                    parts = [p.strip() for p in val.strip("[]()").split(",")]
                    if len(parts) >= 3:
                        try:
                            inputs["WorldDirection"] = [float(p) for p in parts[:3]]
                        except ValueError:
                            pass
                break
    if "WorldDirection" not in inputs:
        inputs["WorldDirection"] = [1.0, 0.0, 0.0]
    if "ScaleValue" not in inputs:
        inputs["ScaleValue"] = 1.0
    for junk in ("WorldDirectionVector", "Direction", "Dir", "Vector"):
        inputs.pop(junk, None)
    return node.model_copy(
        update={
            "type": "FunctionCall",
            "name": "AddMovementInput",
            "inputs": inputs,
            "outputs": clean_pin_map(node.outputs or {}, is_outputs=True),
        }
    )


@normalizer(lambda n: n.type.lower() == "inputkey", name="InputKey")
def normalize_input_key(node: BPNode) -> BPNode:
    name = node.name.strip() or "F"
    if name.replace(" ", "").lower() in {"space", "spacebar"}:
        name = "SpaceBar"
    elif len(name) == 1:
        name = name.upper()
    inputs = {k: v for k, v in (node.inputs or {}).items() if "event" not in str(k).lower()}
    return node.model_copy(
        update={
            "type": "InputKey",
            "name": name,
            "inputs": inputs,
            "outputs": clean_pin_map(node.outputs or {}, is_outputs=True),
        }
    )


@normalizer(
    lambda n: n.type.lower() == "event" or "beginplay" in _blob(n),
    name="Event",
)
def normalize_event(node: BPNode) -> BPNode:
    name = node.name
    blob = _blob(node)
    if "beginplay" in blob:
        name = "EventBeginPlay"
    elif "tick" in blob:
        name = "EventTick"
    elif "beginoverlap" in blob:
        name = "EventActorBeginOverlap"
    return node.model_copy(
        update={
            "type": "Event",
            "name": name,
            "inputs": {
                k: v
                for k, v in (node.inputs or {}).items()
                if str(k).lower() not in {"exec_in", "actorclass"}
            },
            "outputs": clean_pin_map(node.outputs or {}, is_outputs=True),
        }
    )


@normalizer(lambda n: n.type.lower() == "branch" or "branch" in _blob(n), name="Branch")
def normalize_branch(node: BPNode) -> BPNode:
    inputs = dict(node.inputs or {})
    if "Condition" not in inputs:
        inputs["Condition"] = True
    return node.model_copy(
        update={
            "type": "Branch",
            "name": "Branch",
            "inputs": inputs,
            "outputs": clean_pin_map(node.outputs or {}, is_outputs=True),
        }
    )


_ROTATOR_RE = re.compile(
    r"^[\[\(]?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*[\]\)]?$"
)


def _as_pitch_yaw_roll(value: object) -> list[float] | None:
    """[pitch, yaw, roll]. Acepta array o el texto '[0,90,0]'."""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return [float(value[0]), float(value[1]), float(value[2])]
        except (TypeError, ValueError):
            return None
    if isinstance(value, str):
        match = _ROTATOR_RE.match(value.strip())
        if match:
            return [float(match.group(1)), float(match.group(2)), float(match.group(3))]
    return None


@normalizer(lambda n: "setactorrotation" in _blob(n), name="SetActorRotation")
def normalize_set_rotation(node: BPNode) -> BPNode:
    inputs = dict(node.inputs or {})
    parsed = _as_pitch_yaw_roll(inputs.get("NewRotation"))
    if parsed is not None:
        inputs["NewRotation"] = parsed
    return node.model_copy(update={"inputs": inputs})


@normalizer(lambda n: "destroyactor" in _blob(n), name="DestroyActor")
def normalize_destroy(node: BPNode) -> BPNode:
    return node.model_copy(
        update={"type": "FunctionCall", "name": "DestroyActor"}
    )


# Registrar al importar
ensure_registered()
