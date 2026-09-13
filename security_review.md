# Security and Production-Readiness Review

This review records concrete security risks and production-readiness improvements
identified during the assessment investigation and subsequent hardening work.

Status meanings:
- **Implemented:** control is present and verified in the current solution.
- **Mitigated:** the immediate exposure is addressed, but additional production
  controls may still be appropriate.
- **Follow-up:** intentionally outside the scope of this local Compose assessment.

---

## 1. PostgreSQL credential exposure in application startup logs

- **Risk and evidence:** The original application startup log emitted the full
  `DATABASE_URL` and `REDIS_URL`, including the PostgreSQL credential. This was
  observed during INC-004.
- **Impact:** Anyone with access to container logs could obtain credentials and
  use them to access backend services.
- **Implemented fix / commit:** Added `_safe_connection_metadata()` in
  `app/server.py` so startup logging records only non-secret connection
  metadata such as host, port, and database. Related commit:
  `3af6315`.
- **Production follow-up:** Centralize logs and enforce restricted access,
  retention, and audit controls. Sensitive fields should remain excluded from
  structured logs.
- **How to verify:** Inspect fresh application logs and run:
  `docker logs app-01 2>&1 | grep -Ei 'postgresql://|redis://|password=|POSTGRES_PASSWORD'`
  The expected result is no credential pattern.

**Status: Implemented**

---

## 2. Historical secret stored in a tracked configuration file

- **Risk and evidence:** The original `config/app.env` contained runtime
  database configuration and was tracked in Git history.
- **Impact:** A secret committed to repository history can remain recoverable
  even after the working-tree file is deleted.
- **Implemented fix / commit:** Removed the secret configuration from the
  current working tree, added it to `.gitignore`, stopped relying on it as the
  runtime configuration source, and introduced `.env.example` containing only
  placeholders.
- **Production follow-up:** Historical exposed credentials must be considered
  compromised. Repository history should be retained as incident evidence unless
  an approved history-rewrite procedure is explicitly required.
- **How to verify:** `git ls-files -- config/app.env .env` should return no
  tracked secret file, and `git check-ignore -v .env config/app.env` should
  confirm both paths are ignored.

**Status: Mitigated**

---

## 3. Secret copied into the application image

- **Risk and evidence:** The original Dockerfile copied the secret configuration
  into the application image.
- **Impact:** Credentials could persist in image layers and become accessible to
  anyone able to pull or inspect the image.
- **Implemented fix / commit:** Removed the secret-file copy from the Dockerfile
  and moved runtime configuration to the ignored `.env` mechanism.
- **Production follow-up:** Prefer a dedicated secret-management mechanism such
  as Docker/Compose secrets or an external secret manager for production
  deployments.
- **How to verify:** Inspect the Dockerfile and image filesystem to confirm
  `config/app.env` is not copied into the image.

**Status: Implemented**

---

## 4. Previously exposed PostgreSQL credential required rotation

- **Risk and evidence:** The PostgreSQL credential had previously appeared in
  application logs and diagnostic terminal output. The credential was therefore
  treated as compromised.
- **Impact:** Continuing to use a compromised credential would leave the
  previously exposed access path valid.
- **Implemented fix / commit:** Generated a cryptographically random replacement
  credential, rotated the `barq_app` PostgreSQL role in-place using the
  interactive `psql \password` workflow, updated runtime configuration, and
  recreated the application containers.
- **Production follow-up:** Apply the same incident-response principle to all
  exposed credentials, including external service tokens. External credential
  revocation/rotation must be completed through the owning service.
- **How to verify:** The replacement credential passed consistency checks;
  `/ready` returned HTTP 200, `/records` returned HTTP 200, existing records
  remained available, and the complete validation suite passed.
  The old credential was not replay-tested because recovering or redisclosing a
  compromised secret would create unnecessary exposure.

**Status: Implemented**

---

## 5. Runtime secret file permissions were too broad

- **Risk and evidence:** The runtime `.env` file was initially readable with
  permissions `0644`.
- **Impact:** Other local users could potentially read credentials stored in the
  file.
- **Implemented fix / commit:** Changed the runtime secret file to owner-only
  permissions with `chmod 600 .env`.
- **Production follow-up:** Use platform-native secret stores and least-privilege
  filesystem policies where available.
- **How to verify:** `stat -c 'permissions=%a owner=%U group=%G' .env` should report
  `permissions=600`.

**Status: Implemented**

---

## 6. PostgreSQL and Redis were unnecessarily exposed on host ports

- **Risk and evidence:** The original Compose configuration published backend
  service ports to the host.
- **Impact:** Backend services became reachable outside the intended application
  network, increasing the attack surface and bypassing the NGINX ingress path.
- **Implemented fix / commit:** Removed host port mappings from PostgreSQL and
  Redis. Only NGINX publishes the application port.
- **Production follow-up:** Apply host firewall rules and network policies in
  addition to container-level isolation for production environments.
- **How to verify:** `./validate.py` confirms no published host ports for
  `app-01`, `app-02`, PostgreSQL, or Redis, while NGINX has the expected
  published port.

**Status: Implemented**

---

## 7. NGINX initially had access to the backend network

- **Risk and evidence:** The original topology attached NGINX to both frontend
  and backend networks.
- **Impact:** A compromise of the reverse proxy could potentially provide direct
  network reachability to PostgreSQL and Redis.
- **Implemented fix / commit:** NGINX is attached only to the frontend network.
  PostgreSQL and Redis are attached only to the internal backend network.
  Related commit: `4f46baa`.
- **Production follow-up:** Enforce equivalent network segmentation with
  infrastructure-level network policies where applicable.
- **How to verify:** `./validate.py` verifies runtime network membership and
  confirms NGINX cannot directly reach `postgres:5432` or `redis:6379`.

**Status: Implemented**

---

## 8. Container privilege and least-privilege risk

- **Risk and evidence:** Application containers initially lacked the required
  least-privilege execution control.
- **Impact:** A successful application compromise could provide greater access
  than necessary inside the container.
- **Implemented fix / commit:** The application image creates a dedicated
  non-root `app` user and runs Flask as that user.
- **Production follow-up:** Continue hardening with read-only filesystems,
  dropped Linux capabilities, seccomp/AppArmor policies, and other controls
  appropriate for the deployment platform.
- **How to verify:** `./validate.py` confirms both Flask application containers
  run as the non-root `app` user.

**Status: Implemented**

---

## 9. Container image supply-chain and reproducibility risk

- **Risk and evidence:** Floating container image tags can change over time and
  make builds non-reproducible.
- **Impact:** An unexpected upstream image change can introduce vulnerabilities
  or behavior changes without a corresponding repository change.
- **Implemented fix / commit:** PostgreSQL, Redis, and NGINX images are pinned by
  immutable SHA-256 digests.
- **Production follow-up:** Maintain an image update process including
  vulnerability scanning, controlled digest updates, and rebuild verification.
- **How to verify:** `./validate.py` confirms the infrastructure images are
  digest-pinned rather than floating tags.

**Status: Implemented**

---

## 10. Resource exhaustion and noisy-neighbor risk

- **Risk and evidence:** Containers without resource limits can consume
  disproportionate host resources during failures or abnormal workloads.
- **Impact:** Excessive CPU or memory use can cause service degradation or host
  instability.
- **Implemented fix / commit:** CPU and memory limits are defined for all
  services.
- **Production follow-up:** Tune limits from observed workloads and add
  monitoring/alerting for sustained resource pressure.
- **How to verify:** `./validate.py` confirms memory and CPU limits for all five
  services.

**Status: Implemented**

---

## 11. Data persistence and backup integrity

- **Risk and evidence:** PostgreSQL originally used an incorrect persistence
  configuration and Redis lacked the required persistent data setup.
- **Impact:** Container recreation could cause data loss or inconsistent
  recovery behavior.
- **Implemented fix / commit:** PostgreSQL now uses the named
  `postgres-data` volume at `/var/lib/postgresql/data`. Redis uses a named
  volume with AOF enabled. Backup and restore procedures are provided.
- **Production follow-up:** Store encrypted backups outside the host, define
  retention policies, test restores regularly, and protect backup access
  separately from database credentials.
- **How to verify:** `./validate.py` verifies named volumes and Redis AOF.
  `backup.sh` creates a PostgreSQL custom-format backup and checksum, while the
  restore procedure verifies archive integrity and restored data.

**Status: Implemented with production follow-up**

---

## 12. Availability and failure-detection risk

- **Risk and evidence:** A backend application instance can fail independently
  of the reverse proxy. Dependency failures also need to be distinguished from
  process liveness.
- **Impact:** Without health-aware routing and readiness semantics, traffic can
  be sent to unhealthy instances or an application can incorrectly appear
  healthy while its dependencies are unavailable.
- **Implemented fix / commit:** Separate `/health` liveness from `/ready`
  dependency readiness, configure container healthchecks, configure NGINX
  upstream failover, and use restart policies.
- **Production follow-up:** Add centralized monitoring, alerting, SLOs, and
  longer-term availability testing in a production environment.
- **How to verify:** `./validate.py` verifies liveness/readiness behavior,
  dependency-failure behavior, backend distribution, and service health.
  `failure_test.py` verifies continued HTTP availability while one application
  instance is stopped and verifies recovery afterward.

**Status: Implemented**

---

## 13. Request correlation and operational logging

- **Risk and evidence:** Distributed requests passing through NGINX and multiple
  application instances are difficult to investigate without correlation.
- **Impact:** Incident investigation becomes slower and cross-instance tracing
  becomes unreliable.
- **Implemented fix / commit:** Application responses include `X-Request-ID`
  and instance identity. Validation explicitly checks request-ID behavior.
- **Production follow-up:** Propagate correlation IDs into centralized structured
  logging and tracing systems, with retention and access controls.
- **How to verify:** `./validate.py` checks `X-Request-ID` across the required
  endpoints and confirms distinct application instance identities.

**Status: Implemented with production follow-up**

---

## 14. Diagnostic disclosure during incident investigation

- **Risk and evidence:** Earlier troubleshooting commands exposed a synthetic
  credential in terminal output while investigating configuration mismatches.
- **Impact:** Terminal history, recordings, screenshots, or copied diagnostics
  can become secondary secret-leak channels.
- **Implemented fix / commit:** Subsequent security verification avoids printing
  secret values, uses non-disclosing consistency checks, and treats the exposed
  credential as compromised and rotated.
- **Production follow-up:** Use redacted diagnostics, secret-aware tooling, and
  controlled evidence collection during incidents. Never paste credentials into
  tickets, chat, screenshots, or video recordings.
- **How to verify:** Review current evidence commands and confirm that security
  checks report only PASS/FAIL or non-secret metadata.

**Status: Mitigated**

---

## Security posture summary

The current solution has implemented controls for secret exposure, runtime
secret permissions, host-port minimization, network segmentation, persistence,
backup/restore, least-privilege application execution, resource limits,
digest-pinned infrastructure images, health/readiness behavior, failover, and
request correlation.

The remaining production-oriented follow-ups are intentionally identified
rather than presented as completed controls. These include external secret
management, centralized monitoring, encrypted/off-host backups, vulnerability
scanning, infrastructure-level network policy, and formal SLO/alerting
management.
