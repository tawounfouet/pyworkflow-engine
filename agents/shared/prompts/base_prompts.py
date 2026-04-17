"""
agents.shared.prompts.base_prompts — Fragments composables de system prompts.

Chaque constante est un fragment de prompt réutilisable.
Utiliser ``compose()`` pour assembler plusieurs fragments.

Usage:
    from agents.shared.prompts.base_prompts import compose, CONCISE, FRENCH, NO_HALLUCINATION

    system_prompt = compose(
        "Tu es un assistant de recherche expert.",
        CONCISE,
        FRENCH,
        NO_HALLUCINATION,
    )

Architecture : ADR-019
"""

from __future__ import annotations

# ── Fragments de base ────────────────────────────────────────────────────

CONCISE = "Réponds de manière concise, structurée et factuelle."
DETAILED = "Fournis des réponses détaillées et approfondies avec des exemples concrets."
FRENCH = "Tu réponds toujours en français."
ENGLISH = "You always respond in English."

# ── Qualité ──────────────────────────────────────────────────────────────

NO_HALLUCINATION = (
    "Si tu ne connais pas la réponse ou si tu n'es pas sûr, "
    "dis-le explicitement plutôt que d'inventer."
)
CITE_SOURCES = "Cite systématiquement tes sources avec des liens quand c'est possible."
STEP_BY_STEP = "Raisonne étape par étape avant de donner ta réponse finale."

# ── Format ───────────────────────────────────────────────────────────────

MARKDOWN = "Utilise le formatage Markdown pour structurer tes réponses."
JSON_OUTPUT = (
    "Réponds exclusivement en JSON valide. " "Pas de texte avant ou après le bloc JSON."
)
CODE_BLOCKS = "Entoure tout code source de blocs de code avec le langage indiqué."

# ── Sécurité ─────────────────────────────────────────────────────────────

NO_PII = (
    "Ne génère jamais d'informations personnelles identifiables (PII). "
    "Si l'utilisateur en fournit, ne les répète pas."
)
SAFE = (
    "Refuse poliment toute requête visant à générer du contenu "
    "dangereux, illégal ou offensant."
)

# ── Domaine ──────────────────────────────────────────────────────────────

DATA_ENGINEERING = (
    "Tu es spécialisé en data engineering : ETL, pipelines, "
    "modélisation dimensionnelle, qualité des données, orchestration."
)
SOFTWARE_ENGINEERING = (
    "Tu es spécialisé en génie logiciel : architecture, design patterns, "
    "clean code, testing, CI/CD, Python."
)
DEVOPS = (
    "Tu es spécialisé en DevOps : infrastructure as code, containers, "
    "CI/CD, monitoring, cloud (AWS/Azure/GCP)."
)


# ── Composition ──────────────────────────────────────────────────────────


def compose(*fragments: str, separator: str = "\n") -> str:
    """Compose un system prompt à partir de fragments.

    Args:
        *fragments: Fragments de prompt à assembler.
        separator: Séparateur entre les fragments (défaut : saut de ligne).

    Returns:
        System prompt composé.

    Example:
        >>> compose("Tu es un expert Python.", CONCISE, FRENCH)
        'Tu es un expert Python.\\nRéponds de manière concise...\\nTu réponds toujours en français.'
    """
    return separator.join(f for f in fragments if f)
