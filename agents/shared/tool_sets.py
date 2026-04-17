"""
agents.shared.tool_sets — Groupes de tool_ids courants.

Chaque constante est une liste de tool IDs réutilisable
dans la définition d'un agent (champ ``tool_ids``).

Les IDs doivent correspondre aux ``ToolDefinition.key`` enregistrés
dans le registre d'outils (table ``ai_tools``).

Architecture : ADR-019
"""

from __future__ import annotations

# ── Recherche ────────────────────────────────────────────────────────────

WEB_SEARCH_TOOLS: list[str] = [
    "web-search",
    "url-fetch",
    "html-parser",
]

# ── Base de données ──────────────────────────────────────────────────────

DATABASE_TOOLS: list[str] = [
    "sql-query",
    "schema-inspector",
]

# ── Code ─────────────────────────────────────────────────────────────────

CODE_TOOLS: list[str] = [
    "code-executor",
    "linter",
    "formatter",
]

# ── Fichiers ─────────────────────────────────────────────────────────────

FILE_TOOLS: list[str] = [
    "file-reader",
    "file-writer",
    "csv-parser",
    "json-parser",
]

# ── Data ─────────────────────────────────────────────────────────────────

DATA_TOOLS: list[str] = [
    "sql-query",
    "schema-inspector",
    "csv-parser",
    "json-parser",
]

# ── Combinaisons ─────────────────────────────────────────────────────────

RESEARCHER_TOOLS: list[str] = [*WEB_SEARCH_TOOLS, *FILE_TOOLS]
ANALYST_TOOLS: list[str] = [*DATABASE_TOOLS, *FILE_TOOLS]
FULL_STACK_TOOLS: list[str] = [*CODE_TOOLS, *DATABASE_TOOLS, *FILE_TOOLS]
