"""
agents/shared/guardrails — Validation structurée des inputs/outputs d'agents.

Permet de définir des règles de validation appliquées avant et après
chaque appel LLM dans un ``AgentRunner``.

Inspiré du paradigme OpenAI Agents SDK guardrails, adapté à l'architecture
hexagonale de pyworkflow-engine.

Architecture : ADR-021 (Phase 4)

Usage::

    from agents.shared.guardrails import Guardrail, GuardrailChain

    chain = GuardrailChain([
        Guardrail(
            name="max_length",
            check=lambda text: len(text) <= 4000,
            on_fail="block",
            message="Input exceeds 4000 characters.",
        ),
        Guardrail(
            name="no_pii",
            check=lambda text: "@" not in text,
            on_fail="warn",
            message="Possible PII detected (email address).",
        ),
    ])

    ok, reason = chain.validate_input("Hello!")
    if not ok:
        print(f"Blocked: {reason}")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

_log = logging.getLogger("agents.guardrails")


# ── Types ────────────────────────────────────────────────────────────────────

OnFail = Literal["block", "warn", "retry"]
"""Comportement en cas d'échec d'un guardrail.

- ``"block"`` : Retourne False, empêche l'appel LLM.
- ``"warn"``  : Log un avertissement mais laisse passer.
- ``"retry"`` : Similaire à ``"block"`` mais signale qu'un retry est souhaitable.
"""


@dataclass
class GuardrailViolation:
    """Violation d'un guardrail.

    Attributes:
        guardrail_name: Nom du guardrail violé.
        message: Message descriptif de la violation.
        on_fail: Comportement configuré (``"block"``, ``"warn"``, ``"retry"``).
        text_snippet: Extrait du texte qui a déclenché la violation (max 100 chars).
    """

    guardrail_name: str
    message: str
    on_fail: OnFail = "block"
    text_snippet: str = ""


@dataclass
class Guardrail:
    """Règle de validation appliquée avant ou après un appel LLM.

    Args:
        name: Identifiant unique du guardrail (ex: ``"max_length"``).
        check: Callable qui prend un ``str`` et retourne ``True`` (pass) ou
               ``False`` (fail).
        on_fail: Comportement en cas d'échec (``"block"`` par défaut).
        message: Message d'erreur affiché en cas d'échec.
        apply_to: Appliquer à ``"input"``, ``"output"``, ou ``"both"`` (défaut).

    Exemples de guardrails courants::

        # Limite de longueur
        Guardrail("max_length", lambda t: len(t) <= 4000, message="Input too long.")

        # Pas de code dans la réponse
        Guardrail("no_code_exec", lambda t: "exec(" not in t and "eval(" not in t,
                  apply_to="output", on_fail="warn")

        # Langue française requise (heuristique simple)
        Guardrail("french_only", lambda t: any(w in t.lower()
                  for w in ["le", "la", "les", "de", "est"]),
                  apply_to="output", on_fail="warn",
                  message="Response may not be in French.")
    """

    name: str
    check: Callable[[str], bool]
    on_fail: OnFail = "block"
    message: str = ""
    apply_to: Literal["input", "output", "both"] = "both"

    def __post_init__(self) -> None:
        if not self.message:
            self.message = f"Guardrail '{self.name}' failed."

    def validate(self, text: str) -> GuardrailViolation | None:
        """Valide le texte. Retourne ``None`` si OK, une violation sinon."""
        try:
            passed = self.check(text)
        except Exception as exc:  # noqa: BLE001
            # Un check qui lève une exception est traité comme un "warn"
            _log.warning("Guardrail '%s' check raised: %s", self.name, exc)
            return GuardrailViolation(
                guardrail_name=self.name,
                message=f"Check raised exception: {exc}",
                on_fail="warn",
                text_snippet=text[:100],
            )

        if not passed:
            return GuardrailViolation(
                guardrail_name=self.name,
                message=self.message,
                on_fail=self.on_fail,
                text_snippet=text[:100],
            )
        return None


@dataclass
class GuardrailResult:
    """Résultat d'une validation par ``GuardrailChain``.

    Attributes:
        passed: True si aucun guardrail bloquant n'a échoué.
        violations: Liste de toutes les violations détectées.
        blocked_by: Nom du premier guardrail bloquant (``on_fail="block"``).
        reason: Message du premier guardrail bloquant.
    """

    passed: bool = True
    violations: list[GuardrailViolation] = field(default_factory=list)
    blocked_by: str | None = None
    reason: str | None = None


class GuardrailChain:
    """Chaîne de guardrails appliquée à un ``AgentRunner``.

    Tous les guardrails sont évalués dans l'ordre.
    Un guardrail avec ``on_fail="block"`` ou ``on_fail="retry"`` bloque
    la validation dès le premier échec.
    Un guardrail avec ``on_fail="warn"`` logue un avertissement mais
    laisse passer.

    Args:
        guardrails: Liste ordonnée de ``Guardrail`` à appliquer.

    Usage::

        chain = GuardrailChain([
            Guardrail("max_length", lambda t: len(t) <= 4000),
            Guardrail("no_pii", lambda t: "@" not in t, on_fail="warn"),
        ])

        result = chain.validate_input("Hello, my email is foo@bar.com")
        if not result.passed:
            print(f"Blocked by: {result.blocked_by}")

        # Ou utiliser l'API tuple simple (backward compat) :
        ok, reason = chain.check_input("some text")
    """

    def __init__(self, guardrails: list[Guardrail]) -> None:
        self.guardrails = guardrails

    # ── API principale ───────────────────────────────────────────────

    def validate_input(self, text: str) -> GuardrailResult:
        """Valide le message utilisateur avant envoi au LLM.

        Args:
            text: Message utilisateur à valider.

        Returns:
            ``GuardrailResult`` avec le statut et les violations.
        """
        return self._run_checks(text, target="input")

    def validate_output(self, text: str) -> GuardrailResult:
        """Valide la réponse LLM avant retour à l'utilisateur.

        Args:
            text: Réponse LLM à valider.

        Returns:
            ``GuardrailResult`` avec le statut et les violations.
        """
        return self._run_checks(text, target="output")

    # ── API tuple simple (compatibilité ADR-021 spec) ────────────────

    def check_input(self, text: str) -> tuple[bool, str | None]:
        """Interface tuple (passed, reason) pour validate_input.

        Returns:
            ``(True, None)`` si OK, ``(False, reason)`` si bloqué.
        """
        result = self.validate_input(text)
        return result.passed, result.reason

    def check_output(self, text: str) -> tuple[bool, str | None]:
        """Interface tuple (passed, reason) pour validate_output.

        Returns:
            ``(True, None)`` si OK, ``(False, reason)`` si bloqué.
        """
        result = self.validate_output(text)
        return result.passed, result.reason

    # ── Helpers ──────────────────────────────────────────────────────

    def _run_checks(
        self, text: str, target: Literal["input", "output"]
    ) -> GuardrailResult:
        result = GuardrailResult()

        for g in self.guardrails:
            # Appliquer seulement si le guardrail concerne cette cible
            if g.apply_to not in (target, "both"):
                continue

            violation = g.validate(text)
            if violation is None:
                continue

            result.violations.append(violation)

            if violation.on_fail == "warn":
                _log.warning(
                    "Guardrail '%s' warn (%s): %s",
                    violation.guardrail_name,
                    target,
                    violation.message,
                )
            else:
                # "block" ou "retry" → stopper la validation
                result.passed = False
                result.blocked_by = violation.guardrail_name
                result.reason = violation.message
                _log.info(
                    "Guardrail '%s' blocked (%s): %s",
                    violation.guardrail_name,
                    target,
                    violation.message,
                )
                return result

        return result

    def __len__(self) -> int:
        return len(self.guardrails)

    def __repr__(self) -> str:
        names = ", ".join(g.name for g in self.guardrails)
        return f"GuardrailChain([{names}])"


# ── Guardrails prédéfinis ────────────────────────────────────────────────────


def max_length(limit: int = 4000, on_fail: OnFail = "block") -> Guardrail:
    """Limite la longueur du texte en caractères."""
    return Guardrail(
        name="max_length",
        check=lambda t: len(t) <= limit,
        on_fail=on_fail,
        message=f"Text exceeds {limit} characters (got {{len}}).".replace(
            "{len}", "{0}"
        ),
        apply_to="both",
    )


def no_empty(on_fail: OnFail = "block") -> Guardrail:
    """Refuse les textes vides."""
    return Guardrail(
        name="no_empty",
        check=lambda t: bool(t.strip()),
        on_fail=on_fail,
        message="Text is empty.",
        apply_to="both",
    )


def no_code_execution(on_fail: OnFail = "warn") -> Guardrail:
    """Avertit si la réponse contient des appels exec/eval."""
    _dangerous = {"exec(", "eval(", "__import__", "subprocess.", "os.system("}
    return Guardrail(
        name="no_code_execution",
        check=lambda t: not any(d in t for d in _dangerous),
        on_fail=on_fail,
        message="Response contains potentially dangerous code execution patterns.",
        apply_to="output",
    )


def no_pii_email(on_fail: OnFail = "warn") -> Guardrail:
    """Avertit si le texte contient une adresse email."""
    import re

    _pattern = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    return Guardrail(
        name="no_pii_email",
        check=lambda t: not bool(_pattern.search(t)),
        on_fail=on_fail,
        message="Text may contain PII (email address detected).",
        apply_to="both",
    )
