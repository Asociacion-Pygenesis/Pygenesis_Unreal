"""JSON truncado: soft-stop ya no corta a medias; apply sigue fallando sin fabricar."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_complete import is_syntactically_truncated
from middleware.bp_lite import prepare_apply_payload
from response_filters import should_stop_generation

prompt = (
    'Crea un Blueprint: BeginPlay → PrintString "Hola" → Delay 1s → PrintString "Mundo"'
)
incomplete = r'''```json
{
 "graph_name": "BP-Lite: BeginPlay",
 "nodes":
 [
 {
 "id":"node_01","type":"EventBeginPlay", 
 "name":"",
 "inputs":{"In":"","Out":""},
 "outputs":{
 "Exec":""
'''

# Soft-stop: solo JSON completo / eco — no cortar abiertos (continue + max_tokens)
assert should_stop_generation(incomplete) is False
assert is_syntactically_truncated(incomplete) is True

r = prepare_apply_payload(incomplete, user_prompt=prompt)
assert not r.get("ok"), r
err = str(r.get("error") or "")
assert "truncado" in err.lower() or "incompleto" in err.lower() or "válido" in err.lower(), err
print("HOLA MUNDO truncated→error OK", err)
