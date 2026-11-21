"""JSON-first: tras fence estructurado se corta; eco/prosa ya no se conservan en el 1er pase."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from response_filters import (
    should_stop_generation,
    truncate_repetition,
    limpiar_respuesta_modelo,
)

base = """```json
{"graph_name": "OverlapEvent", "nodes": []}
```

Para crear este Blueprint, sigue estos pasos:

1. Abre el Editor de Blueprints.
2. Agrega ActorBeginOverlap.
3. Conecta PrintString con Overlap.
"""

assert should_stop_generation(base) is True
out = truncate_repetition(base)
assert out.count("```json") == 1
assert '"graph_name"' in out
assert "ActorBeginOverlap" not in out
clean = limpiar_respuesta_modelo(base)
assert "Aplicar BP-Lite" in clean
assert "quieres que te explique" not in clean.lower()
print("json-first truncate OK", f"kept {len(out)}/{len(base)}")

# Mencionar graph_name solo en prosa (sin fence): no cortar
solo = 'El campo "graph_name" identifica el asset.\n'
assert should_stop_generation(solo) is False
assert "identifica" in truncate_repetition(solo)
print("prose-only OK")
