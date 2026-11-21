"""Con JSON-first: tras fence estructurado se para; la prosa se pide con «sí»."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from response_filters import limpiar_respuesta_modelo, should_stop_generation, truncate_repetition

prose = """```json
{\"graph_name\": \"OverlapEvent\", \"nodes\": []}
```

Para aplicar el grafo, el campo \"graph_name\" identifica el Blueprint.
Luego conecta PrintString con InString Overlap y prueba en PIE.
"""

assert should_stop_generation(prose) is True, "fence BP cerrado debe parar"
cut = truncate_repetition(prose)
assert '"graph_name"' in cut
assert "PrintString" not in cut, "prosa post-JSON se descarta en el primer pase"
clean = limpiar_respuesta_modelo(prose)
assert "Aplicar BP-Lite" in clean
assert "PrintString" not in clean or "Cadena esperada" in clean
assert "quieres que te explique" not in clean.lower()
print("json-first stop+explain OK")

# Sin fence cerrado: mencionar graph_name en prosa no debe parar
solo_prosa = 'El campo "graph_name" identifica el asset y PrintString muestra Overlap.'
assert should_stop_generation(solo_prosa) is False
assert "PrintString" in limpiar_respuesta_modelo(solo_prosa)
print("prose-only graph_name OK")
