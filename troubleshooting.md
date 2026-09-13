# Troubleshooting journal

Keep chronological entries. Copy this block for each meaningful investigation.

## Entry / date / time
- Symptom:
- Hypothesis:
- Command or test:
- Actual output:
- Failed attempt and what changed your thinking:
- Root cause:
- Fix:
- Retest evidence:
- Related commit:
- Remaining uncertainty:

Do not fabricate a failed attempt just to fill the template. Record actual attempts.
---

## INC-001 — Application Ingress and Health-Check Configuration

### Entry / 2026-09-08 — Time: 21:02:10 EEST
- **Symptom:** Both Flask application containers were unhealthy, while PostgreSQL and Redis were healthy. Requests through the published NGINX port were unsuccessful.
- **Hypothesis:** The failure could be caused by a healthcheck mismatch, incorrect application binding, incorrect NGINX upstream ports, or an incorrect host-to-container port mapping.
- **Command or test:** `docker compose ps -a`
- **Actual output:** `app-01` and `app-02` were unhealthy. PostgreSQL and Redis were healthy. NGINX was published on host port 8080.
- **Failed attempt and what changed your thinking:** No diagnostic command was fabricated as a failed attempt. The observed runtime failures were used as evidence.
- **Root cause:** Investigation identified multiple configuration mismatches: the healthcheck targets `/healthz` while the application exposes `/health`; Flask is bound to `127.0.0.1`; NGINX has an upstream port mismatch; and the host mapping targets container port 81 while NGINX listens on port 80.
- **Fix:** Set `APP_HOST` to `0.0.0.0` so Flask binds all interfaces inside its container (was `127.0.0.1`, unreachable from other containers). Corrected the compose healthcheck to target `/health` instead of the non-existent `/healthz`. Corrected the NGINX host-to-container port mapping from `:81` to `:80` to match `nginx.conf`'s `listen 80;`. Corrected the NGINX upstream entry for `app-01` from port `8081` to `8080`, matching its actual `APP_PORT`.
- **Retest evidence:** After `docker compose -p barq-assessment up -d`, `docker inspect --format '{{.State.Health.Status}}' app-01` and `app-02` both return `healthy`. `docker exec nginx wget -qO- http://app-01:8080/health` and the same for `app-02` both return `200` with a valid JSON body (previously `Connection refused`). `curl -i http://localhost:8080/health` and `curl -i http://localhost:8080/` both return `200` through the published port. `curl -i http://localhost:8080/ready` correctly returns `503` at this stage, since PostgreSQL/Redis credentials have not yet been corrected (tracked separately as INC-002, Phase 2).
- **Related commit:** `c43dccd` — `fix(ingress): correct app bind address, healthcheck path, and nginx port mapping/upstream`
- **Remaining uncertainty:** Network topology, PostgreSQL persistence, Redis persistence, secrets, container privileges, resource limits, validation, backup/restore, CI, and security controls still require separate investigation.

---

## INC-002 — PostgreSQL and Redis Connectivity (Credentials/Ports)

### Entry / 2026-09-09 — Time: 00:56:57 EEST
_(00:56:57 EEST = 21:56:57 UTC on 2026-09-08, the `Date:` header of the first response confirming the `/ready` failure — i.e. the first recorded symptom evidence, not an independently logged discovery moment. Fix verified at 22:33:51 UTC / 01:33:51 EEST the same evening.)_
- **Symptom:** `/ready` returned 503 with both `postgres` and `redis` marked `unavailable` (observed as part of INC-001 retest, once ingress was fixed and the endpoint became reachable at all).
- **Hypothesis:** PostgreSQL credentials and/or ports did not match between `docker-compose.yml`'s `POSTGRES_PASSWORD` and `config/app.env`'s `DATABASE_URL`; `REDIS_URL` port did not match the Redis service's actual listening port.
- **Command or test:** Structural (redacted) comparison of `POSTGRES_PASSWORD` in `docker-compose.yml` against `DATABASE_URL`/`REDIS_URL` in `config/app.env`; live app logs showing `OperationalError` (postgres) and `ConnectionError` (redis) on `/ready`.
- **Actual output:** `DATABASE_URL` referenced port `5433` (Postgres actually listens on `5432`) and a password differing by one character from `POSTGRES_PASSWORD`. `REDIS_URL` referenced port `6380` (Redis actually listens on `6379`).
- **Failed attempt and what changed your thinking:** No failed attempt fabricated. The redacted structural comparison was sufficient to confirm both mismatches before any fix was applied.
- **Root cause:** `config/app.env` contained an incorrect PostgreSQL password (one-character mismatch vs. `docker-compose.yml`) and incorrect ports for both PostgreSQL (`5433` vs `5432`) and Redis (`6380` vs `6379`).
- **Fix:** Corrected `DATABASE_URL` in `config/app.env` to use the password from `docker-compose.yml`'s `POSTGRES_PASSWORD` and port `5432`; corrected `REDIS_URL` to port `6379`. `app-01` and `app-02` recreated to pick up the updated `env_file`.
- **Retest evidence:** `curl -i http://localhost:8080/ready` returns `200` with `{"dependencies":{"postgres":"ready","redis":"ready"},...}`. `docker logs app-01`/`app-02` confirm `configuration_loaded` now shows `postgres:5432` and `redis:6379`.
- **Related commit:** `0208e67` — `fix(config): correct postgres/redis credentials and ports in app.env`
- **Remaining uncertainty:** At the time of this investigation, the PostgreSQL and Redis configuration had not yet been corrected. The configuration issue was subsequently addressed and `/ready` was re-tested successfully.

The application startup log also exposed the full connection strings at that stage; this was tracked separately as `INC-004`.

The `app-02` instance identity issue was tracked separately as `INC-003`.

---

## INC-003 — Instance Identity (app-02 misreporting as app-01)

### Entry / 2026-09-09 — Time: 01:53:30 EEST
_(01:53:30 EEST = 2026-09-08T22:53:30.416+00:00, the timestamp on the post-fix `configuration_loaded` application log line. The original discovery time was not independently recorded; this is the recorded verification/evidence time, not the discovery time.)_
- **Symptom:** `/instance` and `/ready` responses from app-02 reported `instance_id: "app-01"`, identical to app-01's own identity. Both containers were indistinguishable through their API responses.
- **Hypothesis:** The `app-02` service block in `docker-compose.yml` set `INSTANCE_ID` to the wrong literal value (a copy-paste error from the `app-01` block), rather than an application-code bug, since the app reads `INSTANCE_ID` directly from the environment (`os.getenv("INSTANCE_ID", "local")`).
- **Command or test:** `grep`/direct inspection of `docker-compose.yml` confirmed both `app-01` and `app-02` service blocks contained the literal line `INSTANCE_ID: "app-01"`.
- **Actual output:** Confirmed both blocks were identical; `app-02`'s override did not set a distinct value.
- **Failed attempt and what changed your thinking:** No failed attempt fabricated. Direct file inspection was sufficient to locate the root cause without trial-and-error.
- **Root cause:** `docker-compose.yml`, `app-02` service block, `environment` override contained `INSTANCE_ID: "app-01"` instead of `INSTANCE_ID: "app-02"`.
- **Fix:** Changed the single line in the `app-02` service block from `INSTANCE_ID: "app-01"` to `INSTANCE_ID: "app-02"`. No other lines in the block were touched; `app-01`'s block was not modified.
- **Retest evidence:** After `docker compose -p barq-assessment up -d --force-recreate app-01 app-02`, six sequential `GET /instance` requests through NGINX returned, in order: `app-02, app-01, app-02, app-01, app-02, app-01` — confirming both distinct identities are now being served. Direct per-container checks bypassing NGINX showed `X-Instance-ID: app-01` with body `instance_id: app-01` for app-01, and `X-Instance-ID: app-02` with body `instance_id: app-02` for app-02.
- **Related commit:** `71bd8bc` — `fix(compose): correct app-02 INSTANCE_ID to distinct value`
- **Remaining uncertainty:** None specific to this issue; distribution ratio across a larger request sample was not captured and is not cited as evidence here.

---

## INC-004 — Secret Leakage in Application Startup Logs

### Entry / 2026-09-09 — Time: 01:53:30 EEST
_(01:53:30 EEST = 2026-09-08T22:53:30.416+00:00, the recorded `configuration_loaded` log timestamp from the same post-fix verification cycle as INC-003. The original discovery time was not independently recorded; this is the recorded verification/evidence time, not the discovery time.)_
- **Symptom:** On every process start, `app/server.py`'s `configuration_loaded` log event included the full `DATABASE_URL` and `REDIS_URL` values, including the PostgreSQL username and password, in plaintext in container stdout logs.
- **Hypothesis:** The `if __name__ == "__main__":` block logged `os.getenv("DATABASE_URL", "")` and `os.getenv("REDIS_URL", "")` directly, with no redaction, as part of diagnosing INC-002 connectivity via `docker logs`.
- **Command or test:** Direct inspection of `app/server.py`, confirmed by observing the actual `docker logs app-01`/`app-02` output during INC-002 verification, which showed the full connection strings.
- **Actual output:** `configuration_loaded` log lines contained raw connection URLs including credentials.
- **Failed attempt and what changed your thinking:** No failed attempt fabricated. The leak was identified directly by inspecting log output already produced during INC-002 verification, not through trial-and-error.
- **Root cause:** `app/server.py` logged the raw `DATABASE_URL`/`REDIS_URL` environment values instead of extracting non-secret connection metadata before logging.
- **Fix:** Added a `_safe_connection_metadata()` helper that parses each URL with `urllib.parse.urlsplit` and returns only `host`, `port`, and `database`/path. The `configuration_loaded` log event now calls this helper for both connections instead of logging the raw URLs. The actual dependency connection logic was not changed.
- **Retest evidence:** After rebuilding both app images and recreating both app containers, fresh `configuration_loaded` logs for app-01 and app-02 contained only safe metadata. Both credential-pattern checks returned `0`. `/ready` returned HTTP 200 with PostgreSQL and Redis ready, confirming runtime connectivity was unaffected.
- **Related commit:** `3af6315` — `fix(app): remove credentials from configuration_loaded startup log`
- **Remaining uncertainty:** At the time of this verification, the credential was still stored in the tracked `config/app.env` file and was being copied into the application image.

This was subsequently addressed during security hardening:
- the tracked secret file was removed;
- the Dockerfile stopped copying the secret file into the image;
- runtime configuration was moved to the ignored `.env` file;
- a safe `.env.example` was provided.

Earlier diagnostic commands also exposed the synthetic credential in terminal output. This disclosure is documented separately in `security_review.md`.


---

## INC-005 — Compose Network Isolation and Persistent Storage

### Entry / 2026-09-10 — Time: 15:56:24 EEST
- **Symptom:** The Compose configuration exposed PostgreSQL and Redis host ports, connected NGINX to both frontend and backend networks, and mounted the PostgreSQL named volume at `/var/lib/postgresql/backup` while using `tmpfs` for `/var/lib/postgresql/data`. These settings did not satisfy the required network isolation, host-port, and PostgreSQL persistence requirements.
- **Hypothesis:** The Compose topology and PostgreSQL storage configuration were responsible for the non-compliant network exposure and lack of persistent PostgreSQL storage.
- **Command or test:** Inspected `docker-compose.yml`, inspected the existing `barq-assessment_postgres-data` named volume, recreated the stack with the corrected Compose configuration, checked container/network state, created a PostgreSQL record through `/records`, recreated the PostgreSQL container without deleting the named volume, and queried `/records` again.
- **Actual output:** Before the change, PostgreSQL and Redis had host port mappings and NGINX was attached to both networks. The named PostgreSQL volume existed but was not mounted as the PostgreSQL data directory, while PostgreSQL data was configured on `tmpfs`. After the change, NGINX was attached only to `barq-assessment_frontend`; PostgreSQL and Redis were attached only to `barq-assessment_backend`; `docker compose ps` showed no published host ports for the applications, PostgreSQL, or Redis; and PostgreSQL was healthy.
- **Failed attempt and what changed your thinking:** No failed attempt was fabricated. The existing configuration and controlled runtime verification were sufficient to identify and prove the configuration issue.
- **Root cause:** `docker-compose.yml` used an incorrect PostgreSQL storage mount, an ephemeral `tmpfs` data directory, unnecessary PostgreSQL/Redis host-port publications, and attached NGINX to the backend network.
- **Fix:** Mounted the named `postgres-data` volume at `/var/lib/postgresql/data`, removed the PostgreSQL and Redis host-port mappings, removed the PostgreSQL `tmpfs` data mount, and restricted NGINX to the frontend network. The hardening also added Redis persistence with a named `redis-data` volume.
- **Retest evidence:** `docker compose -p barq-assessment ps` showed all five services healthy, with only NGINX publishing `127.0.0.1:8080->80/tcp`. `./validate.py` passed the host-port and backend-network isolation checks. NGINX was attached only to the frontend network, while PostgreSQL and Redis were attached only to the backend network. A PostgreSQL record was created through `POST /records`; the PostgreSQL container was then recreated with `docker compose -p barq-assessment up -d --force-recreate postgres app-01 app-02` without deleting the named volume, and `GET /records` returned the persistence-proof record afterward. The named `barq-assessment_postgres-data` and `barq-assessment_redis-data` volumes were present.
- **Related commit:** `4f46baa fix(compose): isolate networks and persist postgres data`
- **Remaining uncertainty:** The lab now satisfies the tested Compose isolation and persistence requirements. Production concerns such as encrypted backups, external secret management, centralized monitoring, and multi-host failure tolerance remain outside this local Compose implementation.

---

## Verification-001 — Post-Hardening Verification

### Verification / 2026-09-11
- **Scope:** Verify the implemented deployment, validation, failure recovery, backup/restore, and persistence controls after the infrastructure hardening changes.
- **Command or test:** `python3 -m py_compile app/server.py validate.py failure_test.py scripts/video_challenge.py`; `bash -n backup.sh restore.sh`; `docker compose -p barq-assessment config -q`; `./validate.py`; `./backup.sh`; and the previously executed controlled failure/recovery and persistence recreation tests.
- **Actual output:** Python and shell syntax checks completed successfully. Compose configuration validation completed successfully. `./validate.py` returned `VALIDATION PASSED: all checks succeeded`, including endpoint, request-ID, backend distribution, dependency readiness, host-port, and backend-network checks. `./backup.sh` created a non-empty PostgreSQL custom-format backup with a SHA-256 checksum. The controlled backend failure test previously achieved 100% HTTP availability during the app-01 outage and subsequently proved app-01 recovered and served traffic again. The persistence test previously proved a PostgreSQL record remained available after recreating PostgreSQL and both application containers without deleting the named PostgreSQL volume. The backup/restore test previously proved the restore operation completed and removed a post-backup record that was not present in the backup.
- **Failed attempt and what changed your thinking:** No failed attempt was fabricated for this verification entry. The entry records successful verification of implemented controls; historical failed attempts remain documented in INC-001 through INC-004.
- **Root cause:** Not applicable; this is a post-hardening verification entry rather than a new incident.
- **Fix:** Not applicable; implementation changes are documented in the related incident entries and commits.
- **Retest evidence:** Final validation passed all checks. The running Compose project reported all five services healthy, with only NGINX publishing the host port. Backup creation completed successfully and checksum verification was performed. Earlier controlled failure/recovery, persistence, and restore evidence was retained as part of the assessment verification record.
- **Related commit:** Verification covers the hardening and validation implementation associated with `4f46baa` and `5485bd7`; later documentation and video-related changes will be linked to their actual commits after recording.
- **Remaining uncertainty:** GitHub Actions CI was executed on GitHub for commit `5485bd7` and completed successfully. The final submission CI run must still be linked to the eventual final commit after the video-related changes.

---

## INC-006 — PostgreSQL Credential Rotation and Runtime Secret Hardening

### Entry / 2026-09-12 — Credential remediation
- **Symptom:** A PostgreSQL credential had previously been exposed through application startup logs and diagnostic terminal output. The credential was therefore treated as compromised and required replacement rather than continued use.
- **Hypothesis:** The PostgreSQL application role could be rotated in-place and the replacement credential could be deployed through the ignored runtime configuration without affecting persisted application data or service availability.
- **Command or test:** Generated a cryptographically random replacement credential with Python `secrets` without printing it; updated the ignored `.env` runtime configuration; changed `.env` permissions from `0644` to `0600`; rotated the `barq_app` PostgreSQL role using the interactive `psql \password` workflow so the new credential was not supplied as a command-line argument; recreated `app-01` and `app-02`; verified `/ready`, `/records`, application logs, persisted records, and the full validation suite.
- **Actual output:** The replacement credential was present in both required runtime configuration locations and passed a non-disclosing consistency check. `.env` permissions were `0600` and the file remained ignored by Git. PostgreSQL and both application containers became healthy after recreation. `/ready` returned HTTP 200, `/records` returned HTTP 200, existing PostgreSQL records remained available, and fresh application logs contained no credential patterns. `./validate.py` completed with `VALIDATION PASSED: all checks succeeded`.
- **Failed attempt and what changed your thinking:** No failed attempt was fabricated. The previously compromised credential was not replayed to prove rejection because it was no longer safely available and recovering or redisplaying it would unnecessarily re-expose a compromised secret. Successful authentication with the replacement credential and the complete application validation suite were used as the verification evidence.
- **Root cause:** The original PostgreSQL credential had become a security liability because it had been exposed during the earlier investigation.
- **Fix:** Rotated the PostgreSQL `barq_app` role credential in-place, replaced the runtime credential in the ignored `.env` configuration, restricted `.env` permissions to owner-only access (`0600`), and recreated the application containers so they consumed the replacement credential. No PostgreSQL volume was deleted or recreated.
- **Retest evidence:** `docker compose -p barq-assessment ps` showed PostgreSQL and both application instances healthy. `/ready` returned `200`; `/records` returned `200`; existing records remained queryable; both application log checks returned `PASS: no credential pattern found`; and `./validate.py` returned `VALIDATION PASSED: all checks succeeded`. The validation also reconfirmed dependency readiness, endpoint behavior, host-port isolation, network isolation, persistence, restart policies, resource limits, non-root execution, and digest-pinned images.
- **Related commit:** TBD — documentation and security-remediation changes will be committed after the security documentation audit is complete.
- **Remaining uncertainty:** The historical credential was not replay-tested after rotation because doing so would require recovering or redisclosing the compromised secret. GitLab token revocation/rotation is a separate credential-management action and is not claimed as completed by this entry.

## INC-007 — Docker Desktop published-port reset during pre-video audit

**Date:** 2026-09-13
**Environment:** Docker Desktop on WSL2, project `barq-assessment`
**Severity:** Medium
**Status:** Resolved

### Symptom

During the pre-video runtime audit, the application containers and NGINX were healthy, and NGINX could successfully reach both application instances. However, requests from the WSL host to the published endpoint `127.0.0.1:8080` failed with:

```text
curl: (56) Recv failure: Connection reset by peer
```

### Investigation

The following checks confirmed that the application stack itself was healthy:

- `docker compose -p barq-assessment ps` showed `app-01`, `app-02`, `nginx`, `postgres`, and `redis` running and healthy.
- `docker exec nginx wget -S -O- http://127.0.0.1/health` returned HTTP 200.
- NGINX successfully reached `app-01:8080/health` and `app-02:8080/health`, both returning HTTP 200.
- `docker exec nginx nginx -t` reported that the NGINX configuration syntax was valid.
- NGINX access logs showed successful HTTP 200 requests to both upstream instances.
- The failing host-side `curl` requests did not appear in the NGINX access log.

This isolated the failure to the Docker Desktop/WSL published-port path rather than the Flask application, NGINX configuration, or backend network connectivity.

### Resolution

The NGINX container was restarted without performing a full-stack reset:

```bash
docker compose -p barq-assessment restart nginx
```

After the restart, the published endpoint was verified successfully:

```text
HTTP/1.1 200 OK
X-Instance-ID: app-01
```

The Docker Compose project remained running, and no volumes were removed.

### Verification

The successful response after the NGINX-only restart confirmed recovery of the request path:

```text
WSL host -> 127.0.0.1:8080 -> Docker published port -> NGINX -> application
```

### Operational note

`docker compose down` was deliberately not used. The issue was resolved with the smallest bounded recovery action, preserving the running stack and persistent data.

### Lesson learned

If the containers and internal NGINX/upstream checks are healthy but the host-side published port returns `Connection reset by peer` and the request is absent from the NGINX access log, first investigate the Docker Desktop/WSL published-port path. An NGINX-only restart can be tested as a bounded recovery action before considering broader environment changes.
