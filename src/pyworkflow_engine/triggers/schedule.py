"""
ScheduleTrigger — déclenchement planifié par expression cron (stdlib).

Implémente un déclencheur cron complet sans dépendance externe :
  - Parser d'expressions cron 5 champs (minute heure jour mois jour-semaine)
  - Planification via ``threading.Thread`` en arrière-plan
  - Support ``*``, valeur fixe, ``*/n`` (pas), ``a-b`` (plage), ``a,b,c`` (liste)

Zéro dépendance externe — stdlib uniquement (threading, datetime, time).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .base import BaseTrigger, TriggerState

if TYPE_CHECKING:
    from ..facade import WorkflowEngine
    from ..models import Job, JobRun


# ---------------------------------------------------------------------------
# Cron expression parser
# ---------------------------------------------------------------------------

class CronExpression:
    """Parser et évaluateur d'expressions cron 5 champs.

    Format : ``minute hour day month weekday``

    Chaque champ supporte :
    - ``*``   — toutes les valeurs du champ.
    - ``n``   — valeur exacte.
    - ``*/n`` — toutes les n unités.
    - ``a-b`` — plage inclusive.
    - ``a,b,c,...`` — liste de valeurs (les éléments peuvent être des plages
      ou des pas : ``1-5,10,*/15``).

    Plages valides :
      - minute   : 0–59
      - hour     : 0–23
      - day      : 1–31
      - month    : 1–12
      - weekday  : 0–6  (0 = dimanche)

    Examples:
        >>> expr = CronExpression("*/5 * * * *")   # toutes les 5 minutes
        >>> expr = CronExpression("0 9 * * 1-5")   # 9h00, lundi–vendredi
        >>> expr = CronExpression("30 6 1,15 * *") # 6h30, le 1er et le 15
        >>> now = datetime.now()
        >>> expr.matches(now)
        True / False
    """

    _FIELD_RANGES = [
        (0, 59),   # minute
        (0, 23),   # hour
        (1, 31),   # day
        (1, 12),   # month
        (0, 6),    # weekday (0 = Sunday)
    ]

    def __init__(self, expression: str) -> None:
        self._expression = expression
        parts = expression.strip().split()
        if len(parts) != 5:
            raise ValueError(
                f"Invalid cron expression {expression!r}: expected 5 fields "
                f"(minute hour day month weekday), got {len(parts)}."
            )
        self._fields: list[set[int]] = []
        for i, part in enumerate(parts):
            lo, hi = self._FIELD_RANGES[i]
            self._fields.append(self._parse_field(part, lo, hi))

    # ------------------------------------------------------------------

    def matches(self, dt: datetime) -> bool:
        """Vérifie si ``dt`` correspond à l'expression cron."""
        # weekday : Python datetime.weekday() → 0=lundi, 6=dimanche
        # Cron standard : 0=dimanche … 6=samedi
        # Conversion : (python_weekday + 1) % 7
        cron_weekday = (dt.weekday() + 1) % 7
        return (
            dt.minute in self._fields[0]
            and dt.hour in self._fields[1]
            and dt.day in self._fields[2]
            and dt.month in self._fields[3]
            and cron_weekday in self._fields[4]
        )

    @property
    def expression(self) -> str:
        return self._expression

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @classmethod
    def _parse_field(cls, field: str, lo: int, hi: int) -> set[int]:
        values: set[int] = set()
        for part in field.split(","):
            values.update(cls._parse_part(part, lo, hi))
        return values

    @classmethod
    def _parse_part(cls, part: str, lo: int, hi: int) -> set[int]:
        # */step
        if part.startswith("*/"):
            step = int(part[2:])
            if step <= 0:
                raise ValueError(f"Step must be positive, got {step!r}")
            return set(range(lo, hi + 1, step))

        # *
        if part == "*":
            return set(range(lo, hi + 1))

        # a-b/step  or  a-b
        if "-" in part:
            range_part, *step_part = part.split("/")
            a_str, b_str = range_part.split("-", 1)
            a, b = int(a_str), int(b_str)
            cls._check_range(a, lo, hi)
            cls._check_range(b, lo, hi)
            step = int(step_part[0]) if step_part else 1
            return set(range(a, b + 1, step))

        # n/step
        if "/" in part:
            start_str, step_str = part.split("/", 1)
            start = int(start_str)
            step = int(step_str)
            cls._check_range(start, lo, hi)
            return set(range(start, hi + 1, step))

        # exact value
        val = int(part)
        cls._check_range(val, lo, hi)
        return {val}

    @staticmethod
    def _check_range(val: int, lo: int, hi: int) -> None:
        if not (lo <= val <= hi):
            raise ValueError(
                f"Value {val} out of range [{lo}, {hi}]"
            )

    def __repr__(self) -> str:
        return f"CronExpression({self._expression!r})"


# ---------------------------------------------------------------------------
# ScheduleTrigger
# ---------------------------------------------------------------------------

class ScheduleTrigger(BaseTrigger):
    """Trigger planifié par expression cron.

    Démarre un thread d'arrière-plan qui vérifie toutes les secondes si la
    minute courante correspond à l'expression cron. Quand c'est le cas, il
    appelle ``fire(job)`` une seule fois par minute correspondante.

    Args:
        engine: Instance ``WorkflowEngine``.
        job: Job à exécuter à chaque déclenchement.
        cron: Expression cron 5 champs : ``"minute hour day month weekday"``.
            Exemples :
            - ``"* * * * *"``   — toutes les minutes
            - ``"0 * * * *"``   — toutes les heures (à :00)
            - ``"0 9 * * 1-5"`` — 9h00, lundi–vendredi
        name: Nom lisible (défaut : ``"ScheduleTrigger"``).
        initial_context_factory: Callable sans argument retournant un dict
            de contexte initial à chaque déclenchement. Utilisé pour injecter
            des données dynamiques (timestamp, etc.).
        timezone_aware: Si ``True``, utilise ``datetime.now(tz=timezone.utc)``
            pour les comparaisons. Défaut : ``False`` (heure locale).
        **kwargs: Transmis à ``BaseTrigger.__init__``.

    Examples:
        >>> trigger = ScheduleTrigger(
        ...     engine=engine,
        ...     job=my_job,
        ...     cron="0 6 * * 1-5",  # 6h00 du lundi au vendredi
        ...     name="morning-etl",
        ... )
        >>> trigger.start()
        >>> # ... le trigger tourne en arrière-plan ...
        >>> trigger.stop()
    """

    def __init__(
        self,
        engine: WorkflowEngine,
        job: Job,
        cron: str,
        name: str = "ScheduleTrigger",
        initial_context_factory: Callable[[], dict[str, Any]] | None = None,
        timezone_aware: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(engine=engine, name=name, **kwargs)
        self._job = job
        self._cron = CronExpression(cron)
        self._initial_context_factory = initial_context_factory
        self._timezone_aware = timezone_aware
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_fired_minute: int | None = None  # (year, month, day, hour, minute)

    # ------------------------------------------------------------------
    # BaseTrigger interface
    # ------------------------------------------------------------------

    @property
    def cron(self) -> CronExpression:
        """Expression cron configurée."""
        return self._cron

    def start(self) -> None:
        """Démarre le thread de planification en arrière-plan.

        Raises:
            RuntimeError: Si le trigger est déjà actif.
        """
        if self._state == TriggerState.RUNNING:
            raise RuntimeError(f"Trigger '{self._name}' is already running")
        self._stop_event.clear()
        self._last_fired_minute = None
        self._thread = threading.Thread(
            target=self._loop,
            name=f"ScheduleTrigger-{self._name}",
            daemon=True,
        )
        self._set_state(TriggerState.RUNNING)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Arrête proprement le thread de planification.

        Args:
            timeout: Secondes d'attente maximale pour la fin du thread.
        """
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        self._set_state(TriggerState.STOPPED)

    def fire(
        self,
        job: Job | None = None,
        initial_context: dict[str, Any] | None = None,
    ) -> JobRun:
        """Déclenche une exécution immédiate du job configuré.

        Args:
            job: Job à exécuter. Si ``None``, utilise le job configuré.
            initial_context: Données initiales. Si ``None`` et qu'une
                ``initial_context_factory`` est configurée, elle est appelée.

        Returns:
            ``JobRun`` résultant.
        """
        target_job = job or self._job
        ctx = initial_context
        if ctx is None and self._initial_context_factory is not None:
            ctx = self._initial_context_factory()
        return self._do_fire(target_job, initial_context=ctx)

    # ------------------------------------------------------------------
    # Internal scheduling loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        """Boucle principale du thread d'arrière-plan.

        Vérifie toutes les secondes si la minute courante correspond à
        l'expression cron et n'a pas déjà été déclenchée.
        """
        from ..logging import get_logger
        logger = get_logger("triggers.schedule")

        while not self._stop_event.is_set():
            now = self._now()
            minute_key = (now.year, now.month, now.day, now.hour, now.minute)

            if self._cron.matches(now) and minute_key != self._last_fired_minute:
                self._last_fired_minute = minute_key
                logger.info(
                    "ScheduleTrigger '%s' firing at %s (cron: %s)",
                    self._name,
                    now.strftime("%Y-%m-%d %H:%M"),
                    self._cron.expression,
                )
                try:
                    self.fire()
                except Exception as exc:
                    logger.error(
                        "ScheduleTrigger '%s' error during fire: %s",
                        self._name,
                        exc,
                    )
                    self._set_state(TriggerState.ERROR)
                    return

            # Dormir jusqu'à la prochaine seconde (résolution : 1 s).
            self._stop_event.wait(timeout=1.0)

    def _now(self) -> datetime:
        if self._timezone_aware:
            return datetime.now(tz=timezone.utc)
        return datetime.now()  # noqa: DTZ005
