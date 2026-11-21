"""Huecos semánticos vs prompt: dispara continue, no inventa nodos."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from middleware.bp_complete import missing_vs_prompt  # noqa: E402
from prompts.bp_system import UNREAL_SYSTEM_BP  # noqa: E402


BRANCH_SHORT = {
    "graph_name": "BP_Branch",
    "nodes": [
        {"id": "node_01", "type": "Event", "name": "EventBeginPlay", "inputs": {}, "outputs": {"exec_out": "node_02.exec_in"}},
        {"id": "node_02", "type": "Branch", "name": "Branch", "inputs": {"exec_in": "node_01.exec_out", "Condition": True}, "outputs": {"then": "node_03.exec_in"}},
        {"id": "node_03", "type": "FunctionCall", "name": "PrintString", "inputs": {"exec_in": "node_02.then", "InString": "OK"}, "outputs": {}},
    ],
}

HOLA_SHORT = {
    "graph_name": "BP_HelloWorld",
    "nodes": [
        {"id": "node_01", "type": "Event", "name": "EventBeginPlay", "inputs": {}, "outputs": {"exec_out": "node_02.exec_in"}},
        {"id": "node_02", "type": "FunctionCall", "name": "PrintString", "inputs": {"exec_in": "node_01.exec_out", "InString": "Hola"}, "outputs": {"exec_out": "node_03.exec_in"}},
        {"id": "node_03", "type": "FunctionCall", "name": "Delay", "inputs": {"exec_in": "node_02.exec_out", "Duration": 1.0}, "outputs": {}},
    ],
}

STRAFE_SHORT = {
    "graph_name": "BP_Character_Strafe",
    "nodes": [
        {"id": "node_01", "type": "InputKey", "name": "A", "inputs": {}, "outputs": {"Pressed": "node_02.exec_in"}},
        {"id": "node_02", "type": "FunctionCall", "name": "AddMovementInput", "inputs": {"exec_in": "node_01.Pressed", "WorldDirection": [-1.0, 0.0, 0.0], "ScaleValue": 1.0}, "outputs": {}},
    ],
}

F_OK = {
    "graph_name": "FKeyInteraction",
    "nodes": [
        {"id": "node_01", "type": "InputKey", "name": "F", "inputs": {}, "outputs": {"Pressed": "node_02.exec_in"}},
        {"id": "node_02", "type": "FunctionCall", "name": "PrintString", "inputs": {"exec_in": "node_01.Pressed", "InString": "Interactuando"}, "outputs": {}},
    ],
}


def test_branch_sin_else_detecta_hueco():
    gaps = missing_vs_prompt(
        'Branch tras BeginPlay; si true imprime "OK", si false "FAIL"',
        BRANCH_SHORT,
    )
    assert any("else" in g.lower() or "FAIL" in g or "dos salidas" in g for g in gaps), gaps


def test_hola_mundo_sin_segundo_print():
    gaps = missing_vs_prompt(
        'BeginPlay → PrintString "Hola" → Delay 1s → PrintString "Mundo"',
        HOLA_SHORT,
    )
    assert any("Mundo" in g or "pocos nodos" in g for g in gaps), gaps


def test_strafe_solo_dos_movimientos_pide_las_teclas():
    gaps = missing_vs_prompt(
        "Crea un Blueprint Character: tecla A strafe izquierda y D strafe derecha con AddMovementInput.",
        {
            "graph_name": "Character Strafing",
            "nodes": [
                {
                    "id": "node_01",
                    "type": "FunctionCall",
                    "name": "AddMovementInput",
                    "inputs": {"WorldDirection": [0, -1, 0], "ScaleValue": 1},
                    "outputs": {"exec_out": "node_02.exec_in"},
                },
                {
                    "id": "node_02",
                    "type": "FunctionCall",
                    "name": "AddMovementInput",
                    "inputs": {"exec_in": "node_01.exec_out", "WorldDirection": [0, 1, 0], "ScaleValue": 1},
                    "outputs": {},
                },
            ],
        },
    )
    assert any("InputKey A" in g for g in gaps), gaps
    assert any("InputKey D" in g for g in gaps), gaps


def test_strafe_sin_d():
    gaps = missing_vs_prompt(
        "Character: tecla A strafe izquierda y D strafe derecha con AddMovementInput",
        STRAFE_SHORT,
    )
    assert any("InputKey D" in g for g in gaps), gaps


def test_patrulla_solo_beginplay_pide_los_dos_movimientos():
    gaps = missing_vs_prompt(
        "Crea un Blueprint de patrulla: BeginPlay → AIMoveTo al punto (400, 0, 0) "
        "→ Delay 2s → AIMoveTo al punto (-400, 0, 0). Sin teclas y sin EventTick.",
        {
            "graph_name": "Patrulla",
            "nodes": [
                {
                    "id": "node_01",
                    "type": "Event",
                    "name": "BeginPlay",
                    "inputs": {},
                    "outputs": {"exec_out": "node_02.exec_in"},
                }
            ],
        },
    )
    assert any("AIMoveTo" in g and "0<2" in g for g in gaps), gaps
    assert any("Delay" in g for g in gaps), gaps


def test_jump_no_exige_launchcharacter():
    gaps = missing_vs_prompt(
        "al pulsar Espacio llama a Jump. Sin EventTick y sin LaunchCharacter.",
        {
            "graph_name": "CharacterJump",
            "nodes": [
                {"id": "node_01", "type": "InputKey", "name": "SpaceBar", "inputs": {}, "outputs": {"Pressed": "node_02.exec_in"}},
                {"id": "node_02", "type": "FunctionCall", "name": "Jump", "inputs": {"exec_in": "node_01.Pressed"}, "outputs": {}},
            ],
        },
    )
    assert not any("LaunchCharacter" in g for g in gaps), gaps
    assert not any("Jump" in g for g in gaps), gaps


def test_grafo_completo_sin_huecos():
    gaps = missing_vs_prompt(
        'al pulsar F imprime "Interactuando" con PrintString',
        F_OK,
    )
    assert gaps == [], gaps


def test_bp_system_sin_anclar_a_tests():
    # No few-shots que clonen los prompts de prueba ni "copia el patrón".
    assert "copia el patrón" not in UNREAL_SYSTEM_BP.lower()
    assert "BP_HelloWorld" not in UNREAL_SYSTEM_BP
    assert "BP_Character_Strafe" not in UNREAL_SYSTEM_BP
    assert '"FAIL"' not in UNREAL_SYSTEM_BP
    assert "Emite TODOS los nodos" in UNREAL_SYSTEM_BP
    assert "AIMoveTo" in UNREAL_SYSTEM_BP
    assert 'name":"PrintString"|"Delay"' not in UNREAL_SYSTEM_BP
