# BARQ Systems DevOps Internship Assessment — Submission README

Flask API backed by real PostgreSQL and Redis, deployed behind NGINX with Docker Compose.
This document is the operational entry point for the submission: commands below are
designed to be copy-paste runnable from the repository root, with explicitly marked
placeholders where a generated artifact such as a backup filename is required.
It also directly answers the assessment's required questions (see
**Design Rationale & Required Questions** near the end).

**Authoritative sources:** `assessment/TASK.md` (requirements),
`assessment/APPLICATION.md` (endpoint contract).
**Evidence sources for every claim below:** `troubleshooting.md`
(investigation journal), `log_analysis.md` (historical log analysis),
`decisions.md`, `security_review.md`,
`docs/EVIDENCE_INDEX.md` (requirement → file/output → commit →
video timestamp).

---

## State disclosure (read this first)

This README documents the **pre-video baseline state**: 2 application instances
(`app-01`, `app-02`), public port **8080**. TASK.md's Part 5 video requires a **live**
transition to 3 instances (`app-01`/`app-02`/`app-03`) and public port **8090**, performed
once, on camera, without `docker compose down`. Where that matters, it's called out
explicitly below rather than papered over. The final submission's README, architecture
diagram, and evidence index will be updated to reflect the post-video three-instance/8090
state — see `docs/EVIDENCE_INDEX.md` for which state each artifact currently describes.

---

## Architecture

```
                         Client
                           │
                           ▼
                ┌─────────────────────┐
                │  NGINX (nginx)       │  ← only container publishing a host port
                │  host 127.0.0.1:8080│     (127.0.0.1:${PUBLIC_PORT:-8080} -> 80)
                └──────────┬───────────┘
                     frontend network
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
      ┌─────────────┐             ┌─────────────┐
      │   app-01     │             │   app-02     │   Flask, non-root, resource-limited,
      │ (frontend +  │             │ (frontend +  │   restart: unless-stopped
      │  backend)    │             │  backend)    │
      └──────┬───────┘             └──────┬───────┘
             │          backend network (internal: true)         │
             └───────────────┬───────────────────────┬───────────┘
                              ▼                       ▼
                     ┌─────────────┐         ┌─────────────┐
                     │  postgres    │         │   redis      │
                     │  named vol   │         │  named vol   │
                     │  no host port│         │  AOF enabled │
                     │  backend only│         │  backend only│
                     └─────────────┘         └─────────────┘
```

NGINX is deliberately **not** attached to `backend` — it can only reach `app-01`/`app-02`
via `frontend`, and has no network path to PostgreSQL or Redis at all. This is verified
live, not just declared: `validate.py` runs `docker exec nginx nc -z postgres 5432` and
`... redis 6379` and asserts both **fail**.

A rendered architecture diagram (`architecture.png`) is tracked at the repository root.
The current diagram documents the pre-video baseline (2 application instances on public
port 8080). It will be updated after the live Part 5 transition to the final
three-instance/8090 state. See `docs/EVIDENCE_INDEX.md` for the corresponding evidence
and commit.

---

## Prerequisites

- Linux or WSL2
- Docker Engine + Compose v2 (`docker compose version`)
- `curl`, `jq`, `python3` (3.9+) — used by the verification commands in this document
- No cloud account, no paid registry — all images are public and digest-pinned

## Repository layout

```
app/server.py              Flask application: endpoints, dependency logic, safe logging
database/init.sql          PostgreSQL schema, applied only on a fresh (empty) volume
nginx/nginx.conf            NGINX reverse-proxy config (upstream, retry policy, logging)
docker-compose.yml           Service topology, networks, volumes, resource limits
Dockerfile                   Application image: non-root user, digest-pinned base image
.env.example                 Safe placeholder env file — copy to .env, never commit .env
validate.py                   Bounded PASS/FAIL environment validator (see below)
failure_test.py               Backend failure/recovery test with duplicate-record check
backup.sh / restore.sh        PostgreSQL backup/restore with integrity verification
.github/workflows/ci.yml     CI: syntax -> compose validate -> build -> start -> validate
troubleshooting.md             Investigation journal: INC-001..INC-006 + verification
log_analysis.md                 Analysis of the three supplied historical logs
decisions.md                     >=5 engineering decisions, trade-offs, alternatives
security_review.md               >=8 concrete risks, implemented vs. production follow-up
AI_USAGE.md                       AI assistance disclosure
docs/EVIDENCE_INDEX.md            Requirement -> evidence -> commit -> video timestamp
```

---

## 1. Secret setup

The original starter configuration baked a PostgreSQL credential into a git-tracked file
(`config/app.env`) that was also `COPY`'d into the Docker image. Both are confirmed fixed —
see `troubleshooting.md` INC-004/INC-005 and `security_review.md` — and the current design
reads configuration from a git-ignored `.env` file instead:

```bash
cp .env.example .env
# Edit .env: replace every CHANGE_ME with your own local, disposable value.
# This is a local lab environment — never put a real credential here.
```

Verify `.env` cannot be accidentally committed:

```bash
git check-ignore -v .env          # expect: a match against .gitignore
git ls-files | grep -E '^\.env$'  # expect: no output
```

## 2. Build

```bash
docker compose -p barq-assessment build
```

## 3. Start

```bash
docker compose -p barq-assessment up -d
docker compose -p barq-assessment ps -a
```

Expected: all five containers (`app-01`, `app-02`, `postgres`, `redis`, `nginx`) reach
`Up ... (healthy)` within roughly 30–60 seconds (dependency-aware startup — apps wait for
`postgres`/`redis` to report `service_healthy` before starting; NGINX waits for both apps).

## 4. Health and readiness

```bash
curl -i http://127.0.0.1:8080/health   # 200 — liveness only, no dependency check
curl -i http://127.0.0.1:8080/ready    # 200 only if PostgreSQL AND Redis respond; else 503
```

## 5. Endpoint tests (copyable)

```bash
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/instance
curl -H 'Content-Type: application/json' -d '{"title":"Persistence proof"}' http://127.0.0.1:8080/records
curl -i http://127.0.0.1:8080/records
curl -i http://127.0.0.1:8080/counter

# invalid input -> 400
curl -i -H 'Content-Type: application/json' -d '{"title":""}' http://127.0.0.1:8080/records
# unknown route -> 404
curl -i http://127.0.0.1:8080/does-not-exist
```

Every response carries `X-Request-ID`. `/instance` additionally carries `X-Instance-ID`.
Prove both backends serve traffic through NGINX:

```bash
for i in $(seq 1 8); do
  curl -s http://127.0.0.1:8080/instance | python3 -c "import sys,json; print(json.load(sys.stdin)['instance_id'])"
done
```

## 6. Validation

```bash
./validate.py
```

Bounded (60s max wait), explicit `PASS`/`FAIL` per check, **non-zero exit on any failure**.
Covers: every required endpoint and status code; request IDs; instance identity and
distribution across all discovered backends; PostgreSQL/Redis readiness including a **live**
dependency-failure test (pauses Redis via `docker pause`, confirms `/health` stays `200`
while `/ready` correctly drops to `503`, unpauses, confirms recovery); published-port and
runtime network-membership checks against the exact required topology; named-volume and
persistence configuration (Postgres data-dir mount, Redis AOF checked live via
`redis-cli CONFIG GET appendonly`, not just read from the compose file); restart policies;
resource limits; non-root execution; digest-pinned images. **Application instances and the
public port are discovered from the running environment, not hardcoded** — the same script
runs unmodified against the 2-instance/8080 state or the 3-instance/8090 final video state.

## 7. Failure / recovery test

```bash
./failure_test.py
```

Discovers all `app-0N` containers, stops the lowest-numbered one, sends a bounded traffic
sample while it's down, proves the remaining instance(s) keep serving (attributing every
response to the actual instance that served it via `X-Instance-ID`, not just measuring raw
availability), restores the stopped backend, proves it recovers and serves again, and
sends unique-titled `POST /records` before/during/after the outage to confirm **no record is
duplicated by an NGINX upstream retry** — directly testing the double-counting risk that
`nginx.conf`'s `proxy_next_upstream` retry policy introduces (see `decisions.md`). Never runs
`docker compose down`; always attempts to restart the stopped backend, even if an assertion
fails mid-test.

## 8. Backup

```bash
./backup.sh
```

Verifies the target container is genuinely the Compose project's `postgres` service (both
project and service labels checked, not just container name), confirms it's healthy,
produces a timestamped `pg_dump -Fc` archive under `backups/`, verifies archive integrity
by copying it into the container and running `pg_restore --list` against it (not just
checking the file is non-empty), and writes a `.sha256` checksum alongside it.

## 9. Restore

```bash
./restore.sh backups/barq_tasks_<TIMESTAMP>.dump
```

Verifies the checksum if present, re-confirms PostgreSQL health, restores with
`pg_restore --clean --if-exists --no-owner`, then runs a **post-restore verification query**
against the `records` table and fails non-zero if that query doesn't succeed — restoring
without proving the result is queryable is not treated as success.

## 10. Persistence proof

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"title":"persistence-proof-'"$(date -u +%s)"'"}' \
  http://127.0.0.1:8080/records

docker compose -p barq-assessment up -d --force-recreate postgres app-01 app-02

docker compose -p barq-assessment ps -a   # wait for all to report healthy again
curl -s http://127.0.0.1:8080/records     # the record above must still be present
```

This never deletes the named `postgres-data` volume — recreation targets the containers
only. Volume-safe by construction: nothing in this repository's scripts runs
`docker compose down -v` during a persistence test.

## 11. Cleanup

```bash
docker compose -p barq-assessment down        # stops/removes containers, KEEPS volumes
docker compose -p barq-assessment down -v     # also deletes named volumes (destructive)
```

---

## Networking and ports (declared and verified at runtime)

| Service | Networks | Host port |
|---|---|---|
| `nginx` | `frontend` only | `127.0.0.1:${PUBLIC_PORT:-8080}` — the **only** published port in the whole stack |
| `app-01`, `app-02` | `frontend` + `backend` | none |
| `postgres` | `backend` only | none |
| `redis` | `backend` only | none |

`backend` is declared `internal: true` (no default route out of the network). Both the
Compose-declared topology **and** the live running topology are checked by `validate.py` —
declaring isolation correctly and actually running with it are treated as separate
questions, since they can silently drift apart (see `decisions.md`).

## CI

`.github/workflows/ci.yml` runs on every `push` and `pull_request`: checkout → Python/shell
syntax checks → `docker compose config` validation → image build → stack start with a
bounded readiness wait → `./validate.py` → diagnostics dump (`docker compose logs`) on
failure → cleanup. A disposable random PostgreSQL password is generated **inside the CI
run**; no credential is stored in the workflow file or the repository. CI run link and
result: see `docs/EVIDENCE_INDEX.md` (populated once a run against the final submission
commit exists — not fabricated here).

## Security notes

Full risk review: `security_review.md` (≥8 findings, implemented fixes separated from
production follow-up). Highlights:
- All credentials in this repository are synthetic and disposable, scoped to a local lab.
- A synthetic PostgreSQL password and a separately-issued GitLab access token were both
  transiently exposed during the documented investigation (`troubleshooting.md`).
  Both are treated as compromised and are not reused in the current configuration.
  The PostgreSQL credential was rotated; GitLab token revocation/rotation is not claimed
  as completed.
- No TLS — plaintext HTTP on loopback only, acceptable for this local assessment, flagged
  as a production gap.

## Known limitations / remaining single points of failure

- Single PostgreSQL instance, single Redis instance — no replication/failover for either.
- Local, unencrypted backup files under `backups/` — not a production backup strategy.
- No TLS termination; no external authentication/authorization layer.
- NGINX retry policy (`proxy_next_upstream error timeout http_502 http_503 http_504`,
  `proxy_next_upstream_tries 2`) trades some availability risk (a narrow window where a
  backend accepts a POST, then fails before responding) for failover — see `decisions.md`
  for the full trade-off and `failure_test.py`'s duplicate-record check for how this is
  actively monitored rather than left unverified.

Production remediation ideas for each of these are in `security_review.md`'s
"production follow-up" column — not implemented here, and not claimed to be.

---

## Design Rationale & Required Questions

*(Answering TASK.md's "Questions - answer in your README or reports" directly.)*

**What failed first? What proved the cause? Which failed attempt taught you something?**
The first thing to break, in investigation order, was application ingress: both `app-01`
and `app-02` reported `unhealthy`, and NGINX could not reach either. `docker exec nginx
wget ... /health` returning `Connection refused` proved the failure was network-level, not
application-level — the healthcheck's separate `/healthz` vs. `/health` mismatch was a
second, independent bug discovered at the same time and easy to conflate with the first;
distinguishing "unreachable" from "wrong healthcheck path" (two different root causes with
the same symptom) was the key lesson. Full command-by-command record: `troubleshooting.md`
INC-001.

**What patterns did the logs reveal? How did you avoid double-counting requests?**
See `log_analysis.md` in full. In short: four distinct incident windows (connection
failure, Redis timeout, PostgreSQL auth failure, response-timeout) were identifiable by
correlating `access.log`/`error.log`/`application.log` on `request_id`; 5 of 725 raw
`access.log` lines were exact duplicates at 5-minute log-rotation boundaries, so every
count in the analysis deduplicates by `request_id` before aggregating (720 distinct
requests, not 725 lines) — reproducible commands are in `log_analysis.md` Q1–Q3. The same
double-counting risk exists live in `failure_test.py`, addressed by sending uniquely-titled
records and verifying no title appears more than once in `GET /records` afterward.

**How do requests flow? Why these ports, networks and readiness checks?**
See the architecture diagram above. Port/network choices are documented individually in
`decisions.md` (NGINX as sole entrypoint; frontend/backend separation; `internal: true`
backend). `/health` vs `/ready` are split deliberately — `/health` must stay `200` during a
dependency outage (so Docker/orchestrators don't kill a process that's fine, just
temporarily unable to reach a dependency) while `/ready` must accurately reflect
dependency state (so traffic isn't routed to an instance that can't serve it) — this
distinction is directly tested by `validate.py`'s dependency-failure check.

**Why these timeouts, retries, restart settings and resource limits?**
Each is a separate, documented decision in `decisions.md`, including the specific trade-off
of enabling NGINX upstream retries (`decisions.md`, "NGINX failover policy") — retries
improve availability during a single-backend failure but introduce a narrow window for a
duplicate write on a POST, which is why `failure_test.py` explicitly checks for duplicates
rather than assuming the trade-off is safe.

**When should validation fail? What does green CI prove, or not prove?**
`validate.py` fails non-zero on *any* single check failing — there is no partial-pass
state. A green CI run proves: the image builds from a clean checkout, the declared Compose
topology renders and starts, and the full `validate.py` suite (config-level, runtime-level,
and functional/endpoint-level checks) passes in a fresh, disposable CI environment. It does
**not** prove: the failure-recovery behavior (`failure_test.py` is not part of CI's default
job), backup/restore integrity, or anything about the live video-challenge/port-change
workflow, none of which run in CI.

**Which single points of failure remain? How would you fix them in production?**
Listed above under "Known limitations," with production remediation direction in
`security_review.md`.

**What would you improve? How did you verify AI-assisted work?**
See `AI_USAGE.md` for the full, honest disclosure of what AI assistance was used, on which
files, and how every generated script/config was independently executed and its real
output reviewed before being accepted (not accepted on the basis of plausibility alone).

---

## Documentation index

- `troubleshooting.md` — investigation journal (INC-001..INC-006 + Verification-001)
- `log_analysis.md` — analysis of the three supplied historical logs
- `decisions.md` — engineering decisions, alternatives, trade-offs
- `security_review.md` — risk review
- `AI_USAGE.md` — AI assistance disclosure
- `docs/EVIDENCE_INDEX.md` — requirement → evidence → commit → video timestamp
- `architecture.png` — system diagram (current pre-video baseline; updated after the Part 5 live transition)
