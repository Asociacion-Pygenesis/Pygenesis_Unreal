import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Consulta, construir_prompt, _es_seguimiento_uso
from response_filters import limpiar_respuesta_followup

prev = (
    '```json\n{"graph_name":"BP_PrintString","nodes":[]}\n```\n\n'
    "¿Quieres que te explique cómo aplicarlo en el Editor?"
)
assert _es_seguimiento_uso("si", prev)

raw = (
    '{"graph_name": "BP-Lite: F -> PrintString", "nodes": [{"id":"node_01"}]}.\n\n'
    "Para aplicarlo en el Editor, sigue estos pasos:\n\n"
    "1. Crea un nuevo Blueprint.\n"
    "2. Conecta PrintString.\n\n"
    "¿Quieres que te explique cómo aplicarlo en el Editor?\n"
)
clean = limpiar_respuesta_followup(raw)
assert "graph_name" not in clean, repr(clean)
assert "PrintString" in clean
assert "quieres que te explique" not in clean.lower()
print("strip JSON+offer OK:", clean[:80])

p2 = construir_prompt(Consulta(prompt="si", ultima_respuesta=prev), [])
assert "PROHIBIDO" in p2
assert p2.rstrip().endswith("1.") or "\n1." in p2[-20:]
print("followup priming OK")
