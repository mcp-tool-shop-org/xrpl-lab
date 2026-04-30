"""Artifact generation — proof packs, certificates, and reports."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .state import (
    WORKSPACE_DIR_MODE,
    LabState,
    TxRecord,
    _ensure_dir_mode,
    get_workspace_dir,
)
from .transport.xrpl_testnet import get_rpc_url


def _explorer_url(txid: str, network: str) -> str:
    if network == "testnet":
        return f"https://testnet.xrpl.org/transactions/{txid}"
    if network == "dry-run":
        return f"dry-run://tx/{txid}"
    return f"https://xrpl.org/transactions/{txid}"


def _tx_detail(tx_record: TxRecord, network: str) -> dict:
    """Build per-tx detail for proof pack."""
    return {
        "txid": tx_record.txid,
        "module_id": tx_record.module_id,
        "success": tx_record.success,
        "timestamp": datetime.fromtimestamp(tx_record.timestamp, tz=UTC).isoformat(),
        "network": tx_record.network,
        "explorer_url": tx_record.explorer_url or _explorer_url(tx_record.txid, network),
    }


def generate_proof_pack(state: LabState) -> dict:
    """Generate a shareable proof pack (no secrets)."""
    modules = []
    for cm in state.completed_modules:
        modules.append(
            {
                "module_id": cm.module_id,
                "completed_at": datetime.fromtimestamp(
                    cm.completed_at, tz=UTC
                ).isoformat(),
                "txids": cm.txids,
                "explorer_urls": [
                    _explorer_url(txid, state.network) for txid in cm.txids
                ],
            }
        )

    # Per-tx detail (v0.2.0+)
    transactions = [_tx_detail(tx, state.network) for tx in state.tx_index]

    # Receipt table (v0.3.1+): human-readable transaction summary
    receipt_table = []
    for tx in state.tx_index:
        receipt_table.append({
            "txid": tx.txid[:16] + "..." if len(tx.txid) > 16 else tx.txid,
            "txid_full": tx.txid,
            "module": tx.module_id,
            "status": "ok" if tx.success else "FAIL",
            "network": tx.network,
            "timestamp": datetime.fromtimestamp(
                tx.timestamp, tz=UTC
            ).strftime("%Y-%m-%d %H:%M"),
        })

    pack = {
        "xrpl_lab_proof_pack": True,
        "version": __version__,
        "network": state.network,
        "endpoint": get_rpc_url(),
        "address": state.wallet_address or "unknown",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "completed_modules": modules,
        "transactions": transactions,
        "receipt_table": receipt_table,
        "total_transactions": len(state.tx_index),
        "successful_transactions": sum(1 for tx in state.tx_index if tx.success),
        "failed_transactions": sum(1 for tx in state.tx_index if not tx.success),
    }

    # Add integrity hash (hash of the pack content without the hash field itself)
    content = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    pack["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()

    return pack


def generate_certificate(state: LabState) -> dict:
    """Generate a slim completion certificate (no secrets)."""
    from .modules import load_all_modules

    completed_ids = [cm.module_id for cm in state.completed_modules]
    all_mods = load_all_modules()
    module_titles = {
        cm.module_id: all_mods[cm.module_id].title
        if cm.module_id in all_mods else cm.module_id
        for cm in state.completed_modules
    }
    total_tx = len(state.tx_index)
    successful_tx = sum(1 for tx in state.tx_index if tx.success)

    n = len(completed_ids)
    summary_line = (
        f"Completed {n} module{'s' if n != 1 else ''} "
        f"with {total_tx} transaction{'s' if total_tx != 1 else ''}."
    )

    cert = {
        "xrpl_lab_certificate": True,
        "version": __version__,
        "network": state.network,
        "address": state.wallet_address or "unknown",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "modules_completed": completed_ids,
        "module_titles": module_titles,
        "total_modules": len(state.completed_modules),
        "total_transactions": total_tx,
        "successful_transactions": successful_tx,
        "summary_line": summary_line,
    }

    content = json.dumps(cert, sort_keys=True, separators=(",", ":"))
    cert["sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()

    return cert


def write_proof_pack(state: LabState, output_dir: Path | None = None) -> Path:
    """Write proof pack to workspace."""
    out = output_dir or (get_workspace_dir() / "proofs")
    # DD-1: proofs/ is workshop-shareable (0o755 — facilitator handoff).
    _ensure_dir_mode(out, WORKSPACE_DIR_MODE)
    path = out / "xrpl_lab_proof_pack.json"
    pack = generate_proof_pack(state)
    path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    return path


def write_certificate(state: LabState, output_dir: Path | None = None) -> Path:
    """Write certificate to workspace."""
    out = output_dir or (get_workspace_dir() / "proofs")
    # DD-1: proofs/ is workshop-shareable (0o755).
    _ensure_dir_mode(out, WORKSPACE_DIR_MODE)
    path = out / "xrpl_lab_certificate.json"
    cert = generate_certificate(state)
    path.write_text(json.dumps(cert, indent=2), encoding="utf-8")
    return path


def write_module_report(
    module_id: str,
    title: str,
    sections: list[tuple[str, str]],
    output_dir: Path | None = None,
) -> Path:
    """Write a human-readable module report.

    sections: list of (heading, body) pairs.
    """
    if "/" in module_id or "\\" in module_id or ".." in module_id:
        raise ValueError(f"Invalid module_id: {module_id!r}")
    out = output_dir or (get_workspace_dir() / "reports")
    # DD-1: reports/ is workshop-shareable (0o755).
    _ensure_dir_mode(out, WORKSPACE_DIR_MODE)
    path = out / f"{module_id}.md"

    lines = [
        f"# {title}",
        "",
        f"Generated by XRPL Lab v{__version__}",
        f"Date: {datetime.now(tz=UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    for heading, body in sections:
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(body)
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Verification — close the trust loop
# ---------------------------------------------------------------------------


def verify_proof_pack(pack: dict) -> tuple[bool, str]:
    """Verify a proof pack's integrity hash.

    Returns (valid, message).
    """
    if not isinstance(pack, dict):
        return False, "Not a valid JSON object"

    if not pack.get("xrpl_lab_proof_pack"):
        return False, "Missing xrpl_lab_proof_pack marker"

    stored_hash = pack.get("sha256")
    if not stored_hash:
        return False, "No SHA-256 hash found in proof pack"

    # Recompute: hash of the pack content without the hash field
    check = {k: v for k, v in pack.items() if k != "sha256"}
    content = json.dumps(check, sort_keys=True, separators=(",", ":"))
    computed = hashlib.sha256(content.encode("utf-8")).hexdigest()

    if computed != stored_hash:
        return False, f"Hash mismatch: expected {stored_hash[:16]}…, got {computed[:16]}…"

    return True, "Integrity verified"


def verify_certificate(cert: dict) -> tuple[bool, str]:
    """Verify a certificate's integrity hash.

    Returns (valid, message).
    """
    if not isinstance(cert, dict):
        return False, "Not a valid JSON object"

    if not cert.get("xrpl_lab_certificate"):
        return False, "Missing xrpl_lab_certificate marker"

    stored_hash = cert.get("sha256")
    if not stored_hash:
        return False, "No SHA-256 hash found in certificate"

    check = {k: v for k, v in cert.items() if k != "sha256"}
    content = json.dumps(check, sort_keys=True, separators=(",", ":"))
    computed = hashlib.sha256(content.encode("utf-8")).hexdigest()

    if computed != stored_hash:
        return False, f"Hash mismatch: expected {stored_hash[:16]}…, got {computed[:16]}…"

    return True, "Integrity verified"
