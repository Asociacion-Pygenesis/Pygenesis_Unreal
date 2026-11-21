"""El modelo mete eco de instrucciones dentro/tras el JSON; hay que cortar al objeto."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from response_filters import (
    explicacion_determinista,
    limpiar_respuesta_modelo,
    should_stop_generation,
)

sample = r'''```json
{
 "graph_name": "BP-Lite: PrintString F",
 "nodes":
 [
 {
 "id":"node_01",
 "type":"InputKeyNode",
 "name":"",
 "inputs":{"Pressed":["F"]},
 "outputs":{"ExecIn":[], "ExecOut":[{"Name": "", "Type": ""}]}
 },
 {
 "id":"node_02",
 "type":"FunctionCallNode","name":"","inputs":{"String":"Interactuando"},
 "outputs":{"exec_out":""}
 }
 ]
}

Fence: ¿Qué sucede cuando se ejecuta este Blueprint? (UI añadirá la pregunta) ¡No es necesario escribir nada más!
```
'''

partial_until_brace = sample.split("Fence:")[0]
assert should_stop_generation(partial_until_brace) is True

clean = limpiar_respuesta_modelo(sample)
assert "Fence:" not in clean
assert "UI añadirá" not in clean
assert "graph_name" in clean
assert "Aplicar BP-Lite" in clean
assert "quieres que te explique" not in clean.lower()
print("clean OK:\n", clean[:400])

exp = explicacion_determinista(clean)
assert exp is not None
assert "Aplicar BP-Lite" in exp
assert "InputActionComponent" not in exp
print("canned OK")
