"""Preserve-model: dialecto Ollama, Branch cableado, InputKey+Released."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from middleware.bp_lite import prepare_apply_payload


def test_ollama_hola_mundo():
    raw = (
        '{"graph_name":"BP-Lite","nodes":['
        '{"id":"1","type":"Event_BeginPlay","name":"BeginPlay","inputs":[],"outputs":[]},'
        '{"id":"2","type":"PrintString","name":"Hola","inputs":["1"],"outputs":[]},'
        '{"id":"3","type":"Delay","name":"1s","inputs":["2"],"outputs":[]},'
        '{"id":"4","type":"PrintString","name":"Mundo","inputs":["3"],"outputs":[]}'
        "]}"
    )
    r = prepare_apply_payload(
        raw,
        user_prompt='BeginPlay → PrintString "Hola" → Delay 1s → PrintString "Mundo"',
    )
    assert r.get("ok"), r
    names = [n["name"] for n in r["graph"]["nodes"]]
    assert names == ["EventBeginPlay", "PrintString", "Delay", "PrintString"], names
    prints = [n for n in r["graph"]["nodes"] if n["name"] == "PrintString"]
    assert prints[0]["inputs"]["InString"] == "Hola"
    assert prints[1]["inputs"]["InString"] == "Mundo"
    assert r["graph"]["nodes"][0]["outputs"].get("exec_out")
    print("preserve ollama dialect OK")


def test_branch_then_else_preserved():
    raw = '''```json
{"graph_name":"BranchBeginPlay","nodes":[
  {"id":"node_01","type":"Event","name":"EventBeginPlay","inputs":{},"outputs":{"exec_out":"node_02.exec_in"}},
  {"id":"node_02","type":"Branch","name":"Branch","inputs":{"exec_in":"node_01.exec_out","Condition":true},"outputs":{"then":"node_03.exec_in","else":"node_04.exec_in"}},
  {"id":"node_03","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_02.then","InString":"OK"},"outputs":{}},
  {"id":"node_04","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_02.else","InString":"FAIL"},"outputs":{}}
]}
```'''
    r = prepare_apply_payload(raw, user_prompt='Branch BeginPlay OK/FAIL')
    assert r.get("ok"), r
    br = next(n for n in r["graph"]["nodes"] if n["type"] == "Branch")
    assert br["outputs"]["then"] == "node_03.exec_in"
    assert br["outputs"]["else"] == "node_04.exec_in"
    prints = [n for n in r["graph"]["nodes"] if n["name"] == "PrintString"]
    assert {p["inputs"]["InString"] for p in prints} == {"OK", "FAIL"}
    print("preserve branch then/else OK")


def test_inputkey_released_preserved():
    raw = '''```json
{"graph_name":"KeyReleased","nodes":[
  {"id":"node_01","type":"InputKey","name":"F","inputs":{},"outputs":{"Pressed":"node_02.exec_in","Released":"node_03.exec_in"}},
  {"id":"node_02","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_01.Pressed","InString":"down"},"outputs":{}},
  {"id":"node_03","type":"FunctionCall","name":"PrintString","inputs":{"exec_in":"node_01.Released","InString":"up"},"outputs":{}}
]}
```'''
    r = prepare_apply_payload(raw, user_prompt="F Pressed/Released prints")
    assert r.get("ok"), r
    ik = next(n for n in r["graph"]["nodes"] if n["type"] == "InputKey")
    assert "Released" in ik["outputs"], ik["outputs"]
    assert ik["outputs"]["Released"] == "node_03.exec_in"
    assert ik["outputs"]["Pressed"] == "node_02.exec_in"
    print("preserve InputKey Released OK", json.dumps(ik["outputs"]))


if __name__ == "__main__":
    test_ollama_hola_mundo()
    test_branch_then_else_preserved()
    test_inputkey_released_preserved()
    print("ALL PRESERVE-MODEL OK")
