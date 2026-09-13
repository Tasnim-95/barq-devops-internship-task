# AI Usage Disclosure

AI assistance was used during this assessment as a technical support and review aid.
The implementation, command execution, troubleshooting, verification, and final
engineering decisions were reviewed and validated against the actual repository
and running Docker Compose environment.

## 1. Troubleshooting and root-cause analysis

- **Tool/model:** ChatGPT (OpenAI)
- **Purpose:** Assist with investigating application ingress, healthcheck, port,
  PostgreSQL, Redis, and application-instance configuration problems.
- **Files or decisions affected:** `app/server.py`, `docker-compose.yml`,
  `nginx/nginx.conf`, `config/app.env`, `troubleshooting.md`.
- **What was changed or rejected:** Used AI suggestions to structure hypotheses,
  diagnostic commands, root-cause explanations, and verification steps. Changes
  were applied only after inspecting the actual command output and repository
  state. Proposed approaches were rejected or adjusted when they did not match
  the observed runtime behavior.
- **How independently verified:** Docker Compose services were started and
  inspected directly; `curl`, Docker health status, service logs, connectivity
  checks, and the validation scripts were executed against the running stack.
- **Related commits:** `c43dccd`, `0208e67`, `71bd8bc`,
  `44625cb`.

## 2. Application and security hardening

- **Tool/model:** ChatGPT (OpenAI)
- **Purpose:** Review application behavior and identify security weaknesses,
  especially credential disclosure, dependency readiness, network exposure,
  and least-privilege execution.
- **Files or decisions affected:** `app/server.py`, `Dockerfile`,
  `docker-compose.yml`, `.gitignore`, `.env.example`, `decisions.md`,
  `security_review.md`, `troubleshooting.md`.
- **What was changed or rejected:** Applied changes to stop credentials from
  appearing in application logs, remove the tracked secret configuration from
  the current tree, prevent the secret file from being copied into the image,
  isolate backend services, run the application as a non-root user, add resource
  limits, and use explicit readiness behavior. Production-only controls such as
  a dedicated external secrets manager were documented as follow-up rather than
  added as unnecessary assessment infrastructure.
- **How independently verified:** Inspected the resulting source and Compose
  configuration, checked Git tracking/ignore behavior, inspected container
  runtime configuration, tested application logs for credential patterns,
  checked container users and resource limits, and ran `./validate.py`.
- **Related commits:** `3af6315`, `cc3bb82`, `4f46baa`,
  `5485bd7`.

## 3. Credential exposure response and rotation

- **Tool/model:** ChatGPT (OpenAI)
- **Purpose:** Assist with the response to a previously exposed PostgreSQL
  credential and define a safe rotation and verification procedure.
- **Files or decisions affected:** local `.env`, `decisions.md`,
  `security_review.md`, `troubleshooting.md`.
- **What was changed or rejected:** The previously exposed PostgreSQL
  credential was treated as compromised. A replacement credential was
  generated and the PostgreSQL role was rotated in-place. Runtime
  configuration was updated and `.env` permissions were tightened to `0600`.
  The old credential was deliberately not replay-tested because doing so would
  require recovering or redisclosing a compromised secret.
- **How independently verified:** The replacement credential was checked
  without printing its value, application containers were recreated and became
  healthy, `/ready` and `/records` returned successfully, existing data
  remained available, application logs contained no credential patterns, and
  `./validate.py` completed successfully.
- **Related commits:** Documentation is associated with the current hardening
  work in `5485bd7`; the credential rotation itself was performed as a local
  runtime security action and should not be represented as a separate commit
  unless explicitly committed in the repository history.

## 4. Historical log analysis

- **Tool/model:** ChatGPT (OpenAI)
- **Purpose:** Assist with organizing analysis of the three supplied historical
  training logs, correlating events, identifying incident timelines, and
  improving the reproducibility of the analysis.
- **Files or decisions affected:** `log_analysis.md`.
- **What was changed or rejected:** AI suggestions were used to structure the
  investigation around timestamps, request/error correlation, hypotheses,
  commands, counts, and conclusions. The original log files were treated as
  immutable evidence and were not modified.
- **How independently verified:** Analysis commands and results were checked
  against the supplied logs using Bash/Python-based inspection, and the final
  document was reviewed for reproducible commands, explicit counts, timelines,
  and conclusions.
- **Related commit:** `c5a434b`.

## 5. Validation, failure testing, and operational evidence

- **Tool/model:** ChatGPT (OpenAI)
- **Purpose:** Assist with designing comprehensive validation and failure/recovery
  checks for the required Docker Compose architecture.
- **Files or decisions affected:** `validate.py`, `failure_test.py`,
  `backup.sh`, `restore.sh`, `.github/workflows/ci.yml`,
  `troubleshooting.md`.
- **What was changed or rejected:** AI-assisted test ideas were used to cover
  health/readiness, API behavior, dependency failure, backend failover,
  persistence, backup/restore, networking, ports, resource limits, and
  non-root execution. Test behavior was adjusted when actual runtime timing
  showed that the initial readiness timeout was too short.
- **How independently verified:** Scripts were executed against the actual
  Docker Compose environment. Validation passed, the failure test maintained
  traffic while one backend was stopped, backup/restore integrity was verified,
  and the GitHub Actions CI run completed successfully.
- **Related commit:** `5485bd7`.

## 6. Documentation and engineering review

- **Tool/model:** ChatGPT (OpenAI)
- **Purpose:** Assist with reviewing and improving assessment documentation for
  completeness, clarity, traceability, and alignment with the stated
  requirements.
- **Files or decisions affected:** `README.md`, `decisions.md`,
  `security_review.md`, `troubleshooting.md`, `AI_USAGE.md`.
- **What was changed or rejected:** AI-generated wording was reviewed and
  adapted to reflect the actual implementation and evidence. Claims that could
  not be independently verified were not presented as completed work. Known
  limitations and production follow-ups were retained where appropriate.
- **How independently verified:** Documentation was checked against repository
  files, commit history, runtime test results, and generated evidence. Markdown
  whitespace checks were also performed with `git diff --check`.
- **Related commits:** `5485bd7`, `c5a434b`, with earlier
  troubleshooting/security changes linked in the relevant documents.

## Independent verification statement

AI assistance did not replace execution or verification of the assessment.
Commands, Docker Compose behavior, application responses, logs, persistence,
failure recovery, backup/restore, validation, and CI results were checked
against the actual repository and runtime environment.

Where an AI suggestion conflicted with observed behavior, the observed runtime
result was treated as authoritative and the implementation or documentation
was adjusted accordingly.

No credentials or access tokens are intentionally recorded in this document.
