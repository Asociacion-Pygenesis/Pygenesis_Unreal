import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from middleware.bp_lite import prepare_apply_payload
from response_filters import limpiar_respuesta_modelo, should_stop_generation

sample = r'''
```json
{
 "graph_name": "BP_PrintString",
 "nodes":
 [
 {
 "id":"node_01","type":"InputKeyEventNode", 
 "name":"","inputs":{"Pressed":[{"Name":"In_String"}]}, 
 "outputs":[]
 },
 
 { "id":"node_02","type":"FunctionCallNode", 
 "name":"",
 "inputs":{ }, 
 "outputs":
 [
 {"Pin Name":"Exec_In"}
 ]
 }
 ]

}
```

1. Crea un nuevo Blueprint en tu proyecto.
2. Agrega el nodo InputKeyEvent (node_01) y configúralo para que se active al pulsar la tecla F.
4. Configura node_02 como PrintString, estableciendo el valor de In_String en "Interactuando".

Espero que esto te ayude! Si tienes alguna pregunta adicional o necesitas más ayuda, no dudes en preguntar.
Un saludo desde Pygenesis UnrealExpert AI. :) (Si el JSON BP-Lite es demasiado grande...)
'''

assert should_stop_generation(sample) is True
clean = limpiar_respuesta_modelo(sample)
assert "Espero que esto te ayude" not in clean
assert "Un saludo desde" not in clean
assert "PrintString" in clean or "printstring" in clean.lower() or "Interactuando" in clean
print("farewell strip OK")

r = prepare_apply_payload(sample)
print(r.get("summary"), r.get("error"))
assert r.get("ok"), r
assert any(n["type"] == "InputKey" and n["name"] == "F" for n in r["graph"]["nodes"])
pr = next(n for n in r["graph"]["nodes"] if n["name"] == "PrintString")
# "Interactuando" solo aparece en la prosa posterior: el texto del Print no se
# extrae de la explicación, así que el pin queda vacío a propósito.
assert "InString" in pr["inputs"], pr
assert pr["inputs"]["exec_in"] == "node_01.Pressed", pr
print(json.dumps(r["graph"], indent=2, ensure_ascii=False))
print("APPLY OK")
