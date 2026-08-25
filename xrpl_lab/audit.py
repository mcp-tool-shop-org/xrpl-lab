"""Audit engine — batch verify transactions and produce reports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import click

from . import __version__

# _atomic_write_text (F-55604e7e) + sanitize_endpoint (RA-002 / F-60b2df48)
# are shared with the proof-pack writers so both artifact families strip
# credentials and replace atomically with ONE implementation. reporting.py
# never imports audit — no cycle.
from .reporting import _atomic_write_text, sanitize_endpoint
from .state import WORKSPACE_DIR_MODE, _ensure_dir_mode
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
    # CL-001: provenance. True when the audit ran against the offline
    # DryRunTransport (fabricated tesSUCCESS/validated verdicts), NOT a live
    # ledger. Defaults False so every existing constructor keeps the real
    # (on-ledger) pack shape unchanged.
    dry_run: bool = False
    # RA-001 (F-a8db1a2d): the CLASSIFIED network the audit actually ran
    # against, populated by run_audit from the transport's own
    # get_network_info(). The writers used to hardcode 'testnet' here — but
    # audit is a READ path with no network guard and XRPL_LAB_RPC_URL supports
    # devnet/local (and, for reads, even mainnet) overrides, so a hash-sealed
    # audit pack could claim network=testnet while its own sealed endpoint
    # contradicted it. Defaults 'testnet' only for direct constructors that
    # predate the field; every run_audit-produced report carries the truth.
    network: str = "testnet"

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


# RA-007 (F-6b3c9205): accepted txid shapes. Real XRPL txids are strictly
# 64-hex; dry-run fixture ids (TX1, TX_FAIL_1, DRYRUN-...) get a permissive
# letters/digits/_/- shape. Both alphabets exclude every spreadsheet-formula
# metacharacter except a leading '-' (which the CSV writer defuses), so a
# hostile line like ``=HYPERLINK("http://evil","ok")`` or ``=cmd|' /C calc'!A0``
# is rejected at parse time instead of riding into a report.
_TXID_SHAPE = re.compile(r"[0-9A-Za-z_-]{1,128}")


def parse_txids_file(path: Path) -> list[str]:
    """Parse a txids file — one txid per line, ignore blanks and # comments.

    RA-007: every non-comment line must look like a txid (64-hex) or a
    dry-run fixture id (letters/digits/_/-, max 128 chars). The realistic
    audit flow is a FACILITATOR feeding a LEARNER-SUBMITTED txids file to
    ``xrpl-lab audit``; rejecting malformed lines here both blocks CSV
    formula-injection payloads and surfaces pasted garbage early.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise click.ClickException(f"Cannot read txids file: {path}: {e}") from e
    txids: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not _TXID_SHAPE.fullmatch(stripped):
            raise click.ClickException(
                f"Invalid txid on line {lineno} of {path.name}: "
                f"{stripped[:40]!r} — txids are 64 hex characters (dry-run "
                "fixture ids may use letters, digits, '_' and '-'). Remove or "
                "fix the line and re-run."
            )
        txids.append(stripped)
    return txids


def parse_txids_list(txids_raw: list[str]) -> list[str]:
    """Filter a list of txid strings (ignore blanks)."""
    return [t.strip() for t in txids_raw if t.strip()]


def parse_expectations(path: Path) -> AuditConfig:
    """Parse an expectations JSON file into AuditConfig."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise click.ClickException(f"Cannot read expectations file: {path}: {e}") from e
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Invalid JSON in expectations file: {path}: {e}") from e
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

    # Check: tx fetched (not a fetch/network error)
    # A network/read-back failure populates tx.fetch_error (live path) or, for
    # batch/fixture inputs, carries a "fetch_error: ..." result_code. The tx may
    # still have succeeded on-ledger; surface the network reason rather than
    # attributing the fault to the transaction itself.
    fetch_error = getattr(tx, "fetch_error", None)
    if fetch_error or tx.result_code.startswith("fetch_error"):
        detail = fetch_error or tx.result_code
        failures.append(
            f"Could not fetch transaction to verify (network issue): {detail}"
        )
        reasons.append(NOT_FOUND)
        return AuditVerdict(
            txid=tx.txid,
            status="not_found",
            checks=checks,
            failures=failures,
            failure_reasons=reasons,
            tx_info=tx,
        )

    # Empty result_code with no validated flag means the fetch returned
    # an incomplete or error response — treat as not found.
    if tx.result_code == "" and not tx.validated:
        failures.append("Transaction not found or fetch error (empty result code)")
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
    on_progress=None,
    dry_run: bool = False,
) -> AuditReport:
    """Run audit on a list of txids. Returns AuditReport.

    Args:
        on_progress: optional callable(i, total, txid) called before each fetch,
                     where i is 1-based index.
        dry_run: CL-001 provenance. When True the audit ran against the offline
                 DryRunTransport (fabricated verdicts) — sealed into the pack
                 hash and surfaced as a SIMULATED banner in reports.
    """
    if config is None:
        config = AuditConfig()

    verdicts: list[AuditVerdict] = []
    total = len(txids)
    for i, txid in enumerate(txids):
        if on_progress is not None:
            on_progress(i + 1, total, txid)
        tx = await transport.fetch_tx(txid)
        verdict = audit_tx(tx, config)
        verdicts.append(verdict)

    net_info = await transport.get_network_info()
    return AuditReport(
        verdicts=verdicts,
        config=config,
        # RA-002: strip credentials/query BEFORE the endpoint can reach any
        # hashed pack or shareable report — a credentialed XRPL_LAB_RPC_URL
        # (basic-auth userinfo, path tokens, ?api_key=) must never be sealed.
        endpoint=sanitize_endpoint(endpoint or net_info.rpc_url),
        tool_version=__version__,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        dry_run=dry_run,
        # RA-001: seal the network the transport ACTUALLY classified — an
        # audit against devnet/local/mainnet must not be labeled 'testnet'.
        # A dry-run audit is labeled honestly as such.
        network="dry-run" if dry_run else (net_info.network or "unknown"),
    )


# ── Report generation ────────────────────────────────────────────────


def write_audit_report_md(report: AuditReport, path: Path) -> Path:
    """Write a markdown audit report."""
    lines: list[str] = []
    lines.append("# XRPL Lab Audit Report\n")
    # CL-001: a dry-run audit is NOT a proof — the offline transport fabricates
    # tesSUCCESS/validated for any txid. Mark it unmistakably so a simulated
    # report is never mistaken for an on-ledger one in a shareable handoff.
    if report.dry_run:
        lines.append(
            "> **⚠ SIMULATED — not on-ledger, not a proof.** This report was "
            "produced with `--dry-run` (offline sandbox). Verdicts are "
            "fabricated by the local transport and prove nothing about the "
            "real XRPL ledger. Re-run without `--dry-run` on testnet for a "
            "genuine audit.\n"
        )
    lines.append(f"- **Tool version**: {report.tool_version}")
    # RA-001: report the classified network the audit ran against, never a
    # hardcoded 'testnet' — a devnet/local/mainnet read must be labeled
    # honestly in a shareable report.
    lines.append(
        f"- **Network**: "
        f"{'dry-run (SIMULATED)' if report.dry_run else report.network}"
    )
    # RA-002: belt-and-braces — run_audit already sanitizes, but a directly
    # constructed report must not leak a credentialed endpoint either.
    lines.append(f"- **Endpoint**: {sanitize_endpoint(report.endpoint)}")
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

    # DD-1: audit reports are workshop-shareable (facilitator handoff,
    # no secrets per threat model). 0o755.
    _ensure_dir_mode(path.parent, WORKSPACE_DIR_MODE)
    # F-55604e7e: atomic replace — never leave a truncated report behind.
    _atomic_write_text(path, "\n".join(lines))
    return path


def _csv_defuse(value: str) -> str:
    """Neutralize spreadsheet formula injection in a CSV cell (RA-007).

    A cell beginning with ``= + - @`` (or a tab/CR) executes as a formula when
    the CSV is opened in Excel / LibreOffice / Sheets. Prefixing a single
    quote makes the cell render as text. Applied to every data cell — the
    txid column is the attacker-controlled one (parse-time validation is the
    first gate), but ledger-sourced columns get the same defensive treatment.
    """
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def write_audit_report_csv(report: AuditReport, path: Path) -> Path:
    """Write a CSV audit report."""
    # DD-1: audit reports are workshop-shareable. 0o755.
    _ensure_dir_mode(path.parent, WORKSPACE_DIR_MODE)
    buf = io.StringIO()
    # CL-001: prepend a comment banner when the audit was simulated so a
    # shared CSV can't be mistaken for on-ledger evidence. Leading '#' keeps
    # it out of the parsed data for spreadsheet/skiprows consumers.
    if report.dry_run:
        buf.write(
            "# SIMULATED — not on-ledger, not a proof. "
            "Produced with --dry-run (offline sandbox); verdicts are "
            "fabricated and prove nothing about the real XRPL ledger.\n"
        )
    writer = csv.writer(buf)
    writer.writerow([
        "txid", "status", "tx_type", "result_code",
        "account", "destination", "fee", "validated",
        "failure_reasons",
    ])

    for v in report.verdicts:
        tx = v.tx_info
        # RA-007: defuse every cell against formula injection.
        writer.writerow([
            _csv_defuse(str(cell))
            for cell in (
                v.txid,
                v.status,
                tx.tx_type if tx else "",
                tx.result_code if tx else "",
                tx.account if tx else "",
                tx.destination if tx else "",
                tx.fee if tx else "",
                str(tx.validated) if tx else "",
                "; ".join(v.failure_reasons),
            )
        ])

    # F-55604e7e: atomic replace — never leave a truncated CSV behind.
    _atomic_write_text(path, buf.getvalue())
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
        # RA-002: sanitized (scheme://host[:port] only) BEFORE hashing —
        # a credential sealed inside the hash could never be redacted later
        # without breaking integrity verification.
        "endpoint": sanitize_endpoint(report.endpoint),
        # CL-001: provenance sealed into the pack. ``dry_run`` and ``network``
        # are ordinary top-level keys, so they participate in the sort_keys
        # canonical serialization that ``integrity_sha256`` hashes below — the
        # seal is non-vacuous (flipping either WITHOUT recomputing the hash is
        # detected). This is tamper-EVIDENT, not tamper-PROOF: the hash is an
        # unkeyed digest the holder fully controls, so a determined forger can
        # set dry_run=false and recompute a valid hash. The real defense against
        # passing a simulated pack off as real is the on-ledger ``--live`` check
        # (the DRYRUN- txids resolve to nothing on the public ledger), not this
        # digest. What the seal + the visible SIMULATED banner prevent is the
        # ACCIDENTAL case — a dry-run pack quietly mistaken for a real one.
        "dry_run": report.dry_run,
        # RA-001 (F-a8db1a2d): seal the network run_audit classified from the
        # transport itself — the old hardcoded 'testnet' literal made an audit
        # against devnet/local/mainnet (reads are unguarded) produce a sealed
        # credibility artifact whose own endpoint field contradicted it.
        "network": "dry-run" if report.dry_run else report.network,
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

    # DD-1: audit packs are workshop-shareable (facilitator handoff,
    # no secrets per threat model). 0o755.
    _ensure_dir_mode(path.parent, WORKSPACE_DIR_MODE)
    # F-55604e7e: atomic replace — a crash mid-write must not destroy a
    # previously good pack at the same path.
    _atomic_write_text(path, json.dumps(pack, indent=2, sort_keys=True))
    return path


def verify_audit_pack(pack: dict) -> tuple[bool, str]:
    """Verify an audit pack's ``integrity_sha256`` (F-0fb57446).

    Implements the sentinel procedure documented on :func:`write_audit_pack`
    — until now that procedure existed only as a docstring replicated in
    tests, leaving the trust loop closed for proof packs and certificates but
    OPEN for audit packs (no tool-supported tamper check). Returns
    ``(valid, message)``, mirroring ``verify_proof_pack`` /
    ``verify_certificate`` in reporting.py so callers can dispatch uniformly.
    """
    if not isinstance(pack, dict):
        return False, "Not a valid JSON object"

    if pack.get("tool") != "xrpl-lab" or "verdicts" not in pack:
        return False, (
            "Missing audit-pack markers (tool='xrpl-lab' + verdicts) — you "
            "may have pasted a proof pack (use `proof verify`) or a partial "
            "file."
        )

    stored_hash = pack.get("integrity_sha256")
    if not stored_hash:
        return False, (
            "No integrity_sha256 found in audit pack — the file may be "
            "truncated or partial; regenerate with `xrpl-lab audit`."
        )

    # The documented sentinel procedure: blank the hash field, serialize
    # canonically (sort_keys=True, indent=2), hash, compare. Operate on a
    # copy so the caller's dict is untouched.
    check = dict(pack)
    check["integrity_sha256"] = ""
    canonical = json.dumps(check, indent=2, sort_keys=True)
    computed = hashlib.sha256(canonical.encode()).hexdigest()

    if computed != stored_hash:
        return False, (
            f"Hash mismatch: expected {stored_hash[:16]}…, got {computed[:16]}… "
            "— the file was edited after generation; regenerate with "
            "`xrpl-lab audit`."
        )

    return True, "Integrity verified"


def is_audit_pack(pack: object) -> bool:
    """True when ``pack`` carries audit-pack markers (tool + verdicts).

    Used by ``reporting.verify_offline_artifact`` and api-cli ``/api/verify``
    auto-detect. Distinct from proof-pack / certificate marker fields.
    """
    return (
        isinstance(pack, dict)
        and pack.get("tool") == "xrpl-lab"
        and "verdicts" in pack
    )


def audit_pack_simulated(pack: dict) -> bool:
    """SIMULATED banner parity with proof verify / cert-verify.

    Dry-run packs seal ``dry_run=True`` and/or ``network`` in
    {dry-run, dry_run, mixed}. A green integrity PASS is not on-ledger truth.
    """
    if pack.get("dry_run") is True:
        return True
    return str(pack.get("network", "") or "").lower() in (
        "dry-run",
        "dry_run",
        "mixed",
    )


def verify_audit_pack_surface(pack: dict) -> dict:
    """Product-facing audit-pack verify result (F-ad988398 / F-c2d0587d).

    Calls :func:`verify_audit_pack` and returns a dict shaped for CLI /
    ``POST /api/verify`` wiring: ``artifact_kind``, ``hash_valid``,
    ``hash_message``, ``overall_passed``, ``simulated``, identity echoes.
    Hash-only (no ``--live`` tx claims — audit packs are not proof packs).
    """
    valid, message = verify_audit_pack(pack)
    network = ""
    version = ""
    simulated = False
    if isinstance(pack, dict):
        network = str(pack.get("network", "") or "")
        version = str(pack.get("version", "") or "")
        simulated = audit_pack_simulated(pack)
    return {
        "artifact_kind": "audit_pack",
        "hash_valid": valid,
        "hash_message": message,
        "overall_passed": valid,
        "simulated": simulated,
        "network": network,
        "version": version,
        "live_requested": False,
        "live": None,
        "all_verified": True,
    }
