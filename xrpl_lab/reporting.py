"""Artifact generation — proof packs, certificates, and reports."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import time
import zipfile
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


# ---------------------------------------------------------------------------
# Session export — cohort archive (F-BACKEND-FT-002)
# ---------------------------------------------------------------------------

# Subdirectories under each learner's .xrpl-lab/ that are workshop-shareable
# (per the DD-1 threat model in state.py: proofs/, reports/, audit_packs/,
# certificates/). These are facilitator-handoff at session end and contain
# no secrets.
SESSION_EXPORT_INCLUDE_DIRS = ("proofs", "reports", "audit_packs", "certificates")

# Files we MUST never archive — these are private to the learner's machine.
# wallet.json holds the seed; state.json + doctor.log hold incremental
# learner-private progress + diagnostic data outside the threat-model line.
SESSION_EXPORT_EXCLUDE_FILES = ("wallet.json", "state.json", "doctor.log")


def _sha256_file(path: Path) -> str:
    """Stream a file through SHA-256 — handles arbitrarily large artifacts."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_learner_artifacts(learner_dir: Path) -> list[tuple[Path, str]]:
    """Return [(absolute_path, archive_relpath)] for one learner.

    Only files under SESSION_EXPORT_INCLUDE_DIRS are collected. The
    ``archive_relpath`` is rooted at ``<learner-id>/<subdir>/<file>``.
    Excluded files are silently skipped — caller doesn't need to know
    what we filtered. The exclusion is defensive: state.json/wallet.json
    live in ~/.xrpl-lab not <workspace>/.xrpl-lab in the canonical
    layout, but workshop dirs sometimes carry both.
    """
    learner_id = learner_dir.name
    workspace = learner_dir / ".xrpl-lab"
    if not workspace.is_dir():
        return []
    items: list[tuple[Path, str]] = []
    for subdir_name in SESSION_EXPORT_INCLUDE_DIRS:
        subdir = workspace / subdir_name
        if not subdir.is_dir():
            continue
        for file_path in sorted(subdir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.name in SESSION_EXPORT_EXCLUDE_FILES:
                continue
            rel = file_path.relative_to(workspace)
            archive_rel = f"{learner_id}/{rel.as_posix()}"
            items.append((file_path, archive_rel))
    return items


def build_session_manifest(
    cohort_dir: Path,
    learner_artifacts: dict[str, list[tuple[Path, str]]],
) -> dict:
    """Construct the MANIFEST.json contents for a session export.

    Schema:
        {
          "manifest_version": 1,
          "tool_version": "<xrpl-lab version>",
          "created_at": "<iso8601>",
          "cohort_dir": "<resolved abs path>",
          "learners": ["alice", "bob", ...],
          "files": [{"path": "alice/proofs/x.json", "sha256": "..."}],
        }
    """
    files: list[dict] = []
    for _learner_id, artifacts in learner_artifacts.items():
        for src, archive_rel in artifacts:
            files.append({
                "path": archive_rel,
                "sha256": _sha256_file(src),
                "size": src.stat().st_size,
            })
    return {
        "manifest_version": 1,
        "tool_version": __version__,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "cohort_dir": str(cohort_dir.resolve()),
        "learners": sorted(learner_artifacts.keys()),
        "files": files,
    }


def write_session_export(
    cohort_dir: Path,
    outfile: Path,
    archive_format: str = "tar.gz",
) -> dict:
    """Walk cohort_dir for learner workspaces and write an archive.

    Returns a summary dict: ``{"learners": N, "files": M, "bytes": P,
    "outfile": Path, "manifest": <manifest dict>}``. The MANIFEST.json
    includes per-file SHA-256s computed from the source file, not the
    archive entry — facilitators verifying integrity check the source
    truth, not the container framing.

    Skips wallet.json + state.json + doctor.log per the workshop threat
    model. Only proofs/, reports/, audit_packs/, certificates/ are
    archived.
    """
    if archive_format not in ("tar.gz", "zip"):
        raise ValueError(f"Unsupported format: {archive_format!r}")

    cohort_dir = Path(cohort_dir)
    if not cohort_dir.is_dir():
        raise FileNotFoundError(f"Cohort dir not found: {cohort_dir}")

    # Collect per-learner artifacts. A learner is any direct subdir
    # containing a .xrpl-lab/ workspace.
    learner_artifacts: dict[str, list[tuple[Path, str]]] = {}
    for sub in sorted(cohort_dir.iterdir()):
        if not sub.is_dir():
            continue
        if not (sub / ".xrpl-lab").is_dir():
            continue
        items = _collect_learner_artifacts(sub)
        if items:
            learner_artifacts[sub.name] = items

    # Single-shared-workspace mode: cohort_dir itself has .xrpl-lab/.
    # Treat the cohort dir as one learner ("_cohort") rather than
    # walking subdirs.
    if not learner_artifacts and (cohort_dir / ".xrpl-lab").is_dir():
        items = _collect_learner_artifacts(cohort_dir)
        if items:
            # Re-key the archive paths under "_cohort/" rather than
            # the cohort dir's actual name (which may be a temp path).
            rekeyed = [
                (src, f"_cohort/{rel.split('/', 1)[1]}")
                for src, rel in items
            ]
            learner_artifacts["_cohort"] = rekeyed

    manifest = build_session_manifest(cohort_dir, learner_artifacts)
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=False).encode("utf-8")

    outfile.parent.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    total_files = 0
    if archive_format == "tar.gz":
        with tarfile.open(outfile, "w:gz") as tar:
            mtime = time.time()
            mi = tarfile.TarInfo(name="MANIFEST.json")
            mi.size = len(manifest_bytes)
            mi.mtime = mtime
            tar.addfile(mi, io.BytesIO(manifest_bytes))
            total_files += 1
            total_bytes += len(manifest_bytes)
            for _learner_id, artifacts in learner_artifacts.items():
                for src, archive_rel in artifacts:
                    tar.add(src, arcname=archive_rel)
                    total_files += 1
                    total_bytes += src.stat().st_size
    else:  # zip
        with zipfile.ZipFile(outfile, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("MANIFEST.json", manifest_bytes)
            total_files += 1
            total_bytes += len(manifest_bytes)
            for _learner_id, artifacts in learner_artifacts.items():
                for src, archive_rel in artifacts:
                    zf.write(src, arcname=archive_rel)
                    total_files += 1
                    total_bytes += src.stat().st_size

    return {
        "learners": len(learner_artifacts),
        "files": total_files,
        "bytes": total_bytes,
        "outfile": outfile,
        "manifest": manifest,
    }
