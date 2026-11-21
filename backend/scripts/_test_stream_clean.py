"""Reproduce soft-stop / limpia wiping overlap answers mid-stream."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from response_filters import limpiar_respuesta_modelo, should_stop_generation, truncate_repetition

BASE = """```json
{
 "graph_name": "OverlapEvent",
 "nodes": [
  {"id":"node_01","type":"Event","name":"EventActorBeginOverlap","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},
  {"id":"node_02","type":"FunctionCall","name":"PrintString","inputs":{"InString":"Overlap","exec_in":"node_01.exec_out"},"outputs":{}}
 ]
}
```

Para crear este Blueprint, sigue estos pasos:

1. Abre el Editor de Blueprints y crea un nuevo grafico.
2. Agrega el evento ActorBeginOverlap.
3. Conecta PrintString con el texto Overlap.
4. Coloca un collider en el nivel.

El resultado deber ser un Blueprint que imprima Overlap al solapar.

Para probarlo:

1. Coloca una caja.
2. Pulsa Play en PIE y veras Overlap.

Recuerda que puedes ajustar Collision en el actor.
"""

# Case: model starts a second fence in explanation (common)
WITH_EXTRA_FENCE = (
    BASE
    + """

El flujo resultante:

```
Event → PrintString
```
"""
)

# Case: model starts regenerating json
WITH_SECOND_JSON = (
    BASE
    + """

```json
{
 "graph_name": "OverlapEvent",
 "nodes": []
}
```
"""
)


def scan(label: str, text: str) -> None:
    print(f"\n=== {label} len={len(text)} ===")
    for i in range(80, len(text) + 1, 30):
        t = text[:i]
        stop = should_stop_generation(t)
        clean = limpiar_respuesta_modelo(t)
        if stop or len(clean) < max(20, int(len(t) * 0.4)) or ("graph_name" in t and "graph_name" not in clean):
            print(
                f"  i={i} stop={stop} raw={len(t)} clean={len(clean)} "
                f"lost_json={'graph_name' in t and 'graph_name' not in clean}"
            )
            if "graph_name" not in clean:
                print("  CLEAN:", repr(clean[:180]))


scan("BASE", BASE)
scan("EXTRA_FENCE", WITH_EXTRA_FENCE)
scan("SECOND_JSON", WITH_SECOND_JSON)

# Full clean
c = limpiar_respuesta_modelo(BASE)
print("\nFull BASE clean has graph_name:", "graph_name" in c, "len", len(c))
c2 = limpiar_respuesta_modelo(WITH_EXTRA_FENCE)
print("EXTRA clean has graph_name:", "graph_name" in c2, "len", len(c2), "stop", should_stop_generation(WITH_EXTRA_FENCE))
print("truncate EXTRA:", len(truncate_repetition(WITH_EXTRA_FENCE)))
