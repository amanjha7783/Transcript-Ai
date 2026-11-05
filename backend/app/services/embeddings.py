from functools import lru_cache
from typing import Sequence
from app.core.config import settings


@lru_cache(maxsize=1)
def get_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("sentence-transformers is not installed. Install backend requirements.") from exc
    return SentenceTransformer(settings.embedding_model)


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    if not texts:
        return []
    model = get_model()
    vectors = model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
    return vectors.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    # Vectors are normalized by the embedding model; dot product is cosine similarity.
    return sum(x * y for x, y in zip(a, b))
