# Technical Decisions

At least 5 decisions are required; 8 are documented below, covering base image, health
checks, networks, timeouts/retries, restart/resource settings, persistence, secrets, and
non-root execution, per TASK.md's Part 4 checklist. Each entry states the context, the
chosen approach, the alternatives considered, the trade-offs accepted, and the limitation
that remains. Evidence for each decision (commands, real output) lives in
`troubleshooting.md` and is cross-referenced by incident number where applicable.

---

## Decision 1 — NGINX as the sole public entrypoint

- **Context/problem:** The starter environment published host ports for `nginx`,
  `postgres`, and `redis` simultaneously (`127.0.0.1:15432:5432`, `127.0.0.1:16379:6379`
  in addition to NGINX's port) — directly violating TASK.md's "Publish only NGINX on host
  port 8080. Do not publish app, PostgreSQL or Redis ports."
- **Assumption:** Nothing outside this Docker host needs direct PostgreSQL/Redis access;
  all legitimate access goes through the application, which goes through NGINX.
- **Chosen approach:** Removed the `ports:` mappings from `postgres` and `redis` entirely
  in `docker-compose.yml`. Only `nginx` retains a `ports:` entry.
- **Alternatives considered:** Keeping loopback-only bindings (`127.0.0.1:...`) on the
  grounds that they're not reachable from outside the host anyway. Rejected — the
  requirement is explicit and unconditional, and loopback-only still fails a literal
  "prohibited host ports" check (which `validate.py` implements).
- **Trade-off:** Local debugging via `psql -h 127.0.0.1 -p 15432` (a workflow used during
  early investigation) is no longer available; debugging PostgreSQL/Redis now requires
  `docker compose exec postgres psql ...` instead.
- **Limitation:** In a real multi-host production deployment, database access for
  operational tooling (backup agents, monitoring) would need a separate, access-controlled
  path — not addressed here since this is a single-host Compose lab.
- **Evidence:** `troubleshooting.md` INC-005; `validate.py`'s `check_compose_ports()` and
  `check_runtime_ports()`.

## Decision 2 — Frontend/backend network separation, backend marked `internal: true`

- **Context/problem:** The starter placed `nginx` on both `frontend` and `backend`
  networks, meaning NGINX could resolve and directly reach `postgres`/`redis` by service
  name even though it has no legitimate reason to.
- **Assumption:** NGINX's only job is reverse-proxying to `app-01`/`app-02`; it never
  needs to talk to the database or cache directly.
- **Chosen approach:** `nginx` is attached to `frontend` only. `app-01`/`app-02` bridge
  both networks (they need `frontend` to receive traffic from NGINX and `backend` to reach
  PostgreSQL/Redis). `postgres`/`redis` are `backend`-only. `backend` is declared
  `internal: true`, meaning Docker gives it no default route out of the network at all.
- **Alternatives considered:** Relying on `internal: true` alone without also removing
  NGINX from the network — rejected, since a container attached to an internal network can
  still reach other containers *on that same network*; `internal: true` restricts egress
  to the outside world, it does not by itself prevent one attached container from reaching
  another attached container. Membership itself has to be correct.
- **Trade-off:** None significant — this is strictly additive isolation with no
  functional cost to the application.
- **Limitation:** `internal: true` is a Docker-network-level control, not a firewall rule
  with logging; a compromised `app-01`/`app-02` container (which does have backend
  access) is not restricted from reaching `postgres`/`redis` beyond what the app itself
  needs. Defense-in-depth (e.g. PostgreSQL `pg_hba.conf` restrictions) is not implemented
  here.
- **Evidence:** `troubleshooting.md` INC-005; `validate.py`'s
  `check_runtime_network_membership()` and `check_network_isolation()` (live `nc -z` probe
  from inside `nginx` against `postgres:5432`/`redis:6379`, expected to fail).

## Decision 3 — Service-name DNS instead of container IPs

- **Context/problem:** Container IPs are assigned by Docker at creation time and are not
  stable across recreation — hardcoding them anywhere would break on the next
  `docker compose up -d --force-recreate`.
- **Chosen approach:** All service-to-service communication (`app/server.py`'s
  `DATABASE_URL`/`REDIS_URL`, `nginx.conf`'s `upstream` block, every validation/test
  script) uses Compose service names (`postgres`, `redis`, `app-01`, `app-02`), resolved
  via Docker's embedded DNS.
- **Alternatives considered:** None seriously — IP-based addressing was never viable given
  Docker's IP-reassignment behavior; this is closer to a hard requirement than an open
  design choice, but is recorded because TASK.md asks for it explicitly and it is worth
  stating why it's non-negotiable.
- **Trade-off:** None.
- **Limitation:** N/A.
- **Evidence:** Direct inspection of `nginx.conf` (`upstream application_pool { server
  app-01:8080; server app-02:8080; }`) and `docker-compose.yml`'s `env_file`/environment
  blocks — no IP literal appears anywhere in application or infrastructure config.

## Decision 4 — PostgreSQL named volume, mounted at the real data directory

- **Context/problem:** The starter Compose file mounted the named `postgres-data` volume
  at `/var/lib/postgresql/backup` (an unused path) while the actual PostgreSQL data
  directory (`/var/lib/postgresql/data`) was on `tmpfs` — meaning the named volume existed
  but provided **zero real persistence**; all data was lost on every container recreation.
- **Assumption:** TASK.md's persistence and backup/restore requirements assume data
  genuinely survives container recreation, not just that a volume is declared.
- **Chosen approach:** Mount `postgres-data` at `/var/lib/postgresql/data` (the actual data
  directory Postgres uses) and remove the `tmpfs` mount entirely.
- **Alternatives considered:** Bind-mounting a host directory instead of a named volume —
  rejected in favor of a named volume for portability across host filesystems/permissions
  and easier `docker volume` lifecycle management.
- **Trade-off:** None functional; this is a straightforward bug fix, not a design
  trade-off — noted here because TASK.md explicitly asks for a documented persistence
  decision, and the "no persistence" starting state was itself worth recording as a
  deliberate finding, not silently patched over.
- **Limitation:** Single-node volume — no replication, no automatic failover if the
  Docker host's disk fails. Acceptable for a local lab; not production-grade.
- **Evidence:** `troubleshooting.md` INC-005 (before/after `docker inspect postgres
  --format '{{json .Mounts}}'` output); persistence proof in README §10; `validate.py`'s
  `check_storage_persistence()`.

## Decision 5 — Redis AOF persistence enabled

- **Context/problem:** The starter Redis configuration explicitly disabled all
  persistence (`--save "" --appendonly no`). `/counter` is a shared, cumulative value —
  losing it on every restart is a real (if low-stakes) behavior change a user of the API
  would notice.
- **Assumption:** For this assessment's `/counter` semantics (a simple, non-critical
  request counter), durability is a "nice to have," not a strict requirement — but TASK.md
  explicitly asks for a *documented* Redis persistence decision either way, so leaving it
  disabled silently was not acceptable even if that had been the final choice.
- **Chosen approach:** Enabled AOF (`--appendonly yes`) with its own named volume
  (`redis-data:/data`), so `/counter` survives container recreation the same way
  PostgreSQL records do.
- **Alternatives considered:** (a) Leave persistence off, since the counter is disposable
  and low-value — rejected because it produces a visibly regressive user experience for no
  real performance gain at this scale. (b) RDB snapshotting instead of AOF — rejected in
  favor of AOF because AOF's continuous append gives a smaller data-loss window than
  periodic RDB snapshots, and the performance cost is negligible at this traffic volume.
- **Trade-off:** AOF has a small, continuous write-amplification cost versus no
  persistence at all — irrelevant at this scale but would need revisiting under
  significantly higher throughput.
- **Limitation:** Single-node Redis; no replica, no Sentinel/Cluster. A crash between an
  AOF `fsync` and acknowledgment can still lose the most recent write(s) — AOF reduces but
  does not eliminate the data-loss window.
- **Evidence:** `docker-compose.yml`'s `redis:` `command:` and `volumes:`; `validate.py`'s
  live check via `redis-cli CONFIG GET appendonly` (checked against the running container,
  not just the declared config, since the two can drift).

## Decision 6 — NGINX upstream failover policy (and its double-counting trade-off)

- **Context/problem:** The starter `nginx.conf` set `proxy_next_upstream off;` with
  `max_fails=0` on both upstream servers — meaning NGINX would never automatically retry a
  failed request against the healthy backend, and would never mark a backend as
  temporarily unavailable. This directly undermines the "prove the recovered backend
  serves requests" / general availability goal of Part 3's failure test.
- **Assumption:** Automatic retry improves availability during a single-backend outage,
  but for POST /records specifically, a retry after the original backend already committed
  the write (but failed to respond) could cause a duplicate insert. This risk needed to be
  weighed explicitly, not assumed away.
- **Chosen approach:** Enabled retries with `proxy_next_upstream error timeout http_502
  http_503 http_504;` and `proxy_next_upstream_tries 2;`, plus `max_fails=2
  fail_timeout=5s` on each upstream server so NGINX temporarily stops routing to a backend
  after repeated failures rather than retrying it every single request.
- **Alternatives considered:** Leaving retries off (the starter state) to eliminate the
  double-write risk entirely — rejected because it fails the availability requirement
  outright (a stopped backend simply returns errors to every request routed to it, with no
  attempt to serve from the healthy one). Retrying only idempotent GET requests via
  per-location config — considered as a more surgical alternative, not implemented in this
  pass because it adds configuration complexity for a risk that is now actively monitored
  instead (see below), not eliminated by config alone.
- **Trade-off (the one explicitly accepted, not hidden):** A backend that accepts a POST
  connection, performs the `INSERT`, and then fails before sending its HTTP response
  creates a narrow window where NGINX could retry the same POST against the surviving
  backend, producing a duplicate record. This is a real, non-zero risk, not a theoretical
  one.
- **How the risk is actively verified, not just accepted on faith:** `failure_test.py`
  sends uniquely-titled `POST /records` requests before, during, and after a real backend
  outage, then checks that each title appears in `GET /records` **exactly once** —
  directly testing for the duplicate-write failure mode this decision introduces, rather
  than assuming the trade-off is safe.
- **Limitation:** The duplicate check is a sampling check (one POST per phase), not an
  exhaustive proof that duplication can never occur under all possible failure timings. A
  production system handling this class of risk would typically use an idempotency key on
  the endpoint itself rather than relying on proxy-level retry tuning.
- **Evidence:** `nginx.conf` diff (available in git history); `failure_test.py`'s
  duplicate-record check section and its real run output.

## Decision 7 — Non-root application execution

- **Context/problem:** The starter Dockerfile created a dedicated non-root `app` user
  (`useradd --uid 10001 ...`), copied application files with correct ownership, and then
  immediately undid all of it with `USER root` right before `CMD` — the container actually
  ran as root despite the setup work being present.
- **Chosen approach:** Removed the `USER root` line; the container now runs as the `app`
  user for its entire lifetime.
- **Alternatives considered:** None — running as root with no operational benefit and a
  clear TASK.md requirement against it ("Avoid root/privileged operation where practical")
  is not a defensible choice for this workload, which needs no privileged operation at any
  point (binding to port 8080, a non-privileged port, requires no elevated capability).
- **Trade-off:** None meaningful for this workload.
- **Limitation:** Non-root execution reduces but does not eliminate container-breakout
  risk; it is one layer of defense-in-depth, not a complete mitigation on its own (no
  seccomp/AppArmor profile customization, no read-only root filesystem configured here).
- **Evidence:** `Dockerfile` diff; `validate.py`'s `check_non_root_user()`, which
  independently confirms `docker inspect --format '{{.Config.User}}'` for both app
  containers reports a non-root, non-empty user at runtime, not just at build time.

## Decision 8 — Secrets kept out of git, image layers, and application logs

- **Context/problem:** Three separate secret-handling failures were found: (a) the
  starter's `config/app.env` (containing the PostgreSQL credential in plaintext) was
  tracked in git history; (b) the Dockerfile `COPY`'d that same file directly into the
  built image, baking the credential into an image layer; (c) the application logged
  the full `DATABASE_URL`/`REDIS_URL` — credentials included — on every process start.
  The previously exposed PostgreSQL credential was therefore treated as compromised.

- **Chosen approach:** (a) `config/app.env` removed from the current tracked tree and
  added to `.gitignore`; (b) the Dockerfile no longer copies the secret file into the
  image; (c) runtime configuration flows through a git-ignored `.env` file consumed via
  Compose's `env_file:` directive, with `POSTGRES_PASSWORD` required through
  `${VAR:?...}` so the stack fails fast rather than silently starting with a
  missing/empty credential; (d) `app/server.py` uses `_safe_connection_metadata()` to
  log only non-secret connection metadata; (e) the previously exposed PostgreSQL
  credential was rotated in-place and the replacement credential was deployed to the
  application containers; (f) `.env` permissions were tightened from `0644` to
  owner-only `0600`.

- **Alternatives considered:** A dedicated secrets manager such as Vault, cloud KMS,
  or platform-native secrets is preferable for production. It was not introduced as
  an additional infrastructure dependency in this local Compose assessment. The
  production follow-up is explicitly documented in `security_review.md`.

- **Trade-off:** `.env`-based configuration is not encrypted at rest on the local
  filesystem. This is acceptable for the disposable lab's synthetic credentials but
  is not an appropriate production secret-management control.

- **Limitation:** The historical credential remains recoverable from older git
  commits because repository history is not rewritten under the project's working
  agreement. That credential is treated as permanently compromised and superseded
  by the rotated credential. The old credential was not replay-tested after rotation
  because doing so would require recovering or redisclosing a compromised secret.

- **Verification:** `git ls-files -- config/app.env .env` confirms no secret runtime
  file is tracked; `git check-ignore -v .env config/app.env` confirms both paths are
  ignored; `.env` reports permissions `600`; non-disclosing configuration checks
  confirm the PostgreSQL credential is consistent between `POSTGRES_PASSWORD` and
  `DATABASE_URL`; the recreated application containers are healthy; `/ready` and
  `/records`
  return HTTP 200; fresh application logs contain no credential patterns; and
  `./validate.py` completes with `VALIDATION PASSED: all checks succeeded`.

- **Evidence:** `troubleshooting.md` INC-004, INC-005, and INC-006; `security_review.md`
  findings on secret exposure and credential rotation; `.gitignore`; Dockerfile;
  Compose configuration; and the successful post-rotation validation run.

---

## Summary table

| # | Decision | Category |
|---|---|---|
| 1 | NGINX as sole public entrypoint | Networking / ports |
| 2 | Frontend/backend separation, `internal: true` backend | Networking / isolation |
| 3 | Service-name DNS, never container IPs | Networking |
| 4 | PostgreSQL named volume at the real data directory | Persistence |
| 5 | Redis AOF persistence enabled | Persistence |
| 6 | NGINX retry/failover policy + duplicate-write monitoring | Timeouts/retries |
| 7 | Non-root application execution | Container security |
| 8 | Secrets removed from git, image, and logs | Secrets |
