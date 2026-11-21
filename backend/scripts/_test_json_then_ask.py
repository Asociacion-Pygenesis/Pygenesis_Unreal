import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from main import Consulta, construir_prompt, _es_seguimiento_uso

prev = (
    '```json\n{"graph_name":"BP_X","nodes":[]}\n```\n'
    "¿Quieres que te explique cómo aplicarlo en el Editor?"
)
assert _es_seguimiento_uso("si", prev)
assert _es_seguimiento_uso("vale", prev)
assert _es_seguimiento_uso("explícame", prev)

p = construir_prompt(
    Consulta(prompt="Crea un Blueprint: tecla F PrintString Interactuando"),
    [],
)
assert "BP-Lite" in p or "graph_name" in p
assert "OBLIGATORIO después del JSON: 3" not in p
assert "pasos" not in p.lower() or "NO escribas pasos" in p

p2 = construir_prompt(Consulta(prompt="si", ultima_respuesta=prev), [])
assert "PROHIBIDO JSON" in p2 or "No JSON" in p2
assert "cyberpunk" not in p2.lower() or "PROHIBIDO" in p2
print("json-then-ask OK")
