-- =============================================================================
-- scripts/cleanup_old_tables.sql
-- Nettoyage post-migration ADR-018 — Suppression des anciennes tables
-- non-préfixées qui coexistent avec les nouvelles tables ai_*/wf_*/pl_*
--
-- CONTEXTE :
--   La migration ADR-018 (D1+D2) crée de nouvelles tables préfixées :
--     - ai_*  : domaine AI (agents, conversations, chunks, etc.)
--     - wf_*  : domaine workflow (jobs, job_runs, step_runs)
--     - pl_*  : domaine pipeline (pipelines, stages, pipeline_runs, stage_runs)
--     - log_entries : remplace workflow_logs
--
--   Ce script supprime les anciennes tables non-préfixées devenues obsolètes.
--   Les nouvelles tables sont vides au départ (données de tests non-migrées).
--
-- PRÉREQUIS :
--   - La migration principale a été appliquée (python -m scripts.python.migrate)
--   - Les nouvelles tables ai_*/wf_*/pl_* existent dans la base
--
-- USAGE :
--   sqlite3 workflow.db < scripts/cleanup_old_tables.sql
--
-- ROLLBACK :
--   Aucun rollback automatique — faire un backup avant d'exécuter.
--   cp workflow.db workflow.db.bak
--
-- TABLES SUPPRIMÉES (21) :
--   Domaine AI (renommées en ai_* par D1) :
--     agents, agent_skill_assignments, chunks, conversations, documents,
--     execution_steps, executions, graphs, knowledge_sources, memories,
--     messages, providers, skills, tools
--   Domaine Workflow (remplacées par wf_* en D2) :
--     job_runs, jobs, step_runs, workflow_logs
--   Domaine Pipeline (remplacées par pl_* en D2) :
--     pipeline_runs, stage_runs
--   Infrastructure :
--     schema_version (remplacée par la gestion interne du migrate.py)
-- =============================================================================

PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

-- -------------------------------------------------------------------------
-- Domaine AI — tables renommées en ai_* lors de D1
-- (le renommage n'avait pas été appliqué sur les bases existantes,
--  les ai_* ont été recréées directement par le migrate.py de D2)
-- -------------------------------------------------------------------------
DROP TABLE IF EXISTS "agent_skill_assignments";
DROP TABLE IF EXISTS "agents";
DROP TABLE IF EXISTS "chunks";
DROP TABLE IF EXISTS "conversations";
DROP TABLE IF EXISTS "documents";
DROP TABLE IF EXISTS "execution_steps";
DROP TABLE IF EXISTS "executions";
DROP TABLE IF EXISTS "graphs";
DROP TABLE IF EXISTS "knowledge_sources";
DROP TABLE IF EXISTS "memories";
DROP TABLE IF EXISTS "messages";
DROP TABLE IF EXISTS "providers";
DROP TABLE IF EXISTS "skills";
DROP TABLE IF EXISTS "tools";

-- -------------------------------------------------------------------------
-- Domaine Workflow — remplacées par wf_job_runs, wf_jobs, wf_step_runs
-- -------------------------------------------------------------------------
DROP TABLE IF EXISTS "step_runs";      -- → wf_step_runs  (schéma étendu D2)
DROP TABLE IF EXISTS "job_runs";       -- → wf_job_runs   (schéma étendu D2)
DROP TABLE IF EXISTS "jobs";           -- → wf_jobs       (schéma étendu D2)
DROP TABLE IF EXISTS "workflow_logs";  -- → log_entries   (schéma unifié D2)

-- -------------------------------------------------------------------------
-- Domaine Pipeline — remplacées par pl_pipeline_runs, pl_stage_runs
-- -------------------------------------------------------------------------
DROP TABLE IF EXISTS "pipeline_runs";  -- → pl_pipeline_runs
DROP TABLE IF EXISTS "stage_runs";     -- → pl_stage_runs

-- -------------------------------------------------------------------------
-- Infrastructure — obsolète
-- -------------------------------------------------------------------------
DROP TABLE IF EXISTS "schema_version"; -- remplacé par migrate.py interne

COMMIT;

PRAGMA foreign_keys = ON;

-- =============================================================================
-- Vérification post-suppression
-- =============================================================================
SELECT
    CASE
        WHEN COUNT(*) = 0 THEN '✅ Toutes les anciennes tables ont été supprimées.'
        ELSE '⚠️  ' || COUNT(*) || ' ancienne(s) table(s) encore présente(s) !'
    END AS status
FROM sqlite_master
WHERE type = 'table'
  AND name NOT LIKE 'ai_%'
  AND name NOT LIKE 'wf_%'
  AND name NOT LIKE 'pl_%'
  AND name NOT IN ('log_entries', 'sqlite_sequence');

-- Liste des tables restantes (doit afficher uniquement ai_*/wf_*/pl_*/log_entries)
SELECT '  → ' || name AS tables_restantes
FROM sqlite_master
WHERE type = 'table'
ORDER BY name;
