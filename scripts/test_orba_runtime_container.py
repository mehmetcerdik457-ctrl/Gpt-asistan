"""Exercise the built gateway image locally; no Google/ADC/payment calls."""
import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
import uuid


def command(*args, check=True):
    return subprocess.run(args, capture_output=True, text=True, timeout=30, check=check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    image = parser.parse_args().image
    name = "orba-runtime-smoke-" + uuid.uuid4().hex[:12]
    checks = []
    try:
        command("docker", "run", "--rm", "-d", "--name", name,
                "--label", "omega.task=orba-runtime-smoke", "--read-only",
                "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--pids-limit=64", "--memory=256m", "--cpus=1",
                "--tmpfs", "/data:rw,nosuid,noexec,uid=10001,gid=10001,mode=0700,size=16m",
                "--tmpfs", "/tmp:rw,nosuid,noexec,mode=1777,size=8m",
                "-p", "127.0.0.1::8080", image)
        port = command("docker", "inspect", "--format",
                       '{{(index (index .NetworkSettings.Ports "8080/tcp") 0).HostPort}}', name).stdout.strip()
        base = "http://127.0.0.1:" + port
        deadline = time.monotonic() + 15
        while True:
            try:
                with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                    health = json.load(response)
                break
            except (OSError, ValueError):
                if time.monotonic() >= deadline:
                    raise RuntimeError("CONTAINER_HEALTH_TIMEOUT") from None
                time.sleep(0.2)
        assert health["status"] == "ok" and health["provider_verified"] is False
        checks.append("actual_container_http_health")
        assert command("docker", "exec", name, "id", "-u").stdout.strip() == "10001"
        checks.append("non_root_read_only_container")
        for route, expected in (("/api/v1/play/rtdn", "RTDN_NOT_CONFIGURED"),):
            request = urllib.request.Request(base + route, data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST")
            try:
                urllib.request.urlopen(request, timeout=2)
                raise AssertionError("DISABLED_ROUTE_ACCEPTED")
            except urllib.error.HTTPError as response:
                assert response.code == 503
                assert json.load(response)["error"] == expected
        checks.append("unconfigured_rtdn_disabled")
        preflight = command("docker", "exec", name, "python", "-m", "server.play_preflight", check=False)
        assert preflight.returncode == 2
        assert json.loads(preflight.stdout)["state"] == "DISABLED"
        checks.append("offline_preflight_reports_disabled")
        command("docker", "exec", name, "python", "-c",
                "import psycopg, server.play_runtime, server.play_purchase_postgres; print('IMPORT_OK')")
        checks.append("postgres_runtime_dependencies_present")
        incomplete = command("docker", "run", "--rm", "--network=none",
            "-e", "ORBA_PLAY_RTDN_ENABLED=YES", "-e",
            "ORBA_PLAY_DATABASE_DSN=postgresql://synthetic:PRIVATE_SENTINEL@invalid.test/db", image, check=False)
        assert incomplete.returncode != 0
        assert "PLAY_RUNTIME_CONFIGURATION_INVALID" in incomplete.stderr
        assert "PRIVATE_SENTINEL" not in incomplete.stdout + incomplete.stderr
        checks.append("partial_activation_fails_before_listener_without_secret_reflection")
        print(json.dumps({"status": "PASS", "image": image,
            "image_id": command("docker", "image", "inspect", "--format", "{{.Id}}", image).stdout.strip(),
            "checks": checks, "google_calls": 0, "production_acceptance": False}, indent=2))
        return 0
    finally:
        command("docker", "rm", "-f", name, check=False)


if __name__ == "__main__":
    raise SystemExit(main())
