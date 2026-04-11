#!/usr/bin/env bash
# =============================================================================
# rename_persistence_to_storage.sh
#
# Renomme tous les symboles, fichiers et dossiers liés à "persistence"
# en "storage" dans le codebase pyworkflow-engine.
#
# Contexte : ADR-012 — Renommage persistence → storage
# Voir : docs/changelog/2026-04-12_adr_012_rename-persistence-to-storage.md
#
# Usage :
#   chmod +x scripts/bash/rename_persistence_to_storage.sh
#   ./scripts/bash/rename_persistence_to_storage.sh
#
# Prérequis :
#   - macOS bash 3.2+ ou zsh compatible
#   - Avoir git disponible dans le PATH
#   - macOS : utilise sed -i '' (BSD sed). Sur Linux, remplacer par sed -i
#
# Note : ce script utilise bash mais s'exécute aussi via zsh grâce à l'absence
#        de mapfile (bash 4+) — remplacé par while+read compatibles bash 3.2.
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BRANCH_NAME="refactor/rename-persistence-to-storage"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log_step() { echo -e "\n${BOLD}${BLUE}=== $* ===${NC}"; }
log_ok()   { echo -e "  ${GREEN}✅  $*${NC}"; }
log_warn() { echo -e "  ${YELLOW}⚠️   $*${NC}"; }
log_err()  { echo -e "  ${RED}❌  $*${NC}" >&2; }
log_info() { echo -e "  ${NC}$*"; }

die() {
    log_err "$*"
    exit 1
}

# sed portable macOS (BSD) / Linux
sed_inplace() {
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# ---------------------------------------------------------------------------
# Vérifications préliminaires
# ---------------------------------------------------------------------------
log_step "Vérifications préliminaires"

cd "${PROJECT_ROOT}"
log_info "Répertoire de travail : ${PROJECT_ROOT}"

command -v git >/dev/null 2>&1 || die "git n'est pas disponible dans le PATH"

# Vérifier qu'on est dans un dépôt git
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "Ce répertoire n'est pas un dépôt git"

# Vérifier qu'il n'y a pas de modifications non commitées (hors fichiers untouched)
if ! git diff --quiet || ! git diff --cached --quiet; then
    log_warn "Des modifications non commitées sont présentes."
    read -r -p "  Continuer quand même ? [y/N] " confirm
    [[ "${confirm}" =~ ^[yY]$ ]] || die "Abandon. Commitez ou stashez vos changements d'abord."
fi

log_ok "Prérequis OK"

# ---------------------------------------------------------------------------
# Étape 0 — Créer une branche dédiée
# ---------------------------------------------------------------------------
log_step "Étape 0 : Création de la branche ${BRANCH_NAME}"

if git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}"; then
    log_warn "La branche '${BRANCH_NAME}' existe déjà."
    read -r -p "  La réutiliser (checkout) ? [y/N] " confirm
    [[ "${confirm}" =~ ^[yY]$ ]] || die "Abandon. Supprimez la branche ou choisissez un autre nom."
    git checkout "${BRANCH_NAME}"
else
    git checkout -b "${BRANCH_NAME}"
    log_ok "Branche '${BRANCH_NAME}' créée"
fi

# ---------------------------------------------------------------------------
# Étape 1a — Bilan avant renommage
# ---------------------------------------------------------------------------
log_step "Étape 1a : Bilan — occurrences de 'persistence' avant renommage"

BEFORE_COUNT=$(grep -rni "persistence" \
    --include="*.py" --include="*.md" --include="*.toml" \
    --include="*.yaml" --include="*.yml" --include="*.rst" \
    --include="*.cfg" --include="*.ini" \
    --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
    --exclude-dir=__pycache__ --exclude-dir=htmlcov \
    --exclude-dir=".mypy_cache" --exclude-dir=".ruff_cache" \
    . 2>/dev/null | wc -l | tr -d ' ')

FILE_COUNT=$(grep -rli "persistence" \
    --include="*.py" --include="*.md" --include="*.toml" \
    --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
    --exclude-dir=__pycache__ --exclude-dir=htmlcov \
    . 2>/dev/null | wc -l | tr -d ' ')

log_info "Occurrences totales     : ${BEFORE_COUNT}"
log_info "Fichiers impactés       : ${FILE_COUNT}"
echo ""

grep -rni "persistence" \
    --include="*.py" --include="*.md" --include="*.toml" \
    --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
    --exclude-dir=__pycache__ --exclude-dir=htmlcov \
    . 2>/dev/null | head -30 || true

[[ "${BEFORE_COUNT}" -eq 0 ]] && { log_warn "Aucune occurrence trouvée — le renommage a peut-être déjà été fait."; exit 0; }

# ---------------------------------------------------------------------------
# Étape 1b — Fichiers et dossiers à renommer
# ---------------------------------------------------------------------------
log_step "Étape 1b : Fichiers et dossiers à renommer"

# Compatible bash 3.2 / macOS (pas de mapfile)
FILES_TO_RENAME=()
while IFS= read -r line; do
    FILES_TO_RENAME+=("${line}")
done < <(
    find . -type f -name "*persistence*" \
        -not -path "./.git/*" \
        -not -path "./.venv/*" \
        -not -path "./venv/*" \
        -not -path "./__pycache__/*" \
        -not -path "*/__pycache__/*" \
        -not -path "./htmlcov/*" \
        -not -path "./docs/changelog/*" \
        -not -name "CHANGELOG.md" \
        -not -name "$(basename "$0")" \
    | sort
)

DIRS_TO_RENAME=()
while IFS= read -r line; do
    DIRS_TO_RENAME+=("${line}")
done < <(
    find . -type d -name "*persistence*" \
        -not -path "./.git/*" \
        -not -path "./.venv/*" \
        -not -path "./venv/*" \
        -not -path "*/__pycache__/*" \
    | sort -r   # plus profond en premier
)

log_info "Fichiers : ${#FILES_TO_RENAME[@]}"
for f in "${FILES_TO_RENAME[@]}"; do log_info "  $f"; done

log_info "Dossiers : ${#DIRS_TO_RENAME[@]}"
for d in "${DIRS_TO_RENAME[@]}"; do log_info "  $d"; done

# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------
echo ""
echo -e "${BOLD}Ce script va :${NC}"
echo "  1. Remplacer tous les symboles 'persistence' → 'storage' dans les fichiers"
echo "  2. Renommer les fichiers *persistence* → *storage*"
echo "  3. Renommer les dossiers *persistence* → *storage*"
echo ""
read -r -p "Lancer le renommage ? [y/N] " confirm
[[ "${confirm}" =~ ^[yY]$ ]] || { log_warn "Abandon — aucune modification effectuée."; exit 0; }

# ---------------------------------------------------------------------------
# Étape 2 — Remplacement dans le contenu des fichiers
# ---------------------------------------------------------------------------
log_step "Étape 2 : Remplacement dans le contenu des fichiers"

CONTENT_FILES=$(
    find . -type f \( \
        -name "*.py" -o -name "*.md" -o -name "*.toml" \
        -o -name "*.yaml" -o -name "*.yml" -o -name "*.rst" \
        -o -name "*.cfg" -o -name "*.ini" \
    \) \
    -not -path "./.git/*" \
    -not -path "./.venv/*" \
    -not -path "./venv/*" \
    -not -path "./__pycache__/*" \
    -not -path "./htmlcov/*" \
    -not -path "./.mypy_cache/*" \
    -not -path "./.ruff_cache/*" \
    -not -path "./docs/changelog/*" \
    -not -name "CHANGELOG.md" \
    -not -name "$(basename "$0")" \
    2>/dev/null
)

echo "${CONTENT_FILES}" | while IFS= read -r filepath; do
    [[ -z "${filepath}" ]] && continue
    grep -qi "persistence" "${filepath}" 2>/dev/null || continue

    # 2a. Noms de classes (PascalCase)
    sed_inplace \
        -e 's/PersistenceConfig/StorageConfig/g' \
        -e 's/PersistenceBackend/StorageBackend/g' \
        -e 's/PersistencePort/StoragePort/g' \
        -e 's/PersistenceError/StorageError/g' \
        -e 's/PersistenceException/StorageException/g' \
        -e 's/SQLitePersistence/SQLiteStorage/g' \
        -e 's/MemoryPersistence/MemoryStorage/g' \
        -e 's/JsonPersistence/JsonStorage/g' \
        -e 's/FilePersistence/FileStorage/g' \
        -e 's/BasePersistence/BaseStorage/g' \
        -e 's/AbstractPersistence/AbstractStorage/g' \
        "${filepath}"

    # 2b. Chemins de modules dans les imports
    sed_inplace \
        -e 's/adapters\.persistence/adapters.storage/g' \
        -e 's/config\.persistence/config.storage/g' \
        -e 's/ports\.persistence/ports.storage/g' \
        "${filepath}"

    # 2c. Références textuelles génériques (snake_case, chemins, commentaires)
    sed_inplace \
        -e 's/persistence_backends/storage_backends/g' \
        -e 's/persistence_simple/storage_simple/g' \
        -e 's/persistence_layer/storage_layer/g' \
        -e 's/persistence_backend/storage_backend/g' \
        "${filepath}"

    log_info "Traité : ${filepath}"
done

log_ok "Remplacement dans les fichiers terminé"

# ---------------------------------------------------------------------------
# Étape 3 — Renommer les fichiers
# ---------------------------------------------------------------------------
log_step "Étape 3 : Renommage des fichiers"

for filepath in "${FILES_TO_RENAME[@]}"; do
    [[ -f "${filepath}" ]] || { log_warn "Fichier introuvable (déjà renommé ?) : ${filepath}"; continue; }
    newpath="${filepath//persistence/storage}"
    newdir="$(dirname "${newpath}")"
    mkdir -p "${newdir}"
    git mv "${filepath}" "${newpath}"
    log_ok "${filepath} → ${newpath}"
done

# ---------------------------------------------------------------------------
# Étape 4 — Renommer les dossiers (du plus profond au moins profond)
# ---------------------------------------------------------------------------
log_step "Étape 4 : Renommage des dossiers"

for dirpath in "${DIRS_TO_RENAME[@]}"; do
    [[ -d "${dirpath}" ]] || { log_warn "Dossier introuvable (déjà renommé ?) : ${dirpath}"; continue; }
    newdir="${dirpath//persistence/storage}"
    git mv "${dirpath}" "${newdir}"
    log_ok "${dirpath} → ${newdir}"
done

# ---------------------------------------------------------------------------
# Étape 5 — Vérification : occurrences restantes
# ---------------------------------------------------------------------------
log_step "Étape 5 : Vérification des occurrences restantes"

REMAINING=$(grep -rni "persistence" \
    --include="*.py" --include="*.md" --include="*.toml" \
    --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
    --exclude-dir=__pycache__ --exclude-dir=htmlcov \
    --exclude-dir=".mypy_cache" --exclude-dir=".ruff_cache" \
    . 2>/dev/null || true)

if [[ -z "${REMAINING}" ]]; then
    log_ok "Aucune occurrence de 'persistence' restante ✅"
else
    log_warn "Occurrences restantes (à vérifier manuellement) :"
    echo "${REMAINING}" | head -40
    echo ""
    log_warn "Ces occurrences peuvent être légitimes (ex. ADR, CHANGELOG, commentaires historiques)."
fi

# ---------------------------------------------------------------------------
# Étape 6 — Résumé et prochaines étapes
# ---------------------------------------------------------------------------
log_step "Résumé"

AFTER_COUNT=$(grep -rni "persistence" \
    --include="*.py" --include="*.md" --include="*.toml" \
    --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
    --exclude-dir=__pycache__ --exclude-dir=htmlcov \
    . 2>/dev/null | wc -l | tr -d ' ')

log_info "Occurrences avant : ${BEFORE_COUNT}"
log_info "Occurrences après : ${AFTER_COUNT}"
echo ""
log_ok "Renommage terminé. Prochaines étapes :"
echo ""
echo "  1. Inspecter le diff :"
echo "       git diff --stat"
echo "       git diff"
echo ""
echo "  2. Vérifier les imports Python :"
echo "       python -c \"from pyworkflow_engine.config.storage import StorageConfig; print('✅ Import OK')\""
echo ""
echo "  3. Lancer les tests :"
echo "       python -m pytest tests/ -v"
echo ""
echo "  4. Vérifier les types :"
echo "       python -m mypy src/"
echo ""
echo "  5. Commiter si tout est OK :"
echo "       git add -A"
echo "       git commit -m 'refactor: rename persistence → storage across codebase (ADR-012)'"
echo ""
