"""Lighting-Spec: extract / normalize / prepare (PlanUnreal.md)."""

from __future__ import annotations

import json
import re
from typing import Any

_LIGHTING_KEYS = (
    "environment_type",
    "directional_light",
    "sky_light",
    "exponential_fog",
    "post_process",
)


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}
    return default


def _as_vec3(value: Any, default: list[float]) -> list[float]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return [float(value[0]), float(value[1]), float(value[2])]
        except (TypeError, ValueError):
            return list(default)
    if isinstance(value, str):
        nums = re.findall(r"[-+]?\d*\.?\d+", value)
        if len(nums) >= 3:
            return [float(nums[0]), float(nums[1]), float(nums[2])]
    return list(default)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _unwrap_lighting_root(data: dict[str, Any]) -> dict[str, Any]:
    """El LLM a veces envuelve todo en {"Lighting-Spec": {...}}."""
    if not isinstance(data, dict):
        return {}
    for key in (
        "Lighting-Spec",
        "LightingSpec",
        "lighting_spec",
        "lighting-spec",
        "lighting",
        "Lighting",
    ):
        inner = data.get(key)
        if isinstance(inner, dict):
            # Conservar claves hermanas si las hay
            merged = dict(inner)
            for k, v in data.items():
                if k == key:
                    continue
                if k not in merged:
                    merged[k] = v
            return merged
    return data


def looks_like_lighting_spec(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    d = _unwrap_lighting_root(data)
    hits = sum(1 for k in _LIGHTING_KEYS if k in d)
    if hits >= 2:
        return True
    if "environment_type" in d and hits >= 1:
        return True
    blob = " ".join(list(data.keys()) + list(d.keys())).lower().replace("-", "_")
    return any(
        x in blob
        for x in (
            "directional",
            "fog",
            "post_process",
            "skylight",
            "sky_light",
            "lighting_spec",
            "post_process_fog",
        )
    )


def _coerce_directional(value: Any) -> dict[str, Any]:
    """Objeto normal, o vec3 (dirección/rotación), o número (intensidad)."""
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        # El modelo suele mandar dirección o rotación como array
        return {"rotation": _as_vec3(value, [-45.0, 0.0, 0.0]), "intensity": 0.8, "temperature": 8500.0}
    if isinstance(value, (int, float)):
        return {"intensity": float(value)}
    if isinstance(value, bool):
        return {"intensity": 1.0 if value else 0.0}
    return {}


def _coerce_sky(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, bool):
        return {"intensity": 1.0 if value else 0.0, "realtime_capture": bool(value)}
    if isinstance(value, (int, float)):
        return {"intensity": float(value), "realtime_capture": True}
    return {}


def _coerce_fog(value: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Objeto, false (desactivar densidades altas), o true (defaults)."""
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        out.update(value)
    elif value is False:
        out["density"] = 0.0
        out["volumetric_fog"] = False
    elif value is True:
        out["density"] = 0.02
        out["volumetric_fog"] = True

    if extra:
        # post_process_fog / fog_color del LLM
        if "density" in extra and "density" not in out:
            out["density"] = extra["density"]
        elif "density" in extra and (
            not isinstance(value, dict) or "density" not in value
        ):
            out["density"] = extra["density"]
        color = (
            extra.get("fog_color")
            or extra.get("inscattering_color")
            or extra.get("color")
        )
        if color is not None:
            out["inscattering_color"] = color
        if "volumetric_fog" in extra:
            out["volumetric_fog"] = extra["volumetric_fog"]
        # Si había post_process_fog con density, activar fog aunque exponential_fog=false
        if value is False and _as_float(extra.get("density"), 0) > 0:
            out["volumetric_fog"] = True
            out["density"] = _as_float(extra.get("density"), 0.05)
    return out


def normalize_lighting_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """Rellena defaults sensatos y unifica nombres / formas raras del LLM."""
    d = _unwrap_lighting_root(dict(raw or {}))

    # Aliases frecuentes del LLM
    if "directional" in d and "directional_light" not in d:
        d["directional_light"] = d.pop("directional")
    if "sun" in d and "directional_light" not in d:
        d["directional_light"] = d.pop("sun")
    if "fog" in d and "exponential_fog" not in d:
        d["exponential_fog"] = d.pop("fog")
    if "postprocess" in d and "post_process" not in d:
        d["post_process"] = d.pop("postprocess")
    if "skylight" in d and "sky_light" not in d:
        d["sky_light"] = d.pop("skylight")

    # post_process_fog → datos de fog (a veces el LLM inventa esta clave)
    ppf = d.pop("post_process_fog", None)
    if not isinstance(ppf, dict):
        ppf = d.pop("height_fog", None) if isinstance(d.get("height_fog"), dict) else None

    env = str(d.get("environment_type") or d.get("name") or "Custom Atmosphere")
    # "Sky" solo no es descriptivo; si hay niebla densa, renombrar mejor
    if env.lower() in {"sky", "default", "custom"} and isinstance(ppf, dict):
        env = "Custom Atmosphere (fog)"

    dl = _coerce_directional(d.get("directional_light"))
    # Intensidad por defecto más baja si rotation venía como vec3 "luna"
    default_intensity = 0.8 if "rotation" in dl and "intensity" in dl else 10.0
    directional = {
        "intensity": _as_float(dl.get("intensity", dl.get("Intensity")), default_intensity),
        "temperature": _as_float(dl.get("temperature", dl.get("Temperature")), 6500.0),
        "rotation": _as_vec3(dl.get("rotation", dl.get("Rotation")), [-45.0, 0.0, 0.0]),
        "cast_shadows": _as_bool(dl.get("cast_shadows", dl.get("castShadows", True)), True),
    }

    sl = _coerce_sky(d.get("sky_light"))
    sky = {
        "intensity": _as_float(sl.get("intensity", sl.get("Intensity")), 1.0),
        "realtime_capture": _as_bool(
            sl.get("realtime_capture", sl.get("bRealTimeCapture", True)), True
        ),
    }

    fog_in = _coerce_fog(d.get("exponential_fog"), _as_dict(ppf))
    fog = {
        "density": _as_float(fog_in.get("density", fog_in.get("FogDensity")), 0.02),
        "height_falloff": _as_float(
            fog_in.get("height_falloff", fog_in.get("FogHeightFalloff")), 0.2
        ),
        "inscattering_color": _as_vec3(
            fog_in.get(
                "inscattering_color",
                fog_in.get("FogInscatteringColor", fog_in.get("fog_color")),
            ),
            [0.447, 0.639, 1.0],
        ),
        "volumetric_fog": _as_bool(
            fog_in.get("volumetric_fog", fog_in.get("bEnableVolumetricFog", True)), True
        ),
    }

    pp_in = _as_dict(d.get("post_process"))
    # A veces meten bloom/exposure dentro de post_process_fog
    if isinstance(ppf, dict):
        for k in ("exposure_compensation", "bloom_intensity", "vignette_intensity"):
            if k in ppf and k not in pp_in:
                pp_in[k] = ppf[k]
    post = {
        "exposure_compensation": _as_float(
            pp_in.get("exposure_compensation", pp_in.get("AutoExposureBias")), 0.0
        ),
        "bloom_intensity": _as_float(
            pp_in.get("bloom_intensity", pp_in.get("BloomIntensity")), 0.675
        ),
        "vignette_intensity": _as_float(
            pp_in.get("vignette_intensity", pp_in.get("VignetteIntensity")), 0.4
        ),
    }
    if "temperature" in pp_in:
        post["temperature"] = _as_float(pp_in.get("temperature"), 6500.0)
    if "saturation" in pp_in:
        post["saturation"] = _as_vec3(pp_in.get("saturation"), [1.0, 1.0, 1.0])

    return {
        "environment_type": env,
        "directional_light": directional,
        "sky_light": sky,
        "exponential_fog": fog,
        "post_process": post,
    }


def validate_lighting_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["Lighting-Spec no es un objeto"]
    if "directional_light" not in spec and "exponential_fog" not in spec and "post_process" not in spec:
        errors.append("Falta al menos directional_light, exponential_fog o post_process")
    return errors


def _try_parse_json_object(raw: str) -> dict[str, Any] | None:
    """Strict-first: loads → raw_decode → cierre de braces si truncado."""
    s = (raw or "").strip()
    if not s:
        return None
    if s.startswith("{"):
        try:
            data = json.loads(s)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    start = s.find("{")
    if start < 0:
        return None
    chunk = s[start:]
    try:
        data, _ = json.JSONDecoder().raw_decode(chunk)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    open_braces = chunk.count("{") - chunk.count("}")
    open_brackets = chunk.count("[") - chunk.count("]")
    if open_braces < 0 or open_brackets < 0:
        return None
    s2 = chunk + ("]" * open_brackets) + ("}" * open_braces)
    try:
        data = json.loads(s2)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _try_repair_json(raw: str) -> dict[str, Any] | None:
    return _try_parse_json_object(raw)


def extract_lighting_from_text(text: str) -> dict[str, Any] | None:
    """Extrae el primer JSON Lighting-Spec de una respuesta del modelo."""
    if not text or not text.strip():
        return None

    candidates: list[str] = []
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        candidates.append(fence.group(1).strip())
    candidates.append(text.strip())
    start = text.find("{")
    if start >= 0:
        candidates.append(text[start:].strip())

    best: dict[str, Any] | None = None
    for raw in candidates:
        data = _try_parse_json_object(raw)
        if not data:
            continue
        # Evitar confundir con BP-Lite
        if "nodes" in data and "graph_name" in data and not looks_like_lighting_spec(data):
            continue
        if looks_like_lighting_spec(data):
            return normalize_lighting_spec(data)
        if best is None and any(k in data for k in _LIGHTING_KEYS):
            best = data
    if best is not None:
        return normalize_lighting_spec(best)
    return None


def lighting_summary(spec: dict[str, Any]) -> str:
    dl = spec.get("directional_light") or {}
    fog = spec.get("exponential_fog") or {}
    pp = spec.get("post_process") or {}
    return (
        f"Lighting: {spec.get('environment_type')} | "
        f"sun I={dl.get('intensity')} T={dl.get('temperature')}K | "
        f"fog dens={fog.get('density')} | "
        f"PP exposure={pp.get('exposure_compensation')} bloom={pp.get('bloom_intensity')}"
    )


def _fog_explicitly_disabled(text: str) -> bool:
    """Negaciones explícitas: sin niebla / no fog / clear sky → apagar fog."""
    t = (text or "").lower()
    patterns = (
        r"\bsin\s+niebla\b",
        r"\bsin\s+fog\b",
        r"\bno\s+fog\b",
        r"\bsin\s+neblina\b",
        r"\bniebla\s+desactivad[ao]\b",
        r"\bfog\s+off\b",
        r"\bdisable[d]?\s+fog\b",
        r"\bclear\s+sky\b",
        r"\bcielo\s+despejado\b",
        r"\bsin\s+niebla\s+volum[eé]tric",
        r"\bno\s+volumetric\s+fog\b",
    )
    return any(re.search(p, t) for p in patterns)


def synthesize_lighting_from_prose(text: str) -> dict[str, Any] | None:
    """
    Si el modelo solo escribió prosa (sin JSON), infiere un preset razonable
    a partir de palabras clave + números sueltos (intensity, Kelvin, density).
    """
    if not text or not text.strip():
        return None
    t = text.lower()
    # Evitar sintetizar si el texto no habla de luz/atmósfera
    if not any(
        k in t
        for k in (
            "luz",
            "light",
            "niebla",
            "fog",
            "ilumin",
            "atmósfer",
            "atmosfer",
            "exposición",
            "exposicion",
            "bloom",
            "moon",
            "luna",
            "noche",
            "bosque",
            "cyber",
            "atardecer",
            "temperature",
            "temperatura",
            "directional",
        )
    ):
        return None

    # Presets base
    if any(k in t for k in ("cyber", "neón", "neon", "lluvia", "alley")):
        base = {
            "environment_type": "Cyberpunk Rainy Alley",
            "directional_light": {
                "intensity": 2.0,
                "temperature": 7500,
                "rotation": [-25.0, 120.0, 0.0],
                "cast_shadows": True,
            },
            "sky_light": {"intensity": 1.5, "realtime_capture": True},
            "exponential_fog": {
                "density": 0.04,
                "height_falloff": 0.2,
                "inscattering_color": [0.05, 0.1, 0.2],
                "volumetric_fog": True,
            },
            "post_process": {
                "exposure_compensation": 0.5,
                "bloom_intensity": 2.0,
                "vignette_intensity": 0.4,
            },
        }
    elif any(k in t for k in ("atardecer", "sunset", "desierto", "desert", "cálid", "calid")):
        base = {
            "environment_type": "Warm Desert Sunset",
            "directional_light": {
                "intensity": 8.0,
                "temperature": 3500,
                "rotation": [-15.0, 200.0, 0.0],
                "cast_shadows": True,
            },
            "sky_light": {"intensity": 0.8, "realtime_capture": True},
            "exponential_fog": {
                "density": 0.01,
                "height_falloff": 0.3,
                "inscattering_color": [1.0, 0.55, 0.25],
                "volumetric_fog": False,
            },
            "post_process": {
                "exposure_compensation": 0.2,
                "bloom_intensity": 0.8,
                "vignette_intensity": 0.35,
            },
        }
    elif any(k in t for k in ("noche", "night", "luna", "moon", "bosque", "forest", "frí", "fri")):
        base = {
            "environment_type": "Misty Night Forest",
            "directional_light": {
                "intensity": 0.8,
                "temperature": 8500,
                "rotation": [-60.0, 45.0, 0.0],
                "cast_shadows": True,
            },
            "sky_light": {"intensity": 0.6, "realtime_capture": True},
            "exponential_fog": {
                "density": 0.08,
                "height_falloff": 0.15,
                "inscattering_color": [0.02, 0.05, 0.12],
                "volumetric_fog": True,
            },
            "post_process": {
                "exposure_compensation": -1.0,
                "bloom_intensity": 0.5,
                "vignette_intensity": 0.6,
            },
        }
    else:
        base = {
            "environment_type": "Custom Atmosphere",
            "directional_light": {
                "intensity": 5.0,
                "temperature": 6500,
                "rotation": [-45.0, 30.0, 0.0],
                "cast_shadows": True,
            },
            "sky_light": {"intensity": 1.0, "realtime_capture": True},
            "exponential_fog": {
                "density": 0.02,
                "height_falloff": 0.2,
                "inscattering_color": [0.45, 0.64, 1.0],
                "volumetric_fog": True,
            },
            "post_process": {
                "exposure_compensation": 0.0,
                "bloom_intensity": 0.675,
                "vignette_intensity": 0.4,
            },
        }

    # Sobrescribir con números mencionados en la prosa
    kelvin = re.search(r"(\d{3,5})\s*k\b", t)
    if kelvin:
        base["directional_light"]["temperature"] = float(kelvin.group(1))
    dens = re.search(r"(?:densidad|density)\s*[:=]?\s*([0-9]*\.?[0-9]+)", t)
    if dens:
        base["exponential_fog"]["density"] = float(dens.group(1))
    inten = re.search(
        r"(?:intensidad|intensity)\s*(?:de\s+la\s+luz)?\s*[:=]?\s*([0-9]*\.?[0-9]+)", t
    )
    if inten:
        base["directional_light"]["intensity"] = float(inten.group(1))
    expo = re.search(
        r"(?:exposici[oó]n|exposure(?:\s*compensation)?|auto\s*exposure)\s*[:=]?\s*(-?[0-9]*\.?[0-9]+)",
        t,
    )
    if expo:
        base["post_process"]["exposure_compensation"] = float(expo.group(1))
    bloom = re.search(r"bloom\s*[:=]?\s*([0-9]*\.?[0-9]+)", t)
    if bloom:
        base["post_process"]["bloom_intensity"] = float(bloom.group(1))

    if _fog_explicitly_disabled(t):
        base["exponential_fog"]["density"] = 0.0
        base["exponential_fog"]["volumetric_fog"] = False
    elif "niebla" in t or "fog" in t or "densa" in t:
        base["exponential_fog"]["volumetric_fog"] = True
        if base["exponential_fog"]["density"] < 0.04 and "densa" in t:
            base["exponential_fog"]["density"] = max(
                base["exponential_fog"]["density"], 0.08
            )

    return normalize_lighting_spec(base)


def prepare_lighting_payload(text_or_spec: str | dict[str, Any]) -> dict[str, Any]:
    synthesized = False
    if isinstance(text_or_spec, dict):
        spec = normalize_lighting_spec(text_or_spec)
    else:
        spec = extract_lighting_from_text(text_or_spec)
        if spec is None:
            spec = synthesize_lighting_from_prose(text_or_spec)
            synthesized = spec is not None
        if spec is None:
            return {
                "ok": False,
                "error": "No se encontró JSON Lighting-Spec en el texto",
            }

    errors = validate_lighting_spec(spec)
    if errors:
        return {"ok": False, "error": "; ".join(errors), "spec": spec}

    summary = lighting_summary(spec)
    if synthesized:
        summary = "[inferido de la prosa] " + summary

    return {
        "ok": True,
        "spec": spec,
        "summary": summary,
        "synthesized": synthesized,
    }


def _editor_actor_subsystem(unreal_mod: Any) -> Any:
    """UE5: EditorActorSubsystem; fallback a EditorLevelLibrary si hace falta."""
    try:
        return unreal_mod.get_editor_subsystem(unreal_mod.EditorActorSubsystem)
    except Exception:  # noqa: BLE001
        return None


def _actors_of_class(unreal_mod: Any, cls: Any) -> list[Any]:
    sub = _editor_actor_subsystem(unreal_mod)
    if sub is not None:
        try:
            return list(sub.get_all_level_actors_of_class(cls))
        except Exception:  # noqa: BLE001
            pass
    # Deprecated UE4 path
    return list(unreal_mod.EditorLevelLibrary.get_all_level_actors_of_class(cls))


def _spawn_actor(unreal_mod: Any, cls: Any, location: Any | None = None) -> Any:
    sub = _editor_actor_subsystem(unreal_mod)
    loc = location or unreal_mod.Vector(0.0, 0.0, 0.0)
    rot = unreal_mod.Rotator(0.0, 0.0, 0.0)
    if sub is not None:
        try:
            return sub.spawn_actor_from_class(cls, loc, rot)
        except Exception:  # noqa: BLE001
            pass
    return unreal_mod.EditorLevelLibrary.spawn_actor_from_class(cls, loc, rot)


def apply_lighting_preset(config: dict[str, Any]) -> None:
    """
    Ejecutar dentro del entorno `unreal` del Editor (scaffold Python).
    UE5: ``EditorActorSubsystem``; crea fog/PPV si el nivel no los tiene.
    El camino principal del plugin es el applier C++.
    """
    try:
        import unreal  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Solo usable dentro de Unreal Editor Python") from exc

    cfg = normalize_lighting_spec(config)

    dir_lights = _actors_of_class(unreal, unreal.DirectionalLight)
    if not dir_lights:
        spawned = _spawn_actor(unreal, unreal.DirectionalLight)
        if spawned is not None:
            dir_lights = [spawned]
    if dir_lights:
        sun = dir_lights[0].light_component
        d_cfg = cfg["directional_light"]
        sun.set_intensity(d_cfg["intensity"])
        sun.set_use_temperature(True)
        sun.set_temperature(d_cfg["temperature"])
        rot = d_cfg["rotation"]
        dir_lights[0].set_actor_rotation(
            unreal.Rotator(rot[0], rot[1], rot[2]), False
        )

    fog_actors = _actors_of_class(unreal, unreal.ExponentialHeightFog)
    if not fog_actors:
        spawned = _spawn_actor(unreal, unreal.ExponentialHeightFog)
        if spawned is not None:
            fog_actors = [spawned]
    if fog_actors:
        fog = fog_actors[0].component
        f_cfg = cfg["exponential_fog"]
        fog.set_fog_density(f_cfg["density"])
        fog.set_volumetric_fog(f_cfg["volumetric_fog"])
        if "height_falloff" in f_cfg:
            try:
                fog.set_fog_height_falloff(f_cfg["height_falloff"])
            except Exception:  # noqa: BLE001
                pass

    pp_actors = _actors_of_class(unreal, unreal.PostProcessVolume)
    if not pp_actors:
        spawned = _spawn_actor(unreal, unreal.PostProcessVolume)
        if spawned is not None:
            pp_actors = [spawned]
            try:
                spawned.set_editor_property("unbound", True)
            except Exception:  # noqa: BLE001
                pass
    if pp_actors:
        pp = pp_actors[0].settings
        p_cfg = cfg["post_process"]
        pp.set_editor_property("auto_exposure_bias", p_cfg["exposure_compensation"])
        pp.set_editor_property("bloom_intensity", p_cfg["bloom_intensity"])
        pp.set_editor_property("vignette_intensity", p_cfg["vignette_intensity"])

    unreal.log("Configuración de iluminación aplicada correctamente.")
