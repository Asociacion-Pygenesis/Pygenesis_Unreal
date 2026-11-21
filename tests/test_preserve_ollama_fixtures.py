"""Suite Fase 4: fixtures estilo Ollama — preservar nodos/pines/params."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from middleware.bp_lite import prepare_apply_payload
from middleware.lighting import (
    _fog_explicitly_disabled,
    prepare_lighting_payload,
    synthesize_lighting_from_prose,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ollama"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _node_by_id(graph: dict, nid: str) -> dict:
    return next(n for n in graph["nodes"] if n["id"] == nid)


# Pines que el modelo nombra a su manera y se reescriben al nombre real de UE
CANONICAL_PIN_RENAMES = {"WorldDirectionVector": "WorldDirection"}


def _assert_canonical_preserved(raw: dict, out_graph: dict) -> None:
    """Nodos, types, names y cables exec del fixture canónico no se alteran."""
    raw_nodes = raw["nodes"]
    out_nodes = out_graph["nodes"]
    assert len(out_nodes) == len(raw_nodes)
    for src, dst in zip(raw_nodes, out_nodes):
        assert dst["id"] == src["id"]
        assert dst["type"] == src["type"]
        assert dst["name"] == src["name"]
        # Inputs relevantes (valores escalares / refs): el valor se conserva
        # aunque el pin pase a llamarse como en Unreal.
        for k, v in (src.get("inputs") or {}).items():
            key = k if k in dst["inputs"] else CANONICAL_PIN_RENAMES.get(k, k)
            assert key in dst["inputs"], (src["id"], k, dst["inputs"])
            assert dst["inputs"][key] == v, (src["id"], key, dst["inputs"][key], v)
        for k, v in (src.get("outputs") or {}).items():
            if v in (None, ""):
                continue
            assert k in dst["outputs"], (src["id"], k, dst["outputs"])
            assert dst["outputs"][k] == v, (src["id"], k, dst["outputs"][k], v)


@pytest.mark.parametrize(
    "fname",
    [
        "bp_fkey_print_canonical.json",
        "bp_fkey_released.json",
        "bp_branch_then_else.json",
        "bp_beginplay_delay_print.json",
        "bp_w_move.json",
        "bp_launch_space.json",
        "bp_custom_event_interact.json",
        "bp_destroy_beginplay.json",
        "bp_overlap_print.json",
    ],
)
def test_bp_canonical_preserve(fname: str) -> None:
    fx = _load(fname)
    raw = fx["raw"]
    prompt = (fx.get("_meta") or {}).get("prompt", "")
    r = prepare_apply_payload(raw, user_prompt=prompt)
    assert r.get("ok"), r
    _assert_canonical_preserved(raw, r["graph"])
    if "must_keep_names" in fx:
        names = [n["name"] for n in r["graph"]["nodes"]]
        for keep in fx["must_keep_names"]:
            assert keep in names
    if "preserve_output_pins" in fx:
        ik = next(n for n in r["graph"]["nodes"] if n["type"] == "InputKey")
        for pin in fx["preserve_output_pins"]:
            assert pin in ik["outputs"]


def test_bp_hola_mundo_dialect() -> None:
    fx = _load("bp_hola_mundo_dialect.json")
    r = prepare_apply_payload(
        fx["raw"], user_prompt=(fx.get("_meta") or {}).get("prompt", "")
    )
    assert r.get("ok"), r
    names = [n["name"] for n in r["graph"]["nodes"]]
    assert names == fx["expect_names"]
    prints = [n for n in r["graph"]["nodes"] if n["name"] == "PrintString"]
    assert [p["inputs"]["InString"] for p in prints] == fx["expect_print_strings"]
    delay = next(n for n in r["graph"]["nodes"] if n["name"] == "Delay")
    assert delay["inputs"]["Duration"] == fx["expect_delay"]
    # Cadena cableada BeginPlay → …
    assert r["graph"]["nodes"][0]["outputs"].get("exec_out")


def test_bp_inputkey_dialect_pressed() -> None:
    fx = _load("bp_inputkey_dialect.json")
    r = prepare_apply_payload(fx["raw"], user_prompt="F Print")
    assert r.get("ok"), r
    names = [n["name"] for n in r["graph"]["nodes"]]
    assert names == fx["expect_names"]
    ik = r["graph"]["nodes"][0]
    pr = r["graph"]["nodes"][1]
    assert ik["type"] == "InputKey"
    assert fx["expect_src_pin"] in ik["outputs"]
    assert pr["inputs"]["exec_in"].endswith(f".{fx['expect_src_pin']}")
    assert pr["inputs"]["InString"] == "Interactuando"


@pytest.mark.parametrize(
    "fname",
    [
        "light_desert_sunset.json",
        "light_cyberpunk.json",
        "light_no_fog_studio.json",
        "light_misty_forest.json",
    ],
)
def test_lighting_canonical_preserve(fname: str) -> None:
    fx = _load(fname)
    raw = fx["raw"]
    r = prepare_lighting_payload(raw)
    assert r.get("ok"), r
    spec = r["spec"]
    assert spec["environment_type"] == raw["environment_type"]
    for section in (
        "directional_light",
        "sky_light",
        "exponential_fog",
        "post_process",
    ):
        for k, v in raw[section].items():
            assert k in spec[section], (section, k)
            got = spec[section][k]
            if isinstance(v, float):
                assert abs(float(got) - v) < 1e-6, (section, k, got, v)
            elif isinstance(v, list):
                assert list(got) == list(v), (section, k, got, v)
            else:
                assert got == v, (section, k, got, v)


@pytest.mark.parametrize(
    "prose",
    [
        "Iluminación de estudio limpio sin niebla, 6500K",
        "Preset día claro, no fog, clear sky",
        "Exterior soleado con niebla desactivada",
        "Studio lighting fog off",
    ],
)
def test_fog_negations(prose: str) -> None:
    assert _fog_explicitly_disabled(prose)
    spec = synthesize_lighting_from_prose(prose)
    assert spec is not None
    fog = spec["exponential_fog"]
    assert fog["volumetric_fog"] is False
    assert float(fog["density"]) == 0.0


def test_fog_positive_still_works() -> None:
    prose = "Escena de bosque de noche con niebla densa volumétrica"
    assert not _fog_explicitly_disabled(prose)
    spec = synthesize_lighting_from_prose(prose)
    assert spec is not None
    assert spec["exponential_fog"]["volumetric_fog"] is True
    assert float(spec["exponential_fog"]["density"]) >= 0.08


def test_fixture_count() -> None:
    files = list(FIXTURES.glob("*.json"))
    assert len(files) >= 14, f"esperábamos ≥14 fixtures, hay {len(files)}"
