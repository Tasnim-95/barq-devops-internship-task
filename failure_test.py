#!/usr/bin/env python3
"""
Backend failure/recovery test for the BARQ assessment.

The test discovers app-N instances at runtime, so it works unchanged
with the pre-video 2-instance deployment and the final 3-instance
deployment.

Behavior proved:
  1. Public traffic works before failure.
  2. A real PostgreSQL-backed record can be created before failure.
  3. One backend is deliberately stopped.
  4. Remaining backends continue serving traffic.
  5. Availability and errors are measured during the outage.
  6. PostgreSQL-backed writes continue during the outage.
  7. The stopped backend is restarted and becomes healthy.
  8. The recovered backend serves traffic again.
  9. All surviving backends continue serving traffic after recovery.
 10. Test-created records occur exactly once in PostgreSQL.

The script never tears down the Compose project. It only stops/starts
the single backend selected for the test and always attempts recovery
in finally.

Exit code:
  0 = all assertions passed
  1 = one or more assertions failed
"""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request


PROJECT = os.getenv("COMPOSE_PROJECT_NAME", "barq-assessment")
PUBLIC_PORT = os.getenv("PUBLIC_PORT", "8080")
BASE_URL = f"http://127.0.0.1:{PUBLIC_PORT}"

TOTAL_REQUESTS = int(os.getenv("FAILURE_TEST_REQUESTS", "20"))
HTTP_TIMEOUT = float(os.getenv("FAILURE_TEST_HTTP_TIMEOUT", "5"))
POST_TIMEOUT = float(os.getenv("FAILURE_TEST_POST_TIMEOUT", "7"))
HEALTH_TIMEOUT = int(os.getenv("FAILURE_TEST_HEALTH_TIMEOUT", "60"))
RECOVERY_TRAFFIC_TIMEOUT = int(os.getenv("FAILURE_TEST_RECOVERY_TIMEOUT", "30"))
MIN_AVAILABILITY = float(os.getenv("FAILURE_TEST_MIN_AVAILABILITY", "90"))

FAILURES = 0


def run(*args):
    """Run a bounded local command and return the CompletedProcess."""
    return subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def get(path, timeout=HTTP_TIMEOUT):
    """GET an endpoint and return (status, headers, body)."""
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=timeout) as response:
            return response.status, response.headers, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read().decode()
    except Exception:
        return 0, {}, ""


def post_record(title, timeout=POST_TIMEOUT):
    """Create a real PostgreSQL-backed record and return its HTTP status."""
    try:
        request = urllib.request.Request(
            BASE_URL + "/records",
            data=json.dumps({"title": title}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except Exception:
        return 0


def wait_health(container, timeout=HEALTH_TIMEOUT):
    """Wait for a container healthcheck to report healthy."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        result = run(
            "docker",
            "inspect",
            "-f",
            "{{.State.Health.Status}}",
            container,
        )

        if result.returncode == 0 and result.stdout.strip() == "healthy":
            return True

        time.sleep(2)

    return False


def wait_running(container, timeout=HEALTH_TIMEOUT):
    """Wait for a container to reach running state."""
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        result = run(
            "docker",
            "inspect",
            "-f",
            "{{.State.Status}}",
            container,
        )

        if result.returncode == 0 and result.stdout.strip() == "running":
            return True

        time.sleep(1)

    return False


def discover_app_instances():
    """
    Discover all app-N containers belonging to this Compose project.

    Only exact names matching app-<number> are accepted.
    """
    result = run(
        "docker",
        "ps",
        "-a",
        "--filter",
        f"label=com.docker.compose.project={PROJECT}",
        "--format",
        "{{.Names}}",
    )

    if result.returncode != 0:
        return []

    names = [
        name.strip()
        for name in result.stdout.splitlines()
        if name.strip()
    ]

    return sorted(
        name
        for name in names
        if re.fullmatch(r"app-\d+", name)
    )


def parse_records(body):
    """Parse GET /records JSON and return the records list."""
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return None

    records = payload.get("records")

    if not isinstance(records, list):
        return None

    return records


def exact_title_count(records, title):
    """Count records whose title exactly equals the supplied title."""
    return sum(
        1
        for record in records
        if isinstance(record, dict) and record.get("title") == title
    )


def main():
    global FAILURES

    def fail(message):
        global FAILURES
        FAILURES += 1
        print(f"FAIL: {message}")

    def ok(message):
        print(f"PASS: {message}")

    print("=== Backend failure/recovery test ===")
    print(f"Compose project: {PROJECT}")
    print(f"Target: {BASE_URL}")
    print(f"Requests during outage: {TOTAL_REQUESTS}")
    print(f"Minimum availability: {MIN_AVAILABILITY:.1f}%")
    print()

    instances = discover_app_instances()
    print(f"Discovered application instances: {instances}")

    if len(instances) < 2:
        fail(
            "need at least 2 app instances to test failure/recovery; "
            f"found {len(instances)}"
        )
        sys.exit(1)

    # Deterministic target: lowest-numbered backend.
    backend = instances[0]
    survivors = set(instances[1:])

    ok(
        f"targeting {backend} for controlled stop; "
        f"survivors expected: {sorted(survivors)}"
    )

    duplicate_check_titles = []
    backend_stopped = False

    try:
        # ------------------------------------------------------------
        # Baseline
        # ------------------------------------------------------------
        print()
        print("--- Baseline ---")

        status, _, _ = get("/")
        if status == 200:
            ok("baseline public request returned HTTP 200")
        else:
            fail(f"baseline public request returned {status}, expected 200")
            return

        baseline_title = f"failtest-baseline-{int(time.time())}"
        code = post_record(baseline_title)

        if code == 201:
            ok(f"baseline POST /records succeeded ({baseline_title})")
            duplicate_check_titles.append(baseline_title)
        else:
            fail(f"baseline POST /records returned {code}, expected 201")
            return

        # ------------------------------------------------------------
        # Stop one backend
        # ------------------------------------------------------------
        print()
        print(f"--- Stopping {backend} ---")

        result = run(
            "docker",
            "compose",
            "-p",
            PROJECT,
            "stop",
            backend,
        )

        if result.returncode != 0:
            fail(
                f"docker compose stop {backend} failed: "
                f"{result.stderr.strip()}"
            )
            return

        stopped_state = run(
            "docker",
            "inspect",
            "-f",
            "{{.State.Status}}",
            backend,
        ).stdout.strip()

        if stopped_state == "exited":
            backend_stopped = True
            ok(f"{backend} is stopped (state=exited)")
        else:
            fail(
                f"{backend} state is {stopped_state}; "
                "expected exited"
            )
            return

        # ------------------------------------------------------------
        # Traffic during outage
        # ------------------------------------------------------------
        print()
        print(
            f"--- Sending {TOTAL_REQUESTS} requests while "
            f"{backend} is down ---"
        )

        success = 0
        errors = 0
        latencies = []
        instances_during_outage = set()

        for number in range(1, TOTAL_REQUESTS + 1):
            start = time.monotonic()

            status, _, _ = get("/")
            elapsed = time.monotonic() - start

            latencies.append(elapsed)

            if status == 200:
                success += 1
            else:
                errors += 1

            inst_status, inst_headers, _ = get("/instance")
            served_by = (
                inst_headers.get("X-Instance-ID", "")
                if inst_status == 200
                else ""
            )

            if served_by:
                instances_during_outage.add(served_by)

            print(
                f"request={number:02d} "
                f"status={status} "
                f"instance={served_by or '-'} "
                f"latency={elapsed:.3f}s"
            )

        availability = success / TOTAL_REQUESTS * 100
        max_latency = max(latencies) if latencies else 0

        print()
        print(
            f"Requests: {TOTAL_REQUESTS}  "
            f"HTTP200: {success}  "
            f"Errors: {errors}  "
            f"Availability: {availability:.1f}%"
        )
        print(f"Max latency: {max_latency:.3f}s")
        print(
            "Instances observed during outage: "
            f"{sorted(instances_during_outage)}"
        )

        if availability >= MIN_AVAILABILITY:
            ok(
                f"service availability remained at "
                f"{availability:.1f}% during backend failure"
            )
        else:
            fail(
                f"availability dropped to {availability:.1f}%; "
                f"minimum required is {MIN_AVAILABILITY:.1f}%"
            )

        if instances_during_outage:
            unexpected = instances_during_outage - survivors

            if unexpected:
                fail(
                    "stopped backend appeared to serve traffic during "
                    f"outage: {sorted(unexpected)}"
                )
            else:
                ok(
                    "only surviving backend(s) served traffic during "
                    f"outage: {sorted(instances_during_outage)}"
                )
        else:
            fail("could not confirm any surviving backend served traffic")

        missing_survivors = survivors - instances_during_outage

        if not missing_survivors:
            ok(
                "all surviving backend(s) were observed serving "
                f"traffic during outage: {sorted(survivors)}"
            )
        else:
            fail(
                "surviving backend(s) were not observed during outage: "
                f"{sorted(missing_survivors)}"
            )

        # ------------------------------------------------------------
        # Real PostgreSQL write during outage
        # ------------------------------------------------------------
        outage_title = f"failtest-outage-{int(time.time())}"

        print()
        print("--- PostgreSQL write during backend outage ---")

        code = post_record(outage_title)

        if code == 201:
            ok(
                "POST /records succeeded through a surviving backend "
                f"({outage_title})"
            )
            duplicate_check_titles.append(outage_title)
        else:
            # This is intentionally a hard failure.
            fail(
                "POST /records during backend outage returned "
                f"{code}; expected 201"
            )

        # ------------------------------------------------------------
        # Restore backend
        # ------------------------------------------------------------
        print()
        print(f"--- Restoring {backend} ---")

        result = run(
            "docker",
            "compose",
            "-p",
            PROJECT,
            "start",
            backend,
        )

        if result.returncode == 0:
            ok(f"docker compose start {backend} succeeded")
        else:
            fail(
                f"docker compose start {backend} failed: "
                f"{result.stderr.strip()}"
            )

        backend_stopped = False

        if wait_running(backend):
            ok(f"{backend} returned to running state")
        else:
            fail(f"{backend} did not return to running state within bounded wait")

        if wait_health(backend):
            ok(f"{backend} recovered to healthy")
        else:
            fail(
                f"{backend} did not become healthy within "
                f"{HEALTH_TIMEOUT}s"
            )

        # ------------------------------------------------------------
        # Prove recovered backend serves traffic
        # ------------------------------------------------------------
        print()
        print("--- Proving post-recovery traffic distribution ---")

        seen_after_recovery = set()
        deadline = time.monotonic() + RECOVERY_TRAFFIC_TIMEOUT

        while time.monotonic() < deadline:
            status, headers, _ = get("/instance")

            if status == 200:
                current = headers.get("X-Instance-ID", "")

                if current:
                    seen_after_recovery.add(current)

            expected = survivors | {backend}

            if expected.issubset(seen_after_recovery):
                break

            time.sleep(0.5)

        print(
            "Instances observed after recovery: "
            f"{sorted(seen_after_recovery)}"
        )

        if backend in seen_after_recovery:
            ok(f"recovered {backend} served traffic")
        else:
            fail(
                f"recovered {backend} was not observed within "
                f"{RECOVERY_TRAFFIC_TIMEOUT}s"
            )

        missing_after_recovery = (
            survivors - seen_after_recovery
        )

        if not missing_after_recovery:
            ok(
                "all surviving backend(s) continued serving traffic "
                f"after recovery: {sorted(survivors)}"
            )
        else:
            fail(
                "surviving backend(s) not observed after recovery: "
                f"{sorted(missing_after_recovery)}"
            )

        # ------------------------------------------------------------
        # Real PostgreSQL write after recovery
        # ------------------------------------------------------------
        recovery_title = f"failtest-recovery-{int(time.time())}"

        print()
        print("--- PostgreSQL write after recovery ---")

        code = post_record(recovery_title)

        if code == 201:
            ok(
                f"post-recovery POST /records succeeded "
                f"({recovery_title})"
            )
            duplicate_check_titles.append(recovery_title)
        else:
            fail(
                f"post-recovery POST /records returned {code}; "
                "expected 201"
            )

        # ------------------------------------------------------------
        # Exact duplicate check
        # ------------------------------------------------------------
        print()
        print("--- Exact PostgreSQL duplicate check ---")

        status, _, body = get("/records")

        if status != 200:
            fail(
                f"GET /records for duplicate check returned "
                f"{status}, expected 200"
            )
        else:
            records = parse_records(body)

            if records is None:
                fail("GET /records returned invalid JSON records payload")
            else:
                for title in duplicate_check_titles:
                    occurrences = exact_title_count(records, title)

                    if occurrences == 1:
                        ok(
                            f"record '{title}' appears exactly once "
                            "in PostgreSQL"
                        )
                    elif occurrences == 0:
                        fail(
                            f"record '{title}' was not found in PostgreSQL"
                        )
                    else:
                        fail(
                            f"record '{title}' appears {occurrences} times "
                            "in PostgreSQL; possible duplicate insert"
                        )

    finally:
        # Always restore the selected backend if anything failed midway.
        result = run(
            "docker",
            "inspect",
            "-f",
            "{{.State.Status}}",
            backend,
        )

        current_state = result.stdout.strip()

        if current_state != "running":
            print()
            print(
                f"Cleanup: ensuring {backend} is running "
                f"(current state={current_state or 'unknown'})..."
            )

            recover = run(
                "docker",
                "compose",
                "-p",
                PROJECT,
                "start",
                backend,
            )

            if recover.returncode == 0:
                if wait_running(backend, timeout=30):
                    if wait_health(backend, timeout=30):
                        print(
                            f"Cleanup: {backend} restored and healthy."
                        )
                    else:
                        fail(
                            f"Cleanup: {backend} is running but did not "
                            "become healthy within 30s"
                        )
                else:
                    fail(
                        f"Cleanup: {backend} did not return to running "
                        "state within 30s"
                    )
            else:
                fail(
                    f"Cleanup: failed to restore {backend}: "
                    f"{recover.stderr.strip()}"
                )

    print()

    if FAILURES:
        print(
            f"FAILURE TEST FAILED: {FAILURES} check(s) failed"
        )
        sys.exit(1)

    print("FAILURE TEST PASSED")


if __name__ == "__main__":
    main()
