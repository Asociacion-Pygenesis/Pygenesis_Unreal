"""Parity: JSON reales de Ollama (testunreal1.md) → BP-Lite canónico."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from middleware.bp_lite import prepare_apply_payload
from middleware.bp_normalize.dialect import coerce_model_dialect, _extract_input_action_key

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ollama"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "fname",
    [
        "live_fkey_interact.json",
        "live_w_move.json",
        "live_destroy.json",
        "live_space_launch.json",
        "live_ad_strafe.json",
        "live_delay_listo.json",
    ],
)
def test_ollama_live_prepare(fname: str) -> None:
    fx = _load(fname)
    raw = fx["raw"]
    expect = fx["expect"]
    prompt = (fx.get("_meta") or {}).get("prompt", "")
    r = prepare_apply_payload(raw, user_prompt=prompt)
    assert r.get("ok"), (fname, r)
    nodes = r["graph"]["nodes"]
    names = [n["name"] for n in nodes]
    types = [n["type"] for n in nodes]
    if "names" in expect:
        assert names == expect["names"], names
    if "types" in expect:
        assert types == expect["types"], types
    if expect.get("no_beginplay"):
        assert "EventBeginPlay" not in names
    if "print" in expect:
        pr = next(n for n in nodes if n["name"] == "PrintString")
        assert pr["inputs"].get("InString") == expect["print"]
    if "duration" in expect:
        delay = next(n for n in nodes if n["name"] == "Delay")
        assert float(delay["inputs"]["Duration"]) == float(expect["duration"])
    if "direction" in expect:
        mv = next(n for n in nodes if n["name"] == "AddMovementInput")
        # WorldDirection es el nombre real del pin en UE (ver test_pin_contract)
        assert list(mv["inputs"]["WorldDirection"]) == list(expect["direction"])
    if "src_pin" in expect:
        ik = next(n for n in nodes if n["type"] == "InputKey")
        assert expect["src_pin"] in ik["outputs"]
        child = next(n for n in nodes if n["type"] != "InputKey")
        assert child["inputs"]["exec_in"].endswith(f".{expect['src_pin']}")


def test_extract_input_action_key() -> None:
    assert _extract_input_action_key("Event_InputAction_F", "") == "F"
    assert _extract_input_action_key("Event_InputAction_W", "") == "W"
    assert _extract_input_action_key("Event_InputAction_Spacebar", "") == "SpaceBar"
    assert _extract_input_action_key("FunctionCall", "Jump") is None
    assert _extract_input_action_key("InputAction_A", "") == "A"


def test_dialect_w_pressed() -> None:
    raw = {
        "graph_name": "M",
        "nodes": [
            {"id": "1", "type": "Event_InputAction_W", "name": "", "inputs": [], "outputs": []},
            {
                "id": "2",
                "type": "Add Movement Input Forward",
                "name": "Go",
                "inputs": ["1"],
                "outputs": [],
            },
        ],
    }
    out = coerce_model_dialect(raw)
    assert out["nodes"][0]["type"] == "InputKey"
    assert out["nodes"][0]["name"] == "W"
    assert out["nodes"][1]["name"] == "AddMovementInput"
    assert out["nodes"][0]["outputs"].get("Pressed")
    assert out["nodes"][1]["inputs"]["exec_in"].endswith(".Pressed")
