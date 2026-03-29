"""Audit engine — batch verify transactions and produce reports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .transport.base import Transport, TxInfo

# ── Failure reason codes ─────────────────────────────────────────────

NOT_FOUND = "NOT_FOUND"
NOT_VALIDATED = "NOT_VALIDATED"
ENGINE_RESULT_MISMATCH = "ENGINE_RESULT_MISMATCH"
TYPE_DISALLOWED = "TYPE_DISALLOWED"
MEMO_MISSING = "MEMO_MISSING"
FIELD_MISMATCH = "FIELD_MISMATCH"


# ── Data structures ──────────────────────────────────────────────────


@dataclass
class AuditConfig:
    """Configuration for an audit run."""

    require_validated: bool = True
    require_success: bool = True
    memo_prefix: str = ""
    types_allowed: list[str] | None = None
    overrides: dict[str, dict] = field(default_factory=dict)


@dataclass
class AuditVerdict:
    """Result of auditing a single transaction."""

    txid: str
    status: str  # "pass", "fail", "not_found"
    checks: list[str]
    failures: list[str]
    failure_reasons: list[str]
    tx_info: TxInfo | None = None


@dataclass
class AuditReport:
    """Full audit report with all verdicts and metadata."""

    verdicts: list[AuditVerdict]
    config: AuditConfig
    endpoint: str
    tool_version: str
    timestamp: str

    @property
    def total(self) -> int:
        return len(self.verdicts)

    @property
    def passed(self) -> int:
        return sum(1 for v in self.verdicts if v.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for v in self.verdicts if v.status == "fail")

    @property
    def not_found(self) -> int:
        return sum(1 for v in self.verdicts if v.status == "not_found")

    def failure_summary(self) -> dict[str, int]:
        """Count failure reasons across all verdicts."""
        counts: dict[str, int] = {}
        for v in self.verdicts:
            for reason in v.failure_reasons:
                counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))


# ── Parsing ──────────────────────────────────────────────────────────


def parse_txids_file(path: Path) -> list[str]:
    """Parse a txids file — one txid per line, ignore blanks and # comments."""
    txids: list[str] = []
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        txids.append(stripped)
    return txids


def parse_txids_list(txids_raw: list[str]) -> list[str]:
    """Filter a list of txid strings (ignore blanks)."""
    return [t.strip() for t in txids_raw if t.strip()]


def parse_expectations(path: Path) -> AuditConfig:
    """Parse an expectations JSON file into AuditConfig."""
    data = json.loads(path.read_text(encoding="utf-8"))
    defaults = data.get("defaults", {})
    config = AuditConfig(
        require_validated=defaults.get("require_validated", True),
        require_success=defaults.get("require_success", True),
        memo_prefix=defaults.get("memo_prefix", ""),
        types_allowed=defaults.get("types_allowed"),
        overrides=data.get("overrides", {}),
    )
    return config


# ── Verdict logic ────────────────────────────────────────────────────


def audit_tx(tx: TxInfo, config: AuditConfig) -> AuditVerdict:
    """Audit a single fetched transaction against config."""
    checks: list[str] = []
    failures: list[str] = []
    reasons: list[str] = []

    # Get per-tx overrides
    override = config.overrides.get(tx.txid, {})
    require_success = override.get("require_success", config.require_success)
    require_validated = override.get("require_validated", config.require_validated)
    expected_result = override.get("expected_engine_result")
    memo_prefix = override.get("memo_prefix", config.memo_prefix)
    types_allowed = override.get("types_allowed", config.types_allowed)

    # Check: tx fetched (not a fetch error)
    if tx.result_code.startswith("fetch_error"):
        failures.append(f"Transaction not found: {tx.result_code}")
        reasons.append(NOT_FOUND)
        return AuditVerdict(
            txid=tx.txid,
            status="not_found",
            checks=checks,
            failures=failures,
            failure_reasons=reasons,
            tx_info=tx,
        )

    checks.append(f"Transaction exists: {tx.txid[:16]}...")

    # Check: validated
    if require_validated:
        if tx.validated:
            checks.append("Transaction is validated")
        else:
            failures.append("Transaction is NOT validated")
            reasons.append(NOT_VALIDATED)

    # Check: result code
    if expected_result:
        # Expecting a specific result (e.g. tecPATH_DRY for expected failures)
        if tx.result_code == expected_result:
            checks.append(f"Result code matches expected: {expected_result}")
        else:
            failures.append(
                f"Result code mismatch: expected {expected_result}, "
                f"got {tx.result_code}"
            )
            reasons.append(ENGINE_RESULT_MISMATCH)
    elif require_success:
        if tx.result_code == "tesSUCCESS":
            checks.append("Result: tesSUCCESS")
        else:
            failures.append(f"Expected tesSUCCESS, got {tx.result_code}")
            reasons.append(ENGINE_RESULT_MISMATCH)

    # Check: transaction type
    if types_allowed:
        if tx.tx_type in types_allowed:
            checks.append(f"Type: {tx.tx_type} (allowed)")
        else:
            failures.append(
                f"Type {tx.tx_type} not in allowed list: "
                f"{', '.join(types_allowed)}"
            )
            reasons.append(TYPE_DISALLOWED)
    elif tx.tx_type:
        checks.append(f"Type: {tx.tx_type}")

    # Check: memo prefix
    if memo_prefix:
        memos = tx.memos or []
        has_prefix = any(m.startswith(memo_prefix) for m in memos)
        if has_prefix:
            checks.append(f"Memo prefix '{memo_prefix}' found")
        else:
            memo_display = ", ".join(memos) if memos else "(none)"
            failures.append(
                f"Expected memo prefix '{memo_prefix}', "
                f"found: {memo_display}"
            )
            reasons.append(MEMO_MISSING)

    # Record basic fields
    if tx.account:
        checks.append(f"Account: {tx.account}")
    if tx.destination:
        checks.append(f"Destination: {tx.destination}")
    if tx.fee:
        checks.append(f"Fee: {tx.fee} drops")

    status = "pass" if not failures else "fail"
    return AuditVerdict(
        txid=tx.txid,
        status=status,
        checks=checks,
        failures=failures,
        failure_reasons=reasons,
        tx_info=tx,
    )


# ── Audit runner ─────────────────────────────────────────────────────


async def run_audit(
    transport: Transport,
    txids: list[str],
    config: AuditConfig | None = None,
    endpoint: str = "",
) -> AuditReport:
    """Run audit on a list of txids. Returns AuditReport."""
    if config is None:
        config = AuditConfig()

    verdicts: list[AuditVerdict] = []
    for txid in txids:
        tx = await transport.fetch_tx(txid)
        verdict = audit_tx(tx, config)
        verdicts.append(verdict)

    net_info = await transport.get_network_info()
    return AuditReport(
        verdicts=verdicts,
        config=config,
        endpoint=endpoint or net_info.rpc_url,
        tool_version=__version__,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


# ── Report generation ────────────────────────────────────────────────


def write_audit_report_md(report: AuditReport, path: Path) -> Path:
    """Write a markdown audit report."""
    lines: list[str] = []
    lines.append("# XRPL Lab Audit Report\n")
    lines.append(f"- **Tool version**: {report.tool_version}")
    lines.append(f"- **Endpoint**: {report.endpoint}")
    lines.append(f"- **Timestamp**: {report.timestamp}")
    lines.append(f"- **Transactions**: {report.total}")
    lines.append(
        f"- **Results**: {report.passed} pass, "
        f"{report.failed} fail, {report.not_found} not found"
    )
    lines.append("")

    # Failure summary
    summary = report.failure_summary()
    if summary:
        lines.append("## Failure Reasons\n")
        for reason, count in summary.items():
            lines.append(f"- {reason}: {count}")
        lines.append("")

    # Per-tx details
    lines.append("## Transaction Details\n")
    lines.append("| TXID | Status | Type | Result | Failures |")
    lines.append("|------|--------|------|--------|----------|")

    for v in report.verdicts:
        txid_short = v.txid[:16] + "..."
        tx_type = v.tx_info.tx_type if v.tx_info else ""
        result_code = v.tx_info.result_code if v.tx_info else ""
        fail_text = "; ".join(v.failure_reasons) if v.failure_reasons else "-"
        status_icon = {
            "pass": "PASS",
            "fail": "FAIL",
            "not_found": "NOT_FOUND",
        }.get(v.status, v.status)
        lines.append(
            f"| {txid_short} | {status_icon} | {tx_type} "
            f"| {result_code} | {fail_text} |"
        )

    lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_audit_report_csv(report: AuditReport, path: Path) -> Path:
    """Write a CSV audit report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "txid", "status", "tx_type", "result_code",
        "account", "destination", "fee", "validated",
        "failure_reasons",
    ])

    for v in report.verdicts:
        tx = v.tx_info
        writer.writerow([
            v.txid,
            v.status,
            tx.tx_type if tx else "",
            tx.result_code if tx else "",
            tx.account if tx else "",
            tx.destination if tx else "",
            tx.fee if tx else "",
            str(tx.validated) if tx else "",
            "; ".join(v.failure_reasons),
        ])

    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def write_audit_pack(report: AuditReport, path: Path) -> Path:
    """Write a JSON audit pack with sha256 integrity hash.

    Integrity verification procedure:
      1. Read the file and parse JSON.
      2. Set ``pack["integrity_sha256"] = ""``.
      3. Serialize with ``json.dumps(pack, sort_keys=True, indent=2)``.
      4. Compute ``hashlib.sha256(serialization.encode()).hexdigest()``.
      5. Compare to the original ``integrity_sha256`` value.
    """
    pack: dict = {
        "tool": "xrpl-lab",
        "version": report.tool_version,
        "endpoint": report.endpoint,
        "timestamp": report.timestamp,
        "summary": {
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "not_found": report.not_found,
        },
        "failure_reasons": report.failure_summary(),
        "verdicts": [],
    }

    for v in report.verdicts:
        entry: dict = {
            "txid": v.txid,
            "status": v.status,
            "checks": v.checks,
            "failures": v.failures,
            "failure_reasons": v.failure_reasons,
        }
        if v.tx_info:
            entry["tx"] = {
                "tx_type": v.tx_info.tx_type,
                "account": v.tx_info.account,
                "destination": v.tx_info.destination,
                "amount": v.tx_info.amount,
                "fee": v.tx_info.fee,
                "result_code": v.tx_info.result_code,
                "ledger_index": v.tx_info.ledger_index,
                "validated": v.tx_info.validated,
                "memos": v.tx_info.memos,
            }
        pack["verdicts"].append(entry)

    # Compute integrity hash using sentinel approach so the hash is
    # externally verifiable without reading the source code.
    # Verification: set integrity_sha256="" in parsed dict, serialize
    # with sort_keys=True, indent=2, hash, compare.
    pack["integrity_sha256"] = ""
    canonical = json.dumps(pack, indent=2, sort_keys=True)
    sha = hashlib.sha256(canonical.encode()).hexdigest()
    pack["integrity_sha256"] = sha

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(pack, indent=2, sort_keys=True), encoding="utf-8"
    )
    return path
