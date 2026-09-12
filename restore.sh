#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

PROJECT="${COMPOSE_PROJECT_NAME:-barq-assessment}"
CONTAINER="${POSTGRES_CONTAINER:-postgres}"
DB_NAME="${POSTGRES_DB:-barq_tasks}"
DB_USER="${POSTGRES_USER:-barq_app}"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 backups/barq_tasks_TIMESTAMP.dump" >&2
    exit 2
fi

BACKUP="$1"

if [[ ! -f "$BACKUP" ]]; then
    fail "backup file does not exist: $BACKUP"
fi

if [[ ! -s "$BACKUP" ]]; then
    fail "backup file is empty: $BACKUP"
fi

command -v docker >/dev/null 2>&1 \
    || fail "Docker CLI is not available in PATH"

command -v sha256sum >/dev/null 2>&1 \
    || fail "sha256sum is not available in PATH"

echo "=== PostgreSQL restore ==="
echo "Compose project: $PROJECT"
echo "Database: $DB_NAME"
echo "Database user: $DB_USER"
echo "Container: $CONTAINER"
echo "Backup: $BACKUP"
echo

if [[ -f "${BACKUP}.sha256" ]]; then
    echo "Verifying SHA-256 checksum..."

    if ! sha256sum -c "${BACKUP}.sha256" --status; then
        fail "checksum verification failed for $BACKUP"
    fi

    echo "PASS: checksum verified"
else
    echo \
        "WARNING: no checksum file found at ${BACKUP}.sha256; " \
        "skipping checksum verification" \
        >&2
fi

echo
echo "Checking backup archive integrity..."

TOC_PREVIEW="$(mktemp "${TMPDIR:-/tmp}/restore_toc_preview.XXXXXX")"

cleanup() {
    rm -f "$TOC_PREVIEW" 2>/dev/null || true
}

trap cleanup EXIT

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    fail "container '$CONTAINER' was not found"
fi

PROJECT_LABEL="$(
    docker inspect \
        -f '{{ index .Config.Labels "com.docker.compose.project" }}' \
        "$CONTAINER" \
        2>/dev/null || true
)"

if [[ "$PROJECT_LABEL" != "$PROJECT" ]]; then
    fail \
        "container '$CONTAINER' is not part of Compose project '$PROJECT' " \
        "(found project label: ${PROJECT_LABEL:-<empty>})"
fi

SERVICE_LABEL="$(
    docker inspect \
        -f '{{ index .Config.Labels "com.docker.compose.service" }}' \
        "$CONTAINER" \
        2>/dev/null || true
)"

if [[ "$SERVICE_LABEL" != "postgres" ]]; then
    fail \
        "container '$CONTAINER' is not the Compose 'postgres' service " \
        "(found service label: ${SERVICE_LABEL:-<empty>})"
fi

echo "PASS: Compose project/service identity verified"

CONTAINER_STATE="$(
    docker inspect \
        -f '{{.State.Status}}' \
        "$CONTAINER"
)"

if [[ "$CONTAINER_STATE" != "running" ]]; then
    fail \
        "PostgreSQL container '$CONTAINER' is not running " \
        "(state: $CONTAINER_STATE)"
fi

HEALTH="$(
    docker inspect \
        -f '{{.State.Health.Status}}' \
        "$CONTAINER" \
        2>/dev/null || true
)"

if [[ "$HEALTH" != "healthy" ]]; then
    fail \
        "PostgreSQL container '$CONTAINER' is not healthy " \
        "(health: ${HEALTH:-<none>})"
fi

echo "PASS: PostgreSQL container is running and healthy"

VERIFY_PATH="/tmp/verify_restore_$(basename "$BACKUP")"

cleanup_container() {
    docker exec \
        "$CONTAINER" \
        rm -f "$VERIFY_PATH" \
        >/dev/null 2>&1 || true
}

trap 'cleanup_container; cleanup' EXIT

if ! docker cp \
    "$BACKUP" \
    "$CONTAINER:$VERIFY_PATH" \
    >/dev/null
then
    fail "failed to copy backup into PostgreSQL container"
fi

if ! docker exec \
    "$CONTAINER" \
    pg_restore \
        --list \
        "$VERIFY_PATH" \
    > "$TOC_PREVIEW" 2>&1
then
    echo "Archive TOC verification failed:" >&2
    cat "$TOC_PREVIEW" >&2
    fail "backup archive failed pg_restore --list validation"
fi

ENTRY_COUNT="$(
    grep -c ';' "$TOC_PREVIEW" || true
)"

if [[ "$ENTRY_COUNT" -le 0 ]]; then
    fail "backup archive contains no table-of-contents entries"
fi

echo \
    "PASS: backup archive integrity verified " \
    "($ENTRY_COUNT table-of-contents entries)"

echo
echo "Restoring PostgreSQL backup..."

if ! docker exec \
    -i \
    "$CONTAINER" \
    pg_restore \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        --clean \
        --if-exists \
        --no-owner \
    < "$BACKUP"
then
    fail "PostgreSQL restore failed"
fi

echo "PASS: restore command completed"

echo
echo "Verifying restored data..."

VERIFY_ERROR="$(mktemp "${TMPDIR:-/tmp}/restore_verify.XXXXXX")"

cleanup_verify() {
    rm -f "$VERIFY_ERROR" 2>/dev/null || true
}

trap 'cleanup_container; cleanup; cleanup_verify' EXIT

if ! ROW_COUNT="$(
    docker exec \
        "$CONTAINER" \
        psql \
            -U "$DB_USER" \
            -d "$DB_NAME" \
            -t \
            -A \
            -c "SELECT COUNT(*) FROM records;" \
        2>"$VERIFY_ERROR"
)"
then
    echo "Post-restore verification query failed:" >&2
    cat "$VERIFY_ERROR" >&2
    fail "post-restore verification query failed"
fi

ROW_COUNT="$(
    echo "$ROW_COUNT" | tr -d '[:space:]'
)"

if ! [[ "$ROW_COUNT" =~ ^[0-9]+$ ]]; then
    fail \
        "post-restore verification returned a non-numeric " \
        "row count: $ROW_COUNT"
fi

echo \
    "PASS: restored database is queryable, " \
    "records table contains $ROW_COUNT row(s)"

echo
echo "=== RESTORE PASSED ==="
echo "Database: $DB_NAME"
echo "Backup: $BACKUP"
echo "TOC entries: $ENTRY_COUNT"
echo "Records: $ROW_COUNT"
