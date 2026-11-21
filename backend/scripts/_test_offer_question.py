"""JSON + explicación corta en un solo turno (sin pregunta de oferta)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from response_filters import limpiar_respuesta_modelo, should_stop_generation

bp = '```json\n{"graph_name": "BP_X", "nodes": []}\n```\n'
assert should_stop_generation(bp) is True
out = limpiar_respuesta_modelo(bp)
assert "Aplicar BP-Lite" in out
assert "quieres que te explique" not in out.lower()
assert "graph_name" in out
print("BP json+explain OK:", repr(out[-120:]))

light = '```json\n{"environment_type": "noche", "directional_light": {}}\n```\nalgo de mas\n'
out2 = limpiar_respuesta_modelo(light)
assert "Aplicar Lighting" in out2
assert "explique" not in out2.lower()
assert "environment_type" in out2
print("Light json+explain OK")
