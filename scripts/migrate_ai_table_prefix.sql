-- =============================================================================
-- scripts/migrate_ai_table_prefix.sql
-- Migration ADR-018 / D1 — Ajout du préfixe ai_ sur les tables du domaine AI
--
-- À exécuter UNE SEULE FOIS sur les bases SQLite existantes créées AVANT
-- la version qui implémente ADR-018.
-- Les nouvelles bases créées après ADR-018 n'ont pas besoin de ce script
-- (les tables sont créées directement avec le bon nom).
--
-- IMPORTANT : SQLite ne supporte pas les clés étrangères lors d'un RENAME TABLE,
-- mais les FK sont stockées comme contraintes dans le DDL de création.
-- Les données sont préservées intégralement. Les index sont recréés automatiquement
-- lors du prochain appel à storage.migrate().
--
-- Usage :
--   sqlite3 workflow.db < scripts/migrate_ai_table_prefix.sql
--
-- Rollback (si nécessaire, avant tout usage post-migration) :
--   scripts/rollback_ai_table_prefix.sql
-- =============================================================================

-- Désactiver les FK temporairement pour éviter les erreurs d'ordre de renommage
PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

-- Feuilles (pas de dépendants) — renommer en premier
ALTER TABLE "chunks"                  RENAME TO "ai_chunks";
ALTER TABLE "execution_steps"         RENAME TO "ai_execution_steps";

-- Dépendants intermédiaires
ALTER TABLE "messages"                RENAME TO "ai_messages";
ALTER TABLE "documents"               RENAME TO "ai_documents";
ALTER TABLE "agent_skill_assignments" RENAME TO "ai_agent_skill_assignments";

-- Parents directs
ALTER TABLE "conversations"           RENAME TO "ai_conversations";
ALTER TABLE "executions"              RENAME TO "ai_executions";
ALTER TABLE "graphs"                  RENAME TO "ai_graphs";
ALTER TABLE "memories"                RENAME TO "ai_memories";
ALTER TABLE "knowledge_sources"       RENAME TO "ai_knowledge_sources";

-- Racines
ALTER TABLE "agents"                  RENAME TO "ai_agents";
ALTER TABLE "tools"                   RENAME TO "ai_tools";
ALTER TABLE "skills"                  RENAME TO "ai_skills";
ALTER TABLE "providers"               RENAME TO "ai_providers";

COMMIT;

-- Réactiver les FK
PRAGMA foreign_keys = ON;

-- Vérification optionnelle : liste les tables après migration
-- SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
