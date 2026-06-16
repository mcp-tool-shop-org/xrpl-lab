"""Artifact generation — proof packs, certificates, and reports."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from . import __version__
from .state import (
    WORKSPACE_DIR_MODE,
    LabState,
    TxRecord,
    _ensure_dir_mode,
    get_workspace_dir,
)
from .transport.xrpl_testnet import get_rpc_url

if TYPE_CHECKING:
    from .transport.base import Transport, TxInfo

# Per-network explorer hosts for artifact links. Mirrors the transport-side
# mapping in xrpl_testnet.py (_EXPLORER_BASES): testnet and devnet get their
# own explorer; dry-run / local / unknown / mainnet get NO link. The old
# fallback minted https://xrpl.org/... (the MAINNET explorer) for any
# non-testnet network — so a dry-run proof pack (the recommended offline flow)
# shipped sealed mainnet links for simulated txids that 404. A broken/wrong
# link in a SHA-sealed credibility artifact is worse than no link.
_EXPLORER_BASES = {
    "testnet": "https://testnet.xrpl.org/transactions",
    "devnet": "https://devnet.xrpl.org/transactions",
}


def _explorer_url(txid: str, network: str) -> str:
    """Build an explorer URL for a txid on ``network``, or "" if none applies."""
    base = _EXPLORER_BASES.get(network)
    if not base or not txid:
        return ""
    return f"{base}/{txid}"


# The id of the culminating capstone module (curriculum.py 'capstone' track).
# Completing it composes a full game economy across tracks; the proof pack
# surfaces a top-level boolean derived purely from the completed-module list so
# a verifier can tell at a glance that the learner finished the capstone. This
# is metadata (no secret, no new persistence) and is folded into the SHA-256
# like every other field, so integrity still verifies.
CAPSTONE_MODULE_ID = "game_economy_capstone"


def _tx_detail(tx_record: TxRecord) -> dict:
    """Build per-tx detail for proof pack.

    The explorer link is ALWAYS recomputed from the tx's OWN recorded network
    via ``_explorer_url`` — we deliberately do NOT trust ``tx_record.explorer_url``,
    because a transport can persist a cross-network link (the dry-run transport
    historically stored a testnet.xrpl.org URL for simulated txids), which the
    old ``stored or computed`` precedence would then ship into the SHA-sealed
    pack as a dead link. For a real testnet/devnet tx the recompute yields the
    identical URL; for dry-run/local/unknown it yields no link. A proof pack
    can span runs on different networks, so each receipt resolves independently.
    """
    return {
        "txid": tx_record.txid,
        "module_id": tx_record.module_id,
        "success": tx_record.success,
        "timestamp": datetime.fromtimestamp(tx_record.timestamp, tz=UTC).isoformat(),
        "network": tx_record.network,
        "explorer_url": _explorer_url(tx_record.txid, tx_record.network),
    }


def _summary_network(state: LabState) -> str:
    """Top-level network label for a pack/certificate.

    The single network if every recorded tx agrees, ``"mixed"`` if a session
    spanned networks (the per-tx records carry the precise network), else the
    current ``state.network`` when there are no transactions yet. Avoids a
    multi-network pack being mislabeled as just the last run's network.
    """
    nets = {tx.network for tx in state.tx_index if tx.network}
    if len(nets) == 1:
        return next(iter(nets))
    if len(nets) > 1:
        return "mixed"
    return state.network


def generate_proof_pack(state: LabState) -> dict:
    """Generate a shareable proof pack (no secrets)."""
    from .modules import load_all_modules

    # Map each txid to the network it was actually recorded on, so explorer
    # links resolve per-tx rather than against a single (possibly wrong)
    # top-level network — a pack can span testnet + dry-run runs.
    tx_net = {tx.txid: tx.network for tx in state.tx_index}

    # FT-ARCH-02: resolve each completed module's kb_source at pack time so the
    # learner's REAL receipt carries its capability identity end-to-end. This
    # is the join that used to live only in the KB's external MODULE_CAPABILITY
    # map (which drifted the moment a new KB-sourced module shipped); the pack
    # now self-describes which capability each module proves, so the KB can
    # ingest ANY future module's proofs with zero script edits. A module
    # without a kb_source (or one no longer present in the curriculum) yields
    # "" — backward-compatible and never a hard failure. The slug is curriculum
    # metadata, not a secret, so it does not affect the no-secrets posture.
    all_mods = load_all_modules()

    modules = []
    for cm in state.completed_modules:
        mod = all_mods.get(cm.module_id)
        modules.append(
            {
                "module_id": cm.module_id,
                "completed_at": datetime.fromtimestamp(
                    cm.completed_at, tz=UTC
                ).isoformat(),
                "txids": cm.txids,
                "kb_source": mod.kb_source if mod else "",
                "explorer_urls": [
                    _explorer_url(txid, tx_net.get(txid, state.network))
                    for txid in cm.txids
                ],
            }
        )

    # Per-tx detail (v0.2.0+)
    transactions = [_tx_detail(tx) for tx in state.tx_index]

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

    # Capstone completion flag — derived purely from the completed-module list
    # (no new state, no persistence). True iff the learner finished the
    # culminating capstone module; it's folded into the pack BEFORE the hash so
    # the SHA-256 integrity check covers it like every other field.
    capstone = any(
        cm.module_id == CAPSTONE_MODULE_ID for cm in state.completed_modules
    )

    pack = {
        "xrpl_lab_proof_pack": True,
        "version": __version__,
        "network": _summary_network(state),
        "endpoint": get_rpc_url(),
        "address": state.wallet_address or "unknown",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "completed_modules": modules,
        "capstone": capstone,
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
        "network": _summary_network(state),
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
# Ledger-anchored verification (v2.0.0 signature feature)
# ---------------------------------------------------------------------------
#
# THE GAP this closes: ``verify_proof_pack`` / ``verify_certificate`` above
# recompute the embedded SHA-256 ONLY — they prove the JSON wasn't edited
# locally, NOT that the claimed txids exist or still validate on-ledger. A
# learner could hand-craft a pack with FAKE txids plus a correct self-hash and
# it "verifies". The product's whole thesis is "prove by artifact": a proof
# must be checkable against the live public XRPL by anyone, without trusting
# the learner's machine or any server.
#
# These functions ADD an on-ledger trust layer ON TOP of the hash layer. They
# compose with (never duplicate) the offline hash check: the caller runs the
# hash check first (always), then the live check (when ``--live``). The hash
# layer is tamper-evidence; the live layer is ground truth.
#
# Networks XRPL Lab actually mints real txids for — testnet/devnet. A dry-run
# pack records "dry-run" (or carries DRYRUN-prefixed simulated txids) and has
# NO on-ledger presence: that is reported honestly ("no on-ledger txids"), not
# as a failure. A "mixed" pack verifies only its real-network txids.

# Per-tx network labels that have real, publicly-verifiable on-ledger txids.
# Mirrors transport.xrpl_testnet.SAFE_NETWORKS minus "local" — a local rippled
# is not a *public* ledger anyone else can re-check, so a local txid is not a
# shareable proof (treated like dry-run: no public on-ledger anchor).
_LIVE_VERIFIABLE_NETWORKS = frozenset({"testnet", "devnet"})

# Per-tx live verdict statuses.
LIVE_PASS = "PASS"
LIVE_FAIL = "FAIL"
LIVE_SKIPPED = "SKIPPED"  # not a real-network tx (dry-run / local / simulated)


@dataclass
class TxLiveResult:
    """Live (on-ledger) verification result for a single claimed txid."""

    txid: str
    network: str
    status: str  # LIVE_PASS / LIVE_FAIL / LIVE_SKIPPED
    reason: str
    checks: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == LIVE_PASS

    @property
    def failed(self) -> bool:
        return self.status == LIVE_FAIL

    def to_dict(self) -> dict:
        return {
            "txid": self.txid,
            "network": self.network,
            "status": self.status,
            "reason": self.reason,
            "checks": list(self.checks),
        }


@dataclass
class LiveVerificationResult:
    """Aggregate ledger-anchored verification result for a pack/certificate."""

    artifact_kind: str  # "proof_pack" / "certificate"
    tx_results: list[TxLiveResult] = field(default_factory=list)
    # Set when the artifact had no real-network txids to anchor against
    # (a fully dry-run pack). Distinct from "all passed" — there is simply
    # nothing on-ledger to check, which is honest, not a failure.
    no_onledger_txids: bool = False
    note: str = ""

    @property
    def real_tx_results(self) -> list[TxLiveResult]:
        """Per-tx results that were actually checked on-ledger (not skipped)."""
        return [r for r in self.tx_results if r.status != LIVE_SKIPPED]

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.tx_results if r.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.tx_results if r.failed)

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.tx_results if r.status == LIVE_SKIPPED)

    @property
    def overall_passed(self) -> bool:
        """Overall verdict.

        A dry-run pack (no on-ledger txids) is NOT a failure — there is simply
        nothing to anchor, which is honest given the network-honesty model. A
        mixed/real pack passes only when EVERY real-network tx passed and none
        failed.
        """
        if self.failed_count > 0:
            return False
        if self.no_onledger_txids:
            return True
        # At least one real tx and none failed → pass.
        return len(self.real_tx_results) > 0

    def to_dict(self) -> dict:
        return {
            "artifact_kind": self.artifact_kind,
            "overall_passed": self.overall_passed,
            "no_onledger_txids": self.no_onledger_txids,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "skipped": self.skipped_count,
            "note": self.note,
            "tx_results": [r.to_dict() for r in self.tx_results],
        }


# A factory maps a per-tx network label → a Transport that resolves txids
# against THAT network. Injected so the live path is unit-testable with a stub
# (or a single DryRunTransport with fixtures) and never touches the real
# network in tests. The default factory (used by the CLI) builds a real
# testnet/devnet transport pointed at the network's RPC.
TransportFactory = Callable[[str], "Transport"]


def _default_transport_factory(network: str) -> Transport:
    """Build a real read-only transport pointed at ``network``'s public RPC.

    Used by the CLI ``--live`` path. testnet/devnet each resolve to their own
    public JSON-RPC endpoint so a per-tx network resolves against the CORRECT
    ledger (a testnet txid is fetched from testnet, a devnet txid from devnet).
    Honors ``XRPL_LAB_RPC_URL`` for the tx's own network only when that
    override classifies to the SAME network — otherwise the default public
    endpoint is used so an override aimed at one network never silently
    misroutes another network's txid.
    """
    import os

    from .transport.xrpl_testnet import (
        XRPLTestnetTransport,
        classify_network,
    )

    public_rpc = {
        "testnet": "https://s.altnet.rippletest.net:51234",
        "devnet": "https://s.devnet.rippletest.net:51234",
    }
    rpc_url = public_rpc.get(network, public_rpc["testnet"])
    override = os.environ.get("XRPL_LAB_RPC_URL")
    if override and classify_network(override) == network:
        rpc_url = override

    transport = XRPLTestnetTransport()
    # Pin the transport to THIS tx's network rather than the process-wide
    # env default — a pack can span testnet + devnet and each receipt must
    # resolve against its own ledger.
    transport._rpc_url = rpc_url
    return transport


def _is_simulated_txid(txid: str) -> bool:
    """A dry-run / simulated txid has no public on-ledger anchor.

    The dry-run transport hashes ``DRYRUN-...`` into its synthetic txids, so a
    SHA-256-of-DRYRUN id is indistinguishable from a real 64-hex hash by shape
    alone. We rely on the recorded per-tx ``network`` as the authority (the
    primary signal); this helper only guards the degenerate case of an empty
    txid, which can never be fetched.
    """
    return not txid


async def _verify_one_tx_live(
    txid: str,
    network: str,
    transport: Transport,
    *,
    expected_account: str = "",
    expected_tx_type: str = "",
) -> TxLiveResult:
    """Re-fetch ONE claimed txid and assert it exists + validated + succeeded.

    Asserts, in order: the tx was fetched (a ``fetch_error`` is a NETWORK
    failure — "couldn't reach the ledger" — NOT proof the tx is fake), the tx
    exists (non-empty result_code / validated), is ``validated``, has
    ``result_code == 'tesSUCCESS'``, and — only where the pack RECORDS them —
    that the tx TYPE and the acting account MATCH the pack's claims.
    """
    checks: list[str] = []
    tx: TxInfo = await transport.fetch_tx(txid)

    # A read-back failure is a NETWORK problem, never evidence the tx is fake.
    # Mirror verify_tx (actions/verify.py) / audit.py: surface a distinct,
    # non-fake-attributing reason. This is a FAIL of the live check (we could
    # not confirm the anchor) but the reason must not claim the tx doesn't
    # exist — re-running when the ledger is reachable may pass.
    if tx.fetch_error:
        return TxLiveResult(
            txid=txid,
            network=network,
            status=LIVE_FAIL,
            reason=(
                "Couldn't reach the ledger to confirm this txid "
                f"(network issue) — it may still exist on-ledger; retry. "
                f"(details: {tx.fetch_error})"
            ),
            checks=checks,
        )

    # Not found: an empty result_code AND not validated means the public ledger
    # returned no such transaction. THIS is the headline failure — a fake txid
    # with a correct self-hash gets caught right here.
    if not tx.result_code and not tx.validated:
        return TxLiveResult(
            txid=txid,
            network=network,
            status=LIVE_FAIL,
            reason=(
                "Transaction not found on the public ledger — the pack claims "
                "this txid but the live XRPL has no such transaction."
            ),
            checks=checks,
        )
    checks.append("Exists on-ledger")

    # Validated (the tx is in a closed, validated ledger — not merely proposed).
    if tx.validated:
        checks.append("Validated: yes")
    else:
        return TxLiveResult(
            txid=txid,
            network=network,
            status=LIVE_FAIL,
            reason="Transaction is NOT validated on-ledger (not in a closed ledger).",
            checks=checks,
        )

    # Engine result.
    if tx.result_code == "tesSUCCESS":
        checks.append("Result: tesSUCCESS")
    else:
        return TxLiveResult(
            txid=txid,
            network=network,
            status=LIVE_FAIL,
            reason=f"On-ledger result is {tx.result_code or '(unknown)'}, not tesSUCCESS.",
            checks=checks,
        )

    # Account match — only assert when the pack records an account to claim.
    # The pack's top-level ``address`` is the learner's wallet; their own
    # transactions are sent FROM that account, so a mismatch means the txid
    # belongs to someone else (a borrowed/forged receipt).
    if expected_account:
        if tx.account == expected_account:
            checks.append(f"Account matches: {expected_account}")
        else:
            return TxLiveResult(
                txid=txid,
                network=network,
                status=LIVE_FAIL,
                reason=(
                    "On-ledger account does not match the pack's claimed "
                    f"address: pack claims {expected_account}, ledger shows "
                    f"{tx.account or '(none)'}."
                ),
                checks=checks,
            )

    # Type match — only assert when the pack records a tx type for this txid.
    if expected_tx_type:
        if tx.tx_type == expected_tx_type:
            checks.append(f"Type matches: {expected_tx_type}")
        else:
            return TxLiveResult(
                txid=txid,
                network=network,
                status=LIVE_FAIL,
                reason=(
                    "On-ledger transaction type does not match the pack's "
                    f"claim: pack claims {expected_tx_type}, ledger shows "
                    f"{tx.tx_type or '(none)'}."
                ),
                checks=checks,
            )

    return TxLiveResult(
        txid=txid,
        network=network,
        status=LIVE_PASS,
        reason="Verified on-ledger.",
        checks=checks,
    )


def _iter_pack_tx_claims(pack: dict) -> list[dict]:
    """Extract per-tx claims (txid, network, account, tx_type) from a pack.

    The authoritative per-tx list is ``transactions`` (each carries its own
    ``network``). The pack's top-level ``address`` is the learner wallet — used
    as the expected ACCOUNT for every tx (the learner's own receipts are sent
    FROM their address). ``tx_type`` is asserted only when a forward-compatible
    per-tx ``tx_type`` field is present (older packs don't record it; we don't
    fabricate a claim we can't substantiate from the artifact).

    Falls back to the ``completed_modules[].txids`` list (no per-tx network) for
    packs that predate the ``transactions`` block — those resolve against the
    pack's top-level ``network``.
    """
    top_address = pack.get("address", "") or ""
    if top_address == "unknown":
        top_address = ""
    top_network = pack.get("network", "") or ""

    claims: list[dict] = []
    seen: set[str] = set()

    transactions = pack.get("transactions")
    if isinstance(transactions, list) and transactions:
        for tx in transactions:
            if not isinstance(tx, dict):
                continue
            txid = tx.get("txid", "") or ""
            if not txid or txid in seen:
                continue
            seen.add(txid)
            claims.append({
                "txid": txid,
                "network": tx.get("network", "") or top_network,
                # The learner's wallet sent it — match the acting account.
                "account": top_address,
                # Forward-compatible: assert type only if the artifact records it.
                "tx_type": tx.get("tx_type", "") or "",
            })
        return claims

    # Legacy fallback: completed_modules[].txids (no per-tx network).
    for cm in pack.get("completed_modules", []) or []:
        if not isinstance(cm, dict):
            continue
        for txid in cm.get("txids", []) or []:
            if not txid or txid in seen:
                continue
            seen.add(txid)
            claims.append({
                "txid": txid,
                "network": top_network,
                "account": top_address,
                "tx_type": "",
            })
    return claims


async def verify_proof_pack_live(
    pack: dict,
    transport_factory: TransportFactory | None = None,
    *,
    transport: Transport | None = None,
) -> LiveVerificationResult:
    """Ledger-anchor a proof pack: re-fetch EVERY real-network txid it claims.

    For each txid, resolve a transport for the txid's OWN recorded network
    (testnet txid → testnet transport, devnet → devnet) and assert it exists,
    is validated, succeeded (tesSUCCESS), and — where the pack records them —
    the type/account match. dry-run / local / simulated txids are SKIPPED with
    an honest "no on-ledger anchor" note rather than failed.

    This is the on-ledger TRUST layer; it does NOT recompute the SHA-256 (that
    is ``verify_proof_pack``'s job and the caller runs it first, always). The
    two compose: hash = tamper-evidence, live = ground truth.

    Testability: pass ``transport`` to force a SINGLE injected transport for
    every txid (the common unit-test path — a DryRunTransport with
    ``set_tx_fixtures``), or ``transport_factory`` to resolve per-network. The
    CLI passes the default factory so each network resolves to its public RPC.
    """
    result = LiveVerificationResult(artifact_kind="proof_pack")

    claims = _iter_pack_tx_claims(pack)
    if not claims:
        result.no_onledger_txids = True
        result.note = (
            "Pack records no transactions — nothing to anchor on-ledger."
        )
        return result

    resolve = _build_resolver(transport, transport_factory)

    real_seen = False
    for claim in claims:
        txid = claim["txid"]
        network = claim["network"]
        # dry-run / local / simulated txids have no public on-ledger anchor.
        if network not in _LIVE_VERIFIABLE_NETWORKS or _is_simulated_txid(txid):
            result.tx_results.append(TxLiveResult(
                txid=txid,
                network=network or "dry-run",
                status=LIVE_SKIPPED,
                reason=(
                    f"No on-ledger txid to verify (network='{network or 'dry-run'}')."
                ),
            ))
            continue
        real_seen = True
        tx_transport = resolve(network)
        result.tx_results.append(await _verify_one_tx_live(
            txid,
            network,
            tx_transport,
            expected_account=claim["account"],
            expected_tx_type=claim["tx_type"],
        ))

    if not real_seen:
        result.no_onledger_txids = True
        result.note = (
            "Dry-run pack — no on-ledger txids to verify. The offline "
            "integrity (SHA-256) check is the only applicable proof here."
        )
    elif result.skipped_count:
        result.note = (
            f"Mixed pack — verified {len(result.real_tx_results)} real-network "
            f"txid(s); skipped {result.skipped_count} dry-run/local txid(s)."
        )
    return result


async def verify_certificate_live(
    cert: dict,
    transport_factory: TransportFactory | None = None,
    *,
    transport: Transport | None = None,
) -> LiveVerificationResult:
    """Ledger-anchor a certificate.

    The slim certificate format does NOT embed individual txids (only counts +
    module IDs) — there is nothing to re-fetch on-ledger. We report this
    honestly: a certificate's on-ledger trust is established by ledger-anchoring
    the matching PROOF PACK (which DOES carry the txids), so the verdict here is
    "no on-ledger txids in a certificate — verify the proof pack with --live".

    Forward-compatible: if a future certificate format embeds a ``transactions``
    list, those txids are verified exactly like a proof pack.
    """
    result = LiveVerificationResult(artifact_kind="certificate")

    claims = _iter_pack_tx_claims(cert)
    if not claims:
        result.no_onledger_txids = True
        result.note = (
            "Certificates record no individual txids — there is nothing to "
            "anchor on-ledger. To verify on-ledger, run "
            "'proof verify <proof_pack.json> --live' instead (the proof pack "
            "carries the txids)."
        )
        return result

    resolve = _build_resolver(transport, transport_factory)
    real_seen = False
    for claim in claims:
        txid = claim["txid"]
        network = claim["network"]
        if network not in _LIVE_VERIFIABLE_NETWORKS or _is_simulated_txid(txid):
            result.tx_results.append(TxLiveResult(
                txid=txid,
                network=network or "dry-run",
                status=LIVE_SKIPPED,
                reason=(
                    f"No on-ledger txid to verify (network='{network or 'dry-run'}')."
                ),
            ))
            continue
        real_seen = True
        tx_transport = resolve(network)
        result.tx_results.append(await _verify_one_tx_live(
            txid,
            network,
            tx_transport,
            expected_account=claim["account"],
            expected_tx_type=claim["tx_type"],
        ))

    if not real_seen:
        result.no_onledger_txids = True
        result.note = "Dry-run certificate — no on-ledger txids to verify."
    return result


def _build_resolver(
    transport: Transport | None,
    transport_factory: TransportFactory | None,
):
    """Return a ``network -> Transport`` resolver from the injected inputs.

    Precedence: an explicit single ``transport`` (used for every network — the
    common unit-test path) wins; otherwise a ``transport_factory`` resolves
    per-network; otherwise the default factory builds a real public-RPC
    transport per network. Caches factory output per network so a multi-tx
    pack on one network reuses one transport.
    """
    if transport is not None:
        return lambda _network: transport

    factory = transport_factory or _default_transport_factory
    cache: dict[str, Transport] = {}

    def resolve(network: str) -> Transport:
        if network not in cache:
            cache[network] = factory(network)
        return cache[network]

    return resolve


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
          "cohort_dir": "<basename only>",
          "learners": ["alice", "bob", ...],
          "files": [{"path": "alice/proofs/x.json", "sha256": "..."}],
        }

    F-BACKEND-004 (privacy): ``cohort_dir`` is the *basename* only, never
    the resolved absolute path. This MANIFEST.json is packed into the
    distributable .tar.gz/.zip a facilitator shares; ``str(path.resolve())``
    would leak the facilitator's OS username and local dir layout into a
    shareable artifact (workshop threat-model violation). The learner
    sub-paths in ``files`` are already relativized, so the absolute path
    adds no value to a consumer of the archive.
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
        # Basename only — never str(cohort_dir.resolve()). See docstring.
        "cohort_dir": cohort_dir.name,
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
