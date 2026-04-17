"""
Port IA — interface abstraite pour la génération d'embeddings (ADR-023).

Sépare l'embedding du LLM chat : un embedder est un service spécialisé
qui transforme du texte en vecteurs numériques.

Note de design : BaseEmbedder est séparé de BaseLLMClient car :
  - Les embeddings ont une interface radicalement différente (batch in → vecteurs out)
  - Certains providers d'embeddings ne font pas de chat (Sentence Transformers, Cohere)
  - Le batching et la normalisation sont spécifiques aux embeddings (SRP)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingResult:
    """Résultat d'un appel d'embedding."""

    embeddings: list[list[float]]
    model: str
    total_tokens: int = 0
    dimensions: int = 0


class BaseEmbedder(ABC):
    """Interface pour tout provider d'embeddings.

    Implémentations prévues :
      - OpenAIEmbedder            (text-embedding-3-large/small)
      - OllamaEmbedder            (nomic-embed-text, mxbai-embed-large)
      - SentenceTransformerEmbedder (local, GGUF)
    """

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        """Génère des embeddings pour une liste de textes.

        Args:
            texts: Textes à encoder (déjà chunkés).

        Returns:
            EmbeddingResult avec les vecteurs et métadonnées.
        """

    @abstractmethod
    async def embed_query(self, query: str) -> list[float]:
        """Génère l'embedding d'une requête utilisateur (un seul texte).

        Certains providers distinguent l'embedding de documents vs queries.
        """

    def get_dimensions(self) -> int:
        """Retourne la dimensionnalité des vecteurs (ex: 3072, 1536, 768)."""
        return 0  # Override par chaque adapter
