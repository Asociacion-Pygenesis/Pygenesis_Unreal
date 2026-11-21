"""Optional FAISS RAG over local vectorstore/."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Callable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = BACKEND_ROOT / "vectorstore"

embedder = None
indice = None
fragmentos: list[dict] = []


def cargar_rag(*, on_loading: Callable[[], None] | None = None) -> None:
    global embedder, indice, fragmentos
    indice_path = VECTOR_DIR / "indice.faiss"
    fragmentos_path = VECTOR_DIR / "fragmentos.pkl"
    if not indice_path.is_file() or not fragmentos_path.is_file():
        print("RAG no disponible (falta vectorstore/). El backend funcionará sin contexto.")
        return

    try:
        import faiss
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        print(f"RAG omitido (dependencias no instaladas): {exc}")
        return

    print("Cargando base de conocimiento...")
    if on_loading is not None:
        on_loading()
    embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    indice = faiss.read_index(str(indice_path))
    with open(fragmentos_path, "rb") as f:
        fragmentos = pickle.load(f)
    print(f"Base cargada: {len(fragmentos)} fragmentos")


def buscar_contexto(pregunta: str, top_k: int = 3) -> list:
    if embedder is None or indice is None:
        return []
    embedding = embedder.encode([pregunta]).astype("float32")
    distancias, indices = indice.search(embedding, top_k)
    resultados = []
    for i, idx in enumerate(indices[0]):
        if idx != -1 and distancias[0][i] < 2.0:
            resultados.append(fragmentos[idx])
    return resultados


def rag_stats() -> dict[str, Any]:
    return {
        "fragmentos": len(fragmentos),
        "rag_activo": embedder is not None,
    }
