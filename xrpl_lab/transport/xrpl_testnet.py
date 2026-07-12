"""XRPL Testnet transport — real network interactions via xrpl-py."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.ledger import get_latest_validated_ledger_sequence
from xrpl.asyncio.transaction import (
    XRPLReliableSubmissionException,
    autofill,
    submit_and_wait,
)
from xrpl.asyncio.transaction import (
    sign as sign_transaction,  # aliased: keypairs' raw `sign` is imported below
)
from xrpl.core.binarycodec import encode_for_signing_claim
from xrpl.core.keypairs import derive_keypair, is_valid_message, sign
from xrpl.models import (
    AccountChannels,
    AccountInfo,
    AccountLines,
    AccountNFTs,
    AccountObjects,
    AccountOffers,
    AccountSet,
    AccountSetAsfFlag,
    AccountTx,
    Clawback,
    CredentialAccept,
    CredentialCreate,
    CredentialDelete,
    DIDDelete,
    DIDSet,
    EscrowCancel,
    EscrowCreate,
    EscrowFinish,
    IssuedCurrencyAmount,
    Memo,
    MPTokenAuthorize,
    MPTokenIssuanceCreate,
    NFTBuyOffers,
    NFTokenAcceptOffer,
    NFTokenBurn,
    NFTokenCreateOffer,
    NFTokenCreateOfferFlag,
    NFTokenMint,
    NFTokenMintFlag,
    NFTokenModify,
    NFTSellOffers,
    OfferCancel,
    OfferCreate,
    OfferCreateFlag,
    Payment,
    PaymentChannelClaim,
    PaymentChannelClaimFlag,
    PaymentChannelCreate,
    PaymentChannelFund,
    PaymentFlag,
    PermissionedDomainDelete,
    PermissionedDomainSet,
    ServerInfo,
    SignerEntry,
    SignerListSet,
    TrustSet,
    TrustSetFlag,
    Tx,
)
from xrpl.models.amounts import MPTAmount
from xrpl.models.transactions.permissioned_domain_set import (
    Credential as PDCredential,
)
from xrpl.transaction import multisign
from xrpl.utils import drops_to_xrp, get_nftoken_id, hex_to_str, str_to_hex, xrp_to_drops
from xrpl.wallet import Wallet

from .base import (
    AccountSnapshot,
    AmmInfo,
    ChannelInfo,
    CredentialInfo,
    DIDInfo,
    EscrowInfo,
    FreezeStatus,
    FundResult,
    MPTIssuanceInfo,
    NetworkInfo,
    NFTInfo,
    NFTOfferInfo,
    OfferInfo,
    PermissionedDomainInfo,
    SignerListInfo,
    SubmitResult,
    Transport,
    TrustLineInfo,
    TxInfo,
)

logger = logging.getLogger(__name__)


def _extract_mpt_issuance_id(meta: dict) -> str:
    """Pull the new MPTokenIssuanceID out of an MPTokenIssuanceCreate's meta.

    rippled returns ``mpt_issuance_id`` directly in the meta on recent
    versions; otherwise we walk AffectedNodes for the created MPTokenIssuance
    object whose ledger index IS the issuance id. Best-effort — the dry-run
    transport sets the id directly, so the tested path is exact.
    """
    direct = meta.get("mpt_issuance_id", "")
    if direct:
        return direct
    for node in meta.get("AffectedNodes", []):
        created = node.get("CreatedNode", {})
        if created.get("LedgerEntryType") == "MPTokenIssuance":
            fields = created.get("NewFields", {})
            return (
                fields.get("mpt_issuance_id")
                or fields.get("MPTokenIssuanceID")
                or created.get("LedgerIndex", "")
            )
    return ""


def _extract_channel_id(meta: dict) -> str:
    """Pull the new channel id out of a PaymentChannelCreate's meta — the created
    PayChannel object's ledger index IS the channel id."""
    for node in meta.get("AffectedNodes", []):
        created = node.get("CreatedNode", {})
        if created.get("LedgerEntryType") == "PayChannel":
            return created.get("LedgerIndex", "")
    return ""


def _extract_domain_id(meta: dict) -> str:
    """Pull the new DomainID out of a PermissionedDomainSet (create) meta.

    The created PermissionedDomain object's ledger index IS the DomainID (the
    Hash256 derived from Owner + Sequence). Best-effort walk of AffectedNodes;
    the dry-run transport sets the id directly, so the offline-tested path is
    exact."""
    for node in meta.get("AffectedNodes", []):
        created = node.get("CreatedNode", {})
        if created.get("LedgerEntryType") == "PermissionedDomain":
            fields = created.get("NewFields", {})
            return fields.get("DomainID") or created.get("LedgerIndex", "")
    return ""


DEFAULT_RPC_URL = "https://s.altnet.rippletest.net:51234"
DEFAULT_FAUCET_URL = "https://faucet.altnet.rippletest.net/accounts"

# Per-network explorer hosts. The old single EXPLORER_BASE hard-coded the
# testnet explorer into EVERY SubmitResult.explorer_url, even when the
# configured endpoint was devnet/local (network is env-overridable via
# XRPL_LAB_RPC_URL — see classify_network). A learner pointed at devnet who
# clicked the receipt link landed on a testnet explorer that 404s the tx.
# ``_explorer_base_for`` is now the single source of truth: testnet/devnet
# get their own explorer host; local/unknown (and the dry-run transport,
# which never reaches this module) get NO link — an empty base — because
# there is no public explorer for a local rippled or an unclassified host,
# and a broken link is worse than no link. mainnet is unreachable here (the
# write path refuses it via _network_guard before any tx is built), but it
# maps to "" too, fail-closed. Mirror of reporting.py's artifact-side
# mapping (coordinator-owned): testnet.xrpl.org / devnet.xrpl.org / none.
_EXPLORER_BASES = {
    "testnet": "https://testnet.xrpl.org/transactions",
    "devnet": "https://devnet.xrpl.org/transactions",
}

# Timeouts and retries
RPC_TIMEOUT = 30  # seconds per RPC call
FAUCET_TIMEOUT = 30
SUBMIT_TIMEOUT = 60  # submissions can take a few ledger closes
MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds between retries

# Upper bound (seconds) on a SINGLE faucet-429 backoff sleep. The 429 retry
# uses escalating backoff (RETRY_DELAY * (attempt + 1)); without a cap the
# last attempt's sleep grows with RETRY_DELAY and the retry count, and the
# whole wait happens INSIDE fund_from_faucet — a synchronous, blocking wait
# the caller (and the dashboard run queue) can't see coming. Capping each
# sleep bounds the worst-case in-request wait: with MAX_RETRIES=2 the two
# backoff sleeps are min(3,6)=3 and min(6,6)=6 → at most 9s total today, and
# the cap keeps that ceiling stable if RETRY_DELAY is later tuned up. The
# 429 FundResult already tells the learner to "wait at least 60 seconds"
# before retrying themselves, so we never block the request that long.
FAUCET_MAX_BACKOFF = 6  # seconds — ceiling on one 429 backoff sleep


def get_rpc_url() -> str:
    return os.environ.get("XRPL_LAB_RPC_URL", DEFAULT_RPC_URL)


def get_faucet_url() -> str:
    return os.environ.get("XRPL_LAB_FAUCET_URL", DEFAULT_FAUCET_URL)


# ── Network classification (testnet-only invariant enforcement) ──────────
#
# XRPL Lab is testnet-only. The RPC/faucet endpoints are env-overridable
# (XRPL_LAB_RPC_URL / XRPL_LAB_FAUCET_URL) so learners can point at a local
# rippled or devnet — but an override to a MAINNET host must NEVER result in
# a signed, submitted transaction. Before this guard the "no mainnet"
# invariant was enforced nowhere in code: ``network_name`` hard-coded
# "testnet" regardless of the actual endpoint, and the write path signed
# against whatever URL was configured. ``classify_network`` is the single
# source of truth; the write methods refuse any endpoint not in
# ``SAFE_NETWORKS`` and the labels reflect the ACTUAL network.

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})
_MAINNET_HOSTS = frozenset(
    {"s1.ripple.com", "s2.ripple.com", "xrplcluster.com", "xrpl.ws", "s.ripple.com"}
)

# Networks XRPL Lab is allowed to sign+submit against. Mainnet and any
# unrecognized host are refused (the write path returns a failed result
# WITHOUT touching the wallet seed or the network).
SAFE_NETWORKS = frozenset({"testnet", "devnet", "local"})


def classify_network(url: str) -> str:
    """Classify an XRPL endpoint URL by network, from its host.

    Returns one of ``"testnet"``, ``"devnet"``, ``"local"``, ``"mainnet"``,
    or ``"unknown"``. This is the enforcement point for the testnet-only
    invariant: the write path refuses anything not in :data:`SAFE_NETWORKS`,
    and ``network_name`` / ``get_network_info`` report the real network
    rather than a hard-coded ``"testnet"``. A URL we cannot parse a host
    from is ``"unknown"`` (treated as unsafe — fail closed).
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return "unknown"
    if not host:
        return "unknown"
    if host in _LOCAL_HOSTS:
        return "local"
    if host == "altnet.rippletest.net" or host.endswith(".altnet.rippletest.net"):
        return "testnet"
    if host == "devnet.rippletest.net" or host.endswith(".devnet.rippletest.net"):
        return "devnet"
    if host in _MAINNET_HOSTS or host.endswith(".ripple.com"):
        return "mainnet"
    return "unknown"


def _memo_field(text: str) -> list[Memo]:
    """Create a memo from plain text."""
    if not text:
        return []
    return [Memo(memo_data=text.encode("utf-8").hex(), memo_type=b"text/plain".hex())]


def _decode_memos(memos_raw: list | None) -> list[str]:
    """Decode memo data fields from hex to text."""
    if not memos_raw:
        return []
    result: list[str] = []
    for m in memos_raw:
        memo = m.get("Memo", m) if isinstance(m, dict) else m
        data_hex = None
        if isinstance(memo, dict):
            data_hex = memo.get("MemoData") or memo.get("memo_data")
        elif hasattr(memo, "memo_data"):
            data_hex = memo.memo_data
        if data_hex:
            try:
                result.append(bytes.fromhex(data_hex).decode("utf-8", errors="replace"))
            except (ValueError, AttributeError):
                result.append(data_hex)
    return result


def _friendly_error(exc: Exception) -> str:
    """Turn exceptions into user-friendly error messages."""
    # Check exception type first — more reliable than string matching
    if isinstance(exc, asyncio.TimeoutError):
        return "Request timed out. The testnet may be slow. Try again in a minute."
    if isinstance(exc, ConnectionRefusedError):
        return (
            "Cannot connect to RPC endpoint. "
            "Check your internet or set XRPL_LAB_RPC_URL."
        )
    if isinstance(exc, ConnectionError):
        return (
            "Connection error reaching RPC endpoint. "
            "Check your internet or set XRPL_LAB_RPC_URL."
        )
    if isinstance(exc, OSError) and exc.errno == 111:  # ECONNREFUSED
        return (
            "Cannot connect to RPC endpoint. "
            "Check your internet or set XRPL_LAB_RPC_URL."
        )

    # Fall back to string matching for unrecognized exception types
    msg = str(exc)
    if "ConnectionRefusedError" in msg or "ConnectError" in msg:
        return (
            "Cannot connect to RPC endpoint. "
            "Check your internet or set XRPL_LAB_RPC_URL."
        )
    if "TimeoutError" in msg or "timed out" in msg.lower():
        return "Request timed out. The testnet may be slow. Try again in a minute."
    if "SSL" in msg or "certificate" in msg.lower():
        return f"SSL/TLS error connecting to endpoint. ({msg})"
    return msg


# XRPL malformed/permanent result-code tokens that mean "do not retry" — the
# tx is structurally bad and resubmitting the identical bytes can never
# succeed. F-1947a03d widened the old ``temBAD*``-only match to ALL ``tem``
# codes: every tem code is malformed by definition (``temMALFORMED``,
# ``temDISABLED``, ``temINVALID_FLAG``, ...), so a tem prelim rejection was
# being pointlessly retried. The ``[A-Z]`` after ``tem`` is load-bearing —
# XRPL codes are tem+UPPERCASE, and plain English words like "temporary"
# must NOT suppress a warranted retry.
#
# TRANSPORT-A-004: the previous heuristic substring-scanned the FRIENDLY
# message for ``("temBAD", "tefBAD", "Invalid", "malformed")``. The bare
# English words "Invalid"/"malformed" are far too broad — a transient error
# whose friendly text merely contains "Invalid" (e.g. "Invalid response from
# RPC endpoint, please retry") would suppress a warranted retry. We now match
# only genuine result-code tokens on word boundaries, so generic prose can no
# longer short-circuit the retry loop while real tem*/tefBAD* aborts still do.
_NO_RETRY_CODE_RE = re.compile(r"\b(?:tem[A-Z]\w*|tefBAD\w*)\b")


def _is_no_retry_error(message: str) -> bool:
    """Return True if *message* names a malformed/permanent XRPL result code.

    Used by the signing/submit retry loops to abort early instead of retrying a
    transaction that can never succeed. Matches ``tem*`` / ``tefBAD*``
    result-code tokens only — not the generic words "Invalid" or "malformed".
    """
    return bool(_NO_RETRY_CODE_RE.search(message or ""))


# Any XRPL engine result-code token in FAILURE classes (tec/tef/tel/tem/ter).
# Deliberately excludes ``tes`` — "Prelim result: tesSUCCESS" appears in
# xrpl-py's expired-LastLedgerSequence message and must not be parsed as a
# final result code.
_RESULT_CODE_RE = re.compile(r"\b(?:tec|tef|tel|tem|ter)[A-Z][A-Z_0-9]*\b")

# xrpl-py raises this exact prefix when a tx VALIDATED with a non-tesSUCCESS
# result (see reliable_submission._wait_for_final_transaction_outcome).
_VALIDATED_FAILURE_PREFIX = "Transaction failed: "


def _code_from_exception_message(message: str) -> str:
    """Pull the first failure-class XRPL result-code token out of *message*."""
    m = _RESULT_CODE_RE.search(message or "")
    return m.group(0) if m else ""


def _structured_failure(result_code: str) -> SubmitResult:
    """Build the failed SubmitResult for a REAL engine result code.

    Routes the code through ``explain_result_code`` (the doctor teach moment)
    exactly like the non-raising parse path, so live failures and dry-run
    failures surface identically to handlers/artifacts.
    """
    from ..doctor import explain_result_code

    info = explain_result_code(result_code)
    return SubmitResult(
        success=False,
        result_code=result_code,
        error=f"{info['meaning']}. {info['action']}",
    )


def _map_reliable_submission_failure(exc: Exception) -> SubmitResult | None:
    """Map a raised ``XRPLReliableSubmissionException`` to a SubmitResult.

    F-1947a03d: xrpl-py 4.x's ``submit_and_wait`` RAISES on failure — it never
    returns a response carrying a tec code:

    * ``"Transaction failed: tecXXX"`` — the tx VALIDATED with a non-tes
      result. It is on-ledger, consumed a fee and a sequence; resubmitting it
      lands ANOTHER fee-claiming failure. Return the structured failure with
      the REAL code; the caller must NOT retry.
    * ``"temXXX: <engine message>"`` — prelim malformed rejection. Can never
      succeed; return the structured failure, no retry.
    * anything else (expired LastLedgerSequence window, missing
      last_ledger_sequence, ...) — the tx did NOT validate; returns None so
      the caller's normal retry policy applies.
    """
    msg = str(exc)
    code = _code_from_exception_message(msg)
    if code and msg.startswith(_VALIDATED_FAILURE_PREFIX):
        return _structured_failure(code)
    if code and _is_no_retry_error(code):
        return _structured_failure(code)
    return None


def _timeout_no_resubmit(label: str) -> SubmitResult:
    """The structured result for a submit that timed out client-side.

    F-0cbd05ef: a 60s client timeout does NOT mean the tx failed — the first
    broadcast is frequently STILL inside its LastLedgerSequence validity
    window (~20 ledgers) and can still validate. Resubmitting the unsigned
    model autofills a FRESH Sequence, so BOTH transactions could land,
    duplicating the payment/offer/mint/escrow. The submit loops therefore
    NEVER auto-resubmit after a timeout; the learner is told to verify before
    retrying.
    """
    return SubmitResult(
        success=False,
        result_code="local_error",
        error=(
            f"{label} submission timed out after {SUBMIT_TIMEOUT}s. The "
            "transaction may STILL validate in the next few ledgers — it was "
            "handed to the network and its validity window may not have "
            "closed. Not resubmitting automatically (a blind resubmit can "
            "DUPLICATE the transaction). Check your account's recent "
            "transactions or the explorer first, then retry only if it never "
            "landed."
        ),
    )


def _parse_submit_fields(result: dict) -> tuple[str, str, str, int | None, int | None]:
    """Parse (result_code, txid, fee, ledger_idx, sequence) from a submit result.

    Shared by every submit path so the API-v2 shape (F-5e672008: tx fields
    under ``tx_json``) is normalized in ONE place. ``hash`` / ``ledger_index``
    stay top-level in v2; ``Fee`` and ``Sequence`` ride in the tx body.
    """
    meta = result.get("meta", {})
    tx = _tx_body(result)
    result_code = meta.get(
        "TransactionResult", result.get("engine_result", "unknown")
    )
    txid = result.get("hash", "") or tx.get("hash", "")
    fee = tx.get("Fee", "0")
    ledger_idx = _int_or_none(
        result.get("ledger_index") or meta.get("ledger_index")
    )
    sequence = _int_or_none(tx.get("Sequence"))
    return result_code, txid, fee, ledger_idx, sequence


def _tx_body(result: dict) -> dict:
    """Resolve the transaction's own fields from a Tx / submit response.

    F-5e672008: xrpl-py 4.x sends ``api_version=2``, where the transaction's
    fields nest under ``tx_json`` (top level keeps hash / ledger_index / meta /
    validated) and a Payment's ``Amount`` is renamed ``DeliverMax``. The old
    parser read the API-v1 top-level shape, so EVERY real-testnet read-back
    yielded empty account/type/destination and zero amount/fee — which made the
    honest-pack live verifier brand the learner's own receipts as forged.
    Falls back to the top level so v1-shaped fixtures/older rippled keep
    parsing.
    """
    tx_json = result.get("tx_json")
    if isinstance(tx_json, dict):
        return tx_json
    return result


def _tx_amount_raw(tx: dict):
    """The tx's Amount field across API versions (v2 renames it DeliverMax)."""
    amount = tx.get("DeliverMax")
    if amount is None:
        amount = tx.get("Amount", "0")
    return amount


def _int_or_none(value) -> int | None:
    """Coerce an RPC field into ``int`` or ``None`` (TXBCD-008).

    XRPL RPC may return ``ledger_index`` as an int, a numeric string, or omit
    it entirely. The typed ``SubmitResult.ledger_index`` / ``TxInfo`` fields
    want ``int | None``; this normalizes at the parse site so a stray string
    never lands in an int field and a missing/garbage value becomes ``None``
    instead of raising. Consistent with the ``int(... or 0)`` discipline used
    for the per-entry parsers below.
    """
    if value is None:
        return None
    if isinstance(value, bool):  # guard: bool is an int subclass — reject it
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value) -> int:
    """Coerce an RPC field into ``int``, defaulting to 0 on garbage/None.

    The per-entry ``int(... or 0)`` discipline (TXBCD-001) in one place: a
    missing field (``None``/``""``) or an unparseable value yields 0 rather
    than raising, so one malformed sub-field can't sink the whole entry.
    """
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _parse_nft_entry(n: dict) -> NFTInfo:
    """Parse one ``account_nfts`` entry into an ``NFTInfo`` (TXBCD-001).

    Pulled out of ``get_account_nfts`` so a single malformed entry can be
    skipped + logged at WARNING by the caller without the broad RPC
    try/except zeroing the learner's ENTIRE NFT list. Numeric fields use the
    ``int(... or 0)`` defensiveness so a missing/garbage taxon or flag yields
    0 rather than raising mid-list. Raises only if *n* is not dict-like.
    """
    uri_hex = n.get("URI", "") or ""
    try:
        uri = hex_to_str(uri_hex) if uri_hex else ""
    except Exception:
        uri = uri_hex
    return NFTInfo(
        nft_id=n.get("NFTokenID", ""),
        issuer=n.get("Issuer", "") or "",
        taxon=_safe_int(n.get("NFTokenTaxon", 0)),
        uri=uri,
        flags=_safe_int(n.get("Flags", 0)),
        transfer_fee=_safe_int(n.get("TransferFee", 0)),
        serial=_safe_int(n.get("nft_serial", 0)),
    )


def _parse_offer_entry(o: dict) -> OfferInfo:
    """Parse one ``account_offers`` entry into an ``OfferInfo`` (TXBCD-001).

    Pulled out of ``get_account_offers`` for the same reason as
    ``_parse_nft_entry``: one malformed offer must skip + log, not zero the
    whole list. ``sequence`` uses ``int(... or 0)`` defensiveness; the amount
    fields route through ``XRPLTestnetTransport._format_amount`` for a clean
    display string (dict → ``value/currency/issuer``).
    """
    return OfferInfo(
        sequence=_safe_int(o.get("Sequence", o.get("seq", 0))),
        taker_pays=XRPLTestnetTransport._format_amount(o.get("taker_pays")),
        taker_gets=XRPLTestnetTransport._format_amount(o.get("taker_gets")),
        quality=str(o.get("quality", "")),
    )


@asynccontextmanager
async def _rpc_client(rpc_url: str):
    """Async-context wrapper around AsyncJsonRpcClient.

    The JSON-RPC client is stateless and — as of xrpl-py 4.5.0 — is NOT itself an
    async context manager (no ``__aenter__``). This wrapper keeps the existing
    ``async with ... as client:`` call sites correct on xrpl-py 4.x; there is
    nothing to clean up on exit.
    """
    yield AsyncJsonRpcClient(rpc_url)


# server_info network ids of the chains XRPL Lab may sign against when the
# endpoint host classifies as 'local' (F-4cf20cef): 1 = testnet, 2 = devnet.
# Mainnet is network_id 0 (often omitted entirely). A standalone/custom-network
# rippled that reports neither can be explicitly allowed with
# XRPL_LAB_ALLOW_LOCAL=1 — an informed opt-in, never a silent default.
_TEST_CHAIN_NETWORK_IDS = frozenset({1, 2})


def _allow_local_env() -> bool:
    """True when the operator explicitly vouched for the localhost endpoint."""
    return os.environ.get("XRPL_LAB_ALLOW_LOCAL", "").strip().lower() in (
        "1", "true", "yes",
    )


class XRPLTestnetTransport(Transport):
    """Real XRPL Testnet transport using xrpl-py async client."""

    def __init__(self) -> None:
        self._rpc_url = get_rpc_url()
        # F-4cf20cef: per-URL cache of the local chain-identity probe. Only
        # DEFINITIVE verdicts are cached (verified test chain -> None, or a
        # verified-mainnet refusal string); an indeterminate probe (server
        # down) is retried on the next write.
        self._local_chain_verdicts: dict[str, str | None] = {}

    @property
    def network_name(self) -> str:
        # Reflect the ACTUAL endpoint, not a hard-coded label. The default
        # testnet RPC classifies as "testnet"; an XRPL_LAB_RPC_URL override
        # to mainnet/devnet/local/unknown is reported honestly so artifacts,
        # the doctor, and the dashboard never claim "testnet" while pointed
        # elsewhere.
        return classify_network(self._rpc_url)

    def _explorer_url(self, txid: str) -> str:
        """Build a network-aware explorer URL for ``txid`` (or "" if none).

        Resolves the explorer host from the ACTUAL configured network
        (via classify_network) rather than the old hard-coded testnet
        base. testnet → testnet.xrpl.org, devnet → devnet.xrpl.org;
        local/unknown/mainnet (and an empty txid) → "" so the receipt
        renders without a link rather than with one that 404s. Keep in
        lockstep with reporting.py's artifact-side ``_explorer_url``.
        """
        if not txid:
            return ""
        base = _EXPLORER_BASES.get(classify_network(self._rpc_url), "")
        return f"{base}/{txid}" if base else ""

    def _network_guard(self) -> str | None:
        """Return a refusal message if the configured RPC is unsafe, else None.

        The testnet-only invariant: XRPL Lab will not sign or submit a
        transaction against a mainnet or unrecognized endpoint. Callers in
        the write path check this BEFORE constructing the wallet or touching
        the network, so a mainnet override never reaches ``Wallet.from_seed``
        or ``submit_and_wait``.
        """
        net = classify_network(self._rpc_url)
        if net in SAFE_NETWORKS:
            return None
        return (
            f"Refusing to submit: XRPL_LAB_RPC_URL points at a '{net}' endpoint "
            f"({self._rpc_url}). XRPL Lab is testnet-only and will not sign or "
            f"submit transactions against mainnet or an unrecognized network. "
            f"Unset XRPL_LAB_RPC_URL to use the default testnet, or run with "
            f"--dry-run for fully offline practice."
        )

    async def _verify_local_chain(self) -> str | None:
        """Verify a 'local' endpoint fronts a TEST chain before any signed write.

        F-4cf20cef: a localhost URL is not inherently safe — a default-config
        rippled peers with MAINNET out of the box, and an SSH tunnel/port
        forward can put a mainnet node behind 127.0.0.1. 'local' being in
        SAFE_NETWORKS therefore left a residual mainnet write path with no
        warning. Before the first signed submit per URL we ask the server for
        its chain identity (``server_info`` → ``info.network_id``) and require
        a known test chain (1 = testnet, 2 = devnet). network_id 0 / absent is
        treated as mainnet — fail closed. ``XRPL_LAB_ALLOW_LOCAL=1`` skips the
        probe for standalone/custom-network rippled nodes (an explicit,
        documented opt-in). Definitive verdicts are cached per URL.
        """
        if _allow_local_env():
            return None
        url = self._rpc_url
        if url in self._local_chain_verdicts:
            return self._local_chain_verdicts[url]
        refusal = (
            f"Refusing to submit: XRPL_LAB_RPC_URL points at a local endpoint "
            f"({url}) whose chain identity is not a known test network. A "
            f"local rippled can front MAINNET (default config, or a tunnel), "
            f"so XRPL Lab requires server_info.info.network_id to be 1 "
            f"(testnet) or 2 (devnet) before signing. Point the node at a test "
            f"network, set XRPL_LAB_ALLOW_LOCAL=1 if you are certain this "
            f"local node is safe, or run with --dry-run."
        )
        try:
            async with _rpc_client(url) as client:
                resp = await asyncio.wait_for(
                    client.request(ServerInfo()), timeout=RPC_TIMEOUT
                )
            info = (resp.result or {}).get("info", {}) or {}
            network_id = info.get("network_id")
        except Exception as exc:
            # Indeterminate — the node is unreachable/broken. Fail closed for
            # THIS write but do not cache, so a recovered node re-probes.
            logger.warning(
                "local chain-identity probe failed for %s: %s",
                url, _friendly_error(exc), exc_info=True,
            )
            return (
                f"Refusing to submit: could not verify the chain identity of "
                f"the local endpoint ({url}) — server_info failed "
                f"({_friendly_error(exc)}). XRPL Lab will not sign against an "
                f"unverified local node; set XRPL_LAB_ALLOW_LOCAL=1 to bypass "
                f"this check for a node you trust, or run with --dry-run."
            )
        if isinstance(network_id, int) and network_id in _TEST_CHAIN_NETWORK_IDS:
            self._local_chain_verdicts[url] = None
            return None
        logger.warning(
            "local endpoint %s reports network_id=%r — refusing signed writes",
            url, network_id,
        )
        self._local_chain_verdicts[url] = refusal
        return refusal

    async def _guard_write(self) -> str | None:
        """Full write-path guard: host classification + local chain identity.

        Every signing method calls this BEFORE ``Wallet.from_seed``. The sync
        ``_network_guard`` host check runs first (mainnet/unknown refused with
        no network traffic at all); a 'local' endpoint must additionally PROVE
        it fronts a test chain (F-4cf20cef) before the first signed submit.
        """
        guard = self._network_guard()
        if guard is not None:
            return guard
        if classify_network(self._rpc_url) == "local":
            return await self._verify_local_chain()
        return None

    async def get_network_info(self) -> NetworkInfo:
        network = classify_network(self._rpc_url)
        try:
            async with _rpc_client(self._rpc_url) as client:
                ledger_idx = await asyncio.wait_for(
                    get_latest_validated_ledger_sequence(client),
                    timeout=RPC_TIMEOUT,
                )
                return NetworkInfo(
                    network=network,
                    rpc_url=self._rpc_url,
                    connected=True,
                    ledger_index=ledger_idx,
                )
        except Exception as exc:
            # TXBCD-003: promote from logger.debug (below default level, so a
            # facilitator never saw WHY the dashboard network card went
            # disconnected) to WARNING, matching the read methods. Log the
            # CLASSIFIED friendly reason (secret-safe — _friendly_error maps
            # known exception types to fixed strings and never echoes a seed),
            # not the raw exception, while still keeping the full traceback at
            # exc_info for facilitators who enable debug.
            logger.warning(
                "get_network_info failed for %s: %s",
                self._rpc_url,
                _friendly_error(exc),
                exc_info=True,
            )
            return NetworkInfo(
                network=network,
                rpc_url=self._rpc_url,
                connected=False,
                ledger_index=None,
            )

    async def fund_from_faucet(self, address: str) -> FundResult:
        import httpx

        guard = await self._guard_write()
        if guard is not None:
            return FundResult(
                success=False, address=address, message=guard, code="CONFIG_NON_TESTNET"
            )

        faucet_url = get_faucet_url()
        # The faucet URL is independently overridable (XRPL_LAB_FAUCET_URL), so
        # the RPC guard above is not enough — a mainnet/attacker faucet override
        # must not receive the user's address even when the RPC stays on
        # testnet. This keeps the transport in lockstep with doctor's env-
        # override check, which already classifies BOTH endpoints.
        faucet_net = classify_network(faucet_url)
        if faucet_net not in SAFE_NETWORKS:
            return FundResult(
                success=False,
                address=address,
                message=(
                    f"Refusing to contact faucet: XRPL_LAB_FAUCET_URL points at "
                    f"a '{faucet_net}' endpoint ({faucet_url}). XRPL Lab is "
                    f"testnet-only. Unset XRPL_LAB_FAUCET_URL to use the default "
                    f"testnet faucet, or run with --dry-run."
                ),
                code="CONFIG_NON_TESTNET",
            )
        last_error = ""
        # Structured LabError code, populated when a specific failure mode
        # has a dedicated taxonomy entry (e.g. 429 → RUNTIME_FAUCET_RATE_LIMITED).
        # Empty string for generic failures so existing message-only consumers
        # still see the humanized text.
        last_code = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=FAUCET_TIMEOUT) as http:
                    resp = await http.post(
                        faucet_url,
                        json={"destination": address},
                    )
                    if resp.status_code == 200:
                        # TXBCD-004: a degraded faucet / captive portal can
                        # return 200 with a non-JSON body (HTML). resp.json()
                        # would then raise, fall through to the generic
                        # ``except Exception`` below, and BREAK the retry loop
                        # with an opaque error. Guard it: treat an unparseable
                        # 200 as a transient faucet-degraded failure, set a
                        # clear last_error with the --dry-run hint, and
                        # ``continue`` so the existing bounded retry applies.
                        try:
                            data = resp.json()
                        except (ValueError, json.JSONDecodeError):
                            last_error = (
                                "Faucet returned HTTP 200 but the body was not "
                                "valid JSON — the testnet faucet may be degraded "
                                "or behind a captive portal. Retry in a minute, "
                                "or use --dry-run to practice this module offline."
                            )
                            last_code = "RUNTIME_FAUCET_DEGRADED"
                            if attempt < MAX_RETRIES:
                                await asyncio.sleep(RETRY_DELAY)
                            continue
                        balance = data.get("balance", "unknown")
                        return FundResult(
                            success=True,
                            address=address,
                            balance=str(balance),
                            message="Funded from testnet faucet",
                        )
                    if resp.status_code == 429:
                        last_error = (
                            "Faucet rate-limited (HTTP 429). The XRPL "
                            "testnet faucet caps funding requests per "
                            "client to prevent abuse and keep test XRP "
                            "available for everyone. Wait at least 60 "
                            "seconds before retrying, or use --dry-run "
                            "to practice this module offline without "
                            "needing a funded testnet wallet."
                        )
                        # Tag the structured code so the dashboard can route
                        # this to a "rate-limited, retry or use --dry-run" UI
                        # distinct from a generic RUNTIME_NETWORK failure.
                        last_code = "RUNTIME_FAUCET_RATE_LIMITED"
                        if attempt < MAX_RETRIES:
                            # Escalating backoff, but capped at
                            # FAUCET_MAX_BACKOFF so a single in-request sleep
                            # can't surprise the caller with a multi-second
                            # blocking wait (see FAUCET_MAX_BACKOFF rationale).
                            backoff = min(
                                RETRY_DELAY * (attempt + 1), FAUCET_MAX_BACKOFF
                            )
                            await asyncio.sleep(backoff)
                        continue
                    last_error = f"Faucet returned {resp.status_code}: {resp.text[:200]}"
                    # Non-429 HTTP error — clear any prior 429 code so the
                    # final result reflects the latest failure mode.
                    last_code = ""
                    # F-69a13b3b: back off before re-POSTing, like the 429 /
                    # bad-JSON-200 / timeout branches. Without this a degraded
                    # faucet (500/502/503) got hammered with MAX_RETRIES+1
                    # back-to-back requests.
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)
                    continue
            except httpx.TimeoutException:
                last_error = "Faucet timed out. The testnet faucet may be down."
                last_code = ""
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except Exception as exc:
                last_error = _friendly_error(exc)
                last_code = ""
                break

        return FundResult(
            success=False, address=address, message=last_error, code=last_code
        )

    async def submit_payment(
        self,
        wallet_seed: str,
        destination: str,
        amount: str,
        memo: str = "",
        destination_tag: int | None = None,
        source_tag: int | None = None,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        try:
            amount_f = Decimal(amount)
        except (ValueError, TypeError, InvalidOperation):
            return SubmitResult(
                success=False,
                result_code="local_error",
                error=f"Invalid amount: {amount!r} — expected a numeric value like '10' or '1.5'",
            )

        # TR-004: build the wallet + tx model ONCE outside the retry loop.
        # Previously the Payment (and its wallet) were reconstructed on every
        # attempt, so a non-timeout failure after broadcast could re-enter the
        # loop and build a DISTINCT transaction — a double-broadcast risk.
        # Building once means every attempt resubmits the same logical tx.
        #
        # Idempotency contract (residual — see report): submit_and_wait still
        # autofills internally, so it picks a fresh Sequence per call. TRUE
        # sequence-level idempotency needs autofill_and_sign ONCE followed by
        # submit_and_wait(signed_tx, autofill=False); that refactor is deferred
        # because it moves the network seam and would require re-mocking the
        # retry tests (test_transport.py, sibling-owned). The change here closes
        # the object-rebuild half of the defect without disturbing that seam.
        try:
            wallet = Wallet.from_seed(wallet_seed)
            # destination_tag / source_tag: optional 32-bit routing tags
            # (custodial crediting). xrpl-py's model rejects an out-of-range
            # tag at construction, surfaced below as local_error — the dry-run
            # transport mirrors that ceiling. An untagged Payment to an
            # asfRequireDest destination fails tecDST_TAG_NEEDED on-ledger.
            payment = Payment(
                account=wallet.address,
                destination=destination,
                amount=xrp_to_drops(amount_f),  # xrp_to_drops accepts Decimal
                memos=_memo_field(memo) or None,
                destination_tag=destination_tag,
                source_tag=source_tag,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )

        last_error = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(payment, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )

                result = response.result
                (result_code, txid, fee,
                 ledger_idx, tx_sequence) = _parse_submit_fields(result)

                success = result_code == "tesSUCCESS"

                # Build error message with guidance
                error_msg = ""
                if not success:
                    from ..doctor import explain_result_code

                    info = explain_result_code(result_code)
                    error_msg = f"{info['meaning']}. {info['action']}"

                return SubmitResult(
                    success=success,
                    txid=txid,
                    result_code=result_code,
                    fee=fee,
                    ledger_index=ledger_idx,
                    explorer_url=self._explorer_url(txid),
                    error=error_msg,
                    sequence=tx_sequence,
                )

            except TimeoutError:
                # F-0cbd05ef: NEVER resubmit after a client timeout — the first
                # broadcast may still be inside its LastLedgerSequence window
                # and a resubmit autofills a FRESH Sequence, so BOTH payments
                # could validate. Verify-then-retry is the learner's job.
                return _timeout_no_resubmit("Payment")
            except XRPLReliableSubmissionException as exc:
                # F-1947a03d: xrpl-py RAISES on a validated non-tesSUCCESS
                # ("Transaction failed: tecXXX" — fee + sequence consumed,
                # never resubmit) and on tem prelim rejections. Map to the
                # structured failure with the REAL result code.
                failure = _map_reliable_submission_failure(exc)
                if failure is not None:
                    return failure
                # Expired validity window — the tx can never land; a retry
                # with a fresh autofill is safe.
                last_error = _friendly_error(exc)
                if attempt < MAX_RETRIES:
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except Exception as exc:
                last_error = _friendly_error(exc)
                # Don't retry on malformed tx errors
                if _is_no_retry_error(last_error):
                    break
                if attempt < MAX_RETRIES:
                    # PT-004 (observability breadcrumb): this is a NON-TIMEOUT
                    # failure — distinct from the timeout no-resubmit above. If
                    # the first submission actually landed on-ledger before the
                    # error surfaced, the resubmit here is a possible DUPLICATE
                    # tx (the documented idempotency residual — submit_and_wait
                    # autofills a fresh Sequence per call). Log a warning so a
                    # facilitator can spot a double-submit in the logs.
                    logger.warning(
                        "resubmitting after post-broadcast failure — "
                        "possible duplicate if the first landed"
                    )
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue

        return SubmitResult(
            success=False,
            result_code="local_error",
            error=last_error,
        )

    async def submit_trust_set(
        self,
        wallet_seed: str,
        issuer: str,
        currency: str,
        limit: str,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        last_error = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                wallet = Wallet.from_seed(wallet_seed)
                trust_set = TrustSet(
                    account=wallet.address,
                    limit_amount=IssuedCurrencyAmount(
                        currency=currency,
                        issuer=issuer,
                        value=limit,
                    ),
                )
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(trust_set, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )

                result = response.result
                (result_code, txid, fee,
                 ledger_idx, tx_sequence) = _parse_submit_fields(result)

                success = result_code == "tesSUCCESS"
                error_msg = ""
                if not success:
                    from ..doctor import explain_result_code

                    info = explain_result_code(result_code)
                    error_msg = f"{info['meaning']}. {info['action']}"

                return SubmitResult(
                    success=success,
                    txid=txid,
                    result_code=result_code,
                    fee=fee,
                    ledger_index=ledger_idx,
                    explorer_url=self._explorer_url(txid),
                    error=error_msg,
                    sequence=tx_sequence,
                )

            except TimeoutError:
                # F-0cbd05ef: never resubmit after a client timeout (see
                # _timeout_no_resubmit).
                return _timeout_no_resubmit("TrustSet")
            except XRPLReliableSubmissionException as exc:
                # F-1947a03d: validated tec / prelim tem raise — map to the
                # structured failure; never retry a validated failure.
                failure = _map_reliable_submission_failure(exc)
                if failure is not None:
                    return failure
                last_error = _friendly_error(exc)
                if attempt < MAX_RETRIES:
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except Exception as exc:
                last_error = _friendly_error(exc)
                if _is_no_retry_error(last_error):
                    break
                if attempt < MAX_RETRIES:
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue

        return SubmitResult(
            success=False,
            result_code="local_error",
            error=last_error,
        )

    async def submit_issued_payment(
        self,
        wallet_seed: str,
        destination: str,
        currency: str,
        issuer: str,
        amount: str,
        memo: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        last_error = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                wallet = Wallet.from_seed(wallet_seed)
                payment = Payment(
                    account=wallet.address,
                    destination=destination,
                    amount=IssuedCurrencyAmount(
                        currency=currency,
                        issuer=issuer,
                        value=amount,
                    ),
                    memos=_memo_field(memo) or None,
                )
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(payment, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )

                result = response.result
                (result_code, txid, fee,
                 ledger_idx, tx_sequence) = _parse_submit_fields(result)

                success = result_code == "tesSUCCESS"
                error_msg = ""
                if not success:
                    from ..doctor import explain_result_code

                    info = explain_result_code(result_code)
                    error_msg = f"{info['meaning']}. {info['action']}"

                return SubmitResult(
                    success=success,
                    txid=txid,
                    result_code=result_code,
                    fee=fee,
                    ledger_index=ledger_idx,
                    explorer_url=self._explorer_url(txid),
                    error=error_msg,
                    sequence=tx_sequence,
                )

            except TimeoutError:
                # F-0cbd05ef: never resubmit after a client timeout (see
                # _timeout_no_resubmit).
                return _timeout_no_resubmit("Issued payment")
            except XRPLReliableSubmissionException as exc:
                # F-1947a03d: validated tec / prelim tem raise — map to the
                # structured failure; never retry a validated failure.
                failure = _map_reliable_submission_failure(exc)
                if failure is not None:
                    return failure
                last_error = _friendly_error(exc)
                if attempt < MAX_RETRIES:
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except Exception as exc:
                last_error = _friendly_error(exc)
                if _is_no_retry_error(last_error):
                    break
                if attempt < MAX_RETRIES:
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue

        return SubmitResult(
            success=False,
            result_code="local_error",
            error=last_error,
        )

    async def submit_partial_payment(
        self,
        issuer_seed: str,
        destination: str,
        currency: str,
        issuer: str,
        amount: str,
        deliver_min: str,
        send_max: str,
        memo: str = "",
    ) -> SubmitResult:
        """Submit an issued-currency Payment with tfPartialPayment (FC-003).

        Builds a ``Payment`` carrying ``flags=PaymentFlag.TF_PARTIAL_PAYMENT``
        (0x00020000), ``Amount`` as the DeliverMax cap, ``DeliverMin`` as the
        accepted floor, and ``SendMax`` capping source spend. The ledger may
        REDUCE delivery below ``Amount`` and still return ``tesSUCCESS`` — the
        real figure lands in the validated tx's ``delivered_amount`` metadata,
        which ``fetch_tx`` surfaces. XRP-to-XRP is forbidden on-ledger
        (``temBAD_SEND_XRP_PARTIAL``); this path is issued-currency only.
        """
        # Testnet-only invariant: refuse to sign against mainnet/unknown BEFORE
        # Wallet.from_seed (mirrors every other signing method — see
        # tests/test_network_safety.py::_MAINNET_REFUSAL_CALLS).
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(issuer_seed)
            tx = Payment(
                account=wallet.address,
                destination=destination,
                amount=IssuedCurrencyAmount(
                    currency=currency, issuer=issuer, value=amount,
                ),
                deliver_min=IssuedCurrencyAmount(
                    currency=currency, issuer=issuer, value=deliver_min,
                ),
                send_max=IssuedCurrencyAmount(
                    currency=currency, issuer=issuer, value=send_max,
                ),
                flags=PaymentFlag.TF_PARTIAL_PAYMENT,
                memos=_memo_field(memo) or None,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "Payment(partial)")

    async def get_trust_lines(self, address: str) -> list[TrustLineInfo]:
        try:
            async with _rpc_client(self._rpc_url) as client:
                response = await asyncio.wait_for(
                    client.request(
                        AccountLines(account=address, ledger_index="validated")
                    ),
                    timeout=RPC_TIMEOUT,
                )
            lines = response.result.get("lines", [])
            return [
                TrustLineInfo(
                    account=address,
                    peer=line.get("account", ""),
                    currency=line.get("currency", ""),
                    balance=line.get("balance", "0"),
                    limit=line.get("limit", "0"),
                )
                for line in lines
            ]
        except Exception:
            logger.warning("get_trust_lines failed for %s", address, exc_info=True)
            return []

    async def submit_nft_mint(
        self,
        wallet_seed: str,
        uri: str,
        taxon: int = 0,
        transfer_fee: int = 0,
        transferable: bool = True,
        mutable: bool = False,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                wallet = Wallet.from_seed(wallet_seed)
                # tfTransferable=0x8, tfMutable=0x10 (XLS-46). A royalty
                # (TransferFee) only takes effect on a transferable NFT.
                flags = 0
                if transferable:
                    flags |= NFTokenMintFlag.TF_TRANSFERABLE
                if mutable:
                    flags |= NFTokenMintFlag.TF_MUTABLE
                mint = NFTokenMint(
                    account=wallet.address,
                    nftoken_taxon=taxon,
                    uri=str_to_hex(uri) if uri else None,
                    transfer_fee=transfer_fee or None,
                    flags=flags or None,
                )
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(mint, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )

                result = response.result
                meta = result.get("meta", {})
                (result_code, txid, fee,
                 ledger_idx, tx_sequence) = _parse_submit_fields(result)

                success = result_code == "tesSUCCESS"
                nft_id = ""
                error_msg = ""
                if success:
                    try:
                        nft_id = get_nftoken_id(meta)
                    except Exception:
                        nft_id = ""
                else:
                    from ..doctor import explain_result_code

                    info = explain_result_code(result_code)
                    error_msg = f"{info['meaning']}. {info['action']}"

                return SubmitResult(
                    success=success,
                    txid=txid,
                    result_code=result_code,
                    fee=fee,
                    ledger_index=ledger_idx,
                    explorer_url=self._explorer_url(txid),
                    error=error_msg,
                    nft_id=nft_id,
                    sequence=tx_sequence,
                )

            except TimeoutError:
                # F-0cbd05ef: never resubmit after a client timeout (see
                # _timeout_no_resubmit).
                return _timeout_no_resubmit("NFTokenMint")
            except XRPLReliableSubmissionException as exc:
                # F-1947a03d: validated tec / prelim tem raise — map to the
                # structured failure; never retry a validated failure.
                failure = _map_reliable_submission_failure(exc)
                if failure is not None:
                    return failure
                last_error = _friendly_error(exc)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except Exception as exc:
                last_error = _friendly_error(exc)
                if _is_no_retry_error(last_error):
                    break
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                    continue

        return SubmitResult(success=False, result_code="local_error", error=last_error)

    async def get_account_nfts(self, address: str) -> list[NFTInfo]:
        try:
            async with _rpc_client(self._rpc_url) as client:
                response = await asyncio.wait_for(
                    client.request(
                        AccountNFTs(account=address, ledger_index="validated")
                    ),
                    timeout=RPC_TIMEOUT,
                )
            out: list[NFTInfo] = []
            for n in response.result.get("account_nfts", []):
                # Per-entry guard (TXBCD-001): one malformed NFT must skip +
                # log, not zero the learner's ENTIRE list via the broad RPC
                # except below.
                try:
                    nft = _parse_nft_entry(n)
                except Exception:
                    logger.warning(
                        "get_account_nfts: skipping malformed NFT entry (id=%r) for %s",
                        n.get("NFTokenID", "?") if isinstance(n, dict) else "?",
                        address,
                        exc_info=True,
                    )
                    continue
                # _parse_nft_entry can't see the queried address; default the
                # issuer to it only when the entry omitted one.
                if not nft.issuer:
                    nft.issuer = address
                out.append(nft)
            return out
        except Exception:
            logger.warning("get_account_nfts failed for %s", address, exc_info=True)
            return []

    async def submit_nft_burn(
        self,
        wallet_seed: str,
        nftoken_id: str,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = NFTokenBurn(
                account=wallet.address,
                nftoken_id=nftoken_id,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "NFTokenBurn")

    @staticmethod
    def _extract_nft_offer_index(meta: dict) -> str:
        """Pull the created NFTokenOffer's ledger index out of tx metadata.

        NFTokenCreateOffer creates an ``NFTokenOffer`` ledger entry; its
        ``LedgerIndex`` is the value NFTokenAcceptOffer later consumes as
        ``NFTokenSellOffer`` / ``NFTokenBuyOffer``. We scan ``AffectedNodes``
        for the CreatedNode of that type. Best-effort: "" if not found.
        """
        for node in meta.get("AffectedNodes", []):
            created = node.get("CreatedNode")
            if created and created.get("LedgerEntryType") == "NFTokenOffer":
                return created.get("LedgerIndex", "") or ""
        return ""

    async def submit_nft_create_offer(
        self,
        wallet_seed: str,
        nftoken_id: str,
        amount: str,
        sell: bool = True,
        destination: str = "",
        owner: str = "",
        currency: str = "XRP",
        issuer: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            amount_obj = self._amount_obj(currency, amount, issuer)
            # tfSellNFToken=0x1 marks a sell offer; a buy offer has no flag and
            # MUST name the current ``owner`` of the NFT.
            tx = NFTokenCreateOffer(
                account=wallet.address,
                nftoken_id=nftoken_id,
                amount=amount_obj,
                flags=NFTokenCreateOfferFlag.TF_SELL_NFTOKEN if sell else 0,
                destination=destination or None,
                owner=(owner or None) if not sell else None,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        result = await self._submit_tx(tx, wallet, "NFTokenCreateOffer")
        # On success, recover the created NFTokenOffer index from the tx meta so
        # the marketplace flow can hand it to NFTokenAcceptOffer (parity with
        # the dry-run transport, which returns nft_offer_index too).
        if result.success and result.txid:
            try:
                tx_info = await self.fetch_tx(result.txid)
                meta = (tx_info.raw or {}).get("meta", {})
                result.nft_offer_index = self._extract_nft_offer_index(meta)
            except Exception:
                logger.warning(
                    "could not recover NFTokenOffer index for %s",
                    result.txid, exc_info=True,
                )
        return result

    async def submit_nft_accept_offer(
        self,
        wallet_seed: str,
        sell_offer: str = "",
        buy_offer: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = NFTokenAcceptOffer(
                account=wallet.address,
                nftoken_sell_offer=sell_offer or None,
                nftoken_buy_offer=buy_offer or None,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "NFTokenAcceptOffer")

    async def submit_nft_modify(
        self,
        wallet_seed: str,
        nftoken_id: str,
        uri: str,
        owner: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = NFTokenModify(
                account=wallet.address,
                nftoken_id=nftoken_id,
                owner=owner or None,
                uri=str_to_hex(uri) if uri else None,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "NFTokenModify")

    async def get_nft_offers(
        self,
        nftoken_id: str,
        sell: bool = True,
    ) -> list[NFTOfferInfo]:
        req = (
            NFTSellOffers(nft_id=nftoken_id, ledger_index="validated")
            if sell
            else NFTBuyOffers(nft_id=nftoken_id, ledger_index="validated")
        )
        try:
            async with _rpc_client(self._rpc_url) as client:
                response = await asyncio.wait_for(
                    client.request(req), timeout=RPC_TIMEOUT
                )
            offers = response.result.get("offers", [])
            out: list[NFTOfferInfo] = []
            for o in offers:
                out.append(NFTOfferInfo(
                    offer_index=o.get("nft_offer_index", "") or o.get("index", ""),
                    nft_id=nftoken_id,
                    amount=self._format_amount(o.get("amount")),
                    owner=o.get("owner", ""),
                    destination=o.get("destination", "") or "",
                    is_sell=sell,
                ))
            return out
        except Exception:
            # An NFT with no offers raises objectNotFound on some rippled
            # builds; treat any read failure as "no offers" (best-effort read).
            logger.warning(
                "get_nft_offers failed for %s (sell=%s)", nftoken_id, sell, exc_info=True
            )
            return []

    # ── Clawback methods (XLS-39) ────────────────────────────────────

    async def submit_account_set_clawback(
        self,
        wallet_seed: str,
        issuer_address: str = "",
    ) -> SubmitResult:
        # ``issuer_address`` is a dry-run aid (see base contract); the testnet
        # path derives the account from the seed and ignores it.
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = AccountSet(
                account=wallet.address,
                set_flag=AccountSetAsfFlag.ASF_ALLOW_TRUSTLINE_CLAWBACK,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "AccountSet(clawback)")

    async def submit_clawback(
        self,
        issuer_seed: str,
        holder_address: str,
        currency: str,
        amount: str,
        issuer_address: str = "",
    ) -> SubmitResult:
        # ``issuer_address`` is a dry-run aid (see base contract); the testnet
        # path derives the clawing account from the seed and ignores it.
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(issuer_seed)
            # XRPL quirk (XLS-39): the Amount sub-object's ``issuer`` field
            # carries the HOLDER address, not the issuer. The token being
            # recalled is identified by currency + the clawing account (this
            # wallet); the holder rides in Amount.issuer.
            tx = Clawback(
                account=wallet.address,
                amount=IssuedCurrencyAmount(
                    currency=currency,
                    issuer=holder_address,
                    value=amount,
                ),
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "Clawback")

    async def _submit_tx(self, tx, wallet, label: str, extract=None) -> SubmitResult:
        """Submit a built+signed transaction with retry/timeout, returning a parsed SubmitResult.

        ``extract`` is an optional ``meta -> dict`` callback applied on success
        to pull a created-object id out of the transaction metadata (e.g. the
        new MPTokenIssuanceID); the returned dict is splatted into SubmitResult.
        """
        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(tx, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )
                result = response.result
                meta = result.get("meta", {})
                (result_code, txid, fee,
                 ledger_idx, tx_sequence) = _parse_submit_fields(result)
                success = result_code == "tesSUCCESS"
                error_msg = ""
                extra: dict = {}
                if success:
                    if extract is not None:
                        try:
                            extra = extract(meta) or {}
                        except Exception:
                            extra = {}
                else:
                    from ..doctor import explain_result_code

                    info = explain_result_code(result_code)
                    error_msg = f"{info['meaning']}. {info['action']}"
                return SubmitResult(
                    success=success, txid=txid, result_code=result_code, fee=fee,
                    ledger_index=ledger_idx, explorer_url=self._explorer_url(txid),
                    error=error_msg, sequence=tx_sequence, **extra,
                )
            except TimeoutError:
                # F-0cbd05ef: never resubmit after a client timeout (see
                # _timeout_no_resubmit).
                return _timeout_no_resubmit(label)
            except XRPLReliableSubmissionException as exc:
                # F-1947a03d: validated tec / prelim tem raise — map to the
                # structured failure; never retry a validated failure.
                failure = _map_reliable_submission_failure(exc)
                if failure is not None:
                    return failure
                last_error = _friendly_error(exc)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except Exception as exc:
                last_error = _friendly_error(exc)
                if _is_no_retry_error(last_error):
                    break
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
        return SubmitResult(success=False, result_code="local_error", error=last_error)

    # ── Token-freeze methods (FT-CURRIC-003) ─────────────────────────

    async def submit_set_freeze(
        self,
        issuer_seed: str,
        holder: str,
        currency: str,
        freeze: bool,
        issuer_address: str = "",
    ) -> SubmitResult:
        # ``issuer_address`` is a dry-run aid (see base contract); the testnet
        # path derives the account from the seed and ignores it.
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        flag = TrustSetFlag.TF_SET_FREEZE if freeze else TrustSetFlag.TF_CLEAR_FREEZE
        try:
            wallet = Wallet.from_seed(issuer_seed)
            # Individual freeze: the issuer sets tfSetFreeze on ITS side of the
            # (currency, holder) trust line. LimitAmount.issuer carries the
            # HOLDER (the counterparty); the issuer side keeps value 0.
            tx = TrustSet(
                account=wallet.address,
                limit_amount=IssuedCurrencyAmount(
                    currency=currency, issuer=holder, value="0",
                ),
                flags=int(flag),
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "TrustSet(freeze)")

    async def submit_global_freeze(
        self,
        issuer_seed: str,
        enable: bool,
        issuer_address: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(issuer_seed)
            if enable:
                tx = AccountSet(
                    account=wallet.address,
                    set_flag=AccountSetAsfFlag.ASF_GLOBAL_FREEZE,
                )
            else:
                tx = AccountSet(
                    account=wallet.address,
                    clear_flag=AccountSetAsfFlag.ASF_GLOBAL_FREEZE,
                )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "AccountSet(global-freeze)")

    async def get_freeze_status(
        self,
        issuer_address: str,
        holder: str,
        currency: str,
    ) -> FreezeStatus:
        individual = False
        glob = False
        found = False
        try:
            async with _rpc_client(self._rpc_url) as client:
                lines_resp = await asyncio.wait_for(
                    client.request(
                        AccountLines(
                            account=issuer_address, peer=holder,
                            ledger_index="validated",
                        )
                    ),
                    timeout=RPC_TIMEOUT,
                )
                for line in lines_resp.result.get("lines", []):
                    if line.get("currency") == currency and line.get("account") == holder:
                        found = True
                        # On the issuer's own account_lines, ``freeze`` is the
                        # issuer-side Individual Freeze on this line.
                        individual = bool(line.get("freeze", False))
                        break
                info_resp = await asyncio.wait_for(
                    client.request(
                        AccountInfo(account=issuer_address, ledger_index="validated")
                    ),
                    timeout=RPC_TIMEOUT,
                )
                flags = info_resp.result.get("account_data", {}).get("Flags", 0)
                glob = bool(flags & 0x00400000)  # lsfGlobalFreeze
        except Exception:
            logger.warning(
                "get_freeze_status failed for issuer %s", issuer_address, exc_info=True
            )
        return FreezeStatus(individual_frozen=individual, global_frozen=glob, found=found)

    # ── Payment-channel methods (FT-CURRIC-001) ──────────────────────

    async def submit_payment_channel_create(
        self, wallet_seed: str, amount_xrp: str, destination: str,
        settle_delay: int, public_key: str, cancel_after: int | None = None,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = PaymentChannelCreate(
                account=wallet.address,
                amount=xrp_to_drops(Decimal(amount_xrp)),
                destination=destination,
                settle_delay=settle_delay,
                public_key=public_key or wallet.public_key,
                cancel_after=cancel_after,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(
            tx, wallet, "PaymentChannelCreate",
            extract=lambda meta: {"channel_id": _extract_channel_id(meta)},
        )

    async def submit_payment_channel_fund(
        self, wallet_seed: str, channel_id: str, amount_xrp: str,
        expiration: int | None = None,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = PaymentChannelFund(
                account=wallet.address,
                channel=channel_id,
                amount=xrp_to_drops(Decimal(amount_xrp)),
                expiration=expiration,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "PaymentChannelFund")

    async def submit_payment_channel_claim(
        self, wallet_seed: str, channel_id: str, balance_xrp: str = "",
        amount_xrp: str = "", signature: str = "", public_key: str = "",
        close: bool = False,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            kwargs: dict = {"account": wallet.address, "channel": channel_id}
            if balance_xrp:
                kwargs["balance"] = xrp_to_drops(Decimal(balance_xrp))
            if amount_xrp:
                kwargs["amount"] = xrp_to_drops(Decimal(amount_xrp))
            if signature:
                kwargs["signature"] = signature
            if public_key:
                kwargs["public_key"] = public_key
            if close:
                kwargs["flags"] = PaymentChannelClaimFlag.TF_CLOSE
            tx = PaymentChannelClaim(**kwargs)
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "PaymentChannelClaim")

    async def get_account_channels(
        self, address: str, destination: str = ""
    ) -> list[ChannelInfo]:
        try:
            async with _rpc_client(self._rpc_url) as client:
                req = AccountChannels(
                    account=address,
                    destination_account=destination or None,
                    ledger_index="validated",
                )
                resp = await asyncio.wait_for(client.request(req), timeout=RPC_TIMEOUT)
            out: list[ChannelInfo] = []
            for ch in resp.result.get("channels", []):
                out.append(ChannelInfo(
                    channel_id=ch.get("channel_id", ""),
                    amount=str(ch.get("amount", "0")),
                    balance=str(ch.get("balance", "0")),
                    destination=ch.get("destination_account", ""),
                    settle_delay=int(ch.get("settle_delay", 0) or 0),
                    public_key=ch.get("public_key", ""),
                    expiration=_int_or_none(ch.get("expiration")),
                    cancel_after=_int_or_none(ch.get("cancel_after")),
                ))
            return out
        except Exception:
            logger.warning("get_account_channels failed for %s", address, exc_info=True)
            return []

    async def authorize_payment_channel_claim(
        self, wallet_seed: str, channel_id: str, amount_xrp: str
    ) -> str:
        # Off-ledger: sign the cumulative drops amount with the channel key.
        drops = str(xrp_to_drops(Decimal(amount_xrp)))
        blob = encode_for_signing_claim({"channel": channel_id, "amount": drops})
        priv = derive_keypair(wallet_seed)[1]
        return sign(bytes.fromhex(blob), priv)

    async def verify_payment_channel_claim(
        self, channel_id: str, amount_xrp: str, public_key: str, signature: str
    ) -> bool:
        drops = str(xrp_to_drops(Decimal(amount_xrp)))
        blob = encode_for_signing_claim({"channel": channel_id, "amount": drops})
        try:
            return is_valid_message(bytes.fromhex(blob), bytes.fromhex(signature), public_key)
        except Exception:
            return False

    async def _account_objects(self, address: str) -> list[dict]:
        async with _rpc_client(self._rpc_url) as client:
            resp = await asyncio.wait_for(
                client.request(AccountObjects(account=address, ledger_index="validated")),
                timeout=RPC_TIMEOUT,
            )
        return resp.result.get("account_objects", [])

    async def submit_escrow_create(
        self,
        wallet_seed: str,
        amount: str,
        destination: str,
        finish_after: int,
        cancel_after: int | None = None,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = EscrowCreate(
                account=wallet.address,
                amount=xrp_to_drops(Decimal(amount)),
                destination=destination,
                finish_after=finish_after,
                cancel_after=cancel_after,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "EscrowCreate")

    async def submit_require_dest(
        self,
        wallet_seed: str,
        enable: bool = True,
        wallet_address: str = "",
    ) -> SubmitResult:
        # Custodial-pool hygiene: AccountSet asfRequireDest (ledger flag
        # lsfRequireDestTag) makes the account reject any untagged incoming
        # Payment with tecDST_TAG_NEEDED. ``enable=False`` clears the flag
        # (the named compensator). ``wallet_address`` is a dry-run keying aid;
        # the testnet path derives the account from the seed and ignores it.
        # Signs a real tx, so the testnet-only invariant applies — guard
        # BEFORE Wallet.from_seed.
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            if enable:
                tx = AccountSet(
                    account=wallet.address,
                    set_flag=AccountSetAsfFlag.ASF_REQUIRE_DEST,
                )
            else:
                tx = AccountSet(
                    account=wallet.address,
                    clear_flag=AccountSetAsfFlag.ASF_REQUIRE_DEST,
                )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "AccountSet(require-dest)")

    async def submit_allow_trustline_locking(
        self,
        issuer_seed: str,
        issuer_address: str = "",
    ) -> SubmitResult:
        # XLS-85 per-asset opt-in: AccountSet asfAllowTrustLineLocking on the
        # issuer, without which any token escrow of this issuer's IOU fails
        # tecNO_PERMISSION. ``issuer_address`` is a dry-run aid; the testnet path
        # derives the account from the seed and ignores it. Signs a real tx, so
        # the testnet-only invariant applies — guard BEFORE Wallet.from_seed.
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(issuer_seed)
            tx = AccountSet(
                account=wallet.address,
                set_flag=AccountSetAsfFlag.ASF_ALLOW_TRUSTLINE_LOCKING,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "AccountSet(AllowTrustLineLocking)")

    async def submit_token_escrow_create(
        self,
        source_seed: str,
        currency: str,
        issuer: str,
        value: str,
        destination: str,
        cancel_after: int,
        finish_after: int | None = None,
        source_address: str = "",
    ) -> SubmitResult:
        # XLS-85 token escrow: EscrowCreate whose Amount is an
        # IssuedCurrencyAmount (IOU) rather than XRP drops. CancelAfter is
        # mandatory on-ledger; the issuer opt-in and issuer-as-source rules are
        # enforced by rippled (returning tecNO_PERMISSION). ``source_address`` is
        # a dry-run aid; the testnet path derives the source from the seed.
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(source_seed)
            tx = EscrowCreate(
                account=wallet.address,
                amount=IssuedCurrencyAmount(
                    currency=currency, issuer=issuer, value=value
                ),
                destination=destination,
                cancel_after=cancel_after,
                finish_after=finish_after,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "EscrowCreate(token)")

    # ── Multisig treasury methods (SignerListSet + multi-signed Payment) ─

    async def submit_signer_list_set(
        self,
        owner_seed: str,
        quorum: int,
        entries: list[tuple[str, int]],
        owner_address: str = "",
    ) -> SubmitResult:
        # SignerListSet: create/replace (quorum>0 + 1..32 entries) or delete
        # (quorum=0 + entries omitted) the account's signer list. The action
        # layer pre-validates the tem-class preflight rules with the network's
        # codes; xrpl-py's model enforces the same set at construction, so the
        # try/except below is a backstop, not the primary gate.
        # ``owner_address`` is a dry-run keying aid; the testnet path derives
        # the owner from the seed. Signs a real tx, so the testnet-only
        # invariant applies — guard BEFORE Wallet.from_seed.
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(owner_seed)
            if quorum == 0 and not entries:
                # Delete: SignerQuorum=0 with SignerEntries OMITTED (the model
                # rejects a zero quorum WITH entries as malformed).
                tx = SignerListSet(account=wallet.address, signer_quorum=0)
            else:
                tx = SignerListSet(
                    account=wallet.address,
                    signer_quorum=quorum,
                    signer_entries=[
                        SignerEntry(account=acct, signer_weight=weight)
                        for acct, weight in entries
                    ],
                )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "SignerListSet")

    async def submit_multisig_payment(
        self,
        owner_address: str,
        destination: str,
        amount: str,
        signer_seeds: list[str],
        signer_addresses: list[str] | None = None,
        memo: str = "",
    ) -> SubmitResult:
        # Multi-signed Payment: the treasury account's own key NEVER signs.
        # Flow (xrpl-py's own multisign primitives — never hand-rolled):
        #   1. autofill(tx, client, signers_count=N) — fee = base × (1 + N),
        #      plus Sequence/LastLedgerSequence, fixed for every co-signer.
        #   2. sign(autofilled, signer_wallet, multisign=True) per signer —
        #      each yields a one-entry Signers array over the SAME tx.
        #   3. multisign(autofilled, signed_list) — merges + sorts the Signers
        #      (the tx's own SigningPubKey stays ""), producing the final tx.
        #   4. submit_and_wait(combined, client) — already signed, submits as-is.
        # ``signer_addresses`` is the dry-run keying aid; here each signer's
        # address derives from its seed. Signs real txs, so the testnet-only
        # invariant applies — guard BEFORE any Wallet.from_seed.
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        if not signer_seeds:
            return SubmitResult(
                success=False, result_code="temMALFORMED",
                error=(
                    "A multi-signed transaction needs a non-empty Signers "
                    "array — zero signatures can never meet a quorum."
                ),
            )
        try:
            amount_f = Decimal(amount)
        except (ValueError, TypeError, InvalidOperation):
            return SubmitResult(
                success=False,
                result_code="local_error",
                error=f"Invalid amount: {amount!r} — expected a numeric value like '10' or '1.5'",
            )
        try:
            signer_wallets = [Wallet.from_seed(seed) for seed in signer_seeds]
            payment = Payment(
                account=owner_address,
                destination=destination,
                amount=xrp_to_drops(amount_f),
                memos=_memo_field(memo) or None,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        try:
            async with _rpc_client(self._rpc_url) as client:
                autofilled = await asyncio.wait_for(
                    autofill(payment, client, signers_count=len(signer_wallets)),
                    timeout=RPC_TIMEOUT,
                )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        try:
            signed = [
                sign_transaction(autofilled, w, multisign=True)
                for w in signer_wallets
            ]
            combined = multisign(autofilled, signed)
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        # The combined tx is fully signed — submit_and_wait submits it as-is
        # (its wallet parameter is only consulted for unsigned transactions).
        return await self._submit_tx(combined, None, "Payment(multisig)")

    async def get_signer_list(self, address: str) -> SignerListInfo | None:
        try:
            objs = await self._account_objects(address)
        except Exception:
            logger.warning("get_signer_list failed for %s", address, exc_info=True)
            return None
        for o in objs:
            if o.get("LedgerEntryType") != "SignerList":
                continue
            entries: list[tuple[str, int]] = []
            for wrapper in o.get("SignerEntries", []) or []:
                se = wrapper.get("SignerEntry", {}) or {}
                acct = se.get("Account", "")
                weight = _int_or_none(se.get("SignerWeight")) or 0
                if acct:
                    entries.append((acct, weight))
            return SignerListInfo(
                signer_quorum=_int_or_none(o.get("SignerQuorum")) or 0,
                entries=entries,
            )
        return None

    async def _escrow_create_sequences(self, address: str) -> dict[str, int]:
        """Map ``PreviousTxnID`` → EscrowCreate sequence for *address* (TRANSPORT-A-003).

        The ``account_objects`` Escrow ledger entry does NOT expose the
        sequence of the EscrowCreate that made it — but EscrowFinish/Cancel
        need exactly that value as ``OfferSequence``. We resolve it by walking
        the account's transaction history (``account_tx``) and indexing each
        EscrowCreate's hash → its ``Sequence``. The Escrow object's
        ``PreviousTxnID`` (when the object was created in a single tx) points
        back to the EscrowCreate, so ``get_escrows`` can join on it. Best-effort:
        a read failure yields an empty map and ``sequence`` stays 0.
        """
        index: dict[str, int] = {}
        try:
            async with _rpc_client(self._rpc_url) as client:
                # Paginate via the account_tx marker so an EscrowCreate older
                # than the most recent 200 txns is still found. Without this the
                # join missed (sequence -> 0) and verify_escrow_finished could
                # falsely report a still-locked escrow as "gone". Bounded to 10
                # pages (~2000 txns) to cap round-trips for a busy account.
                marker = None
                for _ in range(10):
                    resp = await asyncio.wait_for(
                        client.request(
                            AccountTx(account=address, limit=200, marker=marker)
                        ),
                        timeout=RPC_TIMEOUT,
                    )
                    for entry in resp.result.get("transactions", []):
                        tx = entry.get("tx") or entry.get("tx_json") or {}
                        if tx.get("TransactionType") != "EscrowCreate":
                            continue
                        seq = _int_or_none(tx.get("Sequence"))
                        txid = tx.get("hash") or entry.get("hash", "")
                        if seq is not None and txid:
                            index[txid] = seq
                    marker = resp.result.get("marker")
                    if not marker:
                        break
        except Exception:
            logger.warning(
                "could not resolve EscrowCreate sequences for %s", address, exc_info=True
            )
        return index

    async def get_escrows(self, address: str) -> list[EscrowInfo]:
        try:
            objs = await self._account_objects(address)
        except Exception:
            logger.warning("get_escrows failed for %s", address, exc_info=True)
            return []
        # Resolve create-sequences so EscrowInfo.sequence is populated for
        # finish/cancel (TRANSPORT-A-003). Best-effort: empty map → sequence 0.
        seq_index = await self._escrow_create_sequences(address)
        out: list[EscrowInfo] = []
        for o in objs:
            if o.get("LedgerEntryType") != "Escrow":
                continue
            prev_txn = o.get("PreviousTxnID", "") or ""
            out.append(EscrowInfo(
                # TRANSPORT-A-003: join the Escrow object back to its
                # EscrowCreate tx via PreviousTxnID to recover the create
                # sequence (the value EscrowFinish/Cancel consume).
                sequence=seq_index.get(prev_txn, 0),
                # TXBCD-005: route Amount through _format_amount so an
                # issued-currency / MPT escrow (dict Amount) renders cleanly as
                # "value/currency/issuer" instead of a raw Python dict repr.
                # Latent until token escrows exist, but future-proofs the seam.
                amount=self._format_amount(o.get("Amount", "0")),
                destination=o.get("Destination", ""),
                finish_after=_int_or_none(o.get("FinishAfter")),
                cancel_after=_int_or_none(o.get("CancelAfter")),
                condition=o.get("Condition", "") or "",
            ))
        return out

    async def submit_escrow_finish(
        self,
        wallet_seed: str,
        owner: str,
        offer_sequence: int,
        condition: str = "",
        fulfillment: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = EscrowFinish(
                account=wallet.address,
                owner=owner,
                offer_sequence=offer_sequence,
                condition=condition or None,
                fulfillment=fulfillment or None,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "EscrowFinish")

    async def submit_escrow_cancel(
        self,
        wallet_seed: str,
        owner: str,
        offer_sequence: int,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = EscrowCancel(
                account=wallet.address,
                owner=owner,
                offer_sequence=offer_sequence,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "EscrowCancel")

    async def submit_did_set(self, wallet_seed: str, uri: str = "", data: str = "") -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = DIDSet(
                account=wallet.address,
                uri=str_to_hex(uri) if uri else None,
                data=str_to_hex(data) if data else None,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "DIDSet")

    async def get_did(self, address: str) -> DIDInfo | None:
        try:
            objs = await self._account_objects(address)
        except Exception:
            logger.warning("get_did failed for %s", address, exc_info=True)
            return None
        for o in objs:
            if o.get("LedgerEntryType") != "DID":
                continue
            def _dec(h):
                try:
                    return hex_to_str(h) if h else ""
                except Exception:
                    return h or ""
            return DIDInfo(
                account=address,
                uri=_dec(o.get("URI", "")),
                data=_dec(o.get("Data", "")),
                did_document=o.get("DIDDocument", "") or "",
            )
        return None

    async def submit_did_delete(self, wallet_seed: str) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = DIDDelete(account=wallet.address)
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "DIDDelete")

    # ── Credential methods (FC-002, XLS-70) ──────────────────────────────
    #
    # ``credential_type`` arrives already hex-encoded (the action layer encodes
    # the plaintext tag). Each signing method calls _network_guard() BEFORE
    # Wallet.from_seed so a mainnet override never signs — same invariant as
    # every other write method (pinned by test_network_safety).

    async def submit_credential_create(
        self,
        issuer_seed: str,
        subject: str,
        credential_type: str,
        uri: str = "",
        expiration: int | None = None,
        issuer_address: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(issuer_seed)
            tx = CredentialCreate(
                account=wallet.address,
                subject=subject,
                credential_type=credential_type,
                uri=str_to_hex(uri) if uri else None,
                expiration=expiration,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "CredentialCreate")

    async def submit_credential_accept(
        self,
        subject_seed: str,
        issuer: str,
        credential_type: str,
        subject_address: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(subject_seed)
            tx = CredentialAccept(
                account=wallet.address,
                issuer=issuer,
                credential_type=credential_type,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "CredentialAccept")

    async def submit_credential_delete(
        self,
        wallet_seed: str,
        issuer: str,
        subject: str,
        credential_type: str,
        wallet_address: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = CredentialDelete(
                account=wallet.address,
                issuer=issuer,
                subject=subject,
                credential_type=credential_type,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "CredentialDelete")

    async def get_credential(
        self,
        subject: str,
        issuer: str,
        credential_type: str,
    ) -> CredentialInfo | None:
        # Credential objects live in the SUBJECT's account_objects once accepted
        # AND in the issuer's while provisional; the subject is named on the
        # object either way, so read the subject's objects and match on issuer +
        # type. (A provisional credential the subject hasn't accepted is owned by
        # the issuer's directory, so also fall back to the issuer's objects.)
        want_type = (credential_type or "").upper()
        for owner in (subject, issuer):
            try:
                objs = await self._account_objects(owner)
            except Exception:
                logger.warning("get_credential failed for %s", owner, exc_info=True)
                continue
            for o in objs:
                if o.get("LedgerEntryType") != "Credential":
                    continue
                if o.get("Subject", "") != subject:
                    continue
                if o.get("Issuer", "") != issuer:
                    continue
                if (o.get("CredentialType", "") or "").upper() != want_type:
                    continue
                # lsfAccepted = 0x00010000 — set once the subject accepts.
                flags = int(o.get("Flags", 0) or 0)
                accepted = bool(flags & 0x00010000)

                def _dec(h):
                    try:
                        return hex_to_str(h) if h else ""
                    except Exception:
                        return h or ""

                return CredentialInfo(
                    subject=subject,
                    issuer=issuer,
                    credential_type=o.get("CredentialType", ""),
                    accepted=accepted,
                    uri=_dec(o.get("URI", "")),
                    expiration=o.get("Expiration"),
                )
        return None

    # ── Permissioned Domains & Gated DEX (FC-004, XLS-80 / XLS-81) ────────
    #
    # xrpl-py 4.5.0 has native models: PermissionedDomainSet /
    # PermissionedDomainDelete, an OfferCreate ``domain_id`` field, and
    # OfferCreateFlag.TF_HYBRID. AcceptedCredentials wrap each {Issuer,
    # CredentialType} in a Credential model. Each signing method calls
    # _network_guard() BEFORE Wallet.from_seed — same invariant every other
    # write method holds, pinned by test_network_safety.

    async def submit_permissioned_domain_set(
        self,
        owner_seed: str,
        accepted_credentials: list[tuple[str, str]],
        domain_id: str = "",
        owner_address: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(owner_seed)
            creds = [
                PDCredential(issuer=iss, credential_type=ctype)
                for iss, ctype in accepted_credentials
            ]
            tx = PermissionedDomainSet(
                account=wallet.address,
                accepted_credentials=creds,
                # Omit DomainID to create; include it to modify (owner-only).
                domain_id=domain_id or None,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        # On a CREATE, surface the derived DomainID; on a MODIFY, echo the
        # supplied one (no created node to read).
        if domain_id:
            def _extract(meta: dict, _did=domain_id) -> dict:
                return {"domain_id": _did}
        else:
            def _extract(meta: dict) -> dict:
                return {"domain_id": _extract_domain_id(meta)}
        return await self._submit_tx(tx, wallet, "PermissionedDomainSet", extract=_extract)

    async def submit_permissioned_domain_delete(
        self,
        owner_seed: str,
        domain_id: str,
        owner_address: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(owner_seed)
            tx = PermissionedDomainDelete(
                account=wallet.address,
                domain_id=domain_id,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "PermissionedDomainDelete")

    async def submit_permissioned_offer_create(
        self,
        wallet_seed: str,
        taker_pays_currency: str,
        taker_pays_value: str,
        taker_pays_issuer: str,
        taker_gets_currency: str,
        taker_gets_value: str,
        taker_gets_issuer: str,
        domain_id: str,
        hybrid: bool = False,
        wallet_address: str = "",
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            offer = OfferCreate(
                account=wallet.address,
                taker_pays=self._amount_obj(
                    taker_pays_currency, taker_pays_value, taker_pays_issuer
                ),
                taker_gets=self._amount_obj(
                    taker_gets_currency, taker_gets_value, taker_gets_issuer
                ),
                domain_id=domain_id,
                # tfHybrid also matches the open DEX; plain permissioned matches
                # only the domain book. CredentialIDs are NOT used — eligibility
                # rides on the DomainID (a held accepted credential), a DIFFERENT
                # rail from the deposit-authorization CredentialIDs.
                flags=OfferCreateFlag.TF_HYBRID if hybrid else 0,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )

        result = await self._submit_tx(offer, wallet, "PermissionedOfferCreate")
        # F-88f82c27: the placing tx's Sequence (the value OfferCancel consumes)
        # comes straight from the validated submit response (API v2:
        # tx_json.Sequence — _submit_tx parses it onto SubmitResult.sequence).
        # The old ``get_account_offers()[-1]`` read-back was WRONG whenever the
        # offer crossed fully (returns some OTHER resting offer's sequence — a
        # later OfferCancel with it cancels the wrong offer) or multiple offers
        # rest (ledger-directory order is not creation order).
        if result.success and result.offer_sequence is None:
            result.offer_sequence = result.sequence
        return result

    async def get_permissioned_domains(
        self, owner: str
    ) -> list[PermissionedDomainInfo]:
        try:
            objs = await self._account_objects(owner)
        except Exception:
            logger.warning(
                "get_permissioned_domains failed for %s", owner, exc_info=True
            )
            return []
        domains: list[PermissionedDomainInfo] = []
        for o in objs:
            if o.get("LedgerEntryType") != "PermissionedDomain":
                continue
            accepted: list[tuple[str, str]] = []
            for entry in o.get("AcceptedCredentials", []):
                cred = entry.get("Credential", entry)
                iss = cred.get("Issuer", "")
                ctype = (cred.get("CredentialType", "") or "").upper()
                if iss:
                    accepted.append((iss, ctype))
            domains.append(
                PermissionedDomainInfo(
                    domain_id=o.get("index", "") or o.get("DomainID", ""),
                    owner=owner,
                    accepted_credentials=accepted,
                )
            )
        return domains

    async def submit_mpt_issuance_create(
        self,
        wallet_seed: str,
        maximum_amount: str,
        asset_scale: int = 0,
        transfer_fee: int = 0,
        can_transfer: bool = True,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            tx = MPTokenIssuanceCreate(
                account=wallet.address,
                maximum_amount=str(maximum_amount),
                asset_scale=asset_scale or None,
                transfer_fee=transfer_fee or None,
                flags=0x20 if can_transfer else 0,  # tfMPTCanTransfer
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(
            tx, wallet, "MPTokenIssuanceCreate",
            extract=lambda meta: {"mpt_issuance_id": _extract_mpt_issuance_id(meta)},
        )

    async def submit_mpt_authorize(
        self,
        holder_seed: str,
        issuance_id: str,
        unauthorize: bool = False,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(holder_seed)
            tx = MPTokenAuthorize(
                account=wallet.address,
                mptoken_issuance_id=issuance_id,
                flags=0x01 if unauthorize else 0,  # tfMPTUnauthorize
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "MPTokenAuthorize")

    async def submit_mpt_payment(
        self,
        issuer_seed: str,
        destination: str,
        issuance_id: str,
        amount: str,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)
        try:
            wallet = Wallet.from_seed(issuer_seed)
            tx = Payment(
                account=wallet.address,
                destination=destination,
                amount=MPTAmount(mpt_issuance_id=issuance_id, value=str(amount)),
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )
        return await self._submit_tx(tx, wallet, "Payment(MPT)")

    async def get_mpt_balance(self, holder: str, issuance_id: str) -> str:
        try:
            objs = await self._account_objects(holder)
        except Exception:
            logger.warning("get_mpt_balance failed for %s", holder, exc_info=True)
            return "0"
        for o in objs:
            if o.get("LedgerEntryType") != "MPToken":
                continue
            oid = o.get("MPTokenIssuanceID") or o.get("mpt_issuance_id", "")
            if oid == issuance_id:
                return str(o.get("MPTAmount", "0") or "0")
        return "0"

    async def get_mpt_issuances(self, address: str) -> list[MPTIssuanceInfo]:
        try:
            objs = await self._account_objects(address)
        except Exception:
            logger.warning("get_mpt_issuances failed for %s", address, exc_info=True)
            return []
        out: list[MPTIssuanceInfo] = []
        for o in objs:
            if o.get("LedgerEntryType") != "MPTokenIssuance":
                continue
            out.append(MPTIssuanceInfo(
                issuance_id=o.get("mpt_issuance_id") or o.get("MPTokenIssuanceID", ""),
                maximum_amount=str(o.get("MaximumAmount", "0")),
                asset_scale=int(o.get("AssetScale", 0) or 0),
                transfer_fee=int(o.get("TransferFee", 0) or 0),
                flags=int(o.get("Flags", 0) or 0),
                outstanding_amount=str(o.get("OutstandingAmount", "0")),
            ))
        return out

    def _amount_obj(
        self, currency: str, value: str, issuer: str
    ) -> str | IssuedCurrencyAmount:
        """Build an XRP drops string or IssuedCurrencyAmount."""
        if currency == "XRP":
            try:
                return xrp_to_drops(Decimal(value))  # xrp_to_drops accepts Decimal
            except (ValueError, TypeError, InvalidOperation):
                raise ValueError(
                    f"Invalid XRP amount: {value!r} — expected a numeric value like '10' or '1.5'"
                ) from None
        return IssuedCurrencyAmount(currency=currency, issuer=issuer, value=value)

    @staticmethod
    def _format_amount(amt) -> str:
        """Format an XRPL amount field for display."""
        if isinstance(amt, str):
            return amt  # XRP in drops
        if isinstance(amt, dict):
            v = amt.get("value", "?")
            c = amt.get("currency", "?")
            i = amt.get("issuer", "")[:12]
            return f"{v}/{c}/{i}"
        return str(amt)

    async def submit_offer_create(
        self,
        wallet_seed: str,
        taker_pays_currency: str,
        taker_pays_value: str,
        taker_pays_issuer: str,
        taker_gets_currency: str,
        taker_gets_value: str,
        taker_gets_issuer: str,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        # TR-004: build the wallet + tx model ONCE outside the retry loop so a
        # retry resubmits the same logical tx rather than a freshly-built one.
        # (Same idempotency residual as submit_payment — see its comment.)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            offer = OfferCreate(
                account=wallet.address,
                taker_pays=self._amount_obj(
                    taker_pays_currency, taker_pays_value, taker_pays_issuer
                ),
                taker_gets=self._amount_obj(
                    taker_gets_currency, taker_gets_value, taker_gets_issuer
                ),
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )

        last_error = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(offer, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )

                result = response.result
                (result_code, txid, fee,
                 ledger_idx, tx_sequence) = _parse_submit_fields(result)

                success = result_code == "tesSUCCESS"
                error_msg = ""
                if not success:
                    from ..doctor import explain_result_code

                    info = explain_result_code(result_code)
                    error_msg = f"{info['meaning']}. {info['action']}"

                return SubmitResult(
                    success=success,
                    txid=txid,
                    result_code=result_code,
                    fee=fee,
                    ledger_index=ledger_idx,
                    explorer_url=self._explorer_url(txid),
                    error=error_msg,
                    sequence=tx_sequence,
                )

            except TimeoutError:
                # F-0cbd05ef: never resubmit after a client timeout (see
                # _timeout_no_resubmit).
                return _timeout_no_resubmit("OfferCreate")
            except XRPLReliableSubmissionException as exc:
                # F-1947a03d: validated tec / prelim tem raise — map to the
                # structured failure; never retry a validated failure.
                failure = _map_reliable_submission_failure(exc)
                if failure is not None:
                    return failure
                last_error = _friendly_error(exc)
                if attempt < MAX_RETRIES:
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except Exception as exc:
                last_error = _friendly_error(exc)
                if _is_no_retry_error(last_error):
                    break
                if attempt < MAX_RETRIES:
                    # PT-004 (observability breadcrumb): NON-TIMEOUT failure —
                    # if the first submission landed on-ledger before the error
                    # surfaced, this resubmit is a possible DUPLICATE tx (the
                    # documented idempotency residual). Log a warning so a
                    # facilitator can spot a double-submit in the logs.
                    logger.warning(
                        "resubmitting after post-broadcast failure — "
                        "possible duplicate if the first landed"
                    )
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue

        return SubmitResult(
            success=False,
            result_code="local_error",
            error=last_error,
        )

    async def submit_offer_cancel(
        self,
        wallet_seed: str,
        offer_sequence: int,
    ) -> SubmitResult:
        guard = await self._guard_write()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        # TR-004: build the wallet + tx model ONCE outside the retry loop so a
        # retry resubmits the same logical tx rather than a freshly-built one.
        # (Same idempotency residual as submit_payment — see its comment.)
        try:
            wallet = Wallet.from_seed(wallet_seed)
            cancel = OfferCancel(
                account=wallet.address,
                offer_sequence=offer_sequence,
            )
        except Exception as exc:
            return SubmitResult(
                success=False, result_code="local_error", error=_friendly_error(exc)
            )

        last_error = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(cancel, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )

                result = response.result
                (result_code, txid, fee,
                 ledger_idx, tx_sequence) = _parse_submit_fields(result)

                success = result_code == "tesSUCCESS"
                error_msg = ""
                if not success:
                    from ..doctor import explain_result_code

                    info = explain_result_code(result_code)
                    error_msg = f"{info['meaning']}. {info['action']}"

                return SubmitResult(
                    success=success,
                    txid=txid,
                    result_code=result_code,
                    fee=fee,
                    ledger_index=ledger_idx,
                    explorer_url=self._explorer_url(txid),
                    error=error_msg,
                    sequence=tx_sequence,
                )

            except TimeoutError:
                # F-0cbd05ef: never resubmit after a client timeout (see
                # _timeout_no_resubmit).
                return _timeout_no_resubmit("OfferCancel")
            except XRPLReliableSubmissionException as exc:
                # F-1947a03d: validated tec / prelim tem raise — map to the
                # structured failure; never retry a validated failure.
                failure = _map_reliable_submission_failure(exc)
                if failure is not None:
                    return failure
                last_error = _friendly_error(exc)
                if attempt < MAX_RETRIES:
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except Exception as exc:
                last_error = _friendly_error(exc)
                if _is_no_retry_error(last_error):
                    break
                if attempt < MAX_RETRIES:
                    # PT-004 (observability breadcrumb): NON-TIMEOUT failure —
                    # if the first submission landed on-ledger before the error
                    # surfaced, this resubmit is a possible DUPLICATE tx (the
                    # documented idempotency residual). Log a warning so a
                    # facilitator can spot a double-submit in the logs.
                    logger.warning(
                        "resubmitting after post-broadcast failure — "
                        "possible duplicate if the first landed"
                    )
                    logger.info(
                        "Retry %d/%d after %ds",
                        attempt + 1, MAX_RETRIES, RETRY_DELAY,
                    )
                    await asyncio.sleep(RETRY_DELAY)
                    continue

        return SubmitResult(
            success=False,
            result_code="local_error",
            error=last_error,
        )

    async def get_account_offers(self, address: str) -> list[OfferInfo]:
        try:
            async with _rpc_client(self._rpc_url) as client:
                response = await asyncio.wait_for(
                    client.request(
                        AccountOffers(account=address, ledger_index="validated")
                    ),
                    timeout=RPC_TIMEOUT,
                )
            offers = response.result.get("offers", [])
            out: list[OfferInfo] = []
            for o in offers:
                # Per-entry guard (TXBCD-001): a single malformed offer must
                # skip + log, not zero the learner's ENTIRE offer list.
                try:
                    out.append(_parse_offer_entry(o))
                except Exception:
                    logger.warning(
                        "get_account_offers: skipping malformed offer entry "
                        "(seq=%r) for %s",
                        o.get("Sequence", o.get("seq", "?")) if isinstance(o, dict) else "?",
                        address,
                        exc_info=True,
                    )
                    continue
            return out
        except Exception:
            logger.warning("get_account_offers failed for %s", address, exc_info=True)
            return []

    async def get_account_info(self, address: str) -> AccountSnapshot:
        try:
            async with _rpc_client(self._rpc_url) as client:
                response = await asyncio.wait_for(
                    client.request(
                        AccountInfo(account=address, ledger_index="validated")
                    ),
                    timeout=RPC_TIMEOUT,
                )
            acct = response.result.get("account_data", {})
            return AccountSnapshot(
                address=address,
                balance_drops=acct.get("Balance", "0"),
                owner_count=acct.get("OwnerCount", 0),
                sequence=acct.get("Sequence", 0),
            )
        except Exception:
            logger.warning("get_account_info failed for %s", address, exc_info=True)
            return AccountSnapshot(address=address)

    async def fetch_tx(self, txid: str) -> TxInfo:
        try:
            async with _rpc_client(self._rpc_url) as client:
                response = await asyncio.wait_for(
                    client.request(Tx(transaction=txid)),
                    timeout=RPC_TIMEOUT,
                )

            result = response.result
            meta = result.get("meta", {})
            # F-5e672008: xrpl-py 4.x speaks API v2 — the tx's own fields nest
            # under ``tx_json`` (v1 had them top-level) and a Payment's Amount
            # is renamed DeliverMax. The old top-level reads yielded empty
            # account/type/destination and zero amount/fee on EVERY live
            # read-back, which made the honest-pack live verifier brand the
            # learner's own txid as a borrowed/forged receipt. ``_tx_body``
            # falls back to the top level so v1 fixtures keep parsing.
            tx = _tx_body(result)
            memos_raw = tx.get("Memos", [])

            # FC-003: delivered_amount is a METADATA field (meta.delivered_amount)
            # on a validated tx — the ACTUAL amount delivered, distinct from the
            # Amount field (the requested cap). For XRP it's a drops string; for
            # tokens it's a {currency, issuer, value} object. Legacy pre-2014
            # partial payments can carry the literal string "unavailable". Route
            # it through _format_amount so the token-object case renders as
            # "value/currency/issuer" (matching the Amount display below).
            delivered_raw = meta.get("delivered_amount")
            if delivered_raw is None:
                delivered_str = ""
            elif delivered_raw == "unavailable":
                delivered_str = "unavailable"
            else:
                delivered_str = self._format_amount(delivered_raw)

            return TxInfo(
                txid=txid,
                tx_type=tx.get("TransactionType", ""),
                account=tx.get("Account", ""),
                destination=tx.get("Destination", ""),
                amount=self._format_amount(_tx_amount_raw(tx)),
                fee=tx.get("Fee", "0"),
                result_code=meta.get("TransactionResult", ""),
                # TR-005: match the submit paths' fallback chain. A validated tx
                # response may carry ledger_index only under inLedger or in meta;
                # reading the top-level field alone left a validated tx showing a
                # null ledger_index, weakening the artifact.
                ledger_index=_int_or_none(
                    result.get("ledger_index")
                    or result.get("inLedger")
                    or (result.get("meta") or {}).get("ledger_index")
                ),
                memos=_decode_memos(memos_raw),
                validated=result.get("validated", False),
                raw=result,
                delivered_amount=delivered_str,
                # Custodial crediting: the 32-bit routing tags, read from the
                # tx body (API v2 nests them under tx_json like every other tx
                # field). None when absent — the credit path treats an absent
                # DestinationTag as unattributable.
                destination_tag=_int_or_none(tx.get("DestinationTag")),
                source_tag=_int_or_none(tx.get("SourceTag")),
            )
        except TimeoutError:
            # TXBCD-002: a READ-BACK failure is NOT a tx failure. Populate the
            # distinct ``fetch_error`` field (leaving result_code empty) so
            # verify_tx surfaces a "couldn't fetch — may still have succeeded"
            # message instead of mis-attributing a network timeout as the tx
            # failing on-ledger.
            return TxInfo(
                txid=txid,
                fetch_error="Timed out fetching transaction. Try again.",
            )
        except Exception as exc:
            return TxInfo(txid=txid, fetch_error=_friendly_error(exc))

    async def get_balance(self, address: str) -> str:
        try:
            async with _rpc_client(self._rpc_url) as client:
                response = await asyncio.wait_for(
                    client.request(
                        AccountInfo(account=address, ledger_index="validated")
                    ),
                    timeout=RPC_TIMEOUT,
                )
            balance_drops = response.result.get("account_data", {}).get("Balance", "0")
            return str(drops_to_xrp(balance_drops))
        except Exception:
            logger.warning("get_balance failed for %s", address, exc_info=True)
            return "0"

    # ── AMM stubs (not yet implemented for testnet) ──────────────────
    # TODO: XRPL testnet supports AMM natively. Implement real AMM
    # integration (AMMCreate, AMMDeposit, AMMWithdraw, AMMInfo) in a
    # future Feature Pass. For now these return clear stub errors.

    async def get_amm_info(
        self,
        asset_a_currency: str,
        asset_a_issuer: str,
        asset_b_currency: str,
        asset_b_issuer: str,
    ) -> AmmInfo | None:
        return None

    async def submit_amm_create(
        self,
        wallet_seed: str,
        asset_a_currency: str,
        asset_a_value: str,
        asset_a_issuer: str,
        asset_b_currency: str,
        asset_b_value: str,
        asset_b_issuer: str,
        trading_fee: int = 500,
    ) -> SubmitResult:
        return SubmitResult(
            success=False,
            result_code="notSupported",
            error="AMM not yet implemented for testnet transport. Use --dry-run for AMM modules.",
        )

    async def submit_amm_deposit(
        self,
        wallet_seed: str,
        asset_a_currency: str,
        asset_a_value: str,
        asset_a_issuer: str,
        asset_b_currency: str,
        asset_b_value: str,
        asset_b_issuer: str,
    ) -> SubmitResult:
        return SubmitResult(
            success=False,
            result_code="notSupported",
            error="AMM not yet implemented for testnet transport. Use --dry-run for AMM modules.",
        )

    async def submit_amm_withdraw(
        self,
        wallet_seed: str,
        asset_a_currency: str,
        asset_a_issuer: str,
        asset_b_currency: str,
        asset_b_issuer: str,
        lp_token_value: str = "",
    ) -> SubmitResult:
        return SubmitResult(
            success=False,
            result_code="notSupported",
            error="AMM not yet implemented for testnet transport. Use --dry-run for AMM modules.",
        )

    async def get_lp_token_balance(
        self,
        address: str,
        lp_token_currency: str,
        lp_token_issuer: str,
    ) -> str:
        logger.warning("AMM LP balance not available on testnet — returns 0")
        return "0"
