"""Unit tests for disposable API integration-test configuration safety."""

import importlib.util
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "test_api_integration_config.py"
SPEC = importlib.util.spec_from_file_location("api_integration_config_for_tests", SCRIPT)
config = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = config
assert SPEC.loader is not None
SPEC.loader.exec_module(config)


def test_default_url_uses_loopback_test_database_and_quotes_password():
    url = config.default_database_url("p@ss: word/with?reserved#chars", 3307)
    parsed = urlsplit(url)

    assert parsed.hostname == "127.0.0.1"
    assert parsed.port == 3307
    assert parsed.path == "/novaledger_test"
    assert parsed.username == "novaledger"
    assert unquote(parsed.password) == "p@ss: word/with?reserved#chars"


def test_explicit_url_requires_selected_loopback_test_database():
    database_url = "mysql://novaledger:password@127.0.0.1:3308/novaledger_test"

    assert config.validate_database_url(database_url, 3308) == database_url


@pytest.mark.parametrize(
    ("database_url", "message"),
    [
        (
            "mysql://novaledger:password@example.com:3307/novaledger_test",
            "127.0.0.1",
        ),
        (
            "mysql://novaledger:password@127.0.0.2:3307/novaledger_test",
            "127.0.0.1",
        ),
        (
            "mysql://novaledger:password@127.0.0.1:3308/novaledger_test",
            "match TEST_MYSQL_PORT",
        ),
        (
            "mysql://novaledger:password@127.0.0.1:3307/novaledger",
            "database must be novaledger_test",
        ),
        (
            "mysql://root:password@127.0.0.1:3307/novaledger_test",
            "novaledger user",
        ),
    ],
)
def test_explicit_url_rejects_non_isolated_targets(database_url, message):
    with pytest.raises(ValueError, match=message):
        config.validate_database_url(database_url, 3307)


@pytest.mark.parametrize(
    "project",
    ["novaledger-api-test", "novaledger-api-test-ci1", "novaledger-api-test-ci_2"],
)
def test_project_name_allows_only_test_namespace(project):
    assert config.validate_compose_project(project) == project


@pytest.mark.parametrize("project", ["novaledger", "NovaLedger-api-test", "api-test"])
def test_project_name_rejects_non_test_namespace(project):
    with pytest.raises(ValueError, match="TEST_COMPOSE_PROJECT"):
        config.validate_compose_project(project)
