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
from xrpl.asyncio.transaction import submit_and_wait
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
    Payment,
    PaymentChannelClaim,
    PaymentChannelClaimFlag,
    PaymentChannelCreate,
    PaymentChannelFund,
    TrustSet,
    TrustSetFlag,
    Tx,
)
from xrpl.models.amounts import MPTAmount
from xrpl.utils import drops_to_xrp, get_nftoken_id, hex_to_str, str_to_hex, xrp_to_drops
from xrpl.wallet import Wallet

from .base import (
    AccountSnapshot,
    AmmInfo,
    ChannelInfo,
    DIDInfo,
    EscrowInfo,
    FreezeStatus,
    FundResult,
    MPTIssuanceInfo,
    NetworkInfo,
    NFTInfo,
    NFTOfferInfo,
    OfferInfo,
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
# succeed. These match the canonical ``temBAD…`` / ``tefBAD…`` result codes
# (e.g. ``temBADAmount``, ``tefBAD_AUTH``) as whole tokens.
#
# TRANSPORT-A-004: the previous heuristic substring-scanned the FRIENDLY
# message for ``("temBAD", "tefBAD", "Invalid", "malformed")``. The bare
# English words "Invalid"/"malformed" are far too broad — a transient error
# whose friendly text merely contains "Invalid" (e.g. "Invalid response from
# RPC endpoint, please retry") would suppress a warranted retry. We now match
# only genuine result-code tokens on word boundaries, so generic prose can no
# longer short-circuit the retry loop while real temBAD*/tefBAD* aborts still do.
_NO_RETRY_CODE_RE = re.compile(r"\b(?:temBAD|tefBAD)\w*\b")


def _is_no_retry_error(message: str) -> bool:
    """Return True if *message* names a malformed/permanent XRPL result code.

    Used by the signing/submit retry loops to abort early instead of retrying a
    transaction that can never succeed. Matches ``temBAD*`` / ``tefBAD*``
    result-code tokens only — not the generic words "Invalid" or "malformed".
    """
    return bool(_NO_RETRY_CODE_RE.search(message or ""))


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


class XRPLTestnetTransport(Transport):
    """Real XRPL Testnet transport using xrpl-py async client."""

    def __init__(self) -> None:
        self._rpc_url = get_rpc_url()

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

        guard = self._network_guard()
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
    ) -> SubmitResult:
        guard = self._network_guard()
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

        last_error = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                wallet = Wallet.from_seed(wallet_seed)
                payment = Payment(
                    account=wallet.address,
                    destination=destination,
                    amount=xrp_to_drops(amount_f),  # xrp_to_drops accepts Decimal
                    memos=_memo_field(memo) or None,
                )
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(payment, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )

                result = response.result
                meta = result.get("meta", {})
                result_code = meta.get(
                    "TransactionResult", result.get("engine_result", "unknown")
                )
                txid = result.get("hash", "")
                fee = result.get("Fee", "0")
                ledger_idx = _int_or_none(
                    result.get("ledger_index") or meta.get("ledger_index")
                )

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
                )

            except TimeoutError:
                last_error = (
                    "Transaction submission timed out. The ledger may be under load. "
                    "Try again in a minute."
                )
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
        guard = self._network_guard()
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
                meta = result.get("meta", {})
                result_code = meta.get(
                    "TransactionResult", result.get("engine_result", "unknown")
                )
                txid = result.get("hash", "")
                fee = result.get("Fee", "0")
                ledger_idx = _int_or_none(
                    result.get("ledger_index") or meta.get("ledger_index")
                )

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
                )

            except TimeoutError:
                last_error = (
                    "TrustSet submission timed out. Try again in a minute."
                )
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
        guard = self._network_guard()
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
                meta = result.get("meta", {})
                result_code = meta.get(
                    "TransactionResult", result.get("engine_result", "unknown")
                )
                txid = result.get("hash", "")
                fee = result.get("Fee", "0")
                ledger_idx = _int_or_none(
                    result.get("ledger_index") or meta.get("ledger_index")
                )

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
                )

            except TimeoutError:
                last_error = (
                    "Issued payment timed out. Try again in a minute."
                )
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
        guard = self._network_guard()
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
                result_code = meta.get(
                    "TransactionResult", result.get("engine_result", "unknown")
                )
                txid = result.get("hash", "")
                fee = result.get("Fee", "0")
                ledger_idx = _int_or_none(
                    result.get("ledger_index") or meta.get("ledger_index")
                )

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
                )

            except TimeoutError:
                last_error = "NFTokenMint submission timed out. Try again in a minute."
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
                result_code = meta.get(
                    "TransactionResult", result.get("engine_result", "unknown")
                )
                txid = result.get("hash", "")
                fee = result.get("Fee", "0")
                ledger_idx = _int_or_none(
                    result.get("ledger_index") or meta.get("ledger_index")
                )
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
                    error=error_msg, **extra,
                )
            except TimeoutError:
                last_error = f"{label} submission timed out. Try again in a minute."
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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

    async def submit_mpt_issuance_create(
        self,
        wallet_seed: str,
        maximum_amount: str,
        asset_scale: int = 0,
        transfer_fee: int = 0,
        can_transfer: bool = True,
    ) -> SubmitResult:
        guard = self._network_guard()
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
        guard = self._network_guard()
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
        guard = self._network_guard()
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
                return str(o.get("MPTAmount", o.get("MPTAmount", "0")) or "0")
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
        guard = self._network_guard()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        last_error = ""

        for attempt in range(MAX_RETRIES + 1):
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
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(offer, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )

                result = response.result
                meta = result.get("meta", {})
                result_code = meta.get(
                    "TransactionResult", result.get("engine_result", "unknown")
                )
                txid = result.get("hash", "")
                fee = result.get("Fee", "0")
                ledger_idx = _int_or_none(
                    result.get("ledger_index") or meta.get("ledger_index")
                )

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
                )

            except TimeoutError:
                last_error = (
                    "OfferCreate timed out. Try again in a minute."
                )
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

    async def submit_offer_cancel(
        self,
        wallet_seed: str,
        offer_sequence: int,
    ) -> SubmitResult:
        guard = self._network_guard()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        last_error = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                wallet = Wallet.from_seed(wallet_seed)
                cancel = OfferCancel(
                    account=wallet.address,
                    offer_sequence=offer_sequence,
                )
                async with _rpc_client(self._rpc_url) as client:
                    response = await asyncio.wait_for(
                        submit_and_wait(cancel, client, wallet),
                        timeout=SUBMIT_TIMEOUT,
                    )

                result = response.result
                meta = result.get("meta", {})
                result_code = meta.get(
                    "TransactionResult", result.get("engine_result", "unknown")
                )
                txid = result.get("hash", "")
                fee = result.get("Fee", "0")
                ledger_idx = _int_or_none(
                    result.get("ledger_index") or meta.get("ledger_index")
                )

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
                )

            except TimeoutError:
                last_error = (
                    "OfferCancel timed out. Try again in a minute."
                )
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
            memos_raw = result.get("Memos", [])

            return TxInfo(
                txid=txid,
                tx_type=result.get("TransactionType", ""),
                account=result.get("Account", ""),
                destination=result.get("Destination", ""),
                amount=str(result.get("Amount", "0")),
                fee=result.get("Fee", "0"),
                result_code=meta.get("TransactionResult", ""),
                ledger_index=_int_or_none(result.get("ledger_index")),
                memos=_decode_memos(memos_raw),
                validated=result.get("validated", False),
                raw=result,
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
