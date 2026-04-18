# filepath: jobs/llm/strava_athlete_analysis/prompts.py
"""
Prompts et schéma de réponse pour l'analyse du profil athlète Strava.

Le SYSTEM_PROMPT positionne le modèle comme un coach sportif expert.
L'ANALYSIS_SCHEMA décrit la structure JSON attendue en retour.
"""

from __future__ import annotations

# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Tu es un coach sportif expert en analyse de performances et en planification \
d'entraînement. Tu as accès aux données brutes Strava d'un athlète.

Ton rôle est d'analyser le profil complet (données démographiques, statistiques \
all-time, activités récentes) et de produire une analyse structurée, bienveillante \
et actionnable, comme si tu répondais directement à l'athlète.

Règles :
- Réponds UNIQUEMENT en JSON valide, strictement conforme au schéma fourni.
- Toutes les valeurs textuelles sont en français.
- Les distances sont en kilomètres, les durées en minutes, le dénivelé en mètres.
- Sois précis et chiffré : cite les données réelles pour étayer chaque observation.
- Évite le jargon inutile — reste accessible mais professionnel.
"""

# ── User prompt template ─────────────────────────────────────────────────────

USER_PROMPT_TEMPLATE = """\
Voici les données complètes de l'athlète Strava. Analyse-les et retourne \
une réponse JSON conforme au schéma indiqué.

## Profil athlète
{athlete_section}

## Statistiques all-time
{stats_section}

## Résumé des activités ({activity_count} activités au total)
{activities_summary_section}

## Activités récentes (30 derniers jours)
{recent_activities_section}

---
Schéma JSON attendu :
{schema_section}
"""

# ── Schéma de réponse JSON ────────────────────────────────────────────────────

ANALYSIS_SCHEMA = {
    "type": "object",
    "description": "Analyse complète du profil athlète par le coach IA",
    "properties": {
        "athlete_summary": {
            "type": "object",
            "description": "Résumé du profil athlète",
            "properties": {
                "name": {"type": "string", "description": "Prénom et nom de l'athlète"},
                "profile_headline": {
                    "type": "string",
                    "description": "Une phrase percutante qui résume le profil sportif (ex: 'Coureur régulier avec 8 ans d'historique Strava')",
                },
                "primary_sport": {
                    "type": "string",
                    "description": "Sport dominant en termes de volume (ex: 'Course à pied')",
                },
                "active_since": {
                    "type": "string",
                    "description": "Année de la première activité enregistrée",
                },
                "total_activities": {
                    "type": "integer",
                    "description": "Nombre total d'activités",
                },
            },
            "required": [
                "name",
                "profile_headline",
                "primary_sport",
                "active_since",
                "total_activities",
            ],
        },
        "performance_insights": {
            "type": "array",
            "description": "Liste de 3 à 5 observations clés sur les performances",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Titre court de l'observation",
                    },
                    "detail": {
                        "type": "string",
                        "description": "Explication détaillée, chiffrée",
                    },
                    "sentiment": {
                        "type": "string",
                        "enum": ["positive", "neutral", "improvement_needed"],
                        "description": "Tonalité de l'observation",
                    },
                },
                "required": ["title", "detail", "sentiment"],
            },
            "minItems": 3,
            "maxItems": 5,
        },
        "training_patterns": {
            "type": "object",
            "description": "Analyse des habitudes d'entraînement",
            "properties": {
                "consistency": {
                    "type": "string",
                    "description": "Évaluation de la régularité (ex: 'Très régulier — moyenne de 5 séances/semaine sur 12 mois')",
                },
                "sport_distribution": {
                    "type": "array",
                    "description": "Répartition des sports par pourcentage",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sport": {"type": "string"},
                            "percentage": {"type": "number"},
                            "count": {"type": "integer"},
                        },
                        "required": ["sport", "percentage", "count"],
                    },
                },
                "volume_trend": {
                    "type": "string",
                    "description": "Tendance du volume d'entraînement (croissant / stable / décroissant)",
                    "enum": ["increasing", "stable", "decreasing"],
                },
                "peak_period": {
                    "type": "string",
                    "description": "Période de l'année ou saison avec le plus d'activités",
                },
            },
            "required": ["consistency", "sport_distribution", "volume_trend"],
        },
        "strengths": {
            "type": "array",
            "description": "3 points forts identifiés",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 4,
        },
        "areas_for_improvement": {
            "type": "array",
            "description": "2 à 3 axes de progression concrets",
            "items": {
                "type": "object",
                "properties": {
                    "area": {"type": "string", "description": "Domaine à améliorer"},
                    "recommendation": {
                        "type": "string",
                        "description": "Recommandation concrète et actionnable",
                    },
                },
                "required": ["area", "recommendation"],
            },
            "minItems": 2,
            "maxItems": 3,
        },
        "next_goals": {
            "type": "array",
            "description": "2 à 3 objectifs suggérés pour les 3 prochains mois",
            "items": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Description de l'objectif",
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "Horizon temporel (ex: '4 semaines', '3 mois')",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Pourquoi cet objectif est adapté à ce profil",
                    },
                },
                "required": ["goal", "timeframe", "rationale"],
            },
            "minItems": 2,
            "maxItems": 3,
        },
        "coach_message": {
            "type": "string",
            "description": "Message de conclusion du coach, personnel et motivant (3-5 phrases)",
        },
        "analysis_metadata": {
            "type": "object",
            "description": "Métadonnées de l'analyse",
            "properties": {
                "data_partition": {
                    "type": "string",
                    "description": "Date de la partition analysée",
                },
                "activities_analyzed": {
                    "type": "integer",
                    "description": "Nombre d'activités analysées",
                },
                "model_used": {"type": "string", "description": "Modèle LLM utilisé"},
                "generated_at": {
                    "type": "string",
                    "description": "Timestamp ISO de génération",
                },
            },
            "required": [
                "data_partition",
                "activities_analyzed",
                "model_used",
                "generated_at",
            ],
        },
    },
    "required": [
        "athlete_summary",
        "performance_insights",
        "training_patterns",
        "strengths",
        "areas_for_improvement",
        "next_goals",
        "coach_message",
        "analysis_metadata",
    ],
}
