"""Schema drift detection — ensures TS interfaces match Python models.

Reads site/src/lib/api.ts and extracts interface field names.
Compares them against the Pydantic model fields from schemas.py.
Fails if the sets diverge.
"""

import re
from pathlib import Path

from xrpl_lab.api.schemas import (
    DoctorResponse,
    ModuleDetail,
    ModuleSummary,
    ReportSummary,
    StatusResponse,
)


def _extract_ts_interface_body(source: str, interface_name: str) -> str:
    """Extract the body of a TS interface, handling nested braces."""
    pattern = rf"export\s+interface\s+{interface_name}\s*(?:extends\s+\w+\s*)?\{{"
    match = re.search(pattern, source)
    if not match:
        return ""
    start = match.end()
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    return source[start : i - 1]


def _extract_ts_interface_fields(source: str, interface_name: str) -> set[str]:
    """Extract top-level field names from a TypeScript interface definition.

    Skips fields inside nested object types (e.g. inline { ... } blocks).
    """
    body = _extract_ts_interface_body(source, interface_name)
    if not body:
        return set()

    # Strip nested brace blocks so we only see top-level fields
    # Replace nested { ... } with empty string, iteratively
    cleaned = body
    while True:
        # Remove innermost { ... } blocks (no nested braces inside)
        reduced = re.sub(r"\{[^{}]*\}", "", cleaned)
        if reduced == cleaned:
            break
        cleaned = reduced

    # Now extract field names at top level (word before ':' or '?:')
    fields = re.findall(r"(\w+)\s*\??:", cleaned)
    return set(fields)


def _pydantic_fields(model) -> set[str]:
    """Get field names from a Pydantic model class."""
    return set(model.model_fields.keys())


TS_PATH = Path(__file__).resolve().parent.parent / "site" / "src" / "lib" / "api.ts"


class TestTsPythonDrift:
    """TS interfaces must match Python schema fields."""

    def _ts_source(self) -> str:
        assert TS_PATH.exists(), f"api.ts not found at {TS_PATH}"
        return TS_PATH.read_text(encoding="utf-8")

    def test_status_fields_match(self) -> None:
        ts = _extract_ts_interface_fields(self._ts_source(), "Status")
        py = _pydantic_fields(StatusResponse)
        assert ts == py, f"Status drift: TS-only={ts - py}, Python-only={py - ts}"

    def test_module_summary_fields_match(self) -> None:
        ts = _extract_ts_interface_fields(self._ts_source(), "ModuleSummary")
        py = _pydantic_fields(ModuleSummary)
        # TS may have optional 'description' that Python summary omits — check Python subset
        missing_in_ts = py - ts
        assert not missing_in_ts, f"ModuleSummary drift — missing in TS: {missing_in_ts}"

    def test_module_detail_fields_match(self) -> None:
        ts = _extract_ts_interface_fields(self._ts_source(), "ModuleDetail")
        py = _pydantic_fields(ModuleDetail)
        # ModuleDetail extends ModuleSummary in TS, so combine
        ts_summary = _extract_ts_interface_fields(self._ts_source(), "ModuleSummary")
        ts_combined = ts | ts_summary
        missing_in_ts = py - ts_combined
        assert not missing_in_ts, f"ModuleDetail drift — missing in TS: {missing_in_ts}"

    def test_doctor_fields_match(self) -> None:
        ts = _extract_ts_interface_fields(self._ts_source(), "DoctorResult")
        py = _pydantic_fields(DoctorResponse)
        assert ts == py, f"Doctor drift: TS-only={ts - py}, Python-only={py - ts}"

    def test_report_fields_match(self) -> None:
        ts = _extract_ts_interface_fields(self._ts_source(), "Report")
        py = _pydantic_fields(ReportSummary)
        assert ts == py, f"Report drift: TS-only={ts - py}, Python-only={py - ts}"
