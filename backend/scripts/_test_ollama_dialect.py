"""Dialecto compacto estilo Ollama → grafo Apply canónico."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from middleware.bp_lite import prepare_apply_payload

raw = '''{"graph_name": "BP-Lite", "nodes": [{"id": "1", "type": "Event_BeginPlay", "name": "BeginPlay", "inputs": [], "outputs": []}, {"id": "2", "type": "PrintString", "name": "Hola", "inputs": ["1"], "outputs": []}, {"id": "3", "type": "Delay", "name": "1s", "inputs": ["2"], "outputs": []}, {"id": "4", "type": "PrintString", "name": "Mundo", "inputs": ["3"], "outputs": []}]}'''

r = prepare_apply_payload(raw, user_prompt='BeginPlay → PrintString "Hola" → Delay 1s → PrintString "Mundo"')
assert r.get("ok"), r
names = [n["name"] for n in r["graph"]["nodes"]]
assert names == ["EventBeginPlay", "PrintString", "Delay", "PrintString"], names
prints = [n for n in r["graph"]["nodes"] if n["name"] == "PrintString"]
assert prints[0]["inputs"]["InString"] == "Hola"
assert prints[1]["inputs"]["InString"] == "Mundo"
assert r["graph"]["nodes"][2]["inputs"]["Duration"] == 1.0
# Cables
assert r["graph"]["nodes"][0]["outputs"].get("exec_out")
print("OLLAMA DIALECT OK", json.dumps(names))
