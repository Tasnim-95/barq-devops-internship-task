#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

PROJECT="${COMPOSE_PROJECT_NAME:-barq-assessment}"
CONTAINER="${POSTGRES_CONTAINER:-postgres}"
DB_NAME="${POSTGRES_DB:-barq_tasks}"
DB_USER="${POSTGRES_USER:-barq_app}"
BACKUP_DIR="${BACKUP_DIR:-backups}"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

cleanup() {
    if [[ -n "${VERIFY_PATH:-}" ]]; then
        docker exec \
            "$CONTAINER" \
            rm -f "$VERIFY_PATH" \
            >/dev/null 2>&1 || true
    fi

    if [[ -n "${TOC_PREVIEW:-}" ]]; then
        rm -f "$TOC_PREVIEW" 2>/dev/null || true
    fi
}

trap cleanup EXIT

command -v docker >/dev/null 2>&1 \
    || fail "Docker CLI is not available in PATH"

command -v sha256sum >/dev/null 2>&1 \
    || fail "sha256sum is not available in PATH"

mkdir -p "$BACKUP_DIR"

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

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
CHECKSUM="${OUTPUT}.sha256"

VERIFY_PATH="/tmp/verify_$(basename "$OUTPUT")"
TOC_PREVIEW="$(mktemp "${TMPDIR:-/tmp}/backup_toc_preview.XXXXXX")"

echo "=== PostgreSQL backup ==="
echo "Compose project: $PROJECT"
echo "Compose service: $SERVICE_LABEL"
echo "Database: $DB_NAME"
echo "Database user: $DB_USER"
echo "Container: $CONTAINER"
echo "Output: $OUTPUT"
echo

echo "Creating PostgreSQL custom-format dump..."

if ! docker exec \
    "$CONTAINER" \
    pg_dump \
        -U "$DB_USER" \
        -d "$DB_NAME" \
        -Fc \
    > "$OUTPUT"
then
    rm -f "$OUTPUT" "$CHECKSUM"
    fail "pg_dump failed"
fi

if [[ ! -s "$OUTPUT" ]]; then
    rm -f "$OUTPUT" "$CHECKSUM"
    fail "backup file is empty"
fi

echo "PASS: backup archive created ($(stat -c '%s bytes' "$OUTPUT"))"

echo
echo "Verifying archive integrity..."

if ! docker cp \
    "$OUTPUT" \
    "$CONTAINER:$VERIFY_PATH" >/dev/null
then
    rm -f "$OUTPUT" "$CHECKSUM"
    fail "failed to copy backup into PostgreSQL container for verification"
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

    rm -f "$OUTPUT" "$CHECKSUM"

    fail "pg_restore --list failed; backup archive is not valid"
fi

ENTRY_COUNT="$(
    grep -c ';' "$TOC_PREVIEW" || true
)"

if [[ "$ENTRY_COUNT" -le 0 ]]; then
    rm -f "$OUTPUT" "$CHECKSUM"
    fail "backup archive contains no table-of-contents entries"
fi

echo \
    "PASS: archive integrity verified " \
    "($ENTRY_COUNT table-of-contents entries)"

echo
echo "Generating SHA-256 checksum..."

if ! sha256sum "$OUTPUT" > "$CHECKSUM"; then
    rm -f "$OUTPUT" "$CHECKSUM"
    fail "failed to generate SHA-256 checksum"
fi

if [[ ! -s "$CHECKSUM" ]]; then
    rm -f "$OUTPUT" "$CHECKSUM"
    fail "checksum file was not created correctly"
fi

echo "PASS: SHA-256 checksum generated"

echo
echo "=== BACKUP PASSED ==="
echo "Backup: $OUTPUT"
echo "Checksum: $CHECKSUM"
echo "TOC entries: $ENTRY_COUNT"
