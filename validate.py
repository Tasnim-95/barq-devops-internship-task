#!/usr/bin/env python3
"""Comprehensive environment validator for the BARQ DevOps assessment.

Designed to work unchanged across the pre-video (2 instances, port 8080)
and final video (3 instances, port 8090) states: application instances and
the public port are discovered from the live environment, not hardcoded.

Bounded waits, explicit PASS/FAIL evidence per check, non-zero exit on any
failure. Validates both the Compose-declared configuration and the actual
live runtime state, since the two can drift independently.

Environment variables:
  PUBLIC_PORT                     expected public port (default 8080)
  VALIDATE_SKIP_DEPENDENCY_FAILURE  set to skip the redis pause/unpause test
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

PROJECT = "barq-assessment"
PUBLIC_PORT = os.getenv("PUBLIC_PORT", "8080")
BASE_URL = f"http://127.0.0.1:{PUBLIC_PORT}"
TIMEOUT = 5
WAIT_SECONDS = 60
FAILURES = 0
START_TIME = time.monotonic()

FRONTEND_NET = f"{PROJECT}_frontend"
BACKEND_NET = f"{PROJECT}_backend"


def fail(message):
    global FAILURES
    FAILURES += 1
    print(f"FAIL: {message}")


def passed(message):
    print(f"PASS: {message}")


def section(title):
    print()
    print(f"--- {title} ---")


def run(*args):
    return subprocess.run(
        args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )


def request(path, method="GET", body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return response.status, response.headers, response.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read().decode()
    except Exception as exc:
        return None, {}, str(exc)


def wait_public():
    deadline = time.time() + WAIT_SECONDS
    while time.time() < deadline:
        status, _, _ = request("/health")
        if status == 200:
            return True
        time.sleep(2)
    return False


def inspect_health(container):
    result = run(
        "docker", "inspect", "-f",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}",
        container,
    )
    return result.stdout.strip()


def require_request_id(path, headers):
    if headers.get("X-Request-ID"):
        passed(f"{path} returned X-Request-ID")
        return True
    fail(f"{path} missing X-Request-ID")
    return False


# ------------------------------------------------------- dynamic discovery

def discover_app_instances():
    """Find every app-0N container belonging to this Compose project,
    regardless of whether it was in the original compose file (covers the
    live-added third instance during the video challenge)."""
    result = run(
        "docker", "ps", "-a",
        "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--format", "{{.Names}}",
    )
    if result.returncode != 0:
        return []
    names = [n.strip() for n in result.stdout.splitlines() if n.strip()]
    instances = sorted(n for n in names if re.fullmatch(r"app-\d+", n))
    return instances


APP_INSTANCES = discover_app_instances()
ALL_SERVICES = tuple(APP_INSTANCES) + ("postgres", "redis", "nginx")


def expected_networks_for(container):
    if container in APP_INSTANCES:
        return {FRONTEND_NET, BACKEND_NET}
    if container == "nginx":
        return {FRONTEND_NET}
    if container in ("postgres", "redis"):
        return {BACKEND_NET}
    return set()


# ---------------------------------------------------------------- endpoints

def check_instance_count():
    section("Application instance discovery")
    if not APP_INSTANCES:
        fail("no app-0N containers discovered for this Compose project")
        return
    passed(f"discovered {len(APP_INSTANCES)} application instance(s): {APP_INSTANCES}")
    if len(APP_INSTANCES) not in (2, 3):
        print(f"NOTE: {len(APP_INSTANCES)} instances is outside the expected 2 (pre-video) "
              f"or 3 (final video) count - not a hard failure, just noted.")


def check_container_health():
    section("Docker health status")
    for container in ALL_SERVICES:
        status = inspect_health(container)
        if status == "healthy":
            passed(f"{container} healthcheck is healthy")
        else:
            fail(f"{container} healthcheck is {status}")


def check_root_response():
    section("GET /")
    status, headers, body = request("/")
    if status != 200:
        fail(f"/ returned HTTP {status}, expected 200")
        return
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        fail("/ returned invalid JSON")
        return
    if payload.get("message") == "Welcome to BARQ Systems":
        passed("/ returned the configured application message")
    else:
        fail(f"/ returned unexpected message: {payload.get('message')!r}")
    if payload.get("instance_id"):
        passed("/ response includes instance_id")
    else:
        fail("/ response missing instance_id")
    require_request_id("/", headers)


def check_health_liveness():
    section("GET /health (liveness only)")
    status, headers, body = request("/health")
    if status == 200:
        passed("/health returned HTTP 200")
    else:
        fail(f"/health returned HTTP {status}, expected 200")
    require_request_id("/health", headers)
    try:
        payload = json.loads(body)
        if payload.get("status") == "alive":
            passed("/health body reports status=alive")
        else:
            fail(f"/health body unexpected: {body}")
    except json.JSONDecodeError:
        fail("/health returned invalid JSON")


def check_ready_semantics():
    section("GET /ready (PostgreSQL + Redis dependency check, baseline healthy)")
    status, headers, body = request("/ready")
    if status != 200:
        fail(f"/ready returned HTTP {status}, expected 200 (postgres/redis should be up)")
    else:
        passed("/ready returned HTTP 200")
    require_request_id("/ready", headers)
    try:
        payload = json.loads(body)
        deps = payload.get("dependencies", {})
        for dep in ("postgres", "redis"):
            if deps.get(dep) == "ready":
                passed(f"/ready reports {dep}=ready")
            else:
                fail(f"/ready reports {dep}={deps.get(dep)!r}, expected 'ready'")
    except json.JSONDecodeError:
        fail("/ready returned invalid JSON")


def check_dependency_failure_readiness():
    section("Dependency-failure readiness (/ready 503 while /health stays 200)")
    if os.getenv("VALIDATE_SKIP_DEPENDENCY_FAILURE"):
        print("SKIPPED: VALIDATE_SKIP_DEPENDENCY_FAILURE is set")
        return

    print("Pausing redis container to simulate a dependency outage...")
    pause = run("docker", "pause", "redis")
    if pause.returncode != 0:
        fail("could not pause redis container for dependency-failure test")
        return

    try:
        time.sleep(1)

        status, _, _ = request("/health")
        if status == 200:
            passed("/health remains 200 while redis is paused (liveness independent of dependencies)")
        else:
            fail(f"/health returned {status} while redis was paused, expected 200")

        status, _, body = request("/ready")
        if status == 503:
            passed("/ready returned 503 while redis is paused")
        else:
            fail(f"/ready returned {status} while redis was paused, expected 503")

        try:
            deps = json.loads(body).get("dependencies", {})
            if deps.get("redis") == "unavailable":
                passed("/ready correctly reports redis=unavailable")
            else:
                fail(f"/ready did not report redis=unavailable: {deps}")
            if deps.get("postgres") == "ready":
                passed("/ready correctly reports postgres=ready during a redis-only outage")
            else:
                fail(f"/ready did not report postgres=ready during redis-only outage: {deps}")
        except json.JSONDecodeError:
            fail("/ready body was not valid JSON during dependency failure")

    finally:
        print("Unpausing redis container...")
        unpause = run("docker", "unpause", "redis")
        if unpause.returncode != 0:
            fail("CRITICAL: could not unpause redis container - manual intervention required")
        else:
            deadline = time.time() + 20
            recovered = False
            while time.time() < deadline:
                status, _, _ = request("/ready")
                if status == 200:
                    recovered = True
                    break
                time.sleep(1)
            if recovered:
                passed("/ready recovered to 200 after redis was unpaused")
            else:
                fail("/ready did not recover to 200 within 20s after unpausing redis")


def check_instance_distribution():
    section("GET /instance (distinct identity, all discovered backends)")
    if not APP_INSTANCES:
        fail("cannot check instance distribution: no app instances discovered")
        return

    seen = set()
    attempts = max(12, len(APP_INSTANCES) * 8)

    for _ in range(attempts):
        status, headers, body = request("/instance")
        if status != 200:
            fail(f"/instance returned HTTP {status}")
            continue
        require_request_id("/instance", headers)
        header_instance = headers.get("X-Instance-ID")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            fail("/instance returned invalid JSON")
            continue
        body_instance = payload.get("instance_id")
        if not header_instance:
            fail("/instance missing X-Instance-ID header")
        if not body_instance:
            fail("/instance body missing instance_id")
        if header_instance and body_instance:
            if header_instance == body_instance:
                seen.add(body_instance)
            else:
                fail(f"/instance identity mismatch: header={header_instance}, body={body_instance}")

    expected = set(APP_INSTANCES)
    if expected.issubset(seen):
        passed(f"all {len(expected)} backend instance(s) served traffic: {sorted(seen)}")
    else:
        fail(f"expected {sorted(expected)}, observed {sorted(seen)} after {attempts} requests")


def check_records():
    section("POST/GET /records (PostgreSQL-backed)")
    title = f"validation-{int(time.time())}"
    status, headers, body = request("/records", "POST", {"title": title})
    require_request_id("POST /records", headers)
    if status == 201:
        passed("POST /records created a real database record")
    else:
        fail(f"POST /records returned HTTP {status}: {body}")

    boundary_title = "x" * 200
    status, headers, _ = request("/records", "POST", {"title": boundary_title})
    if status == 201:
        passed("POST /records accepts a title of exactly 200 characters (boundary case)")
    else:
        fail(f"POST /records rejected a valid 200-character title with HTTP {status}")

    status, headers, body = request("/records")
    require_request_id("GET /records", headers)
    if status != 200:
        fail(f"GET /records returned HTTP {status}")
        return
    if title in body:
        passed("GET /records returned the newly created record")
    else:
        fail("new record was not found in GET /records")


def check_counter():
    section("GET /counter (Redis-backed atomic counter)")
    status1, headers1, body1 = request("/counter")
    status2, headers2, body2 = request("/counter")
    require_request_id("/counter", headers1)
    require_request_id("/counter", headers2)
    if status1 != 200 or status2 != 200:
        fail(f"/counter returned {status1}, then {status2}")
        return
    try:
        first_value = int(json.loads(body1)["counter"])
        second_value = int(json.loads(body2)["counter"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        fail("/counter did not return the expected numeric counter field")
        return
    if second_value == first_value + 1:
        passed(f"/counter atomically incremented from {first_value} to {second_value}")
    else:
        fail(f"/counter did not increment by exactly 1: {first_value} -> {second_value}")


def check_invalid_and_unknown():
    section("Invalid input and unknown-route behavior")
    cases = [
        ("empty title", {"title": ""}),
        ("overlong title (201 chars)", {"title": "x" * 201}),
        ("non-string title", {"title": 123}),
        ("missing title key", {}),
    ]
    for label, payload in cases:
        status, headers, _ = request("/records", "POST", payload)
        require_request_id(f"POST /records ({label})", headers)
        if status == 400:
            passed(f"{label} returned HTTP 400")
        else:
            fail(f"{label} returned HTTP {status}, expected 400")

    status, headers, _ = request("/does-not-exist")
    require_request_id("/does-not-exist", headers)
    if status == 404:
        passed("unknown route returned HTTP 404")
    else:
        fail(f"unknown route returned HTTP {status}")


def check_dependency_connectivity():
    section("Direct PostgreSQL/Redis readiness (bypassing the app)")
    for container, command in (
        ("postgres", ("pg_isready", "-U", "barq_app", "-d", "barq_tasks")),
        ("redis", ("redis-cli", "ping")),
    ):
        result = run("docker", "compose", "-p", PROJECT, "exec", "-T", container, *command)
        if result.returncode == 0:
            passed(f"{container} dependency readiness command succeeds")
        else:
            fail(f"{container} dependency readiness failed: {result.stderr.strip()}")


# --------------------------------------------------------- compose/runtime

def load_compose_config():
    result = run("docker", "compose", "-p", PROJECT, "config", "--format", "json")
    if result.returncode != 0:
        fail("docker compose config could not be rendered")
        return None
    try:
        return json.loads(result.stdout)
    except Exception as exc:
        fail(f"could not parse Compose JSON: {exc}")
        return None


def check_public_port_binding():
    section("Public port binding matches expected PUBLIC_PORT")
    result = run("docker", "port", "nginx", "80")
    if result.returncode != 0:
        fail("could not inspect nginx port binding (is nginx running?)")
        return
    bound = result.stdout.strip()
    if f":{PUBLIC_PORT}" in bound:
        passed(f"nginx is actually bound to expected public port {PUBLIC_PORT} ({bound})")
    else:
        fail(f"nginx port binding {bound!r} does not match expected PUBLIC_PORT={PUBLIC_PORT}")


def check_compose_ports():
    section("Declared host port exposure (only nginx, no app/PG/Redis ports)")
    result = run("docker", "compose", "-p", PROJECT, "ps", "--format", "json")
    if result.returncode != 0:
        fail("could not list running containers for port check")
        return
    try:
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError:
        fail("could not parse docker compose ps output")
        return

    for row in rows:
        name = row.get("Service") or row.get("Name", "")
        published = row.get("Publishers") or []
        has_host_port = any(p.get("PublishedPort") for p in published) if isinstance(published, list) else bool(row.get("Ports"))
        if name == "nginx":
            if has_host_port:
                passed("nginx has a published host port")
            else:
                fail("nginx has no published host port")
        elif name in APP_INSTANCES or name in ("postgres", "redis"):
            if has_host_port:
                fail(f"{name} unexpectedly has a published host port")
            else:
                passed(f"{name} has no published host port")


def check_runtime_network_membership():
    section("Runtime network membership (actual container attachment)")
    for container in ALL_SERVICES:
        expected = expected_networks_for(container)
        result = run(
            "docker", "inspect", "-f",
            "{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}",
            container,
        )
        if result.returncode != 0:
            fail(f"could not inspect networks for {container}")
            continue
        actual = set(result.stdout.split())
        if actual == expected:
            passed(f"{container} is attached to exactly {sorted(expected)}")
        else:
            fail(f"{container} is attached to {sorted(actual)}, expected {sorted(expected)}")


def check_network_isolation():
    section("Backend isolation (nginx cannot reach PostgreSQL/Redis directly)")
    for host, port in (("postgres", 5432), ("redis", 6379)):
        result = run("docker", "exec", "nginx", "nc", "-z", "-w", "2", host, str(port))
        if result.returncode != 0:
            passed(f"nginx cannot directly reach backend service {host}:{port}")
        else:
            fail(f"nginx can unexpectedly reach backend service {host}:{port}")


def check_storage_persistence(config):
    section("Named volumes and persistence configuration")
    volumes = config.get("volumes", {}) if config else {}
    if "postgres-data" in volumes:
        passed("PostgreSQL uses a named volume")
    else:
        fail("PostgreSQL named volume is missing from Compose")
    if "redis-data" in volumes:
        passed("Redis uses a named volume")
    else:
        fail("Redis named volume is missing from Compose")

    result = run("docker", "inspect", "-f", "{{json .Mounts}}", "postgres")
    try:
        mounts = json.loads(result.stdout)
        data_mount = next((m for m in mounts if m.get("Destination") == "/var/lib/postgresql/data"), None)
        if data_mount and data_mount.get("Type") == "volume":
            passed(f"PostgreSQL data directory is backed by named volume '{data_mount.get('Name')}'")
        else:
            fail("PostgreSQL data directory is not backed by a named volume")
    except Exception as exc:
        fail(f"could not inspect PostgreSQL mounts: {exc}")

    result = run("docker", "exec", "redis", "redis-cli", "CONFIG", "GET", "appendonly")
    if "yes" in result.stdout:
        passed("Redis AOF persistence is enabled at runtime (CONFIG GET appendonly = yes)")
    else:
        fail(f"Redis AOF persistence is not enabled at runtime: {result.stdout.strip()!r}")


def check_restart_policies():
    section("Restart policies")
    for container in ALL_SERVICES:
        result = run("docker", "inspect", "-f", "{{.HostConfig.RestartPolicy.Name}}", container)
        policy = result.stdout.strip()
        if policy and policy != "no":
            passed(f"{container} has a restart policy: {policy}")
        else:
            fail(f"{container} has no meaningful restart policy (got {policy!r})")


def check_resource_limits():
    section("Resource limits (memory and CPU)")
    for container in ALL_SERVICES:
        result = run(
            "docker", "inspect", "-f",
            "{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}",
            container,
        )
        try:
            mem, cpus = result.stdout.split()
            mem, cpus = int(mem), int(cpus)
        except (ValueError, AttributeError):
            fail(f"could not parse resource limits for {container}")
            continue
        if mem > 0 and cpus > 0:
            passed(f"{container} has memory ({mem // (1024*1024)}MB) and CPU limits set")
        else:
            fail(f"{container} is missing memory and/or CPU limits (mem={mem}, cpus={cpus})")


def check_non_root_user():
    section("Non-root execution (Flask application containers)")
    for container in APP_INSTANCES:
        result = run("docker", "inspect", "-f", "{{.Config.User}}", container)
        user = result.stdout.strip()
        if user and user not in ("0", "root"):
            passed(f"{container} runs as non-root user: {user}")
        else:
            fail(f"{container} runs as root or has no user set (got {user!r})")


def check_pinned_images():
    section("Pinned base images (digest-pinned, not floating tags)")
    for container in ("postgres", "redis", "nginx"):
        result = run("docker", "inspect", "-f", "{{.Config.Image}}", container)
        image = result.stdout.strip()
        if "@sha256:" in image:
            passed(f"{container} image is pinned by digest")
        else:
            fail(f"{container} image is not pinned by digest: {image!r}")


def main():
    print(f"Validation target: {BASE_URL}")
    print(f"Compose project: {PROJECT}")

    if not wait_public():
        fail("public endpoint did not become healthy within bounded wait")
        print(f"\nVALIDATION FAILED: {FAILURES} check(s) failed")
        sys.exit(1)
    passed("public endpoint became reachable")

    check_instance_count()
    check_container_health()
    check_root_response()
    check_health_liveness()
    check_ready_semantics()
    check_dependency_failure_readiness()
    check_instance_distribution()
    check_records()
    check_counter()
    check_invalid_and_unknown()
    check_dependency_connectivity()

    check_public_port_binding()
    check_compose_ports()
    check_runtime_network_membership()
    check_network_isolation()

    config = load_compose_config()
    check_storage_persistence(config)
    check_restart_policies()
    check_resource_limits()
    check_non_root_user()
    check_pinned_images()

    elapsed = time.monotonic() - START_TIME
    print()
    print(f"Elapsed: {elapsed:.1f}s")
    if FAILURES:
        print(f"VALIDATION FAILED: {FAILURES} check(s) failed")
        sys.exit(1)
    print("VALIDATION PASSED: all checks succeeded")


if __name__ == "__main__":
    main()
