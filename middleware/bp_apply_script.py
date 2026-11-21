"""Genera script Python ejecutable en Unreal Editor para materializar BP-Lite."""

from __future__ import annotations

import json
from typing import Any


def build_apply_script(graph: dict[str, Any], asset_path: str = "/Game/Pygenesis") -> str:
    payload = json.dumps(graph, ensure_ascii=False)
    # Usar json.dumps del payload dentro del script para evitar problemas de escaping.
    return f'''# -*- coding: utf-8 -*-
# Pygenesis: aplica BP-Lite (crear Blueprint + metadatos + nodos K2 basicos)
import json
import unreal

GRAPH = json.loads({payload!r})
ASSET_PATH = {asset_path!r}


def ensure_dir(path: str) -> None:
    if not unreal.EditorAssetLibrary.does_directory_exist(path):
        unreal.EditorAssetLibrary.make_directory(path)


def pick_parent(nodes):
    blob = " ".join("%s %s" % (n.get("type", ""), n.get("name", "")) for n in nodes).lower()
    compact = blob.replace(" ", "")
    if "launchcharacter" in compact or "character" in blob:
        return unreal.Character
    return unreal.Actor


def find_ubergraph(bp):
    pages = bp.ubergraph_pages
    if pages and len(pages) > 0:
        return pages[0]
    return None


def spawn_custom_event(graph, name, x, y):
    node = unreal.EditorUtilityLibrary  # placeholder keep import side effects
    # UK2Node_CustomEvent via load class
    cls = unreal.load_class(None, "/Script/BlueprintGraph.K2Node_CustomEvent")
    if not cls:
        return None
    node = unreal.BlueprintEditorLibrary.add_node_to_graph(graph, cls, unreal.Vector2D(x, y)) if hasattr(unreal, "BlueprintEditorLibrary") and hasattr(unreal.BlueprintEditorLibrary, "add_node_to_graph") else None
    return node


def apply():
    nodes = GRAPH.get("nodes") or []
    bp_name = GRAPH.get("graph_name") or "Pygenesis_BP"
    ensure_dir(ASSET_PATH)

    parent = pick_parent(nodes)
    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", parent)
    tools = unreal.AssetToolsHelpers.get_asset_tools()

    full = "%s/%s" % (ASSET_PATH, bp_name)
    if unreal.EditorAssetLibrary.does_asset_exist(full):
        bp_name = bp_name + "_Pygen"
        full = "%s/%s" % (ASSET_PATH, bp_name)

    bp = tools.create_asset(bp_name, ASSET_PATH, unreal.Blueprint, factory)
    if not bp:
        unreal.log_error("Pygenesis: no se pudo crear Blueprint")
        return None

    # Guardar JSON BP-Lite en Saved/
    saved = unreal.Paths.project_saved_dir() + "Pygenesis/"
    try:
        unreal.SystemLibrary.make_directory(saved)
    except Exception:
        import os
        os.makedirs(saved, exist_ok=True)
    json_file = saved + bp_name + "_bplite.json"
    with open(json_file, "w", encoding="utf-8") as fh:
        json.dump(GRAPH, fh, ensure_ascii=False, indent=2)

    # Intento de nodos: el applier C++ del plugin hace el montaje K2 real.
    # Aqui dejamos el asset listo y un resumen en el log.
    lines = []
    for n in nodes:
        lines.append("[%s] %s — %s" % (n.get("id"), n.get("type"), n.get("name")))
    unreal.log("Pygenesis BP-Lite plan:\\n- " + "\\n- ".join(lines))

    unreal.EditorAssetLibrary.save_loaded_asset(bp)
    unreal.log("Pygenesis: Blueprint creado %s" % full)
    unreal.log("Pygenesis: JSON en %s" % json_file)

    try:
        unreal.EditorDialog.show_message(
            "Pygenesis BP-Lite",
            "Blueprint creado:\\n%s\\n\\nNodos: %d\\nJSON: %s\\n\\nSi el plugin C++ esta activo, tambien intenta montar nodos K2." % (full, len(nodes), json_file),
            unreal.AppMsgType.OK,
        )
    except Exception:
        pass

    # Abrir el asset
    try:
        unreal.AssetEditorSubsystem().open_editor_for_assets([bp])
    except Exception:
        pass
    return full


apply()
'''
