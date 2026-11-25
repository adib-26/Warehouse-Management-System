"""Validate configuration for the disposable API integration database.

This module deliberately keeps the integration-test runner on a database that
is both local and named for tests.  It is small enough to run before Docker is
started and has no project dependencies beyond the Python standard library.
"""

from __future__ import annotations

import argparse
import os
import re
from urllib.parse import quote, urlsplit


TEST_DATABASE_NAME = "novaledger_test"
TEST_DATABASE_USER = "novaledger"
PROJECT_PATTERN = re.compile(
    r"novaledger-api-test(?:-[a-z0-9][a-z0-9_-]*)?"
)


def validate_port(value: int | str) -> int:
    """Return a valid TCP port, rejecting accidental shell/config mistakes."""

    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("TEST_MYSQL_PORT must be an integer between 1 and 65535") from exc
    if not 1 <= port <= 65_535:
        raise ValueError("TEST_MYSQL_PORT must be an integer between 1 and 65535")
    return port


def default_database_url(password: str, port: int | str) -> str:
    """Build the local disposable-database URL with a safely quoted password."""

    return (
        f"mysql://{TEST_DATABASE_USER}:{quote(password, safe='')}"
        f"@127.0.0.1:{validate_port(port)}/{TEST_DATABASE_NAME}"
    )


def validate_database_url(database_url: str, port: int | str) -> str:
    """Require an explicit URL to retain the runner's database isolation."""

    expected_port = validate_port(port)
    try:
        parsed = urlsplit(database_url)
        actual_port = parsed.port
    except ValueError as exc:
        raise ValueError("TEST_DATABASE_URL must contain a valid numeric port") from exc

    if parsed.scheme != "mysql":
        raise ValueError("TEST_DATABASE_URL must use the mysql scheme")
    if parsed.username != TEST_DATABASE_USER:
        raise ValueError(f"TEST_DATABASE_URL must use the {TEST_DATABASE_USER} user")
    if parsed.hostname is None:
        raise ValueError("TEST_DATABASE_URL must include a loopback host")
    # docker-compose.test.yml exposes MySQL only on this exact address.  Being
    # stricter than a generic loopback check prevents an override from reaching
    # another local service bound to 127/8 or IPv6 on the same selected port.
    if parsed.hostname != "127.0.0.1":
        raise ValueError("TEST_DATABASE_URL host must be 127.0.0.1")
    if actual_port != expected_port:
        raise ValueError("TEST_DATABASE_URL port must match TEST_MYSQL_PORT")
    if parsed.path != f"/{TEST_DATABASE_NAME}":
        raise ValueError(f"TEST_DATABASE_URL database must be {TEST_DATABASE_NAME}")
    if parsed.query or parsed.fragment:
        raise ValueError("TEST_DATABASE_URL cannot contain a query or fragment")
    return database_url


def validate_compose_project(project: str) -> str:
    """Keep cleanup scoped to a clearly test-only Compose project."""

    if not PROJECT_PATTERN.fullmatch(project):
        raise ValueError(
            "TEST_COMPOSE_PROJECT must be novaledger-api-test or begin with "
            "novaledger-api-test- and contain only lowercase letters, digits, "
            "hyphens, or underscores"
        )
    return project


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the disposable NovaLedger API integration-test configuration."
    )
    parser.add_argument("--port", required=True, help="Disposable MySQL host port")
    parser.add_argument(
        "--password-from-environment",
        action="store_true",
        help="Construct a default URL from TEST_MYSQL_PASSWORD",
    )
    parser.add_argument(
        "--url-from-environment",
        action="store_true",
        help="Validate TEST_DATABASE_URL without placing it in the process arguments",
    )
    parser.add_argument("--project", required=True, help="Disposable Docker Compose project")
    args = parser.parse_args()

    if args.password_from_environment == args.url_from_environment:
        parser.error(
            "provide exactly one of --password-from-environment or "
            "--url-from-environment"
        )

    try:
        validate_compose_project(args.project)
        database_url = (
            default_database_url(os.environ.get("TEST_MYSQL_PASSWORD", ""), args.port)
            if args.password_from_environment
            else validate_database_url(os.environ.get("TEST_DATABASE_URL", ""), args.port)
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(database_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
