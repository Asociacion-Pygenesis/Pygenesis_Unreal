import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from response_filters import limpiar_respuesta_modelo, should_stop_generation

body = """```json
{\"graph_name\": \"OverlapEvent\", \"nodes\": []}
```

Para crear este Blueprint sigue estos pasos.
1. Abre el editor.
2. Conecta PrintString.
</think>"""

clean = limpiar_respuesta_modelo(body)
assert "graph_name" in clean, repr(clean)
assert "Aplicar BP-Lite" in clean, repr(clean)
assert "quieres que te explique" not in clean.lower()
# JSON-first: la prosa post-fence no se conserva en el primer pase
assert "PrintString" not in clean, repr(clean)
print("orphan </think> + offer OK", len(clean))

# fence en explicación sin JSON estructurado no debe disparar stop
extra = "Flujo tipico:\n```\nEvent -> Print\n```\n"
assert should_stop_generation(extra) is False, "code fence in prose should not stop"
print("prose fence OK")

# fence BP cerrado sí
extra2 = '```json\n{"graph_name": "X"}\n```\n'
assert should_stop_generation(extra2) is True
print("bp fence stop OK")
