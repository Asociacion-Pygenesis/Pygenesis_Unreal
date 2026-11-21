import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from response_filters import asegurar_explicacion_aplicar, limpiar_respuesta_modelo

broken = '```json\n{"graph_name": "X", "nodes":\n[\n{\n'
assert "Aplicar BP-Lite" not in asegurar_explicacion_aplicar(broken)
print("broken no-explain OK")

ok = '```json\n{"graph_name": "X", "nodes": []}\n```'
out = limpiar_respuesta_modelo(ok)
assert "Aplicar BP-Lite" in out
assert "quieres que te explique" not in out.lower()
print("closed explain OK")
