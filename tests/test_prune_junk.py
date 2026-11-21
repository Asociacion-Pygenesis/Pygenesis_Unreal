"""Prune: Print huérfano, BeginPlay espurio, pines Launch basura."""

from __future__ import annotations

from middleware.bp_lite import prepare_apply_payload


def test_drop_orphan_print_on_launch() -> None:
    raw = {
        "graph_name": "BP_LaunchCharacter",
        "nodes": [
            {
                "id": "node_01",
                "type": "InputKey",
                "name": "SpaceBar",
                "inputs": {},
                "outputs": {"Pressed": "node_02.exec_in"},
            },
            {
                "id": "node_02",
                "type": "FunctionCall",
                "name": "LaunchCharacter",
                "inputs": {
                    "exec_in": "node_01.Pressed",
                    "LaunchVelocity": [0.0, 0.0, 700.0],
                    "XYOverride": True,
                    "ZOverride": True,
                },
                "outputs": {"SpeedZ": 0, "VelocityScale": 7.0},
            },
            {
                "id": "node_03",
                "type": "FunctionCall",
                "name": "PrintString",
                "inputs": {"InString": "Velocidad: 700 m/s"},
                "outputs": {},
            },
        ],
    }
    r = prepare_apply_payload(
        raw,
        user_prompt="al pulsar Espacio haz LaunchCharacter con velocidad (0,0,700)",
    )
    assert r.get("ok"), r
    names = [n["name"] for n in r["graph"]["nodes"]]
    assert names == ["SpaceBar", "LaunchCharacter"], names
    launch = r["graph"]["nodes"][1]
    assert "SpeedZ" not in (launch.get("outputs") or {})
    assert "VelocityScale" not in (launch.get("outputs") or {})


def test_drop_spurious_beginplay_on_strafe() -> None:
    raw = {
        "graph_name": "BP_Character_Strafe",
        "nodes": [
            {
                "id": "node_01",
                "type": "InputKey",
                "name": "A",
                "inputs": {},
                "outputs": {"Pressed": "node_02.exec_in"},
            },
            {
                "id": "node_02",
                "type": "FunctionCall",
                "name": "AddMovementInput",
                "inputs": {
                    "exec_in": "node_01.Pressed",
                    "WorldDirectionVector": [0.0, -1.0, 0.0],
                    "ScaleValue": 1.0,
                },
                "outputs": {},
            },
            {
                "id": "node_03",
                "type": "Event",
                "name": "EventBeginPlay",
                "inputs": {},
                "outputs": {},
            },
            {
                "id": "node_04",
                "type": "InputKey",
                "name": "D",
                "inputs": {},
                "outputs": {"Pressed": "node_05.exec_in"},
            },
            {
                "id": "node_05",
                "type": "FunctionCall",
                "name": "AddMovementInput",
                "inputs": {
                    "exec_in": "node_04.Pressed",
                    "WorldDirectionVector": [0.0, 1.0, 0.0],
                    "ScaleValue": 1.0,
                },
                "outputs": {},
            },
        ],
    }
    r = prepare_apply_payload(
        raw,
        user_prompt="tecla A strafe izquierda y D strafe derecha con AddMovementInput",
    )
    assert r.get("ok"), r
    names = [n["name"] for n in r["graph"]["nodes"]]
    assert "EventBeginPlay" not in names, names
    assert names.count("AddMovementInput") == 2


def test_dos_addmovement_sin_teclas_no_se_encadenan() -> None:
    prompt = "tecla A strafe izquierda y D strafe derecha con AddMovementInput"
    raw = {
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
                "inputs": {
                    "exec_in": "node_01.exec_out",
                    "WorldDirection": [0, 1, 0],
                    "ScaleValue": 1,
                },
                "outputs": {},
            },
        ],
    }
    r = prepare_apply_payload(raw, user_prompt=prompt)
    assert r.get("ok"), r
    nodes = r["graph"]["nodes"]
    assert [n["name"] for n in nodes] == ["AddMovementInput", "AddMovementInput"]
    assert not any(n["type"] == "InputKey" for n in nodes)
    assert nodes[0]["inputs"]["WorldDirection"] == [0.0, -1.0, 0.0]
    assert nodes[1]["inputs"]["WorldDirection"] == [0.0, 1.0, 0.0]
    assert "exec_in" not in (nodes[1].get("inputs") or {})
    assert not (nodes[0].get("outputs") or {})


def test_keep_print_when_prompt_asks() -> None:
    raw = {
        "graph_name": "FPrint",
        "nodes": [
            {
                "id": "node_01",
                "type": "InputKey",
                "name": "F",
                "inputs": {},
                "outputs": {"Pressed": "node_02.exec_in"},
            },
            {
                "id": "node_02",
                "type": "FunctionCall",
                "name": "PrintString",
                "inputs": {
                    "exec_in": "node_01.Pressed",
                    "InString": "Interactuando",
                },
                "outputs": {},
            },
        ],
    }
    r = prepare_apply_payload(
        raw,
        user_prompt='al pulsar F imprime "Interactuando" con PrintString',
    )
    assert r.get("ok"), r
    assert [n["name"] for n in r["graph"]["nodes"]] == ["F", "PrintString"]
