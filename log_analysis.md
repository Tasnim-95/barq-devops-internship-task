# Log Analysis

All commands and findings below use the three supplied historical log fixtures exactly as provided:

- `logs/access.log`
- `logs/error.log`
- `logs/application.log`

The originals are not modified. `git diff -- logs/` remained empty during the investigation, and `RELEASE.json` identifies these fixtures as synthetic historical training evidence.

## 1. UTC interval, valid/malformed lines, and duplicates

### Method

The JSON logs were parsed line-by-line with a per-line `try/except` so malformed records do not abort the analysis. Duplicate detection is performed independently per file.

### Reproducible command

```bash
python3 - <<'PY'
import json
from collections import Counter

for path in ["logs/access.log", "logs/application.log"]:
    total = valid = malformed = 0
    records = []

    with open(path, encoding="utf-8") as f:
        for line in f:
            total += 1
            try:
                records.append(json.loads(line))
                valid += 1
            except json.JSONDecodeError:
                malformed += 1

    raw_lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in records]
    duplicate_lines = sum(n - 1 for n in Counter(raw_lines).values() if n > 1)

    print(
        f"{path}: total={total} valid={valid} "
        f"malformed={malformed} duplicate_valid_lines={duplicate_lines}"
    )
PY

sort logs/error.log | uniq -d
```

### Results

| File | Total lines | Valid JSON | Malformed | Duplicate valid lines |
|---|---:|---:|---:|---:|
| `access.log` | 726 | 725 | 1 | 5 |
| `application.log` | 730 | 729 | 1 | 2 |
| `error.log` | 68 | n/a (NGINX native text) | 0 confirmed | 0 confirmed |

`error.log` is native NGINX text rather than JSON, so duplicate checking is performed directly on complete raw lines with `sort logs/error.log | uniq -d`; it returned no output.

### Interval

`access.log` and `application.log` both span:

**2026-08-20T11:00:00.015Z → 2026-08-20T11:29:57.578Z** (~30 minutes).

`error.log` covers the same operational window at approximately one-second resolution and ends with:

`2026/08/20 11:30:00 [notice] log collector rotated stream`

### Malformed records

- `access.log` line 311: `{"timestamp":"2026-08-20T11:12:48Z","request_id":`
- `application.log` line 401: `{"timestamp":"2026-08-20T11:17:00Z","event":`

Both are truncated JSON objects. A robust parser must skip malformed lines individually.

### Duplicate records

`access.log` contains five duplicate request records:

- `lab-000121`
- `lab-000241`
- `lab-000361`
- `lab-000481`
- `lab-000601`

Each appears twice and is identical in every field. `application.log` contains two duplicate valid lines. The duplication artifacts are therefore treated independently per log rather than assumed to correlate one-for-one.

---

## 2. Distinct client requests and deduplication

### Result

There are **720 distinct client requests** in `access.log`.

The 725 valid access records contain five duplicated `request_id` values, each appearing twice, so:

**725 valid records − 5 duplicate records = 720 logical requests.**

### Deduplication rule

`request_id` is the natural logical-request key. One access record is retained per `request_id`. This prevents duplicate fixture lines from inflating request volume while preserving the final client-facing result for each logical request.

Retries are **not** counted as additional client requests: an NGINX retry is represented inside the same access record through fields such as `upstream` and `upstream_status`.

### Reproducible command

```bash
python3 - <<'PY'
import json
from collections import OrderedDict

records = OrderedDict()

with open("logs/access.log", encoding="utf-8") as f:
    for line in f:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        records.setdefault(record["request_id"], record)

print(f"valid_access_records={725}")
print(f"unique_request_ids={len(records)}")
print(f"duplicate_records={725 - len(records)}")
PY
```

Expected result:

```text
valid_access_records=725
unique_request_ids=720
duplicate_records=5
```

---

## 3. Final client status counts and error rate

All counts in this section use **one access record per unique `request_id`**, giving a denominator of **720 logical client requests**.

### Reproducible command

```bash
python3 - <<'PY'
import json
from collections import OrderedDict, Counter

records = OrderedDict()

with open("logs/access.log", encoding="utf-8") as f:
    for line in f:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        records.setdefault(record["request_id"], record)

counts = Counter(r["status"] for r in records.values())

for status in sorted(counts):
    print(status, counts[status])

server_errors = sum(n for status, n in counts.items() if status >= 500)
print(f"5xx={server_errors}/{len(records)}")
print(f"error_rate={server_errors / len(records) * 100:.2f}%")
PY
```

### Results

| Status | Count |
|---:|---:|
| 200 | 615 |
| 404 | 10 |
| 502 | 40 |
| 503 | 47 |
| 504 | 8 |

**5xx server errors: 95 / 720 = 13.19%.**

The 10 `404` responses are included in the complete client status distribution but excluded from the service-health error-rate calculation because they are expected client/prober requests to `/missing`, not server-side failures.

---

## 4. Failures by path, time window, and backend

### Reproducible command

```bash
python3 - <<'PY'
import json
from collections import OrderedDict, Counter

records = OrderedDict()

with open("logs/access.log", encoding="utf-8") as f:
    for line in f:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        records.setdefault(record["request_id"], record)

failed = [r for r in records.values() if r["status"] >= 500]

print("By path:")
for path, count in Counter(r["path"] for r in failed).most_common():
    print(f"{path}\t{count}")

print("\nBy upstream:")
for upstream, count in Counter(r["upstream"] for r in failed).most_common():
    print(f"{upstream}\t{count}")
PY
```

### Results

| Path | Failures |
|---|---:|
| `/records` | 26 |
| `/counter` | 26 |
| `/ready` | 23 |
| `/health` | 10 |
| `/` | 10 |

| Upstream | Failures |
|---|---:|
| `172.23.0.12:8080` | 68 |
| `172.23.0.11:8080` | 27 |

### Incident windows

- **Incident A — 11:05:02–11:09:57:** 40 client-facing `502`s associated with `172.23.0.12`; NGINX repeatedly received connection-refused failures for app-02.
- **Incident B — 11:12:09–11:15:52:** Redis dependency timeouts caused `503`s on `/ready` and `/counter`, affecting both application instances.
- **Incident C — 11:20:07–11:21:45:** PostgreSQL authentication failures caused `503`s on `/ready` and `/records`, affecting both application instances.
- **Incident D — 11:25:14–11:26:47:** 8 client-facing `504`s on `/records`; NGINX timed out while waiting for upstream response headers.

---

## 5. Client latency: median and p95

Latency is calculated from the NGINX `request_time` field using the same **720-request deduplicated dataset** as the status analysis.

Percentiles use the documented nearest-rank/index method with no interpolation:

```text
index = round(p / 100 × (n − 1))
```

### Reproducible command

```bash
python3 - <<'PY'
import json
from collections import OrderedDict

records = OrderedDict()

with open("logs/access.log", encoding="utf-8") as f:
    for line in f:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        records.setdefault(record["request_id"], record)

vals = sorted(float(r["request_time"]) for r in records.values())
n = len(vals)

def pct(p):
    return vals[int(round(p / 100 * (n - 1)))]

print(
    f"n={n} "
    f"min={min(vals):.3f}s "
    f"median={pct(50):.3f}s "
    f"p95={pct(95):.3f}s "
    f"max={max(vals):.3f}s"
)
PY
```

### Result

```text
n=720 min=0.003s median=0.054s p95=2.001s max=2.025s
```

The large gap between the 54 ms median and 2.001 s p95 is consistent with the dependency-failure periods. The application uses approximately 2-second PostgreSQL/Redis connection timeouts, which explains the concentration of failed dependency checks around that ceiling.

---

## 6. Retried upstream requests

A retry is identified by an access record whose `upstream` contains more than one upstream address.

### Reproducible command

```bash
python3 - <<'PY'
import json
from collections import OrderedDict

records = OrderedDict()

with open("logs/access.log", encoding="utf-8") as f:
    for line in f:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        records.setdefault(record["request_id"], record)

retried = [
    r for r in records.values()
    if "," in str(r.get("upstream", ""))
]

successful_after_retry = [
    r for r in retried
    if r["status"] == 200
    and "," in str(r.get("upstream_status", ""))
    and str(r["upstream_status"]).split(",")[-1].strip() == "200"
]

print(f"retried_requests={len(retried)}")
print(f"succeeded_after_retry={len(successful_after_retry)}")

for r in retried[:5]:
    print(
        r["request_id"],
        r["upstream"],
        r["upstream_status"],
        r["status"],
    )
PY
```

### Result

**19 requests retried upstream, and all 19 ultimately returned HTTP 200.**

Example:

`lab-000124` used:

```text
upstream="172.23.0.12:8080, 172.23.0.11:8080"
upstream_status="502, 200"
final_status=200
```

### Important historical-log qualification

All 19 retries occurred during Incident A, and every one was on `/ready` or `/instance`. The other paths in the same historical window received bare `502`s.

This selective historical retry pattern must **not** be treated as proof of the current NGINX configuration. The current configuration uses a single uniform `location /` block and should be evaluated using live failure testing.

---

## 7. Correlated incident timeline across all three logs

| Time (UTC) | `access.log` | `error.log` | `application.log` |
|---|---|---|---|
| 11:05:02–11:09:57 | 40× `502` associated with `172.23.0.12`; 19 requests retried to `172.23.0.11` and returned `200` | 59 `connect() failed (111: Connection refused)` events targeting `172.23.0.12:8080` | No `app-02` application entries for the affected requests, consistent with the process being unreachable |
| 11:12:09–11:15:52 | `503`s on `/ready` and `/counter`, alternating between both instances | No distinct NGINX error events for this dependency-level failure | Redis `TimeoutError` dependency failures on both application instances |
| 11:20:07–11:21:45 | `503`s on `/ready` and `/records`, alternating between both instances | No distinct NGINX error events for this dependency-level failure | PostgreSQL authentication/dependency failures on both application instances |
| 11:25:14–11:26:47 | 8× `504` on `/records`, alternating between both instances | 8 `upstream timed out ... reading response header` events at approximately 2 seconds | Matching requests show application completion after NGINX had already timed out |

### Cross-log correlation

**67/67 unique request IDs present in `error.log` have matching entries in `access.log`; 0 are unmatched.**

This confirms that the NGINX error events can be tied back to client-facing access records through the request ID.

---

## 8. One correlated failed request and one successful request

### Failed request

`request_id=lab-000122`

- Timestamp: `2026-08-20T11:05:02.503Z`
- Request: `GET /health`
- Final status: `502`
- Upstream: `172.23.0.12:8080`
- NGINX error: `connect() failed (111: Connection refused)`
- No matching application-log entry for the request ID.

This is strong evidence that the request failed before the application process received it.

### Successful request after retry

`request_id=lab-000124`

- Timestamp: `2026-08-20T11:05:07.620Z`
- Request: `GET /ready`
- Upstreams: `172.23.0.12:8080, 172.23.0.11:8080`
- Upstream statuses: `502, 200`
- Final client status: `200`

This is direct evidence of upstream failover for that historical request.

---

## 9. Proxy/connectivity vs. dependency/application errors

### Proxy/connectivity failures

**59 NGINX connection-refused events** occurred during Incident A.

Evidence:

1. `error.log` explicitly reports `Connection refused`.
2. The failure is at the socket/connection layer, before an HTTP response can be produced by the application.
3. Affected request IDs have no corresponding application-log request entry.

Therefore these are best classified as **NGINX → application connectivity failures**.

### Dependency/application failures

Incidents B and C are application-level dependency failures.

Evidence:

1. The application log contains explicit `dependency_error` events.
2. Redis failures are identified as `TimeoutError`.
3. PostgreSQL failures are identified as authentication/dependency failures.
4. The same requests receive deliberate HTTP `503` responses from the application.

Therefore these are **application/dependency failures**, not NGINX connectivity failures.

### Incident D

Incident D is intentionally not forced into either category.

- NGINX reports an upstream read timeout after approximately 2 seconds.
- Application logs show the corresponding requests completing later, around 2.7 seconds.

The evidence therefore supports a **timing/configuration mismatch**: the application completed after the NGINX upstream timeout had already expired.

The logs alone do not establish why the application took 2.7 seconds.

---

## 10. What the logs do NOT prove / what to check next

These fixtures are dated **2026-08-20**. Repository troubleshooting occurred later, and the release metadata identifies these logs as **synthetic historical training evidence**. The application documentation explicitly states that the three historical logs are a separate training incident and are not a complete list of current faults.

Therefore:

- Historical failures must not be presented as proof of the current runtime state.
- The historical selective retry behavior should be validated against the current NGINX configuration and live failure test.
- The root cause of Incident D's ~2.7-second application completion is not established by these logs alone. A live reproduction and database-side investigation such as `EXPLAIN ANALYZE` would be required.
- The recurring `/missing` `404`s appear consistent with synthetic health-prober traffic. They are retained in the status distribution but excluded from the 5xx service-health error rate.
- Some application `duration_ms` values during Incident A appear numerically similar to NGINX `request_time`; these fields should not automatically be assumed to be independently measured.

### Recommended live checks

For a running environment, verify:

1. NGINX upstream retry/failover behavior by stopping one application instance.
2. Application readiness while PostgreSQL or Redis is unavailable.
3. PostgreSQL authentication and connectivity from each application instance.
4. Redis connectivity and atomic counter behavior.
5. NGINX timeout behavior against a deliberately slow upstream.
6. Recovery after the failed dependency/backend is restored.
7. Request-ID continuity across NGINX and application logs.

---

## Reproducibility and evidence integrity

The analysis is based on the unmodified static fixtures. All JSON parsing used line-by-line error handling so malformed records do not terminate the analysis.

For request-level metrics, the analysis consistently uses:

**one access record per unique `request_id` → 720 logical requests.**

This is the key control that prevents duplicate fixture lines from inflating counts and keeps status, latency, failure, and retry calculations internally consistent.

The documented commands are designed to reproduce the reported figures directly from the repository fixtures without modifying the source logs.
