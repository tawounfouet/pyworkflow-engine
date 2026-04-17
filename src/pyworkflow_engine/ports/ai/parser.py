"""
Port IA — interface abstraite pour l'extraction de texte depuis des fichiers (ADR-023).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO


@dataclass
class ParseResult:
    """Résultat de l'extraction de texte."""

    content: str
    title: str = ""
    doc_type: str = "text"            # pdf, docx, html, text, markdown
    page_count: int = 0
    char_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseDocumentParser(ABC):
    """Interface pour l'extraction de texte depuis des fichiers.

    Implémentations prévues :
      - LocalDocumentParser   (PyPDF2 + python-docx + BeautifulSoup)
      - WebScraperParser      (HTTP + BS4, pour les sources URL)
    """

    @abstractmethod
    def parse(
        self,
        source: str | Path | BinaryIO,
        *,
        doc_type: str | None = None,
    ) -> ParseResult:
        """Extrait le texte d'un fichier ou d'une URL.

        Args:
            source: Chemin fichier, URL, ou buffer binaire.
            doc_type: Type forcé (auto-détecté si None).

        Returns:
            ParseResult avec le contenu et les métadonnées.
        """

    @abstractmethod
    def supported_types(self) -> list[str]:
        """Liste des types de documents supportés par ce parser."""
