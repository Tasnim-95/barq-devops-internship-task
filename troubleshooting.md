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
