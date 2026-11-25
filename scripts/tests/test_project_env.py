"""Regression tests for host-side script environment and mapping safety."""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


project_env = _load_module("project_env_for_tests", SCRIPTS / "project_env.py")
bootstrap = _load_module(
    "bootstrap_m5_test_catalog_for_tests", SCRIPTS / "bootstrap_m5_test_catalog.py"
)


def test_project_env_loads_dotenv_without_overriding_explicit_environment(monkeypatch):
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        (root / ".env").write_text(
            "DATABASE_URL=mysql://from-file\n"
            "QUOTED='a value' # note\n"
            'ESCAPED="p@ss # word\\twith\\\\slash\\\"quote"\n'
            "HASH=unquoted#hash\n"
            "COMMENTED=value \t# note\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("DATABASE_URL", "mysql://from-shell")
        monkeypatch.delenv("QUOTED", raising=False)
        monkeypatch.delenv("ESCAPED", raising=False)
        monkeypatch.delenv("HASH", raising=False)
        monkeypatch.delenv("COMMENTED", raising=False)

        loaded_path = project_env.load_project_env(root)

        assert loaded_path == root / ".env"
        assert os.environ["DATABASE_URL"] == "mysql://from-shell"
        assert os.environ["QUOTED"] == "a value"
        assert os.environ["ESCAPED"] == 'p@ss # word\twith\\slash"quote'
        assert os.environ["HASH"] == "unquoted#hash"
        assert os.environ["COMMENTED"] == "value"


def test_project_env_rejects_invalid_assignments(monkeypatch):
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        (root / ".env").write_text("not an assignment\n", encoding="utf-8")

        with pytest.raises(ValueError, match="Invalid environment assignment"):
            project_env.load_project_env(root)


def test_bootstrap_mapping_path_cannot_replace_the_m5_sales_source():
    with tempfile.TemporaryDirectory() as temporary_directory:
        sales_path = Path(temporary_directory) / "sales.csv"
        sales_path.write_text("item_id,store_id\nITEM,STORE\n", encoding="utf-8")

        with pytest.raises(ValueError, match="cannot overwrite"):
            bootstrap.validate_mapping_output_path(sales_path, sales_path, force=True)


def test_bootstrap_mapping_path_rejects_a_directory_target():
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        sales_path = root / "sales.csv"
        output_path = root / "mapping-directory"
        sales_path.write_text("item_id,store_id\nITEM,STORE\n", encoding="utf-8")
        output_path.mkdir()

        with pytest.raises(ValueError, match="regular file"):
            bootstrap.validate_mapping_output_path(sales_path, output_path, force=True)
