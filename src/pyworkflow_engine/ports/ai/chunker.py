"""
Port IA — interface abstraite pour le chunking de documents (ADR-023).

Découpe un texte brut en fragments optimisés pour l'indexation vectorielle.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChunkResult:
    """Fragment de texte produit par le chunker."""

    content: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseChunker(ABC):
    """Interface pour toute stratégie de chunking.

    Implémentations prévues :
      - RecursiveChunker     (défaut, par taille + overlap)
      - SemanticChunker      (par frontières sémantiques)
      - QAChunker            (préservation Q&A pairs)
      - MarkdownChunker      (header-aware)
    """

    @abstractmethod
    def chunk(
        self,
        text: str,
        *,
        doc_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        """Découpe un texte en chunks.

        Args:
            text: Texte brut à découper.
            doc_type: Type de document (text, pdf, html, markdown, qa).
            metadata: Métadonnées à propager dans chaque chunk.

        Returns:
            Liste ordonnée de ChunkResult.
        """
