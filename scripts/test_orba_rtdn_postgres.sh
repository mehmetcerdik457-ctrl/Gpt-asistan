#!/usr/bin/env bash
# Runs only against a new disposable local PostgreSQL container.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_python="${ORBA_TEST_PYTHON:-python}"
test_container="orba-rtdn-test-$$-${RANDOM}"
test_db_password="$("$test_python" -c 'import secrets; print(secrets.token_hex(24))')"

cleanup() {
  docker rm -f "$test_container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --rm -d --name "$test_container" \
  --label omega.task=orba-rtdn-test \
  --env POSTGRES_USER=orba_test \
  --env POSTGRES_DB=orba_test \
  --env POSTGRES_PASSWORD="$test_db_password" \
  --publish 127.0.0.1::5432 \
  --tmpfs /var/lib/postgresql/data:rw,nosuid,noexec \
  postgres:16-alpine >/dev/null

ready=false
for attempt in {1..40}; do
  if docker exec "$test_container" pg_isready -q -U orba_test -d orba_test; then
    ready=true
    break
  fi
  sleep 0.5
done
if [[ "$ready" != true ]]; then
  printf '%s\n' 'Disposable PostgreSQL did not become ready.' >&2
  exit 1
fi

test_db_port="$(docker inspect --format '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' "$test_container")"
export OMEGA_ORBA_TEST_PG_DSN="postgresql://orba_test:${test_db_password}@127.0.0.1:${test_db_port}/orba_test"
cd -- "$repo_root"
"$test_python" -m unittest -v \
  server.integration_tests.test_play_rtdn_postgres \
  server.integration_tests.test_play_rtdn_postgres_http \
  server.integration_tests.test_play_purchase_postgres \
  server.integration_tests.test_play_preflight_postgres
