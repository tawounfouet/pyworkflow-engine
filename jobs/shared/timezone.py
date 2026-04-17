# filepath: jobs/shared/timezone.py
"""
jobs/shared/timezone.py — Utilitaires de date/heure fuseau-aware.

Source unique de vérité pour tous les jobs du projet.
Le fuseau est lu depuis ``settings.TIMEZONE`` (défaut : ``"local"``),
configurable via la variable d'environnement ``PYWORKFLOW_TIMEZONE``.

Usage :

    from jobs.shared.timezone import now, today

    partition = today()           # "2026-04-13"  ← fuseau du projet
    dt = now()                    # datetime aware dans le bon fuseau

Configurer le fuseau dans .env :

    PYWORKFLOW_TIMEZONE=Europe/Paris

Ou programmatiquement (en début de script, avant tout import de job) :

    from pyworkflow_engine.config.settings import settings
    settings.configure(TIMEZONE="Europe/Paris")
"""

from __future__ import annotations

from datetime import datetime


def now() -> datetime:
    """``datetime.now()`` dans le fuseau configuré par ``settings.TIMEZONE``.

    Returns:
        datetime: Datetime timezone-aware (jamais naive).

    Examples:
        >>> from jobs.shared.timezone import now
        >>> dt = now()
        >>> dt.tzinfo is not None
        True
    """
    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    return settings.now()


def today() -> str:
    """Date du jour au format ``YYYY-MM-DD`` dans le fuseau configuré.

    Remplace partout ``datetime.now(tz=UTC).strftime("%Y-%m-%d")``
    et ``date.today().isoformat()``.

    Returns:
        str: Ex. ``"2026-04-13"``.

    Examples:
        >>> from jobs.shared.timezone import today
        >>> today()
        '2026-04-13'
    """
    from pyworkflow_engine.config.settings import settings  # noqa: PLC0415

    return settings.today()
