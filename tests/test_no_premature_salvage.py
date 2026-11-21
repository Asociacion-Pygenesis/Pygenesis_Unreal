"""El chat no debe maquillar un JSON truncado con salvage a N-1 nodos."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from response_filters import truncate_repetition  # noqa: E402
from middleware.bp_lite import prepare_apply_payload  # noqa: E402


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


def test_truncate_no_reescribe_json_truncado():
    out = truncate_repetition("```json\n" + TRUNCATED, user_prompt=PROMPT)
    # No debe aparecer el grafo salvado de 3 nodos como si estuviera completo.
    assert "BP_Delay_Hola" not in out
    assert "node_04" in out or "Print" in out
    assert out.count('"id"') >= 3  # sigue mostrando el corte, no un rewrite limpio


def test_aplicar_sigue_pudiendo_salvar_nodos_cerrados():
    result = prepare_apply_payload(TRUNCATED, user_prompt=PROMPT)
    assert result.get("ok")
    assert result.get("warning")
    nodes = result["graph"]["nodes"]
    assert len(nodes) == 3
    assert any(n["name"] == "Delay" for n in nodes)
