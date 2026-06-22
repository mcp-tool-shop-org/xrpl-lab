"""XRPL Lab — learn by doing, prove by artifact."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("xrpl-lab")
except PackageNotFoundError:
    # Source-checkout fallback (package not installed). MUST track
    # pyproject [project].version — the anti-drift gate in
    # tests/test_v2_core.py::test_version_matches_pyproject enforces this.
    __version__ = "2.2.0"
