# Evidence and Submission Index

This document maps assessment requirements to repository evidence, verification
outputs, commits, and corresponding video timestamps. Existing pre-video evidence
is recorded now. Any item that depends on the final video or final submission is
Final-video timestamps are recorded in the Video Evidence section; final commit and matching CI remain pending until the submission commit and CI run exist.

## Submission metadata

| Item | Evidence |
|---|---|
| Repository URL | https://github.com/Tasnim-95/barq-devops-internship-task |
| Final commit | TBD — final documentation/finalization commit |
| Matching CI run | TBD — final pushed commit CI run |
| Continuous 12-18 minute video URL | https://drive.google.com/file/d/1nDzShXRaJ0TXTtpxOu-herPSFV4pZ7rR/view?usp=sharing |
| Challenge receipt ID | `5c8459309deb40ad9c9259b6c6fae5af` |
| Starting video commit | `cf8029fc0e195ff7fe04a080a05dad0b4db022c4` |
| Later documentation-only commits | Documentation/finalization commit to be added after this update |

## Evidence mapping

| Requirement | Evidence / verification | Commit | Video timestamp |
|---|---|---|---|
| Baseline preserved and progressive history | `git log --oneline --decorate`; investigation/fix/verification commits | `c43dccd`, `0208e67`, `71bd8bc`, `4f46baa`, `5485bd7`, `c5a434b` | N/A — repository evidence |
| Application ingress through NGINX | `docker-compose.yml`, `nginx/nginx.conf`, `./validate.py` | `c43dccd`, `5485bd7` | N/A — repository evidence |
| Two Flask instances (pre-video baseline) | `docker-compose.yml`, `app/server.py`, `/instance` validation | `71bd8bc`, `5485bd7` | N/A — repository evidence |
| Distinct instance identity (pre-video baseline) | Repeated `/instance` requests discover `app-01` and `app-02` | `71bd8bc`, `5485bd7` | N/A — repository evidence |
| Only NGINX publicly exposed | Compose port inspection and validation output | `4f46baa`, `5485bd7` | N/A — repository evidence |
| Frontend/backend network separation | Compose networks and runtime network checks | `4f46baa`, `5485bd7` | N/A — repository evidence |
| Backend network is internal | `backend: internal: true` plus validation | `4f46baa`, `5485bd7` | N/A — repository evidence |
| NGINX cannot directly reach PostgreSQL/Redis | Runtime TCP isolation checks | `4f46baa`, `5485bd7` | N/A — repository evidence |
| Service-name based communication | `nginx/nginx.conf`, `DATABASE_URL`, `REDIS_URL` | `5485bd7` | N/A — repository evidence |
| PostgreSQL named persistence | `postgres-data` volume and persistence test | `4f46baa`, `5485bd7` | N/A — repository evidence |
| Redis persistence | Named `redis-data` volume and AOF configuration | `5485bd7` | N/A — repository evidence |
| Health/liveness endpoint | `/health` returns HTTP 200 without dependency checks | `5485bd7` | N/A — repository evidence |
| Dependency readiness | `/ready` returns 200 when dependencies work and 503 during dependency failure | `5485bd7` | N/A — repository evidence |
| API records backed by real PostgreSQL | POST/GET `/records` validation | `5485bd7` | N/A — repository evidence |
| Shared atomic counter | `/counter` increments through Redis | `5485bd7` | N/A — repository evidence |
| Request IDs | Required endpoints return `X-Request-ID` | `5485bd7` | N/A — repository evidence |
| Input validation | Invalid titles return HTTP 400 | `5485bd7` | N/A — repository evidence |
| Unknown route handling | Unknown routes return HTTP 404 | `5485bd7` | N/A — repository evidence |
| Dependency failure handling | Redis pause test: `/health` stays 200, `/ready` becomes 503, recovery succeeds | `5485bd7` | N/A — repository evidence |
| Backend failure/recovery | `failure_test.py`: traffic continues while one backend is stopped and both recover | `5485bd7` | N/A — repository evidence |
| No duplicate records during failure test | Failure test verifies baseline/outage/recovery titles exactly once | `5485bd7` | N/A — repository evidence |
| Persistence after application/database recreation | `Video persistence proof` survives PostgreSQL and application recreation | `5485bd7` | N/A — repository evidence |
| Backup creation | `backup.sh` creates PostgreSQL custom-format backup and checksum | `5485bd7` | N/A — repository evidence |
| Backup integrity | TOC/checksum verification | `5485bd7` | N/A — repository evidence |
| Restore verification | `restore.sh` restores data and verifies the `records` table | `5485bd7` | N/A — repository evidence |
| Validation script | `./validate.py` returns `VALIDATION PASSED: all checks succeeded` | `5485bd7` | N/A — repository evidence |
| Validation fails on failed checks | `validate.py` contains non-zero failure behavior and explicit checks | `5485bd7` | N/A — repository evidence |
| CI on push and pull request | `.github/workflows/ci.yml` | `5485bd7` | N/A — repository evidence |
| Successful CI evidence | GitHub Actions CI run for pushed hardening commit | `5485bd7` | N/A — repository evidence |
| Non-root application | Dockerfile dedicated `app` user + runtime validation | `5485bd7` | N/A — repository evidence |
| Resource limits | Compose CPU/memory limits + validation | `5485bd7` | N/A — repository evidence |
| Infrastructure image pinning | Immutable SHA-256 image digests | `5485bd7` | N/A — repository evidence |
| Secrets excluded from current tree | `.gitignore`, `git ls-files`, `.env.example` | `5485bd7` | N/A — repository evidence |
| Secret not copied into image | Dockerfile inspection and image verification | `5485bd7` | N/A — repository evidence |
| Credentials excluded from application logs | `_safe_connection_metadata()` + log checks | `3af6315`, `cc3bb82`, `5485bd7` | N/A — repository evidence |
| Compromised PostgreSQL credential rotated | Runtime rotation, readiness, records, log and validation checks | Runtime action; documentation in working tree | N/A — repository evidence |
| Runtime secret permissions | `.env` permissions verified as `0600` | `5485bd7` | N/A — repository evidence |
| Historical secret limitation documented | `security_review.md`, `decisions.md`, `troubleshooting.md` | `5485bd7` | N/A — repository evidence |
| Historical logs analyzed without modification | `log_analysis.md` and original evidence files | `c5a434b` | N/A — repository evidence |
| Troubleshooting journal | `troubleshooting.md` incident and verification entries | `44625cb`, `5485bd7` | N/A — repository evidence |
| Engineering decisions | `decisions.md` — 8 decisions | `5485bd7` | N/A — repository evidence |
| Security review | `security_review.md` — 14 concrete findings | `5485bd7` | N/A — repository evidence |
| AI disclosure | `AI_USAGE.md` — 6 documented AI-use entries with independent verification | Working tree | N/A before video |
| README operational instructions | `README.md` — pre-video baseline and copyable operational commands | Working tree | N/A before video |
| Architecture diagram | `architecture.png` — final submitted state: 3 app instances / public port 8090 | Working tree / final submission | N/A |
| Evidence index | `docs/EVIDENCE_INDEX.md` — final submission evidence map with verified video timestamps | Final documentation commit | N/A |

## Video Evidence

| Video requirement | Timestamp |
|---|---:|
| Starting repository, starting commit, clean status | 00:20 |
| Build/start stopped environment and service health | 00:35 |
| Health/readiness and required endpoint smoke tests | 01:00 |
| Repeated `/instance` requests prove both initial backends | 01:35 |
| Stop one backend and show continued traffic | 01:48 |
| Recover stopped backend and prove recovery | 02:00–02:48 |
| Run `failure_test.py` and show successful result | 03:00 |
| Create record, recreate PostgreSQL/application containers, and prove persistence | 04:30–06:40 |
| Run `validate.py` successfully | 06:40 |
| Show historical log finding — Incident B / Redis dependency timeout | 07:00 |
| Run `./video_challenge.sh` once and show challenge receipt | 07:36 |
| Diagnose challenge fault, fix it, and recover service | 07:36–08:20 |
| Prove recovered health/readiness after challenge | 08:20 |
| Change public port from 8080 to 8090 and prove old port fails/new port works | 08:40 |
| Add third application instance (`app-03`) live | 12:50 |
| Prove all three application instances serve traffic | 15:10 |
| Rerun validation and create final record on 8090 | 15:10–15:50 |
| Review diff, commit final live changes, and show commit hash | 15:50 |
| Push video commits to GitHub | 15:50–end |

## Final consistency checklist

Before submission, confirm that:

- The README describes the same final state demonstrated in the video.
- The architecture diagram describes the same final state demonstrated in the video.
- GitHub contains the same final code and documentation referenced here.
- The final Compose state has three application instances and public port `8090`.
- The final validation run passes.
- The final CI run corresponds to the submitted final commit.
- Every video timestamp in this index points to real recorded evidence.
- The challenge receipt ID is copied exactly from the actual challenge run.
- No credentials, access tokens, or other secrets are included in this index.

Final live-state evidence:
- Live Part 5 transition: 2 application instances/8080 to 3 application instances/8090, committed in `f910333a8f30777da4fb39c8eceee8b2af627c88`.
- Final validation: `PUBLIC_PORT=8090 ./validate.py` returned `VALIDATION PASSED: all checks succeeded` with app-01, app-02, and app-03 healthy and serving traffic.
- Challenge receipt: `5c8459309deb40ad9c9259b6c6fae5af`.
- Video timestamps above were verified against the recorded video timeline.
