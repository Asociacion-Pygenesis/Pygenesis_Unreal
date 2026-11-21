"""Regresión sobre las respuestas reales del modelo en testunreal2.md.

Cada caso es el JSON que emitió el modelo; se comprueba el grafo que recibe el
applier C++. Estos fallos solo se veían abriendo el Blueprint en el Editor.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from middleware.bp_lite import prepare_apply_payload  # noqa: E402

F_PRINT = """{"graph_name":"FKeyInteraction","nodes":[
{"id":"node_01","type":"InputKey","name":"F","inputs":{},"outputs":{"Pressed":"node_02.exec_in"}},
{"id":"node_02","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_01.Pressed","InString":"Interactuando"},"outputs":{}}]}"""

DELAY_TINY = """{"graph_name":"BP_Launcher_Delay","nodes":[
{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},
{"id":"node_02","type":"FunctionCall","name":"Delay","inputs":{"exec_in":"node_01.exec_out","Duration":1e-06},"outputs":{}}]}"""

MOVE_W = """{"graph_name":"BP_Character_Movement","nodes":[
{"id":"node_01","type":"InputKey","name":"W","inputs":{},"outputs":{"Pressed":"node_02.exec_in"}},
{"id":"node_02","type":"FunctionCall","name":"AddMovementInput","inputs":{"exec_in":"node_01.Pressed","WorldDirectionVector":[1.0,0.0,0.0],"ScaleValue":1.0},"outputs":{}}]}"""

BRANCH_DANGLING = """{"graph_name":"BP_Branch","nodes":[
{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},
{"id":"node_02","type":"Branch","name":"Branch","inputs":{"exec_in":"node_01.exec_out","Condition":true},"outputs":{"TrueNodeID":"3","FalseNodeID":"4"}},
{"id":"node_05","type":"FunctionCall","name":"PrintString","inputs":{"InString":"OK"},"outputs":{}}]}"""

BRANCH_SELF_REF = """{"graph_name":"BP_BranchTest","nodes":[
{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},
{"id":"node_02","type":"Branch","name":"Branch","inputs":{"exec_in":"node_01.exec_out","Condition":true},"outputs":{"true_id":"3"}},
{"id":"node_04","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_04.exec_out","InString":"OK"},"outputs":{"exec_out":"node_04.exec_in"}}]}"""

HELLO_WORLD_GAP = """{"graph_name":"BP_HelloWorld","nodes":[
{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},
{"id":"node_02","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_01.exec_out","InString":"Hola,"},"outputs":{"exec_out":"node_03.exec_in"}},
{"id":"node_03","type":"FunctionCall","name":"Delay","inputs":{"exec_in":"node_02.exec_out","Duration":1.0},"outputs":{}},
{"id":"node_05","type":"FunctionCall","name":"PrintString","inputs":{"InString":"Mundo!"},"outputs":{}}]}"""

STRAFE_TRUNCATED = """```json
{"graph_name":"BP_Character_Strafe","nodes":[{"id":"1","type":"Event_InputAction_A","name":"","inputs":[],"outputs":[]},{"id":"2","type":"Add Movement Input Left","name":"Izquierda","inputs":["1"],"outputs":[]},{"id":"3","type":"Event_InputAction_D"""

LAUNCH_SPACE = """{"graph_name":"BP_LaunchCharacter","nodes":[
{"id":"node_01","type":"InputKey","name":"SpaceBar","inputs":{},"outputs":{"Pressed":"node_02.exec_in"}},
{"id":"node_02","type":"FunctionCall","name":"LaunchCharacter","inputs":{"exec_in":"node_01.Pressed","LaunchVelocity":[0.0,0.0,700.0],"XYOverride":true,"ZOverride":true},"outputs":{}}]}"""

OVERLAP = """{"graph_name":"BP_Overlap","nodes":[
{"id":"node_01","type":"Event","name":"EventActorBeginOverlap","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},
{"id":"node_02","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_01.exec_out","InString":"Overlapeo!"},"outputs":{}}]}"""


def apply_graph(text: str, prompt: str = "") -> dict:
    result = prepare_apply_payload(text, user_prompt=prompt)
    assert result.get("ok"), result.get("error")
    return result["graph"]


def nodes_by_id(graph: dict) -> dict[str, dict]:
    return {n["id"]: n for n in graph["nodes"]}


def exec_targets(node: dict) -> set[str]:
    out = set()
    for key, value in (node.get("outputs") or {}).items():
        if isinstance(value, str) and "." in value and "exec" in f"{key}{value}".lower():
            out.add(value.split(".", 1)[0])
    return out


def test_set_actor_rotation_texto_pasa_a_pitch_yaw_roll():
    raw = (
        '{"graph_name":"BeginPlay a 90 grados","nodes":['
        '{"id":"node_01","type":"Event","name":"BeginPlay","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"SetActorRotation","inputs":'
        '{"exec_in":"node_01.exec_out","NewRotation":"[0,90,0]"}}]}'
    )
    graph = apply_graph(raw, "BeginPlay → SetActorRotation a (0, 90, 0)")
    node = nodes_by_id(graph)["node_02"]
    assert node["inputs"]["NewRotation"] == [0.0, 90.0, 0.0]
    assert node["inputs"]["exec_in"] == "node_01.exec_out"


def test_get_actor_location_con_cables_cruzados():
    raw = (
        '{"graph_name":"BP-Lite BeginPlay GetActorLocation PrintString","nodes":['
        '{"id":"node_01","type":"Event","name":"BeginPlay","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"GetActorLocation","inputs":'
        '{"exec_in":"node_01.exec_out"},"outputs":{"ReturnValue":"node_03.exec_in"}},'
        '{"id":"node_03","type":"FunctionCall","name":"PrintString","inputs":'
        '{"exec_in":"node_02.ReturnValue","InString":"Posición"},"outputs":{}}]}'
    )
    graph = apply_graph(raw, 'BeginPlay → GetActorLocation → PrintString "Posición"')
    nodes = nodes_by_id(graph)
    assert "exec_in" not in nodes["node_02"]["inputs"]
    assert nodes["node_01"]["outputs"]["exec_out"] == "node_03.exec_in"
    assert nodes["node_03"]["inputs"]["exec_in"] == "node_01.exec_out"
    assert nodes["node_03"]["inputs"]["InString"] == "node_02.ReturnValue"
    assert "ReturnValue" not in (nodes["node_02"].get("outputs") or {})


def test_get_actor_location_salta_el_exec_y_alimenta_el_print():
    raw = (
        '{"graph_name":"Posición_al_inicio","nodes":['
        '{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"GetActorLocation","inputs":'
        '{"exec_in":"node_01.exec_out"},"outputs":{"ReturnValue":"[0,0,0]","exec_out":"node_03.exec_in"}},'
        '{"id":"node_03","type":"FunctionCall","name":"PrintString","inputs":'
        '{"exec_in":"node_02.exec_out","InString":"Posición"},"outputs":{}}]}'
    )
    graph = apply_graph(raw, 'BeginPlay → GetActorLocation → PrintString "Posición"')
    nodes = nodes_by_id(graph)
    assert "exec_in" not in nodes["node_02"]["inputs"]
    assert "exec_out" not in nodes["node_02"]["outputs"]
    assert nodes["node_01"]["outputs"]["exec_out"] == "node_03.exec_in"
    assert nodes["node_03"]["inputs"]["exec_in"] == "node_01.exec_out"
    assert nodes["node_03"]["inputs"]["InString"] == "node_02.ReturnValue"
    assert "ReturnValue" not in (nodes["node_02"].get("outputs") or {})


def test_overlap_jugador_salta_el_exec_y_alimenta_el_print():
    raw = (
        '{"graph_name":"ActorBeginOverlap","nodes":['
        '{"id":"node_01","type":"Event","name":"Event ActorBeginOverlap","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"GetPlayerCharacter","inputs":'
        '{"exec_in":"node_01.exec_out"},"outputs":{"ReturnValue":"node_03.exec_in"}},'
        '{"id":"node_03","type":"FunctionCall","name":"PrintString","inputs":'
        '{"exec_in":"node_02.ReturnValue","InString":"Jugador"},"outputs":{}}]}'
    )
    graph = apply_graph(
        raw,
        'Event ActorBeginOverlap → GetPlayerCharacter → PrintString "Jugador"',
    )
    nodes = nodes_by_id(graph)
    assert nodes["node_01"]["name"] == "EventActorBeginOverlap"
    assert "exec_in" not in nodes["node_02"]["inputs"]
    assert "ReturnValue" not in (nodes["node_02"].get("outputs") or {})
    assert nodes["node_01"]["outputs"]["exec_out"] == "node_03.exec_in"
    assert nodes["node_03"]["inputs"]["exec_in"] == "node_01.exec_out"
    assert nodes["node_03"]["inputs"]["InString"] == "node_02.ReturnValue"


def test_target_actor_a_nodo_inexistente_se_quita():
    raw = (
        '{"graph_name":"Enemigo_AIMoveTo","nodes":['
        '{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"AIMoveTo","inputs":'
        '{"exec_in":"node_01.exec_out","TargetActor":"node_03.exec_in"},"outputs":{}}]}'
    )
    graph = apply_graph(
        raw,
        "Crea un Blueprint de enemigo: BeginPlay → AIMoveTo hacia el actor objetivo. Sin teclas y sin EventTick.",
    )
    nodes = nodes_by_id(graph)
    assert [n["id"] for n in graph["nodes"]] == ["node_01", "node_02"]
    assert nodes["node_02"]["name"] == "AIMoveTo"
    assert "TargetActor" not in nodes["node_02"]["inputs"]
    assert "Destination" not in nodes["node_02"]["inputs"]
    assert nodes["node_02"]["inputs"]["exec_in"] == "node_01.exec_out"


def test_target_actor_conserva_el_return_del_jugador():
    raw = (
        '{"graph_name":"Enemigo_PersigueJugador","nodes":['
        '{"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},'
        '"outputs":{"exec_out":"node_03.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"GetPlayerCharacter","inputs":{},'
        '"outputs":{"ReturnValue":"node_03.TargetActor"}},'
        '{"id":"node_03","type":"FunctionCall","name":"AIMoveTo","inputs":'
        '{"exec_in":"node_01.exec_out","TargetActor":"node_02.ReturnValue"},"outputs":{}}]}'
    )
    graph = apply_graph(
        raw,
        "BeginPlay → AIMoveTo hacia el jugador. GetPlayerCharacter ReturnValue al pin TargetActor.",
    )
    nodes = nodes_by_id(graph)
    assert nodes["node_02"]["name"] == "GetPlayerCharacter"
    assert nodes["node_03"]["inputs"]["TargetActor"] == "node_02.ReturnValue"
    assert nodes["node_03"]["inputs"]["exec_in"] == "node_01.exec_out"
    assert "exec_in" not in (nodes["node_02"].get("inputs") or {})


def test_input_key_print_chain_intacta():
    graph = apply_graph(F_PRINT, 'Al pulsar F imprime "Interactuando"')
    nodes = nodes_by_id(graph)
    assert nodes["node_01"]["type"] == "InputKey"
    assert nodes["node_01"]["name"] == "F"
    assert exec_targets(nodes["node_01"]) == {"node_02"}
    assert nodes["node_02"]["inputs"]["InString"] == "Interactuando"


def test_overlap_event_se_conserva():
    graph = apply_graph(OVERLAP, 'Event ActorBeginOverlap → PrintString "Overlap"')
    nodes = nodes_by_id(graph)
    assert nodes["node_01"]["name"] == "EventActorBeginOverlap"
    assert exec_targets(nodes["node_01"]) == {"node_02"}


def test_espacio_jump_sustituye_el_launch_prohibido():
    raw = (
        '{"graph_name":"CharacterJump","nodes":['
        '{"id":"node_01","type":"InputKey","name":"Space","inputs":{},'
        '"outputs":{"Pressed":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"LaunchCharacter","inputs":'
        '{"exec_in":"node_01.Pressed","LaunchVelocity":[0,0,-1000],'
        '"XYOverride":0,"ZOverride":0},"outputs":{}}]}'
    )
    graph = apply_graph(
        raw,
        "Crea un Blueprint Character: al pulsar Espacio llama a Jump. "
        "Sin EventTick y sin LaunchCharacter.",
    )
    jump = nodes_by_id(graph)["node_02"]
    assert jump["name"] == "Jump"
    assert jump["inputs"]["exec_in"] == "node_01.Pressed"
    assert "LaunchVelocity" not in jump["inputs"]
    assert "XYOverride" not in jump["inputs"]
    assert exec_targets(nodes_by_id(graph)["node_01"]) == {"node_02"}


def test_launch_velocity_se_conserva():
    graph = apply_graph(LAUNCH_SPACE, "Al pulsar Espacio LaunchCharacter (0,0,700)")
    launch = nodes_by_id(graph)["node_02"]
    assert launch["inputs"]["LaunchVelocity"] == [0.0, 0.0, 700.0]
    assert launch["inputs"]["XYOverride"] is True


def test_duration_absurda_se_toma_del_prompt():
    graph = apply_graph(DELAY_TINY, "BeginPlay → Delay 2s → PrintString Listo")
    assert nodes_by_id(graph)["node_02"]["inputs"]["Duration"] == 2.0


def test_movimiento_usa_el_pin_real_de_unreal():
    graph = apply_graph(MOVE_W, "Tecla W llama a AddMovementInput hacia adelante")
    move = nodes_by_id(graph)["node_02"]
    # El pin de APawn::AddMovementInput es WorldDirection: con otro nombre el
    # applier no lo encuentra y el vector queda en (0,0,0)
    assert move["inputs"]["WorldDirection"] == [1.0, 0.0, 0.0]
    assert "WorldDirectionVector" not in move["inputs"]
    assert move["inputs"]["ScaleValue"] == 1.0


def test_print_huerfano_se_cablea_en_vez_de_borrarse():
    prompt = 'BeginPlay → PrintString "Hola" → Delay 1s → PrintString "Mundo"'
    graph = apply_graph(HELLO_WORLD_GAP, prompt)
    nodes = nodes_by_id(graph)
    assert len(nodes) == 4, "el segundo PrintString no debe perderse"
    huerfano = nodes["node_05"]
    assert huerfano["inputs"].get("exec_in") == "node_03.exec_out"
    assert exec_targets(nodes["node_03"]) == {"node_05"}


def test_print_huerfano_sobrevive_sin_prompt():
    # El plugin antiguo no enviaba el prompt: aun así no debe perder nodos
    graph = apply_graph(HELLO_WORLD_GAP)
    assert len(graph["nodes"]) == 4


def test_branch_ramas_canonicas_y_reconectadas():
    prompt = 'Branch tras BeginPlay; si true imprime "OK", si false "FAIL"'
    graph = apply_graph(BRANCH_DANGLING, prompt)
    nodes = nodes_by_id(graph)
    branch = nodes["node_02"]
    assert "TrueNodeID" not in branch["outputs"]
    assert "FalseNodeID" not in branch["outputs"]
    # El único Print que emitió el modelo cuelga de una rama real del Branch
    assert branch["outputs"].get("then") == "node_05.exec_in"
    assert nodes["node_05"]["inputs"]["exec_in"] == "node_02.then"


def test_branch_autorreferencia_se_reconecta():
    prompt = 'Branch tras BeginPlay; si true imprime "OK", si false "FAIL"'
    graph = apply_graph(BRANCH_SELF_REF, prompt)
    nodes = nodes_by_id(graph)
    print_node = nodes["node_04"]
    assert print_node["inputs"]["exec_in"] == "node_02.then"
    assert print_node["outputs"] == {}, "la autorreferencia debe desaparecer"


def test_branch_reparte_dos_prints_entre_then_y_else():
    raw = {
        "graph_name": "BP_Branch",
        "nodes": [
            {"id": "node_01", "type": "Event", "name": "EventBeginPlay", "inputs": {}, "outputs": {"exec_out": "node_02.exec_in"}},
            {"id": "node_02", "type": "Branch", "name": "Branch", "inputs": {"exec_in": "node_01.exec_out", "Condition": True}, "outputs": {}},
            {"id": "node_03", "type": "FunctionCall", "name": "PrintString", "inputs": {"InString": "OK"}, "outputs": {}},
            {"id": "node_04", "type": "FunctionCall", "name": "PrintString", "inputs": {"InString": "FAIL"}, "outputs": {}},
        ],
    }
    graph = apply_graph(raw, 'Branch tras BeginPlay; si true imprime "OK", si false "FAIL"')
    branch = nodes_by_id(graph)["node_02"]
    assert branch["outputs"]["then"] == "node_03.exec_in"
    assert branch["outputs"]["else"] == "node_04.exec_in"


def test_nodo_distinto_tras_una_rama_sigue_la_cadena():
    # Un Delay suelto detrás del Print de la rama true continúa la cadena;
    # no debe secuestrar el pin else del Branch.
    raw = {
        "graph_name": "BP_B2",
        "nodes": [
            {"id": "node_01", "type": "Event", "name": "EventBeginPlay", "inputs": {}, "outputs": {"exec_out": "node_02.exec_in"}},
            {"id": "node_02", "type": "Branch", "name": "Branch", "inputs": {"exec_in": "node_01.exec_out", "Condition": True}, "outputs": {"then": "node_03.exec_in"}},
            {"id": "node_03", "type": "FunctionCall", "name": "PrintString", "inputs": {"exec_in": "node_02.then", "InString": "OK"}, "outputs": {}},
            {"id": "node_04", "type": "FunctionCall", "name": "Delay", "inputs": {"Duration": 1.0}, "outputs": {}},
        ],
    }
    graph = apply_graph(raw, "Branch tras BeginPlay imprime OK y luego espera 1s")
    nodes = nodes_by_id(graph)
    assert nodes["node_04"]["inputs"]["exec_in"] == "node_03.exec_out"
    assert "else" not in nodes["node_02"]["outputs"]


def test_json_truncado_salva_los_nodos_completos():
    result = prepare_apply_payload(
        STRAFE_TRUNCATED, user_prompt="Tecla A strafe izquierda y D strafe derecha"
    )
    assert result.get("ok"), result.get("error")
    nodes = result["graph"]["nodes"]
    # A + Add Movement Input Left llegaron completos; el nodo a medias se descarta
    assert len(nodes) == 2
    assert nodes[0]["type"] == "InputKey"
    assert nodes[0]["name"] == "A"
    assert nodes[1]["name"] == "AddMovementInput"
    assert nodes[1]["inputs"]["WorldDirection"] == [0.0, -1.0, 0.0]
    assert "warning" in result


@pytest.mark.parametrize(
    "text",
    [F_PRINT, OVERLAP, LAUNCH_SPACE, HELLO_WORLD_GAP, BRANCH_DANGLING, MOVE_W],
)
def test_ningun_nodo_queda_sin_cablear(text):
    graph = apply_graph(text, "imprime y mueve con tecla y beginplay")
    nodes = graph["nodes"]
    entries = {"inputkey", "event"}
    for node in nodes:
        if node["type"].lower() in entries:
            continue
        exec_in = (node.get("inputs") or {}).get("exec_in")
        assert exec_in, f"{node['id']} ({node['name']}) sin exec_in"
        assert exec_in.split(".", 1)[0] in {n["id"] for n in nodes}
        assert exec_in.split(".", 1)[0] != node["id"]


def test_eventtick_no_pedido_se_quita_de_la_tecla():
    raw = {
        "graph_name": "MoveOnW",
        "nodes": [
            {"id": "node_01", "type": "Event", "name": "EventTick", "inputs": {}, "outputs": {"exec_out": "node_02.exec_in"}},
            {"id": "node_02", "type": "InputKey", "name": "W", "inputs": {}, "outputs": {"Pressed": "node_03.exec_in"}},
            {"id": "node_03", "type": "FunctionCall", "name": "AddMovementInput", "inputs": {"exec_in": "node_02.Pressed", "WorldDirection": [1, 0, 0], "ScaleValue": 1.0}, "outputs": {}},
        ],
    }
    graph = apply_graph(raw, "tecla W llama a AddMovementInput hacia adelante")
    names = [n["name"] for n in graph["nodes"]]
    assert "EventTick" not in names
    assert names == ["W", "AddMovementInput"]


def test_tick_pedido_se_conserva():
    raw = {
        "graph_name": "Patrol",
        "nodes": [
            {"id": "node_01", "type": "Event", "name": "EventTick", "inputs": {}, "outputs": {"exec_out": "node_02.exec_in"}},
            {"id": "node_02", "type": "Branch", "name": "Branch", "inputs": {"exec_in": "node_01.exec_out", "Condition": True}, "outputs": {"then": "node_03.exec_in", "else": "node_04.exec_in"}},
            {"id": "node_03", "type": "FunctionCall", "name": "AddMovementInput", "inputs": {"exec_in": "node_02.then", "WorldDirection": [1, 0, 0]}, "outputs": {}},
            {"id": "node_04", "type": "FunctionCall", "name": "AddMovementInput", "inputs": {"exec_in": "node_02.else", "WorldDirection": [-1, 0, 0]}, "outputs": {}},
        ],
    }
    graph = apply_graph(raw, "EventTick → Branch. Si true adelante, si false atrás")
    assert graph["nodes"][0]["name"] == "EventTick"


def test_rama_no_encadena_then_con_else():
    raw = {
        "graph_name": "BranchBP-Lite",
        "nodes": [
            {"id": "node_01", "type": "Event", "name": "EventBeginPlay", "inputs": {}, "outputs": {"exec_out": "node_02.exec_in"}},
            {"id": "node_02", "type": "Branch", "name": "Branch", "inputs": {"exec_in": "node_01.exec_out", "Condition": True}, "outputs": {"then": "node_03.exec_in", "else": "node_04.exec_in"}},
            {"id": "node_03", "type": "FunctionCall", "name": "PrintString", "inputs": {"exec_in": "node_02.then", "InString": "OK"}, "outputs": {"exec_out": "node_04.exec_in"}},
            {"id": "node_04", "type": "FunctionCall", "name": "PrintString", "inputs": {"exec_in": "node_03.exec_out", "InString": "FAIL"}, "outputs": {}},
        ],
    }
    graph = apply_graph(raw, 'Branch tras BeginPlay; si true imprime "OK", si false "FAIL"')
    nodes = nodes_by_id(graph)
    assert nodes["node_03"]["outputs"] == {}
    assert nodes["node_04"]["inputs"]["exec_in"] == "node_02.else"


def test_destroy_colgado_del_tick_pasa_a_la_cadena_de_la_tecla():
    raw = {
        "graph_name": "BeginPlayDestroy",
        "nodes": [
            {"id": "node_01", "type": "Event", "name": "EventTick", "inputs": {}, "outputs": {"exec_out": "node_02.exec_in"}},
            {"id": "node_02", "type": "InputKey", "name": "E", "inputs": {}, "outputs": {"Pressed": "node_03.exec_in"}},
            {"id": "node_03", "type": "FunctionCall", "name": "PrintString", "inputs": {"exec_in": "node_02.Pressed", "InString": "Interactuar"}, "outputs": {}},
            {"id": "node_04", "type": "FunctionCall", "name": "DestroyActor", "inputs": {"exec_in": "node_01.exec_out"}, "outputs": {}},
        ],
    }
    graph = apply_graph(raw, 'al pulsar E imprime "Interactuar" y luego destruye el actor')
    nodes = nodes_by_id(graph)
    assert "EventTick" not in [n["name"] for n in graph["nodes"]]
    assert nodes["node_04"]["inputs"]["exec_in"] == "node_03.exec_out"
    assert nodes["node_03"]["outputs"]["exec_out"] == "node_04.exec_in"
