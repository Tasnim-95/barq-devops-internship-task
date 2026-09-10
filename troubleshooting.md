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
- **Related commit:** `fix(ingress): correct app bind address, healthcheck path, and nginx port mapping/upstream`
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
- **Related commit:** `fix(config): correct postgres/redis credentials and ports in app.env`
- **Remaining uncertainty:** The credential is still stored in a git-tracked file and baked into the Docker image (`Dockerfile` `COPY config/app.env`); this is deferred to a dedicated hardening phase, not resolved by this fix. The application also logs the full connection string (including credentials) at startup — a separate risk to be documented in `security_review.md`. `app-02` is still misreporting `instance_id` as `app-01` (tracked separately, not in scope for this fix).

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
- **Related commit:** `fix(compose): correct app-02 INSTANCE_ID to distinct value`
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
- **Related commit:** `fix(app): remove credentials from configuration_loaded startup log`
- **Remaining uncertainty:** The credential remains stored in the git-tracked `config/app.env` file and is still copied into the built image via `COPY config/app.env /srv/app.env`. This broader secret-management issue is deferred to the dedicated hardening phase. Earlier diagnostic commands also exposed the credential in terminal output; this will be documented as an investigation disclosure in `security_review.md`.


---

## INC-005 — Compose Network Isolation and PostgreSQL Persistence

### Entry / 2026-09-10 — Time: 15:56:24 EEST
- **Symptom:** The Compose configuration exposed PostgreSQL and Redis host ports, connected NGINX to both frontend and backend networks, and mounted the PostgreSQL named volume at `/var/lib/postgresql/backup` while using `tmpfs` for `/var/lib/postgresql/data`. These settings did not satisfy the required network isolation, host-port, and PostgreSQL persistence requirements.
- **Hypothesis:** The Compose topology and PostgreSQL storage configuration were responsible for the non-compliant network exposure and lack of persistent PostgreSQL storage.
- **Command or test:** Inspected `docker-compose.yml`, inspected the existing `barq-assessment_postgres-data` named volume, recreated the stack with the corrected Compose configuration, checked container/network state, created a PostgreSQL record through `/records`, recreated the PostgreSQL container without deleting the named volume, and queried `/records` again.
- **Actual output:** Before the change, PostgreSQL and Redis had host port mappings and NGINX was attached to both networks. The named PostgreSQL volume existed but contained no files at its mounted `/backup` path, while PostgreSQL data was configured on `tmpfs`. After the change, NGINX was attached only to `barq-assessment_frontend`; PostgreSQL and Redis were attached only to `barq-assessment_backend`; `docker compose ps -a` showed no published host ports for the applications, PostgreSQL, or Redis; and PostgreSQL was healthy.
- **Failed attempt and what changed your thinking:** No failed attempt was fabricated. The existing configuration and controlled runtime verification were sufficient to identify and prove the configuration issue.
- **Root cause:** `docker-compose.yml` used an incorrect PostgreSQL storage mount, an ephemeral `tmpfs` data directory, unnecessary PostgreSQL/Redis host-port publications, and attached NGINX to the backend network.
- **Fix:** Mounted the named `postgres-data` volume at `/var/lib/postgresql/data`, removed the PostgreSQL and Redis host-port mappings, removed the PostgreSQL `tmpfs` data mount, and restricted NGINX to the frontend network.
- **Retest evidence:** All five services started successfully and remained healthy. `docker inspect nginx` showed only `barq-assessment_frontend`; `docker inspect postgres` and `docker inspect redis` showed only `barq-assessment_backend`. A record titled `Volume persistence verification` was created through `POST /records`, PostgreSQL was recreated with `docker compose -p barq-assessment up -d --force-recreate postgres` without deleting the named volume, and `GET /records` returned the same record with `id: 3` afterward, proving PostgreSQL data survived container recreation.
- **Related commit:** Pending — this entry documents the changes currently present in the working tree for the infrastructure hardening commit.
- **Remaining uncertainty:** Redis persistence, restart policies, resource limits, container user privileges, secret management, validation/failure testing, backup/restore, CI, and the remaining documentation requirements still require separate implementation and verification.
