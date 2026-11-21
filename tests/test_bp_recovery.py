"""Recuperación: clean partial + stitch de PrintString pedidos en el prompt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from middleware.bp_complete import (  # noqa: E402
    clean_partial_for_continue,
    fill_obvious_prompt_gaps,
    missing_vs_prompt,
    score_graph_candidate,
)

TRUNCATED = (
    '{"graph_name":"BP-Lite","nodes":['
    '{"id":"node_01","type":"Event","name":"BeginPlay","inputs":{},'
    '"outputs":{"exec_out":"node_02.exec_in"}},'
    '{"id":"node_02","type":"FunctionCall","name":"PrintString",'
    '"inputs":{"exec_in":"node_01.exec_out","InString":"Hola"},"outputs":{}},'
    '{"id":"node_03","type":"FunctionCall","name":"Delay",'
    '"inputs":{"exec_in":"node_02.exec_out","Duration":1.0},'
    '"outputs":{"exec_out":"node_04.exec_in"}},'
    '{"id":"node_04","type":"FunctionCall","name":"Print'
    "                                                                      "
)

PROMPT = 'BeginPlay → PrintString "Hola" → Delay 1s → PrintString "Mundo"'


def test_clean_partial_quita_nodo_a_medias_y_espacios():
    clean = clean_partial_for_continue(TRUNCATED)
    assert "Print     " not in clean
    data = json.loads(clean)
    assert len(data["nodes"]) == 3
    assert data["nodes"][2]["name"] == "Delay"


def test_stitch_anade_print_mundo():
    clean = clean_partial_for_continue(TRUNCATED)
    stitched = fill_obvious_prompt_gaps(clean, PROMPT)
    assert stitched is not None
    names = [(n["name"], (n.get("inputs") or {}).get("InString")) for n in stitched["nodes"]]
    assert ("PrintString", "Mundo") in names
    assert len(stitched["nodes"]) == 4
    assert missing_vs_prompt(PROMPT, stitched) == []


def test_score_prefiere_completo():
    clean = clean_partial_for_continue(TRUNCATED)
    stitched = fill_obvious_prompt_gaps(clean, PROMPT)
    assert score_graph_candidate(PROMPT, stitched) > score_graph_candidate(
        PROMPT, clean
    )


STRAFE_TRUNCATED = (
    '{"graph_name":"CharacterStrafeBP","nodes":['
    '{"id":"node_01","type":"Event","name":"EventTick","inputs":{},'
    '"outputs":{"exec_out":"node_02.exec_in"}},'
    '{"id":"node_02","type":"InputKey","name":"A","inputs":{},'
    '"outputs":{"Pressed":"node_03.exec_in"}},'
    '{"id":"node_03","type":"FunctionCall","name":"AddMovementInput",'
    '"inputs":{"exec_in":"node_02.Pressed","WorldDirection":[-1,0,0],"ScaleValue":1.0},'
    '"outputs":{}},'
    '{"id":"node_04","type":"InputKey","name":"D","inputs":{},'
    '"outputs":{"Pressed":"node_05.exec_in"}},'
    '{"id":"node_05'
    + (" " * 40)
)

STRAFE_PROMPT = (
    "Crea un Blueprint Character: tecla A strafe izquierda y D strafe derecha "
    "con AddMovementInput."
)


def test_finalize_strafe_no_inventa_la_tecla_cortada():
    from middleware.bp_complete import finalize_bp_json, is_syntactically_truncated

    closed = finalize_bp_json(STRAFE_TRUNCATED, STRAFE_PROMPT)
    assert not is_syntactically_truncated(closed)
    data = json.loads(closed)
    names = [(n["type"], n["name"]) for n in data["nodes"]]
    assert ("InputKey", "A") in names
    assert ("InputKey", "D") in names
    moves = [n for n in data["nodes"] if n["name"] == "AddMovementInput"]
    # El corte estaba en node_05. No se fabrica el segundo AddMovementInput.
    assert len(moves) == 1
    assert moves[0]["inputs"]["WorldDirection"] == [-1, 0, 0]
    assert ("Event", "EventTick") in names


def test_strafe_sin_branch_pedido_lo_elimina():
    from middleware.bp_lite import prepare_apply_payload

    raw = {
        "graph_name": "MoveOnA",
        "nodes": [
            {"id": "node_02", "type": "Branch", "name": "Branch", "inputs": {"Condition": True}, "outputs": {"then": "node_03.exec_in", "else": "node_04.exec_in"}},
            {"id": "node_03", "type": "InputKey", "name": "A", "inputs": {}, "outputs": {"Pressed": "node_05.exec_in"}},
            {"id": "node_04", "type": "InputKey", "name": "D", "inputs": {}, "outputs": {"Pressed": "node_06.exec_in"}},
            {"id": "node_05", "type": "FunctionCall", "name": "AddMovementInput", "inputs": {"exec_in": "node_03.Pressed", "WorldDirection": [-1, 0, 0], "ScaleValue": 1.0}, "outputs": {}},
            {"id": "node_06", "type": "FunctionCall", "name": "AddMovementInput", "inputs": {"exec_in": "node_04.Pressed", "WorldDirection": [0.0, 1.0, 0.0], "ScaleValue": 1.0}, "outputs": {}},
        ],
    }
    graph = prepare_apply_payload(
        raw,
        user_prompt="Blueprint Character: tecla A strafe izquierda y D strafe derecha con AddMovementInput",
    )["graph"]
    names = [n["name"] for n in graph["nodes"]]
    assert "Branch" not in names
    assert names.count("AddMovementInput") == 2
    assert "A" in names and "D" in names
    by_key = {}
    for n in graph["nodes"]:
        if n["type"] == "InputKey":
            target = (n.get("outputs") or {}).get("Pressed", "")
            dest = target.split(".", 1)[0]
            move = next(x for x in graph["nodes"] if x["id"] == dest)
            by_key[n["name"]] = move["inputs"]["WorldDirection"]
    # El vector lo pone el modelo: no se reescribe por tecla.
    assert by_key["A"] == [-1, 0, 0] or by_key["A"] == [-1.0, 0.0, 0.0]
    assert by_key["D"] == [0.0, 1.0, 0.0]


def test_strafe_del_modelo_se_conserva():
    from middleware.bp_lite import prepare_apply_payload

    raw = {
        "graph_name": "CharacterStrafeBP",
        "nodes": [
            {"id": "node_02", "type": "InputKey", "name": "A", "inputs": {}, "outputs": {"Pressed": "node_03.exec_in"}},
            {"id": "node_03", "type": "FunctionCall", "name": "AddMovementInput", "inputs": {"exec_in": "node_02.Pressed", "WorldDirection": [0.0, -1.0, 0.0], "ScaleValue": 1.0}, "outputs": {}},
            {"id": "node_04", "type": "InputKey", "name": "D", "inputs": {}, "outputs": {"Pressed": "node_05.exec_in"}},
            {"id": "node_05", "type": "FunctionCall", "name": "AddMovementInput", "inputs": {"exec_in": "node_04.Pressed", "WorldDirection": [0.0, 1.0, 0.0], "ScaleValue": 1.0}, "outputs": {}},
        ],
    }
    graph = prepare_apply_payload(
        raw,
        user_prompt="Blueprint Character: tecla A strafe izquierda y D strafe derecha con AddMovementInput",
    )["graph"]
    dirs = {
        n["inputs"]["exec_in"].split(".")[0]: n["inputs"]["WorldDirection"]
        for n in graph["nodes"]
        if n["name"] == "AddMovementInput"
    }
    assert dirs["node_02"] == [0.0, -1.0, 0.0]
    assert dirs["node_04"] == [0.0, 1.0, 0.0]
    assert [n["name"] for n in graph["nodes"]] == ["A", "AddMovementInput", "D", "AddMovementInput"]


FILLER = (
    "The  is the same, but the first, the role of the following are also known as the, and the\n"
    ", the, the, and is not, the and is not necessary to be a\n"
    ". (But the  is also a good practice, but also have been a good example of the\n"
    ", the. [I\n"
    "    - The\n"
    ", the\n"
    ", the, but the\n"
    "    (but not all) (function as\n"
    "        to the\n"
    ",  is a\n"
    "        and is a\n"
)


def test_bucle_the_the_se_corta():
    from response_filters import (
        is_degenerate_filler,
        should_stop_generation,
        truncate_repetition,
    )

    assert is_degenerate_filler(FILLER)
    assert should_stop_generation(FILLER)
    assert truncate_repetition(FILLER) == ""
    prosa = (
        "BeginPlay llama a AIMoveTo hacia el punto (400, 0, 0) y, tras un Delay, "
        "repite el movimiento hacia (-400, 0, 0). El eje X es adelante."
    )
    assert not is_degenerate_filler(prosa)
    assert not should_stop_generation(prosa)


def test_la_explicacion_tras_el_grafo_se_corta():
    from response_filters import (
        asegurar_explicacion_aplicar,
        should_stop_generation,
        truncate_repetition,
    )

    abierto = (
        '{"graph_name":"Patrulla","nodes":['
        '{"id":"node_01","type":"Event","name":"BeginPlay","inputs":{},"outputs":{}}'
    )
    assert should_stop_generation(abierto) is False
    con_prosa = (
        abierto
        + "]}\nEl flujo de ejecución comienza en BeginPlay y después se explica "
        "durante muchos párrafos cómo colocar cada nodo, compilar, guardar y probar."
    )
    assert should_stop_generation(con_prosa) is True
    cortado = truncate_repetition(con_prosa)
    assert "muchos párrafos" not in cortado
    assert '"graph_name"' in cortado
    final = asegurar_explicacion_aplicar(cortado)
    assert "Aplicar BP-Lite" in final
    assert "muchos párrafos" not in final


def test_claves_help_que_crecen_se_cortan():
    from response_filters import (
        is_degenerate_filler,
        should_stop_generation,
        truncate_repetition,
    )

    tecla = (
        '{"graph_name":"Interactuar y destruir","nodes":['
        '{"id":"node_01","type":"InputKey","name":"E","help":n'
    )
    assert is_degenerate_filler(tecla)
    assert should_stop_generation(tecla)
    assert '"help"' not in truncate_repetition(tecla)

    strafe = (
        '{"graph_name":"Character Strafing","nodes":['
        '{"id":"node_01","type":"Event","name":"EventTick","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}},'
        '{"id":"node_03","type":"InputKey","name":"A",'
        '"helpmethod":"InputAction","helptype":2,'
        '"helpmethodteamteamtype":0,"helpmet'
    )
    assert should_stop_generation(strafe)
    cortado = truncate_repetition(strafe)
    assert "helpmethod" not in cortado
    assert "EventTick" in cortado

    sano = (
        '{"graph_name":"Interactuar","nodes":['
        '{"id":"node_01","type":"InputKey","name":"E","inputs":{},'
        '"outputs":{"Pressed":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"PrintString","inputs":'
        '{"exec_in":"node_01.Pressed","InString":"Interactuar"},"outputs":{}}]}'
    )
    assert not is_degenerate_filler(sano)


def test_bucle_de_guiones_e_imagen_se_corta():
    from response_filters import (
        is_degenerate_filler,
        should_stop_generation,
        truncate_repetition,
    )

    spam = "![](https://i.h" + " - " * 20
    assert is_degenerate_filler(spam)
    assert should_stop_generation(spam)
    assert truncate_repetition(spam) == ""
    grafo = (
        '{"graph_name":"Patrulla","nodes":[{"id":"node_04","type":"FunctionCall",'
        '"name":"AIMoveTo","inputs":{"Destination":[-400,0,0]},"outputs":{}}]}'
    )
    assert not is_degenerate_filler(grafo)
    assert should_stop_generation(grafo)


def test_el_segundo_aimoveto_no_se_toma_por_eco():
    from response_filters import should_stop_generation

    base = (
        '{"graph_name":"Patrulla","nodes":['
        '{"id":"node_01","type":"Event","name":"BeginPlay","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}},'
        '{"id":"node_02","type":"FunctionCall","name":"AIMoveTo","inputs":'
        '{"exec_in":"node_01.exec_out","Destination":"[400,0,0]"},'
        '"outputs":{"exec_out":"node_03.exec_in"}},'
        '{"id":"node_03","type":"Delay","name":"Delay","inputs":'
        '{"exec_in":"node_02.exec_out","Duration":"2"},'
        '"outputs":{"exec_out":"node_04.exec_in"}},'
        '{"id":"node_04","type":"FunctionCall","name":"AIMoveTo","inputs":'
        '{"exec_in":"node_03.exec_out","Destination":"[-400,0,0]"},"outputs":{}}'
    )
    assert should_stop_generation(base) is False
    closed = base + "]}"
    assert should_stop_generation(closed) is True


def test_array_abierto_no_repite_el_beginplay():
    from services.prompt_builder import open_nodes_prefix, stitch_continuation

    partial = (
        '{"graph_name":"Patrulla","nodes":['
        '{"id":"node_01","type":"Event","name":"BeginPlay","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}}]}'
    )
    prefix = open_nodes_prefix(partial)
    assert prefix.endswith(",")
    assert "BeginPlay" in prefix
    stitched = stitch_continuation(
        prefix,
        '{"id":"node_02","type":"FunctionCall","name":"AIMoveTo","inputs":{},"outputs":{}}]}',
    )
    data = json.loads(stitched)
    assert [n["name"] for n in data["nodes"]] == ["BeginPlay", "AIMoveTo"]


def test_colapso_no_relanza_la_generacion():
    from services.bp_recovery import recover_incomplete_blueprint

    def generate(*_a, **_k):
        raise AssertionError("no hay que volver a generar")

    published: list[str] = []
    out = recover_incomplete_blueprint(
        text=FILLER,
        prompt="BeginPlay → AIMoveTo al punto (400, 0, 0)",
        full_prompt="prompt",
        stuck_whitespace=False,
        stuck_degeneration=True,
        generate=generate,
        set_phase=lambda _p: None,
        publish=published.append,
        prefix=lambda t: t,
    )
    assert out == FILLER
    assert published == []

    calls: list[str] = []

    def continuar(prompt, **kwargs):
        calls.append(prompt)
        if "Continúa el JSON" not in prompt:
            raise AssertionError(prompt[-180:])
        if "PROMPT_ORIGINAL_UNICO" in prompt:
            raise AssertionError("no hay que repetir el prompt original")
        assert str(kwargs.get("open_prefix") or "").endswith(",")
        return (
            '{"id":"node_02","type":"FunctionCall","name":"AIMoveTo","inputs":'
            '{"exec_in":"node_01.exec_out","Destination":[400,0,0]},'
            '"outputs":{"exec_out":"node_03.exec_in"}},'
            '{"id":"node_03","type":"FunctionCall","name":"Delay","inputs":'
            '{"exec_in":"node_02.exec_out","Duration":2},'
            '"outputs":{"exec_out":"node_04.exec_in"}},'
            '{"id":"node_04","type":"FunctionCall","name":"AIMoveTo","inputs":'
            '{"exec_in":"node_03.exec_out","Destination":[-400,0,0]},"outputs":{}}]}'
        )

    partial = (
        '{"graph_name":"Patrulla","nodes":['
        '{"id":"node_01","type":"Event","name":"BeginPlay","inputs":{},'
        '"outputs":{"exec_out":"node_02.exec_in"}}]}'
    )
    closed = recover_incomplete_blueprint(
        text=partial,
        prompt=(
            "Crea un Blueprint de patrulla: BeginPlay → AIMoveTo al punto (400, 0, 0) "
            "→ Delay 2s → AIMoveTo al punto (-400, 0, 0). Sin teclas y sin EventTick."
        ),
        full_prompt="PROMPT_ORIGINAL_UNICO",
        stuck_whitespace=False,
        stuck_degeneration=True,
        generate=continuar,
        set_phase=lambda _p: None,
        publish=published.append,
        prefix=lambda t: t,
    )
    assert calls
    assert "PROMPT_ORIGINAL_UNICO" not in calls[0]
    assert closed.count("AIMoveTo") == 2
    assert "Delay" in closed


def test_detener_no_lanza_otro_pase():
    from services.bp_recovery import recover_incomplete_blueprint

    def generar(*_a, **_k):
        raise AssertionError("Detener no debe pedir más tokens")

    partial = (
        '{"graph_name":"Patrulla","nodes":['
        '{"id":"node_01","type":"Event","name":"BeginPlay","inputs":{},"outputs":{}}]}'
    )
    out = recover_incomplete_blueprint(
        text=partial,
        prompt=(
            "Crea un Blueprint de patrulla: BeginPlay → AIMoveTo al punto (400, 0, 0) "
            "→ Delay 2s → AIMoveTo al punto (-400, 0, 0)."
        ),
        full_prompt="NO",
        stuck_whitespace=False,
        generate=generar,
        set_phase=lambda _p: None,
        publish=lambda _t: None,
        prefix=lambda t: t,
        abort=lambda: True,
    )
    assert "BeginPlay" in out


def test_finalize_nunca_deja_json_abierto():
    from middleware.bp_complete import finalize_bp_json, is_syntactically_truncated

    closed = finalize_bp_json(TRUNCATED, PROMPT)
    assert not is_syntactically_truncated(closed)
    data = json.loads(closed)
    assert len(data["nodes"]) == 3
    assert not any(
        (n.get("inputs") or {}).get("InString") == "Mundo" for n in data["nodes"]
    )
