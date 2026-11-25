#!/bin/sh
# Run API integration tests against a disposable MySQL instance.
#
# This script always uses a distinct Compose project and volume. Its cleanup
# therefore cannot remove the application's normal mysql-data volume.
set -eu

TEST_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TEST_PROJECT=${TEST_COMPOSE_PROJECT:-novaledger-api-test}
TEST_COMPOSE_FILE="$TEST_ROOT/docker-compose.test.yml"
TEST_MYSQL_PORT=${TEST_MYSQL_PORT:-3307}
TEST_MYSQL_PASSWORD=${TEST_MYSQL_PASSWORD:-novaledger-test-password}
TEST_MYSQL_ROOT_PASSWORD=${TEST_MYSQL_ROOT_PASSWORD:-novaledger-test-root-password}
PYTHON_BIN=${PYTHON:-python3}
TEST_CONFIG_HELPER="$TEST_ROOT/scripts/test_api_integration_config.py"

export TEST_MYSQL_PORT TEST_MYSQL_PASSWORD TEST_MYSQL_ROOT_PASSWORD

if [ "${TEST_DATABASE_URL+x}" = x ]; then
    export TEST_DATABASE_URL
    TEST_DATABASE_URL=$("$PYTHON_BIN" "$TEST_CONFIG_HELPER" \
        --port "$TEST_MYSQL_PORT" \
        --project "$TEST_PROJECT" \
        --url-from-environment)
else
    TEST_DATABASE_URL=$("$PYTHON_BIN" "$TEST_CONFIG_HELPER" \
        --port "$TEST_MYSQL_PORT" \
        --project "$TEST_PROJECT" \
        --password-from-environment)
fi

cleanup() {
    docker compose -p "$TEST_PROJECT" -f "$TEST_COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
}

trap cleanup EXIT HUP INT TERM

docker compose -p "$TEST_PROJECT" -f "$TEST_COMPOSE_FILE" up -d --wait --wait-timeout 120

cd "$TEST_ROOT"
APP_ENV=test DATABASE_URL="$TEST_DATABASE_URL" "$PYTHON_BIN" -m pytest -q backend/tests/test_api.py "$@"
