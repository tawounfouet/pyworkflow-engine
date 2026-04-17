"""
Adapter RecursiveChunker pour BaseChunker (ADR-023).

Chunking par taille + overlap avec détection de frontières sémantiques.
Idées récupérées de _archives/knowledge/services/chunking.py :
  - Stratégies par type de document (PDF → paragraphes, HTML → sections, Q&A → paires)
  - Préservation du contexte via overlap configurable
  - Minimum chunk size pour éviter les fragments inutiles

Sans dépendance LangChain — utilise uniquement les séparateurs regex natifs Python.
"""
from __future__ import annotations

import re
from typing import Any

from pyworkflow_engine.ports.ai.chunker import BaseChunker, ChunkResult

# Séparateurs par type de document (ordre décroissant de préférence)
_SEPARATORS: dict[str, list[str]] = {
    "markdown": ["\n## ", "\n### ", "\n#### ", "\n\n", "\n", " "],
    "html": ["</p>", "</div>", "</section>", "\n\n", "\n", " "],
    "qa": ["\n\nQ:", "\nQ:", "\n\n", "\n", " "],
    "pdf": ["\n\n", "\n", ". ", " "],
    "text": ["\n\n", "\n", ". ", " "],
    "docx": ["\n\n", "\n", ". ", " "],
}


class RecursiveChunker(BaseChunker):
    """Chunking récursif par taille + overlap, sensible au type de document.

    Args:
        chunk_size: Taille maximale d'un chunk en caractères (défaut : 1000).
        chunk_overlap: Chevauchement entre chunks en caractères (défaut : 200).
        min_chunk_size: Taille minimale pour éviter les fragments inutiles (défaut : 50).
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 50,
    ) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._min_chunk_size = min_chunk_size

    def chunk(
        self,
        text: str,
        *,
        doc_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> list[ChunkResult]:
        if not text or not text.strip():
            return []

        separators = _SEPARATORS.get(doc_type, _SEPARATORS["text"])
        raw_chunks = self._split_recursive(text.strip(), separators)
        merged = self._merge_chunks(raw_chunks)

        base_metadata = metadata or {}
        return [
            ChunkResult(
                content=chunk,
                index=i,
                metadata={**base_metadata, "doc_type": doc_type},
            )
            for i, chunk in enumerate(merged)
        ]

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        """Découpe récursivement en utilisant les séparateurs dans l'ordre."""
        if len(text) <= self._chunk_size:
            return [text] if text.strip() else []

        # Cherche le premier séparateur qui permet de couper le texte
        for sep in separators:
            if sep in text:
                parts = text.split(sep)
                result: list[str] = []
                current = ""
                for part in parts:
                    candidate = current + (sep if current else "") + part
                    if len(candidate) <= self._chunk_size:
                        current = candidate
                    else:
                        if current and len(current.strip()) >= self._min_chunk_size:
                            result.append(current.strip())
                        # Si la partie est encore trop longue, on recurse
                        if len(part) > self._chunk_size:
                            result.extend(self._split_recursive(part, separators[1:]))
                            current = ""
                        else:
                            current = part
                if current and len(current.strip()) >= self._min_chunk_size:
                    result.append(current.strip())
                return result

        # Fallback : découpe par caractères si aucun séparateur ne fonctionne
        return self._split_by_chars(text)

    def _split_by_chars(self, text: str) -> list[str]:
        """Découpe brute par taille de caractères (fallback)."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + self._chunk_size
            chunk = text[start:end].strip()
            if chunk and len(chunk) >= self._min_chunk_size:
                chunks.append(chunk)
            start += self._chunk_size - self._chunk_overlap
        return chunks

    def _merge_chunks(self, chunks: list[str]) -> list[str]:
        """Fusionne les petits fragments et applique l'overlap."""
        if not chunks:
            return []

        merged: list[str] = []
        current = chunks[0]

        for i in range(1, len(chunks)):
            next_chunk = chunks[i]
            if len(current) + len(next_chunk) + 1 <= self._chunk_size:
                current = current + " " + next_chunk
            else:
                merged.append(current)
                # Overlap : réintègre la fin du chunk précédent
                if self._chunk_overlap > 0:
                    overlap_text = current[-self._chunk_overlap:]
                    # Cherche le premier espace pour ne pas couper un mot
                    space_idx = overlap_text.find(" ")
                    if space_idx != -1:
                        overlap_text = overlap_text[space_idx:].strip()
                    current = overlap_text + " " + next_chunk if overlap_text else next_chunk
                else:
                    current = next_chunk

        if current and len(current.strip()) >= self._min_chunk_size:
            merged.append(current)

        return merged
