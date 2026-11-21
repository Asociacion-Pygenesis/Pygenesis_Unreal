"""Contrato de pines entre el middleware Python y el applier C++.

El bug del vector de AddMovementInput en (0,0,0) nació de que Python emitía
`WorldDirectionVector` y el pin de UE se llama `WorldDirection`: FindPin falla
en silencio. Estos tests fijan los nombres reales y vigilan la deriva.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from middleware.bp_lite import normalize_bplite  # noqa: E402

APPLIER_CPP = (
    REPO_ROOT
    / "plugin"
    / "PygenesisUnreal"
    / "Source"
    / "PygenesisUnreal"
    / "Private"
    / "PygenesisBpLiteApplier.cpp"
)

# Nombres de pin de entrada tal y como los expone UE5 para cada nodo.
UE_INPUT_PINS: dict[str, set[str]] = {
    "PrintString": {"InString", "bPrintToScreen", "bPrintToLog", "TextColor", "Duration"},
    "Delay": {"Duration"},
    "AddMovementInput": {"WorldDirection", "ScaleValue", "bForce"},
    "LaunchCharacter": {"LaunchVelocity", "bXYOverride", "bZOverride", "XYOverride", "ZOverride"},
    "DestroyActor": set(),
    "Branch": {"Condition"},
}

EXEC_KEYS = {"exec_in", "exec_out", "execute", "then", "else"}

GRAPHS = {
    "move": {
        "graph_name": "BP_Move",
        "nodes": [
            {"id": "node_01", "type": "InputKey", "name": "W", "inputs": {}, "outputs": {"Pressed": "node_02.exec_in"}},
            {
                "id": "node_02",
                "type": "FunctionCall",
                "name": "AddMovementInput",
                "inputs": {"exec_in": "node_01.Pressed", "WorldDirectionVector": [1.0, 0.0, 0.0]},
                "outputs": {},
            },
        ],
    },
    "launch": {
        "graph_name": "BP_Launch",
        "nodes": [
            {"id": "node_01", "type": "InputKey", "name": "SpaceBar", "inputs": {}, "outputs": {"Pressed": "node_02.exec_in"}},
            {
                "id": "node_02",
                "type": "FunctionCall",
                "name": "LaunchCharacter",
                "inputs": {"exec_in": "node_01.Pressed", "LaunchVelocity": [0.0, 0.0, 700.0]},
                "outputs": {},
            },
        ],
    },
    "print_delay": {
        "graph_name": "BP_PrintDelay",
        "nodes": [
            {"id": "node_01", "type": "Event", "name": "EventBeginPlay", "inputs": {}, "outputs": {"exec_out": "node_02.exec_in"}},
            {
                "id": "node_02",
                "type": "FunctionCall",
                "name": "PrintString",
                "inputs": {"exec_in": "node_01.exec_out", "InString": "Hola"},
                "outputs": {"exec_out": "node_03.exec_in"},
            },
            {
                "id": "node_03",
                "type": "FunctionCall",
                "name": "Delay",
                "inputs": {"exec_in": "node_02.exec_out", "Duration": 2.0},
                "outputs": {},
            },
        ],
    },
}


@pytest.mark.parametrize("key", sorted(GRAPHS))
def test_solo_se_emiten_pines_que_existen_en_unreal(key):
    graph = normalize_bplite(GRAPHS[key], user_prompt="tecla y beginplay con print")
    for node in graph["nodes"]:
        allowed = UE_INPUT_PINS.get(node["name"])
        if allowed is None:
            continue
        for pin in (node.get("inputs") or {}):
            if pin.lower() in EXEC_KEYS:
                continue
            assert pin in allowed, (
                f"{node['name']} emite el pin '{pin}', que no existe en UE5. "
                f"Pines válidos: {sorted(allowed)}"
            )


def test_el_applier_resuelve_alias_de_pines():
    source = APPLIER_CPP.read_text(encoding="utf-8", errors="ignore")
    assert "FindPinWithAliases" in source, "el applier debe resolver alias de pines"
    assert "WorldDirection" in source
    # La red de seguridad tiene que usarse en el bucle genérico, no solo existir
    assert "FindPinWithAliases(Node, Key)" in source


def test_el_applier_aplica_la_condicion_del_branch():
    source = APPLIER_CPP.read_text(encoding="utf-8", errors="ignore")
    assert "ApplyDefaultsFromInputs(Branch" in source, (
        "sin esto el pin Condition queda en false y el Branch siempre va por else"
    )
