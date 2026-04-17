"""
Parsing XML codes.droit.org → articles structurés.

Reproduit fidèlement le format de ``_archives/pytaxes-engine/data/cgi_database.json`` :
- Métadonnées extraites de la racine ``<code>``
- Champ ``code`` compact (ex: "1 A" → "A1A")
- Champ ``parent_section`` — ID du nœud ``<t>`` parent
- Champ ``references`` — liste des ``destinationid`` des renvois croisés
- Contenu avec sauts de ligne (``<br/>`` → ``\\n``)

Utilise uniquement ``xml.etree.ElementTree`` (stdlib — ADR-025 D3).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


# ── Helpers ────────────────────────────────────────────────────────────────────


def _number_to_code(number: str) -> str:
    """Convertit un numéro d'article en code compact.

    Exemples :
        "1 A"    → "A1A"
        "4 B"    → "A4B"
        "8 bis"  → "A8bis"
        "111-1"  → "A111-1"
        "L. 123" → "AL123"
    """
    if not number:
        return ""
    # Supprimer les points et espaces superflus, capitaliser les suffixes
    compact = re.sub(r"[\s.]+", "", number)
    return f"A{compact}"


def _element_text_with_br(element: ET.Element) -> str:
    """Extrait le texte d'un élément en convertissant les ``<br/>`` en ``\\n``.

    Parcourt récursivement les enfants pour reconstruire le texte dans l'ordre
    du document, en insérant ``\\n`` à chaque balise ``<br/>``.
    """
    parts: list[str] = []

    # Texte direct avant le premier enfant
    if element.text:
        parts.append(element.text)

    for child in element:
        tag = child.tag.lower() if isinstance(child.tag, str) else ""
        if tag == "br":
            parts.append("\n")
        else:
            # Récursion pour les éléments imbriqués (ex: <i>, <b>, <a>...)
            parts.append(_element_text_with_br(child))

        # Texte "tail" (après la fermeture de la balise enfant)
        if child.tail:
            parts.append(child.tail)

    return "".join(parts).strip()


def _extract_references(article_elem: ET.Element) -> list[str]:
    """Extrait les identifiants des articles référencés (``destinationid``)."""
    refs: list[str] = []
    for ref_elem in article_elem.iter():
        dest = ref_elem.get("destinationid") or ref_elem.get("destinationId")
        if dest and dest not in refs:
            refs.append(dest)
    return refs


# ── API publique ───────────────────────────────────────────────────────────────


def extract_metadata(xml_path: Path) -> dict[str, Any]:
    """Extrait les métadonnées de l'élément racine ``<code>``.

    Returns:
        Dict avec ``source``, ``source_type``, ``code_id``, ``code_nom``,
        ``lastup``, ``build``, ``articles_count`` (0 avant parsing).
    """
    try:
        # Lire uniquement la racine pour les performances
        for _event, elem in ET.iterparse(
            str(xml_path), events=("start",)
        ):  # noqa: S314
            return {
                "source": xml_path.name,
                "source_type": "xml",
                "code_nom": elem.get("nom", ""),
                "code_id": elem.get("id", ""),
                "lastup": elem.get("lastup", ""),
                "build": elem.get("build", ""),
                "articles_count": 0,  # mis à jour après extraction
            }
    except ET.ParseError:
        pass
    return {"source": xml_path.name, "source_type": "xml", "articles_count": 0}


def _extract_articles(xml_path: Path, slug: str) -> list[dict[str, Any]]:
    """Parse un fichier XML codes.droit.org et extrait les articles en vigueur.

    Format de sortie identique à ``_archives/pytaxes-engine/data/cgi_database.json`` :

    .. code-block:: json

        {
            "code": "A1A",
            "number": "1 A",
            "title": "Article 1 A",
            "content": "Il est établi un impôt...",
            "parent_section": "LEGISCTA000006133844",
            "legiarti_id": "LEGIARTI000006302199",
            "etat": "VIGUEUR",
            "effective_date": "2005-12-31",
            "references": ["LEGIARTI000053544806"],
            "slug": "cgi"
        }

    Filtre :
    - ``article[@etat] == "VIGUEUR"``
    - Contenu textuel non vide

    Args:
        xml_path: Chemin absolu vers le fichier ``.xml``.
        slug:     Identifiant du code source (ex : ``cgi``).

    Returns:
        Liste de dicts avec les champs définis dans ADR-025.
    """
    try:
        tree = ET.parse(xml_path)  # noqa: S314
    except ET.ParseError:
        return []

    root = tree.getroot()
    articles: list[dict[str, Any]] = []

    # Construire un index parent : article_id → section_id
    # On parcourt l'arbre pour trouver quel <t> contient chaque <article>
    parent_map: dict[ET.Element, ET.Element] = {
        child: parent for parent in root.iter() for child in parent
    }

    for article_elem in root.iter("article"):
        etat = article_elem.get("etat", "")
        if etat != "VIGUEUR":
            continue

        content = _element_text_with_br(article_elem)
        if not content:
            continue

        # Remonter jusqu'au premier ancêtre <t> (section/chapitre/titre)
        parent_section = ""
        current = article_elem
        while current in parent_map:
            current = parent_map[current]
            if current.tag == "t":
                parent_section = current.get("id", "")
                break

        legiarti_id = article_elem.get("id", "")
        number = article_elem.get("num", "")
        effective_date = article_elem.get("date", "")
        references = _extract_references(article_elem)

        articles.append(
            {
                "code": _number_to_code(number),
                "number": number,
                "title": f"Article {number}",
                "content": content,
                "parent_section": parent_section,
                "legiarti_id": legiarti_id,
                "etat": etat,
                "effective_date": effective_date,
                "references": references,
                "slug": slug,
            }
        )

    return articles
