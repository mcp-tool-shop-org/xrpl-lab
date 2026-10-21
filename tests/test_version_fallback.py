"""The source-checkout version fallback matches pyproject, and runs.

``xrpl_lab/__init__.py`` falls back to a literal when the package isn't
installed. Installed test runs never reach that line, so each release's version
bump showed as uncovered on codecov/patch; this runs the fallback for real.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import tomllib
from pathlib import Path

import xrpl_lab


def test_the_uninstalled_fallback_is_the_pyproject_version(monkeypatch) -> None:
    def _missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", _missing)
    try:
        reloaded = importlib.reload(xrpl_lab)
        pyproject = tomllib.loads(
            (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
        assert reloaded.__version__ == pyproject["project"]["version"]
    finally:
        monkeypatch.undo()
        importlib.reload(xrpl_lab)
