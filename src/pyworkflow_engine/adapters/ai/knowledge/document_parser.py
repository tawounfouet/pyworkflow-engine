"""
Adapter LocalDocumentParser pour BaseDocumentParser (ADR-023).

Extrait le texte depuis des fichiers locaux (PDF, DOCX, HTML, Markdown, texte brut).
Dépendances optionnelles : pip install pyworkflow-engine[knowledge-parsers]
"""
from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from pyworkflow_engine.ports.ai.parser import BaseDocumentParser, ParseResult

_SUPPORTED_TYPES = ["text", "markdown", "md", "pdf", "docx", "html", "htm"]

_EXT_TO_TYPE: dict[str, str] = {
    ".txt": "text",
    ".md": "markdown",
    ".markdown": "markdown",
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".html": "html",
    ".htm": "html",
}


class LocalDocumentParser(BaseDocumentParser):
    """Parser local supportant PDF, DOCX, HTML, Markdown et texte brut.

    Pour PDF : nécessite PyPDF2 (pip install PyPDF2)
    Pour DOCX : nécessite python-docx (pip install python-docx)
    Pour HTML : nécessite beautifulsoup4 (pip install beautifulsoup4)
    """

    def parse(
        self,
        source: str | Path | BinaryIO,
        *,
        doc_type: str | None = None,
    ) -> ParseResult:
        path = Path(source) if isinstance(source, str) else source  # type: ignore[arg-type]

        if isinstance(path, Path):
            detected_type = doc_type or _EXT_TO_TYPE.get(path.suffix.lower(), "text")
            title = path.stem
        else:
            detected_type = doc_type or "text"
            title = ""

        if detected_type == "pdf":
            return self._parse_pdf(path, title)
        elif detected_type in ("docx", "doc"):
            return self._parse_docx(path, title)
        elif detected_type in ("html", "htm"):
            return self._parse_html(path, title)
        else:
            return self._parse_text(path, title, detected_type)

    def supported_types(self) -> list[str]:
        return _SUPPORTED_TYPES

    def _parse_text(
        self, source: Path | BinaryIO, title: str, doc_type: str
    ) -> ParseResult:
        if isinstance(source, Path):
            content = source.read_text(encoding="utf-8", errors="replace")
        else:
            content = source.read().decode("utf-8", errors="replace")
        return ParseResult(
            content=content,
            title=title,
            doc_type=doc_type,
            char_count=len(content),
        )

    def _parse_pdf(self, source: Path | BinaryIO, title: str) -> ParseResult:
        try:
            import PyPDF2
        except ImportError as exc:
            raise ImportError(
                "PyPDF2 est requis pour parser les PDF.\n"
                "Installez-le avec : pip install pyworkflow-engine[knowledge-parsers]"
            ) from exc

        if isinstance(source, Path):
            fh = source.open("rb")
            close_after = True
        else:
            fh = source
            close_after = False

        try:
            reader = PyPDF2.PdfReader(fh)
            pages = [page.extract_text() or "" for page in reader.pages]
            content = "\n\n".join(pages)
            return ParseResult(
                content=content,
                title=title,
                doc_type="pdf",
                page_count=len(pages),
                char_count=len(content),
            )
        finally:
            if close_after:
                fh.close()

    def _parse_docx(self, source: Path | BinaryIO, title: str) -> ParseResult:
        try:
            import docx
        except ImportError as exc:
            raise ImportError(
                "python-docx est requis pour parser les fichiers DOCX.\n"
                "Installez-le avec : pip install pyworkflow-engine[knowledge-parsers]"
            ) from exc

        doc = docx.Document(source)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        content = "\n\n".join(paragraphs)
        return ParseResult(
            content=content,
            title=title,
            doc_type="docx",
            char_count=len(content),
        )

    def _parse_html(self, source: Path | BinaryIO, title: str) -> ParseResult:
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:
            raise ImportError(
                "beautifulsoup4 est requis pour parser les fichiers HTML.\n"
                "Installez-le avec : pip install pyworkflow-engine[knowledge-parsers]"
            ) from exc

        if isinstance(source, Path):
            raw = source.read_text(encoding="utf-8", errors="replace")
        else:
            raw = source.read().decode("utf-8", errors="replace")

        soup = BeautifulSoup(raw, "html.parser")
        # Extraction du titre depuis <title> ou <h1>
        if not title:
            tag = soup.find("title") or soup.find("h1")
            title = tag.get_text(strip=True) if tag else ""

        # Suppression des scripts et styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        content = soup.get_text(separator="\n", strip=True)
        return ParseResult(
            content=content,
            title=title,
            doc_type="html",
            char_count=len(content),
        )
