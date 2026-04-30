"""Schema drift detection — ensures TS interfaces match Python models.

Reads site/src/lib/api.ts and extracts interface field NAMES + TYPES.
Compares them against the Pydantic model fields and annotations.
Fails if the field sets diverge OR if any shared field has a
backward-incompatible type change (e.g. ``int`` → ``str``,
``Optional[X]`` → ``X``).  See F-TESTS-007.
"""

from __future__ import annotations

import re
import types
import typing
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


def _strip_nested_braces(body: str) -> str:
    """Replace inline ``{ ... }`` blocks with a placeholder so top-level
    field types stay parseable while nested objects are flattened."""
    cleaned = body
    while True:
        reduced = re.sub(r"\{[^{}]*\}", "__OBJECT__", cleaned)
        if reduced == cleaned:
            break
        cleaned = reduced
    return cleaned


def _extract_ts_interface_fields(source: str, interface_name: str) -> set[str]:
    """Extract top-level field names from a TypeScript interface definition.

    Skips fields inside nested object types (e.g. inline { ... } blocks).
    """
    body = _extract_ts_interface_body(source, interface_name)
    if not body:
        return set()
    cleaned = _strip_nested_braces(body)
    fields = re.findall(r"(\w+)\s*\??:", cleaned)
    return set(fields)


def _extract_ts_interface_field_types(
    source: str, interface_name: str,
) -> dict[str, tuple[str, bool]]:
    """Extract top-level field types from a TypeScript interface.

    Returns ``{field_name: (type_str, optional)}`` where ``optional`` is True
    when the TS field is declared with ``?:`` (it may also be inferred from
    a ``| null`` union).  Type strings are normalised via ``_normalise_ts``.
    """
    body = _extract_ts_interface_body(source, interface_name)
    if not body:
        return {}
    cleaned = _strip_nested_braces(body)

    # Match: name (?): TYPE ; or end-of-line.  Type is everything up to ';'
    # or newline at the same nesting level (we already collapsed nested braces).
    out: dict[str, tuple[str, bool]] = {}
    for match in re.finditer(
        r"(\w+)\s*(\??)\s*:\s*([^;\n]+?)\s*;", cleaned + ";",
    ):
        name = match.group(1)
        optional = match.group(2) == "?"
        raw_type = match.group(3).strip()
        out[name] = (_normalise_ts(raw_type), optional)
    return out


def _normalise_ts(ts_type: str) -> str:
    """Reduce a TS type string to a canonical comparable form.

    The goal is to catch backward-incompatible type changes
    (``int → str``, ``Optional[X] → X``) without forcing a perfect
    TS↔Python type equivalence.
    """
    t = ts_type.strip()
    # Drop trailing array brackets — we'll capture them once.
    is_array = False
    while t.endswith("[]"):
        is_array = True
        t = t[:-2].strip()
    # Array<X> form
    arr_match = re.match(r"^Array<\s*(.+)\s*>$", t)
    if arr_match:
        is_array = True
        t = arr_match.group(1).strip()

    # Split on '|' for unions, normalise each part.
    parts = [p.strip() for p in re.split(r"\|", t)]
    has_null = "null" in parts or "undefined" in parts
    parts = [p for p in parts if p not in ("null", "undefined")]

    # TS primitive type keywords we keep verbatim — anything else that's
    # a bare identifier (e.g. ``TrackProgressItem``) is a reference to a
    # custom interface and collapses to ``"object"`` so it lines up with
    # the Pydantic BaseModel-subclass collapse on the Python side.
    _TS_PRIMITIVES = {
        "string", "number", "boolean", "any", "unknown", "void",
        "bigint", "symbol", "never", "object",
    }

    def _norm_atom(p: str) -> str:
        # Trim quotes for string-literal types — they collapse to "string".
        if (p.startswith("'") and p.endswith("'")) or (
            p.startswith('"') and p.endswith('"')
        ):
            return "string"
        # Collapse our placeholder to "object".
        if p == "__OBJECT__":
            return "object"
        # Bare identifier that isn't a TS primitive ⇒ custom interface ref.
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", p) and p not in _TS_PRIMITIVES:
            return "object"
        return p

    parts = sorted({_norm_atom(p) for p in parts})
    base = "|".join(parts) if parts else "any"
    if is_array:
        base = f"list[{base}]"
    if has_null:
        base = f"{base}|null"
    return base


def _pydantic_fields(model) -> set[str]:
    """Get field names from a Pydantic model class."""
    return set(model.model_fields.keys())


def _normalise_py(annotation: object) -> str:
    """Reduce a Python type annotation to the same canonical form as TS.

    Handles ``Optional[X]`` / ``X | None`` (→ trailing ``|null``),
    ``list[X]`` (→ ``list[X]``), unions, primitives, and custom classes
    (collapsed to ``object`` since we already verify field-name parity
    inside nested models elsewhere).
    """
    return _norm_py_inner(annotation, top=True)


def _norm_py_inner(annotation: object, top: bool = False) -> str:
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # Optional/Union handling
    if origin in (typing.Union, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        has_null = len(non_none) != len(args)
        norm_parts = sorted({_norm_py_inner(a) for a in non_none})
        base = "|".join(norm_parts) if norm_parts else "any"
        return f"{base}|null" if has_null else base

    # list[X] / List[X]
    if origin in (list, typing.List):  # noqa: UP006
        if args:
            inner = _norm_py_inner(args[0])
        else:
            inner = "any"
        return f"list[{inner}]"

    # dict[X, Y]
    if origin in (dict, typing.Dict):  # noqa: UP006
        return "object"

    # Primitives
    if annotation is str:
        return "string"
    if annotation is bool:
        return "boolean"
    if annotation is int or annotation is float:
        return "number"
    if annotation is type(None):
        return "null"

    # BaseModel subclasses / dataclasses / etc → "object" (TS shows them as
    # inline ``{ ... }`` which we collapsed to "object" too).
    return "object"


def _pydantic_field_types(model) -> dict[str, str]:
    """Return ``{field_name: normalised_type}`` for a Pydantic model."""
    return {
        name: _normalise_py(field.annotation)
        for name, field in model.model_fields.items()
    }


def _shared_field_type_drift(
    ts_types: dict[str, tuple[str, bool]],
    py_types: dict[str, str],
) -> list[str]:
    """Return drift descriptions for fields present in BOTH sides.

    A field drifts when the normalised TS type doesn't match the normalised
    Python type.  Optional flags are folded into the type (``X | null``)
    before comparison so ``Optional[X] → X`` is also caught.
    """
    drifts: list[str] = []
    for name in sorted(set(ts_types) & set(py_types)):
        ts_type, ts_optional = ts_types[name]
        # Fold the ``?:`` flag into the TS type as a trailing ``|null``,
        # so a field declared ``foo?: string`` matches Python
        # ``foo: str | None`` but not Python ``foo: str``.
        ts_full = ts_type if ts_type.endswith("|null") else (
            f"{ts_type}|null" if ts_optional else ts_type
        )
        py_type = py_types[name]
        if ts_full != py_type:
            drifts.append(f"{name}: TS={ts_full!r} vs Python={py_type!r}")
    return drifts


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


class TestTsPythonTypeDrift:
    """F-TESTS-007: comparator must catch backward-incompatible type changes
    on fields present in BOTH the TS interface and the Pydantic model — not
    just field-name additions/removals."""

    def _ts_source(self) -> str:
        assert TS_PATH.exists(), f"api.ts not found at {TS_PATH}"
        return TS_PATH.read_text(encoding="utf-8")

    def test_status_field_types_match(self) -> None:
        ts_types = _extract_ts_interface_field_types(self._ts_source(), "Status")
        py_types = _pydantic_field_types(StatusResponse)
        drifts = _shared_field_type_drift(ts_types, py_types)
        assert not drifts, "Status type drift:\n  " + "\n  ".join(drifts)

    def test_module_summary_field_types_match(self) -> None:
        ts_types = _extract_ts_interface_field_types(self._ts_source(), "ModuleSummary")
        py_types = _pydantic_field_types(ModuleSummary)
        drifts = _shared_field_type_drift(ts_types, py_types)
        assert not drifts, "ModuleSummary type drift:\n  " + "\n  ".join(drifts)

    def test_module_detail_field_types_match(self) -> None:
        # ModuleDetail extends ModuleSummary in TS; merge both for the
        # full TS type map.
        ts_detail = _extract_ts_interface_field_types(self._ts_source(), "ModuleDetail")
        ts_summary = _extract_ts_interface_field_types(self._ts_source(), "ModuleSummary")
        ts_types = {**ts_summary, **ts_detail}
        py_types = _pydantic_field_types(ModuleDetail)
        drifts = _shared_field_type_drift(ts_types, py_types)
        assert not drifts, "ModuleDetail type drift:\n  " + "\n  ".join(drifts)

    def test_doctor_field_types_match(self) -> None:
        ts_types = _extract_ts_interface_field_types(self._ts_source(), "DoctorResult")
        py_types = _pydantic_field_types(DoctorResponse)
        drifts = _shared_field_type_drift(ts_types, py_types)
        assert not drifts, "Doctor type drift:\n  " + "\n  ".join(drifts)

    def test_report_field_types_match(self) -> None:
        ts_types = _extract_ts_interface_field_types(self._ts_source(), "Report")
        py_types = _pydantic_field_types(ReportSummary)
        drifts = _shared_field_type_drift(ts_types, py_types)
        assert not drifts, "Report type drift:\n  " + "\n  ".join(drifts)
