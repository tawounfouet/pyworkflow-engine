"""
BooksToScrapeClient — Connecteur HTTP pour books.toscrape.com.

Site de démonstration conçu exprès pour le scraping.
Adapté depuis le projet original ``_archives/scraper.py``.

Variables d'environnement :
    BOOKS_BASE_URL   : URL de base (défaut : http://books.toscrape.com/)
    BOOKS_MAX_PAGES  : Nombre max de pages de catalogue à scraper (0 = tout)
    BOOKS_CATEGORIES : Catégories à scraper, séparées par virgule (vide = toutes)

Dépendances opt-in : ``requests``, ``beautifulsoup4``, ``lxml``
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.ingestion.books_toscrape.client")

# ── Constantes ────────────────────────────────────────────────────────────

_DEFAULT_BASE_URL = "http://books.toscrape.com/"
_CATALOGUE_URL = "http://books.toscrape.com/catalogue/"
_CATEGORY_BASE = "http://books.toscrape.com/catalogue/category/books/"

_RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


# ── Client ────────────────────────────────────────────────────────────────


class BooksToScrapeClient:
    """Client HTTP pour books.toscrape.com.

    Args:
        base_url: URL racine du site.
        max_pages: Nombre max de pages de catalogue (0 = illimité).
        categories: Liste de catégories à filtrer (vide = toutes).
        delay_s: Délai poli entre les requêtes (secondes).
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        max_pages: int = 0,
        categories: list[str] | None = None,
        delay_s: float = 0.1,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._max_pages = max_pages
        self._categories = [c.lower().strip() for c in (categories or [])]
        self._delay_s = delay_s

        # Lazy import pour garder la dépendance optionnelle
        import requests  # noqa: PLC0415

        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    @classmethod
    def from_env(cls) -> BooksToScrapeClient:
        """Factory depuis variables d'environnement."""
        base_url = os.environ.get("BOOKS_BASE_URL", _DEFAULT_BASE_URL)
        max_pages = int(os.environ.get("BOOKS_MAX_PAGES", "0"))
        raw_cats = os.environ.get("BOOKS_CATEGORIES", "")
        categories = [c.strip() for c in raw_cats.split(",") if c.strip()] or []
        return cls(base_url=base_url, max_pages=max_pages, categories=categories)

    # ── Public API ───────────────────────────────────────────────────

    def fetch_catalogue(self) -> list[dict[str, Any]]:
        """Scrape le catalogue complet (ou filtré par catégorie).

        Returns:
            Liste de dicts bruts, un par livre.
            Chaque dict contient tous les champs extraits de la page détail.
        """
        category_links = self._get_category_links()

        if self._categories:
            category_links = [
                url
                for url in category_links
                if any(cat in url for cat in self._categories)
            ]
            _logger.info(
                "Filtre catégories actif — %d catégorie(s) sélectionnée(s)",
                len(category_links),
            )

        all_books: list[dict[str, Any]] = []
        for cat_url in category_links:
            # URL: …/catalogue/category/books/mystery_3/index.html
            # [-2] = "mystery_3"  →  split("_")[0] = "mystery"
            cat_slug = cat_url.rstrip("/").split("/")[-2]
            cat_name = cat_slug.split("_")[0]
            _logger.info("▶ Début scraping catégorie : '%s'", cat_name)
            book_links = self._get_category_book_links(cat_url)
            _logger.info(
                "Catégorie '%s' — %d livre(s) à extraire",
                cat_name,
                len(book_links),
            )
            cat_total = len(book_links)
            cat_extracted = 0
            for idx, link in enumerate(book_links, start=1):
                book = self._extract_book(link)
                if book:
                    all_books.append(book)
                    cat_extracted += 1
                    _logger.debug(
                        "Livre %d/%d extrait — '%s' (UPC: %s)",
                        idx,
                        cat_total,
                        book.get("title", "?"),
                        book.get("upc", "?"),
                    )
                if self._delay_s:
                    time.sleep(self._delay_s)
            _logger.info(
                "◀ Fin scraping catégorie '%s' — %d/%d livre(s) extrait(s) (total courant : %d)",
                cat_name,
                cat_extracted,
                cat_total,
                len(all_books),
            )

        _logger.info("Catalogue extrait : %d livres au total", len(all_books))
        return all_books

    # ── Private — Navigation ─────────────────────────────────────────

    def _get(self, url: str) -> Any | None:
        """GET avec gestion d'erreur et parse BeautifulSoup."""
        from bs4 import BeautifulSoup  # noqa: PLC0415

        try:
            response = self._session.get(url, timeout=15)
            response.raise_for_status()
            response.encoding = "utf-8"
            return BeautifulSoup(response.content, "lxml")
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Échec GET %s : %s", url, exc)
            return None

    def _get_category_links(self) -> list[str]:
        """Retourne toutes les URLs de catégorie."""
        _logger.debug(
            "Récupération de la liste des catégories depuis %s", self._base_url
        )
        soup = self._get(self._base_url + "index.html")
        if soup is None:
            _logger.warning(
                "Impossible de charger la page d'accueil — aucune catégorie trouvée"
            )
            return []
        nav = soup.find("ul", class_="nav nav-list")
        if nav is None:
            _logger.warning("Bloc de navigation introuvable — aucune catégorie trouvée")
            return []
        links = nav.find_all("a")[1:]  # skip "Books" root link
        category_urls = [self._base_url + a["href"] for a in links]
        _logger.info("Catégories trouvées : %d", len(category_urls))
        return category_urls

    def _get_category_book_links(self, category_url: str) -> list[str]:
        """Retourne toutes les URLs de livres d'une catégorie (multi-page)."""
        book_links: list[str] = []
        cat_slug = category_url.rstrip("/").split("/")[-2]  # e.g. "mystery_3"
        cat_name = cat_slug.split("_")[0]
        page = 1

        while True:
            if page == 1:
                page_url = category_url
            else:
                page_url = f"{_CATEGORY_BASE}{cat_slug}/page-{page}.html"

            _logger.debug("Récupération page %d — catégorie '%s'", page, cat_name)
            soup = self._get(page_url)
            if soup is None:
                break

            articles = soup.find_all("article", class_="product_pod")
            _logger.debug(
                "Page %d — catégorie '%s' : %d livre(s) trouvé(s)",
                page,
                cat_name,
                len(articles),
            )
            for article in articles:
                relative = article.find("h3").a["href"]
                # Strip leading "../../../"
                clean = relative.lstrip("./").lstrip("../")
                book_links.append(_CATALOGUE_URL + clean)

            # Check for next page
            if not soup.find("li", class_="next"):
                break

            page += 1
            if self._max_pages and page > self._max_pages:
                _logger.debug(
                    "Limite de pages atteinte (%d) pour la catégorie '%s'",
                    self._max_pages,
                    cat_name,
                )
                break
            if self._delay_s:
                time.sleep(self._delay_s)

        _logger.debug(
            "Catégorie '%s' — %d lien(s) collecté(s) sur %d page(s)",
            cat_name,
            len(book_links),
            page,
        )
        return book_links

    # ── Private — Book detail extraction ─────────────────────────────

    def _extract_book(self, url: str) -> dict[str, Any] | None:
        """Scrape la page détail d'un livre et retourne un dict brut."""
        soup = self._get(url)
        if soup is None:
            return None

        try:
            table_rows = soup.find("table", class_="table table-striped").find_all("tr")
            product_main = soup.find("div", class_="col-sm-6 product_main")
            breadcrumb = soup.find("ul", class_="breadcrumb").find_all("a")

            # Prix brut : peut contenir "Â£" (encoding artifact)
            raw_price = product_main.find("p", class_="price_color").text

            book = {
                "upc": table_rows[0].td.text.strip(),
                "title": product_main.find("h1").text.strip(),
                "price_raw": raw_price.strip(),
                "price_excl_tax_raw": table_rows[2].td.text.strip(),
                "tax_raw": table_rows[4].td.text.strip(),
                "availability_raw": table_rows[5].td.text.strip(),
                "rating_raw": product_main.find_all("p")[2].get("class", [""])[1],
                "category": breadcrumb[2].text.strip() if len(breadcrumb) > 2 else "",
                "description": (
                    soup.find_all("p")[3].text.strip()
                    if len(soup.find_all("p")) > 3
                    else ""
                ),
                "img_url": self._base_url
                + (soup.find("div", class_="item active").img["src"].lstrip("../")),
                "source_url": url,
            }
            _logger.debug(
                "Livre extrait — '%s' (UPC: %s)",
                book["title"],
                book["upc"],
            )
            return book
        except Exception as exc:  # noqa: BLE001
            _logger.warning("Extraction échouée pour %s : %s", url, exc)
            return None


# ── Helpers utilisés par la transformation ────────────────────────────────


def _slugify(s: str) -> str:
    """Slugifie une chaîne sans dépendance externe."""
    s = s.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    s = re.sub(r"^-+|-+$", "", s)
    return s


def _clean_price(raw: str) -> float:
    """Nettoie un prix brut HTML (ex: 'Â£12.99') → float."""
    cleaned = re.sub(r"[^\d.]", "", raw)
    return float(cleaned) if cleaned else 0.0


def _clean_availability(raw: str) -> int:
    """Extrait le nombre de stock depuis 'In stock (22 available)' → 22."""
    nums = re.findall(r"\d+", raw)
    return int(nums[0]) if nums else 0
