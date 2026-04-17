"""
DroitCodesClient — Téléchargement XML depuis codes.droit.org.

Aucune dépendance tierce — stdlib uniquement (urllib, ssl).
Reprend et généralise la logique de ``_archives/download_cgi_xml.py``.

Variables d'environnement :
    CODES_DROIT_BASE_URL : URL de base (défaut : https://codes.droit.org/payloads)
    CODES_DROIT_SLUGS    : Slugs séparés par virgule (défaut : tous)
    CODES_DROIT_TIMEOUT  : Timeout HTTP en secondes (défaut : 60)
"""

from __future__ import annotations

import os
import ssl
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyworkflow_engine.logging import get_logger

_logger = get_logger("jobs.ingestion.codes_droit.client")

_DEFAULT_BASE_URL = "https://codes.droit.org/payloads"
_DEFAULT_TIMEOUT = 60

# Catalogue complet — miroir de config.yaml (pas de parsing YAML au runtime)
_ALL_CODES: list[dict[str, str]] = [
    {
        "slug": "cgi",
        "label": "Code général des impôts",
        "filename": "Code%20g%C3%A9n%C3%A9ral%20des%20imp%C3%B4ts.xml",
    },
    {"slug": "code_civil", "label": "Code civil", "filename": "Code%20civil.xml"},
    {"slug": "code_penal", "label": "Code pénal", "filename": "Code%20p%C3%A9nal.xml"},
    {
        "slug": "code_travail",
        "label": "Code du travail",
        "filename": "Code%20du%20travail.xml",
    },
    {
        "slug": "code_commerce",
        "label": "Code de commerce",
        "filename": "Code%20de%20commerce.xml",
    },
    {
        "slug": "livre_procedures_fiscales",
        "label": "Livre des procédures fiscales",
        "filename": "Livre%20des%20proc%C3%A9dures%20fiscales.xml",
    },
    {
        "slug": "code_procedure_civile",
        "label": "Code de procédure civile",
        "filename": "Code%20de%20proc%C3%A9dure%20civile.xml",
    },
    {
        "slug": "code_procedure_penale",
        "label": "Code de procédure pénale",
        "filename": "Code%20de%20proc%C3%A9dure%20p%C3%A9nale.xml",
    },
    {
        "slug": "code_assurances",
        "label": "Code des assurances",
        "filename": "Code%20des%20assurances.xml",
    },
    {
        "slug": "code_monetaire",
        "label": "Code monétaire et financier",
        "filename": "Code%20mon%C3%A9taire%20et%20financier.xml",
    },
    {
        "slug": "code_patrimoine",
        "label": "Code du patrimoine",
        "filename": "Code%20du%20patrimoine.xml",
    },
    {
        "slug": "code_etrangers",
        "label": "Code de l'entrée et du séjour des étrangers et du droit d'asile",
        "filename": "Code%20de%20l%27entr%C3%A9e%20et%20du%20s%C3%A9jour%20des%20%C3%A9trangers%20et%20du%20droit%20d%27asile.xml",
    },
    {
        "slug": "code_famille",
        "label": "Code de la famille et de l'aide sociale",
        "filename": "Code%20de%20la%20famille%20et%20de%20l%27aide%20sociale.xml",
    },
    {
        "slug": "code_relations_public",
        "label": "Code des relations entre le public et l'administration",
        "filename": "Code%20des%20relations%20entre%20le%20public%20et%20l%27administration.xml",
    },
]

CODES_BY_SLUG: dict[str, dict[str, str]] = {c["slug"]: c for c in _ALL_CODES}


# ── Résultat de téléchargement ───────────────────────────────────────────


@dataclass
class DownloadResult:
    """Résultat du téléchargement d'un code juridique."""

    slug: str
    label: str
    url: str
    output_path: str
    size_kb: int
    success: bool
    ssl_fallback: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "label": self.label,
            "url": self.url,
            "output_path": self.output_path,
            "size_kb": self.size_kb,
            "success": self.success,
            "ssl_fallback": self.ssl_fallback,
            "error": self.error,
        }


# ── Client ───────────────────────────────────────────────────────────────


@dataclass
class DroitCodesClient:
    """Client HTTP stdlib pour le téléchargement des codes juridiques XML.

    Reprend la logique de ``_archives/download_cgi_xml.py`` :
    - Headers HTTP identiques (Accept, Accept-Language, User-Agent)
    - Validation XML (header BOM + ``<?xml`` ou ``<``)
    - Fallback SSL automatique si ``ssl.SSLError``

    Args:
        base_url: URL de base de codes.droit.org (sans slash final).
        slugs:    Sous-ensemble de codes à télécharger. ``[]`` = tous.
        timeout:  Timeout HTTP en secondes.

    Examples:
        >>> client = DroitCodesClient.from_env()
        >>> results = client.download_all("/tmp/codes")
        >>> [r.slug for r in results if r.success]
        ['cgi', 'code_civil', ...]
    """

    base_url: str = _DEFAULT_BASE_URL
    slugs: list[str] = field(default_factory=list)
    timeout: int = _DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls) -> DroitCodesClient:
        """Construit un client depuis les variables d'environnement."""
        raw_slugs = os.environ.get("CODES_DROIT_SLUGS", "").strip()
        slugs = (
            [s.strip() for s in raw_slugs.split(",") if s.strip()] if raw_slugs else []
        )
        return cls(
            base_url=os.environ.get("CODES_DROIT_BASE_URL", _DEFAULT_BASE_URL).rstrip(
                "/"
            ),
            slugs=slugs,
            timeout=int(os.environ.get("CODES_DROIT_TIMEOUT", str(_DEFAULT_TIMEOUT))),
        )

    # ── Catalogue ─────────────────────────────────────────────────────

    def resolved_codes(self) -> list[dict[str, str]]:
        """Retourne les entrées du catalogue correspondant aux slugs configurés.

        Returns:
            Tous les codes si ``slugs`` est vide, sinon le sous-ensemble.
        """
        if not self.slugs:
            return list(_ALL_CODES)
        result = []
        for slug in self.slugs:
            if slug not in CODES_BY_SLUG:
                _logger.warning(
                    "Slug inconnu ignoré : '%s' (disponibles : %s)",
                    slug,
                    list(CODES_BY_SLUG),
                )
                continue
            result.append(CODES_BY_SLUG[slug])
        return result

    # ── HTTP ──────────────────────────────────────────────────────────

    def _make_request(self, url: str) -> urllib.request.Request:
        """Construit la requête HTTP avec les headers corrects."""
        return urllib.request.Request(
            url,
            headers={
                "Accept": "application/xml,text/xml,*/*;q=0.8",
                "Accept-Language": "fr,fr-FR;q=0.9,en;q=0.5",
                "User-Agent": "pyworkflow-engine/0.1 (https://github.com/pytaxes)",
            },
        )

    def _is_valid_xml(self, path: str) -> bool:
        """Vérifie que le fichier téléchargé est bien du XML."""
        with open(path, "rb") as f:
            header = f.read(10).lstrip(b"\xef\xbb\xbf")  # strip UTF-8 BOM
        return header.startswith(b"<?xml") or header.startswith(b"<")

    def _fetch(self, url: str, output_path: str, ctx: ssl.SSLContext) -> None:
        """Effectue le GET et écrit le fichier sur disque."""
        req = self._make_request(url)
        with (
            urllib.request.urlopen(req, context=ctx, timeout=self.timeout) as resp,
            open(output_path, "wb") as f,
        ):
            f.write(resp.read())

    def _download_one(
        self, url: str, output_path: str, label: str
    ) -> tuple[bool, bool, str]:
        """Télécharge un seul fichier XML avec fallback SSL.

        Args:
            url:         URL complète du fichier à télécharger.
            output_path: Chemin local de destination.
            label:       Nom lisible du code (pour les logs).

        Returns:
            ``(success, ssl_fallback, error_message)``
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        ctx = ssl.create_default_context()

        try:
            self._fetch(url, output_path, ctx)
            if not self._is_valid_xml(output_path):
                return False, False, "Le fichier téléchargé ne ressemble pas à du XML"
            return True, False, ""

        except ssl.SSLError:
            _logger.warning(
                "[%s] SSL échoué — retry sans vérification de certificat…", label
            )
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                self._fetch(url, output_path, ctx)
                if not self._is_valid_xml(output_path):
                    return (
                        False,
                        True,
                        "Le fichier téléchargé ne ressemble pas à du XML (sans SSL)",
                    )
                return True, True, ""
            except Exception as exc:
                return False, True, str(exc)

        except Exception as exc:
            return False, False, str(exc)

    # ── API publique ──────────────────────────────────────────────────

    def download_all(self, output_dir: str) -> list[DownloadResult]:
        """Télécharge tous les codes configurés vers ``output_dir``.

        Chaque fichier est nommé ``{slug}.xml`` dans ``output_dir``.
        Les erreurs partielles sont loggées mais n'interrompent pas la boucle.

        Args:
            output_dir: Répertoire de sortie (sera créé si absent).

        Returns:
            Liste de :class:`DownloadResult` — un par code tenté.
        """
        codes = self.resolved_codes()
        _logger.info(
            "Téléchargement de %d code(s) depuis %s", len(codes), self.base_url
        )
        results: list[DownloadResult] = []

        for entry in codes:
            slug = entry["slug"]
            label = entry["label"]
            url = f"{self.base_url}/{entry['filename']}"
            output_path = str(Path(output_dir) / f"{slug}.xml")

            _logger.info("[%s] %s", slug, label)
            success, ssl_fallback, error = self._download_one(url, output_path, label)

            size_kb = 0
            if success and Path(output_path).exists():
                size_kb = Path(output_path).stat().st_size // 1024
                _logger.info(
                    "[%s] ✅ %d KB → %s%s",
                    slug,
                    size_kb,
                    output_path,
                    " (sans vérif. SSL)" if ssl_fallback else "",
                )
            else:
                _logger.error("[%s] ❌ %s", slug, error)

            results.append(
                DownloadResult(
                    slug=slug,
                    label=label,
                    url=url,
                    output_path=output_path,
                    size_kb=size_kb,
                    success=success,
                    ssl_fallback=ssl_fallback,
                    error=error,
                )
            )

        ok = sum(1 for r in results if r.success)
        _logger.info(
            "Bilan téléchargement : %d/%d succès, %d échecs",
            ok,
            len(results),
            len(results) - ok,
        )
        return results
