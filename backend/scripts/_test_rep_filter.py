from response_filters import limpiar_respuesta_modelo, should_stop_generation

t = """```json
{"graph_name": "Destroy", "nodes": [{"id": "node_01", "type": "Event", "name": "EventBeginPlay"}]}
```
Al comenzar, DestroyActor.

```json
{"graph_name": "Destroy", "nodes": [{"id": "node_01", "type": "Event", "name": "EventBeginPlay"}]}
```
Al comenzar otra vez.
"""
print("stop", should_stop_generation(t))
print("---cleaned---")
print(limpiar_respuesta_modelo(t))
