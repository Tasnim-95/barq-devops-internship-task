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
- **Fix:** Pending. The corrective configuration will be applied and verified as a separate change.
- **Retest evidence:** Pending corrective change.
- **Related commit:** Pending — `fix: restore application ingress and health checks`
- **Remaining uncertainty:** Network topology, PostgreSQL persistence, Redis persistence, secrets, container privileges, resource limits, validation, backup/restore, CI, and security controls still require separate investigation.
