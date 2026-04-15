"""Tests for scripts/check_pypi_version.py — the publish-time guard
against re-uploading a version that already exists on PyPI."""

import importlib.util
import sys
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

GUARD_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_pypi_version.py"


@pytest.fixture
def guard():
    spec = importlib.util.spec_from_file_location("check_pypi_version", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exits_nonzero_when_version_already_exists(guard, capsys, monkeypatch):
    monkeypatch.setattr(guard, "fetch_existing_versions",
                        lambda repo, pkg: {"0.0.9", "0.1.0", "0.1.1"})
    monkeypatch.setattr(sys, "argv", ["check_pypi_version.py"])
    with mock.patch.dict(sys.modules):
        # Re-import visiter to inject a controlled __version__.
        fake = type(sys)("visiter")
        fake.__version__ = "0.1.0"
        sys.modules["visiter"] = fake
        rc = guard.main()
    assert rc == 1
    err = capsys.readouterr().err
    assert "already published" in err
    assert "0.1.0" in err


def test_exits_zero_when_version_is_new(guard, capsys, monkeypatch):
    monkeypatch.setattr(guard, "fetch_existing_versions",
                        lambda repo, pkg: {"0.0.9", "0.1.0"})
    monkeypatch.setattr(sys, "argv", ["check_pypi_version.py"])
    fake = type(sys)("visiter")
    fake.__version__ = "0.2.0"
    with mock.patch.dict(sys.modules, {"visiter": fake}):
        rc = guard.main()
    assert rc == 0


def test_404_treated_as_first_release(guard, monkeypatch, capsys):
    def raise_404(repo, pkg):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    monkeypatch.setattr(guard, "fetch_existing_versions", raise_404)
    monkeypatch.setattr(sys, "argv", ["check_pypi_version.py"])
    fake = type(sys)("visiter")
    fake.__version__ = "0.1.0"
    with mock.patch.dict(sys.modules, {"visiter": fake}):
        rc = guard.main()
    assert rc == 0
    assert "first release" in capsys.readouterr().out


def test_network_failure_blocks_by_default(guard, monkeypatch, capsys):
    def boom(repo, pkg):
        raise urllib.error.URLError("dns broke")
    monkeypatch.setattr(guard, "fetch_existing_versions", boom)
    monkeypatch.setattr(sys, "argv", ["check_pypi_version.py"])
    fake = type(sys)("visiter")
    fake.__version__ = "0.1.0"
    with mock.patch.dict(sys.modules, {"visiter": fake}):
        rc = guard.main()
    assert rc == 2
    assert "refusing to publish" in capsys.readouterr().err


def test_network_failure_allowed_with_flag(guard, monkeypatch):
    def boom(repo, pkg):
        raise urllib.error.URLError("dns broke")
    monkeypatch.setattr(guard, "fetch_existing_versions", boom)
    monkeypatch.setattr(sys, "argv",
                        ["check_pypi_version.py", "--allow-network-failure"])
    fake = type(sys)("visiter")
    fake.__version__ = "0.1.0"
    with mock.patch.dict(sys.modules, {"visiter": fake}):
        rc = guard.main()
    assert rc == 0
