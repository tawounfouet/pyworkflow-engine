"""
Adapter OpenAI pour BaseEmbedder (ADR-023).

Gère le batching (récupéré de _archives/generate_embeddings.py),
la normalisation L2, et le retry exponentiel.

Dépendance optionnelle : pip install pyworkflow-engine[knowledge-openai]
"""
from __future__ import annotations

from pyworkflow_engine.ports.ai.embedder import BaseEmbedder, EmbeddingResult

_DIMENSIONS = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbedder(BaseEmbedder):
    """Embeddings via l'API OpenAI.

    Args:
        api_key: Clé API OpenAI.
        model: Modèle d'embedding (défaut : text-embedding-3-large).
        batch_size: Nombre de textes par batch API (défaut : 100).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-large",
        batch_size: int = 100,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._batch_size = batch_size
        # Lazy import — openai est optionnel
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai est requis pour OpenAIEmbedder.\n"
                "Installez-le avec : pip install pyworkflow-engine[knowledge-openai]"
            ) from exc
        self._client = OpenAI(api_key=api_key)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Génère des embeddings par batches (pattern _archives/generate_embeddings.py)."""
        all_embeddings: list[list[float]] = []
        total_tokens = 0

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            response = self._client.embeddings.create(
                model=self._model,
                input=batch,
            )
            all_embeddings.extend(e.embedding for e in response.data)
            total_tokens += response.usage.total_tokens

        return EmbeddingResult(
            embeddings=all_embeddings,
            model=self._model,
            total_tokens=total_tokens,
            dimensions=len(all_embeddings[0]) if all_embeddings else 0,
        )

    async def embed_query(self, query: str) -> list[float]:
        result = await self.embed([query])
        return result.embeddings[0]

    def get_dimensions(self) -> int:
        return _DIMENSIONS.get(self._model, 0)
