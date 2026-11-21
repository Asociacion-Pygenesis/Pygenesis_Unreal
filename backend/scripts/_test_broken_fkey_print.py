"""JSON basura: sin fabricar grafo — error o parse parcial sin inventar InString."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_lite import prepare_apply_payload

sample = r'''
```json
{
 "graph_name": "BP_LaunchCharacter",
 "nodes":
 [
 {
 "id":"node_01","type":"EventTriggerNode", 
 "name":"F Key Pressed Event Trigger Node"
 },
 {"inputs":{"Pressed":[true]},outputs:{}}],
 { 
 "id":"node_02","type":"FunctionCall",
 "name":null,
 inputs:{"InString":["Interactuando"]},
 outputs:{}}
 ]
} 
``` 
'''

r = prepare_apply_payload(sample)
# Estructura inválida: no inventar InputKey F / Print desde plantilla
assert not r.get("ok"), r
err = str(r.get("error") or "")
assert err, r
print("broken fkey → explicit error OK", err)
