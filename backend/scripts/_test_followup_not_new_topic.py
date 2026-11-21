"""Preguntas de concepto no deben reutilizar la explicación del último BP."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import _es_pregunta_tema_nuevo, _es_seguimiento_uso

prev = (
    '```json\n{"graph_name":"JumpOnSpace","nodes":['
    '{"id":"node_01","type":"InputKey","name":"SpaceBar","inputs":{},"outputs":{}},'
    '{"id":"node_02","type":"FunctionCall","name":"LaunchCharacter","inputs":{},"outputs":{}}'
    "]}\n```"
)

q = "Explica la diferencia entre Sky Light con Realtime Capture y cubemap estático en UE5."
assert _es_pregunta_tema_nuevo(q) is True
assert _es_seguimiento_uso(q, prev) is False

assert _es_seguimiento_uso("si", prev) is True
assert _es_seguimiento_uso("explícame", prev) is True
assert _es_seguimiento_uso("explícame esto", prev) is True
assert _es_seguimiento_uso("cómo usarlo", prev) is True
assert _es_seguimiento_uso("Explica qué es un Actor", prev) is False
print("followup vs new topic OK")
