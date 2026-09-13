# Evidence and Submission Index

This document maps assessment requirements to repository evidence, verification
outputs, commits, and corresponding video timestamps. Existing pre-video evidence
is recorded now. Any item that depends on the final video or final submission is
intentionally marked `TBD` until it is actually produced.

## Submission metadata

| Item | Evidence |
|---|---|
| Repository URL | TBD — fill from the final GitHub repository |
| Final commit | TBD — final commit after video-related changes |
| Matching CI run | TBD — final pushed commit CI run |
| Continuous 12-18 minute video URL | TBD |
| Challenge receipt ID | TBD — record the receipt shown by `./video_challenge.sh` |
| Starting video commit | TBD — commit checked out at the beginning of the video |
| Later documentation-only commits | TBD — list only if applicable |

## Evidence mapping

| Requirement | Evidence / verification | Commit | Video timestamp |
|---|---|---|---|
| Baseline preserved and progressive history | `git log --oneline --decorate`; investigation/fix/verification commits | `c43dccd`, `0208e67`, `71bd8bc`, `4f46baa`, `5485bd7`, `c5a434b` | TBD |
| Application ingress through NGINX | `docker-compose.yml`, `nginx/nginx.conf`, `./validate.py` | `c43dccd`, `5485bd7` | TBD |
| Two Flask instances | `docker-compose.yml`, `app/server.py`, `/instance` validation | `71bd8bc`, `5485bd7` | TBD |
| Distinct instance identity | Repeated `/instance` requests discover `app-01` and `app-02` | `71bd8bc`, `5485bd7` | TBD |
| Only NGINX publicly exposed | Compose port inspection and validation output | `4f46baa`, `5485bd7` | TBD |
| Frontend/backend network separation | Compose networks and runtime network checks | `4f46baa`, `5485bd7` | TBD |
| Backend network is internal | `backend: internal: true` plus validation | `4f46baa`, `5485bd7` | TBD |
| NGINX cannot directly reach PostgreSQL/Redis | Runtime TCP isolation checks | `4f46baa`, `5485bd7` | TBD |
| Service-name based communication | `nginx/nginx.conf`, `DATABASE_URL`, `REDIS_URL` | `5485bd7` | TBD |
| PostgreSQL named persistence | `postgres-data` volume and persistence test | `4f46baa`, `5485bd7` | TBD |
| Redis persistence | Named `redis-data` volume and AOF configuration | `5485bd7` | TBD |
| Health/liveness endpoint | `/health` returns HTTP 200 without dependency checks | `5485bd7` | TBD |
| Dependency readiness | `/ready` returns 200 when dependencies work and 503 during dependency failure | `5485bd7` | TBD |
| API records backed by real PostgreSQL | POST/GET `/records` validation | `5485bd7` | TBD |
| Shared atomic counter | `/counter` increments through Redis | `5485bd7` | TBD |
| Request IDs | Required endpoints return `X-Request-ID` | `5485bd7` | TBD |
| Input validation | Invalid titles return HTTP 400 | `5485bd7` | TBD |
| Unknown route handling | Unknown routes return HTTP 404 | `5485bd7` | TBD |
| Dependency failure handling | Redis pause test: `/health` stays 200, `/ready` becomes 503, recovery succeeds | `5485bd7` | TBD |
| Backend failure/recovery | `failure_test.py`: traffic continues while one backend is stopped and both recover | `5485bd7` | TBD |
| No duplicate records during failure test | Failure test verifies baseline/outage/recovery titles exactly once | `5485bd7` | TBD |
| Persistence after application/database recreation | `Video persistence proof` survives PostgreSQL and application recreation | `5485bd7` | TBD |
| Backup creation | `backup.sh` creates PostgreSQL custom-format backup and checksum | `5485bd7` | TBD |
| Backup integrity | TOC/checksum verification | `5485bd7` | TBD |
| Restore verification | `restore.sh` restores data and verifies the `records` table | `5485bd7` | TBD |
| Validation script | `./validate.py` returns `VALIDATION PASSED: all checks succeeded` | `5485bd7` | TBD |
| Validation fails on failed checks | `validate.py` contains non-zero failure behavior and explicit checks | `5485bd7` | TBD |
| CI on push and pull request | `.github/workflows/ci.yml` | `5485bd7` | TBD |
| Successful CI evidence | GitHub Actions CI run for pushed hardening commit | `5485bd7` | TBD |
| Non-root application | Dockerfile dedicated `app` user + runtime validation | `5485bd7` | TBD |
| Resource limits | Compose CPU/memory limits + validation | `5485bd7` | TBD |
| Infrastructure image pinning | Immutable SHA-256 image digests | `5485bd7` | TBD |
| Secrets excluded from current tree | `.gitignore`, `git ls-files`, `.env.example` | `5485bd7` | TBD |
| Secret not copied into image | Dockerfile inspection and image verification | `5485bd7` | TBD |
| Credentials excluded from application logs | `_safe_connection_metadata()` + log checks | `3af6315`, `cc3bb82`, `5485bd7` | TBD |
| Compromised PostgreSQL credential rotated | Runtime rotation, readiness, records, log and validation checks | Runtime action; documentation in working tree | TBD |
| Runtime secret permissions | `.env` permissions verified as `0600` | `5485bd7` | TBD |
| Historical secret limitation documented | `security_review.md`, `decisions.md`, `troubleshooting.md` | `5485bd7` | TBD |
| Historical logs analyzed without modification | `log_analysis.md` and original evidence files | `c5a434b` | TBD |
| Troubleshooting journal | `troubleshooting.md` incident and verification entries | `44625cb`, `5485bd7` | TBD |
| Engineering decisions | `decisions.md` — 8 decisions | `5485bd7` | TBD |
| Security review | `security_review.md` — 14 concrete findings | `5485bd7` | TBD |
| AI disclosure | `AI_USAGE.md` — 6 documented AI-use entries with independent verification | Working tree | N/A before video |
| README operational instructions | `README.md` — pre-video baseline and copyable operational commands | Working tree | N/A before video |
| Architecture diagram | `architecture.png` — pre-video baseline: 2 app instances / public port 8080 | Working tree | N/A before video |
| Evidence index | `docs/EVIDENCE_INDEX.md` — pre-video evidence map | Working tree | N/A before video |

## Video evidence requirements

The final video must be continuous and 12-18 minutes long. Timestamps below will
be populated after recording; they must reference the actual video rather than
being estimated in advance.

| Video requirement | Timestamp |
|---|---|
| Repository and starting video commit | TBD |
| Clean starting `git status` | TBD |
| Build/start stopped environment | TBD |
| Service health | TBD |
| Required endpoints | TBD |
| Repeated `/instance` requests | TBD |
| Stop one backend and demonstrate continued traffic | TBD |
| Recover stopped backend | TBD |
| Created record survives application/database recreation | TBD |
| First run of `./video_challenge.sh` | TBD |
| Diagnose and fix challenge runtime fault without `docker compose down` | TBD |
| Change public port 8080 → 8090 live | TBD |
| Add third application instance live | TBD |
| Prove all three instances | TBD |
| Rerun `./validate.py` | TBD |
| Final `git status`, diff and commit hashes | TBD |
| Push final video-related commits | TBD |

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
