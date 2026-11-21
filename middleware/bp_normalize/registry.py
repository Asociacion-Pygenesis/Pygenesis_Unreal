"""Registro abierto de normalizadores por nodo."""

from __future__ import annotations

from typing import Callable, Protocol

from middleware.bp_models import BPNode


class NodeNormalizer(Protocol):
    name: str

    def matches(self, node: BPNode) -> bool: ...

    def normalize(self, node: BPNode) -> BPNode: ...


_REGISTRY: list[NodeNormalizer] = []


def register(normalizer: NodeNormalizer) -> NodeNormalizer:
    _REGISTRY.append(normalizer)
    return normalizer


def normalizer(
    match: Callable[[BPNode], bool], *, name: str = ""
) -> Callable[[Callable[[BPNode], BPNode]], NodeNormalizer]:
    def deco(fn: Callable[[BPNode], BPNode]) -> NodeNormalizer:
        class _N:
            pass

        n = _N()
        n.name = name or fn.__name__
        n.matches = match  # type: ignore[method-assign]
        n.normalize = fn  # type: ignore[method-assign]
        return register(n)  # type: ignore[arg-type]

    return deco


def _ensure_handlers() -> None:
    if _REGISTRY:
        return
    from middleware.bp_normalize import handlers as _handlers

    _handlers.ensure_registered()


def apply_normalizers(nodes: list[BPNode], *, graph_name: str = "") -> list[BPNode]:
    _ = graph_name
    _ensure_handlers()
    out: list[BPNode] = []
    for node in nodes:
        cur = node
        for norm in _REGISTRY:
            if norm.matches(cur):
                cur = norm.normalize(cur)
        out.append(cur)
    return out


def list_normalizers() -> list[str]:
    _ensure_handlers()
    return [n.name for n in _REGISTRY]
