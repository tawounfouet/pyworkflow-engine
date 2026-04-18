"""
Abstraction Data Lake — lecture/écriture de données brutes.

Fournit une interface unifiée pour stocker et lire des données brutes,
indépendamment du backend de stockage (filesystem local, S3, Azure Blob…).

Le backend est choisi via la variable d'environnement ``DATALAKE_PATH`` :
- Dev local : ``./data/datalake`` (défaut)
- Production : ``s3://company-datalake`` (à implémenter)

Examples:
    >>> dl = DataLake.from_env()
    >>> dl.write_json("raw/stripe/payments/2026-04-10/", data)
    42
    >>> records = dl.read_json("raw/stripe/payments/2026-04-10/")
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class DataLake:
    """Interface unifiée pour le Data Lake.

    En développement, le Data Lake est le dossier ``data/datalake/``
    à la racine du projet. En production, il peut pointer vers S3
    ou Azure Blob via ``DATALAKE_PATH``.
    """

    def __init__(self, base_path: str) -> None:
        self._base = base_path

    @classmethod
    def from_env(cls) -> DataLake:
        """Factory depuis variables d'environnement.

        Lit ``DATALAKE_PATH`` (défaut : ``./data/datalake``).
        """
        base = os.environ.get("DATALAKE_PATH", "./data/datalake")
        return cls(base_path=base)

    # ── Propriétés ───────────────────────────────────────────────────

    @property
    def root(self) -> Path:
        """Chemin absolu de la racine du Data Lake."""
        return Path(self._base)

    # ── Écriture ─────────────────────────────────────────────────────

    def write_json_file(
        self,
        relative_dir: str,
        filename: str,
        data: dict[str, Any] | list[dict[str, Any]],
    ) -> Path:
        """Écrit un fichier JSON avec un nom arbitraire dans le Data Lake.

        Contrairement à ``write_json``, le nom du fichier est libre
        (pas forcément ``data.json``). Utile pour les catalogues de référence.

        Args:
            relative_dir: Répertoire relatif (ex: ``raw/imf/meta/2026-04-12``).
            filename:      Nom du fichier (ex: ``indicators.json``).
            data:          Dict ou liste à sérialiser.

        Returns:
            Chemin absolu du fichier écrit.
        """
        dest_dir = self.root / relative_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_file = dest_dir / filename
        dest_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        return dest_file

    def write_json(self, relative_path: str, data: list[dict[str, Any]]) -> int:
        """Écrit des données brutes en JSON dans le Data Lake.

        Args:
            relative_path: Chemin relatif (ex: ``raw/stripe/payments/2026-04-10/``).
            data: Liste de dictionnaires à sérialiser.

        Returns:
            Nombre d'enregistrements écrits.
        """
        full = Path(self._base) / relative_path
        full.mkdir(parents=True, exist_ok=True)
        target = full / "data.json"
        target.write_text(json.dumps(data, default=str, indent=2, ensure_ascii=False))
        return len(data)

    def write_parquet(self, relative_path: str, data: list[dict[str, Any]]) -> int:
        """Écrit des données en Parquet (nécessite ``pyarrow``).

        Args:
            relative_path: Chemin relatif dans le Data Lake.
            data: Liste de dictionnaires à sérialiser.

        Returns:
            Nombre d'enregistrements écrits.
        """
        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        full = Path(self._base) / relative_path
        full.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pylist(data)
        pq.write_table(table, full / "data.parquet")
        return len(data)

    # ── Lecture ───────────────────────────────────────────────────────

    def read_json(self, relative_path: str) -> list[dict[str, Any]]:
        """Lit des données brutes JSON depuis le Data Lake.

        Returns:
            Liste de dictionnaires. Liste vide si le fichier n'existe pas.
        """
        target = Path(self._base) / relative_path / "data.json"
        if not target.exists():
            return []
        return json.loads(target.read_text())  # type: ignore[no-any-return]

    def read_parquet(self, relative_path: str) -> list[dict[str, Any]]:
        """Lit des données Parquet depuis le Data Lake.

        Returns:
            Liste de dictionnaires. Liste vide si le fichier n'existe pas.
        """
        import pyarrow.parquet as pq  # noqa: PLC0415

        target = Path(self._base) / relative_path / "data.parquet"
        if not target.exists():
            return []
        return pq.read_table(target).to_pylist()  # type: ignore[no-any-return]

    # ── Utilitaires ──────────────────────────────────────────────────

    def exists(self, relative_path: str) -> bool:
        """Vérifie si un chemin existe dans le Data Lake."""
        return (Path(self._base) / relative_path).exists()

    def list_partitions(self, relative_path: str) -> list[str]:
        """Liste les partitions (sous-dossiers) d'un chemin.

        Utile pour lister les dates disponibles :
        ``dl.list_partitions("raw/stripe/payments/")``
        → ``["2026-04-10", "2026-04-11"]``
        """
        target = Path(self._base) / relative_path
        if not target.exists():
            return []
        return sorted(d.name for d in target.iterdir() if d.is_dir())
