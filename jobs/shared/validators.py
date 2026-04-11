"""
Validators — Fonctions de validation de données communes.

Utilisées par les steps ``validate_raw`` dans les jobs d'ingestion
et les steps ``quality_check`` dans les jobs de transformation.

Examples:
    >>> validate_required_fields(records, {"id", "amount"})
    >>> validate_non_empty(records, "extract_payments")
"""

from __future__ import annotations

from typing import Any


class ValidationError(Exception):
    """Erreur levée quand la validation des données échoue."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


def validate_non_empty(
    records: list[dict[str, Any]],
    source_name: str = "unknown",
) -> None:
    """Vérifie qu'une liste de records n'est pas vide.

    Raises:
        ValidationError: Si la liste est vide.
    """
    if not records:
        raise ValidationError(
            f"No records returned from source '{source_name}'",
            details={"source": source_name, "count": 0},
        )


def validate_required_fields(
    records: list[dict[str, Any]],
    required: set[str],
) -> list[dict[str, Any]]:
    """Vérifie que les champs requis sont présents dans chaque record.

    Args:
        records: Liste de dictionnaires à valider.
        required: Ensemble des noms de champs obligatoires.

    Returns:
        Liste des records invalides (vide si tout est OK).

    Raises:
        ValidationError: Si plus de 10% des records sont invalides.
    """
    invalid = [r for r in records if not required.issubset(r.keys())]

    if invalid:
        rate = len(invalid) / len(records) * 100
        if rate > 10:
            raise ValidationError(
                f"{len(invalid)}/{len(records)} records ({rate:.1f}%) "
                f"missing required fields {required}",
                details={
                    "invalid_count": len(invalid),
                    "total_count": len(records),
                    "invalid_rate_pct": round(rate, 2),
                    "required_fields": sorted(required),
                },
            )

    return invalid


def validate_no_duplicates(
    records: list[dict[str, Any]],
    key: str,
) -> int:
    """Vérifie les doublons sur une clé donnée.

    Args:
        records: Liste de dictionnaires.
        key: Nom du champ clé.

    Returns:
        Nombre de doublons détectés.
    """
    seen: set[Any] = set()
    duplicates = 0
    for record in records:
        val = record.get(key)
        if val in seen:
            duplicates += 1
        else:
            seen.add(val)
    return duplicates
