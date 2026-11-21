"""graph_name genérico BP-Lite → nombre descriptivo."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_lite import prepare_apply_payload

raw = '''{"graph_name":"BP-Lite","nodes":[{"id":"1","type":"Event_BeginPlay","name":"BeginPlay","inputs":[],"outputs":[]},{"id":"2","type":"PrintString","name":"Hola","inputs":["1"],"outputs":[]},{"id":"3","type":"Delay","name":"1s","inputs":["2"],"outputs":[]},{"id":"4","type":"PrintString","name":"Mundo","inputs":["3"],"outputs":[]}]}'''
r = prepare_apply_payload(
    raw,
    user_prompt='BeginPlay → PrintString "Hola" → Delay 1s → PrintString "Mundo"',
)
assert r.get("ok"), r
gn = r["graph"]["graph_name"]
assert "lite" not in gn.lower(), gn
assert "Hola" in gn or "Mundo" in gn or "hola" in gn.lower(), gn
print("naming OK", gn)
