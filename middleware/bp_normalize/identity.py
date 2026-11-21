"""Identidad de nodo compartida por podar y reparar.

enrich.py no usa esto: su blob no quita guiones bajos y trata
CustomEvent como entrada. Unificarlo cambiaría qué cuenta como huérfano.
"""

from __future__ import annotations

from middleware.bp_models import BPNode


def node_blob(node: BPNode) -> str:
    return f"{node.type}{node.name}".lower().replace(" ", "").replace("_", "")
