"""XRPL Testnet transport — real network interactions via xrpl-py."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.ledger import get_latest_validated_ledger_sequence
from xrpl.asyncio.transaction import submit_and_wait
from xrpl.models import (
    AccountInfo,
    AccountLines,
    AccountNFTs,
    AccountOffers,
    IssuedCurrencyAmount,
    Memo,
    NFTokenMint,
    OfferCancel,
    OfferCreate,
    Payment,
    TrustSet,
    Tx,
)
from xrpl.utils import drops_to_xrp, get_nftoken_id, hex_to_str, str_to_hex, xrp_to_drops
from xrpl.wallet import Wallet

from .base import (
    AccountSnapshot,
    AmmInfo,
    FundResult,
    NetworkInfo,
    NFTInfo,
    OfferInfo,
    SubmitResult,
    Transport,
    TrustLineInfo,
    TxInfo,
)

logger = logging.getLogger(__name__)

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
        except Exception:
            logger.debug("get_network_info failed", exc_info=True)
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
                        data = resp.json()
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
                ledger_idx = result.get("ledger_index") or meta.get("ledger_index")

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
                if any(
                    code in last_error
                    for code in ("temBAD", "tefBAD", "Invalid", "malformed")
                ):
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
                ledger_idx = (
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
                if any(
                    code in last_error
                    for code in ("temBAD", "tefBAD", "Invalid", "malformed")
                ):
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
                ledger_idx = (
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
                if any(
                    code in last_error
                    for code in ("temBAD", "tefBAD", "Invalid", "malformed")
                ):
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
    ) -> SubmitResult:
        guard = self._network_guard()
        if guard is not None:
            return SubmitResult(success=False, result_code="local_error", error=guard)

        last_error = ""
        for attempt in range(MAX_RETRIES + 1):
            try:
                wallet = Wallet.from_seed(wallet_seed)
                mint = NFTokenMint(
                    account=wallet.address,
                    nftoken_taxon=taxon,
                    uri=str_to_hex(uri) if uri else None,
                    transfer_fee=transfer_fee or None,
                    flags=8 if transferable else 0,  # tfTransferable = 0x8
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
                ledger_idx = result.get("ledger_index") or meta.get("ledger_index")

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
                if any(
                    code in last_error
                    for code in ("temBAD", "tefBAD", "Invalid", "malformed")
                ):
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
                uri_hex = n.get("URI", "") or ""
                try:
                    uri = hex_to_str(uri_hex) if uri_hex else ""
                except Exception:
                    uri = uri_hex
                out.append(
                    NFTInfo(
                        nft_id=n.get("NFTokenID", ""),
                        issuer=n.get("Issuer", address),
                        taxon=int(n.get("NFTokenTaxon", 0)),
                        uri=uri,
                        flags=int(n.get("Flags", 0)),
                        transfer_fee=int(n.get("TransferFee", 0)),
                        serial=int(n.get("nft_serial", 0)),
                    )
                )
            return out
        except Exception:
            logger.warning("get_account_nfts failed for %s", address, exc_info=True)
            return []

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
                ledger_idx = (
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
                if any(
                    code in last_error
                    for code in ("temBAD", "tefBAD", "Invalid", "malformed")
                ):
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
                ledger_idx = (
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
                if any(
                    code in last_error
                    for code in ("temBAD", "tefBAD", "Invalid", "malformed")
                ):
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
            return [
                OfferInfo(
                    sequence=o.get("Sequence", o.get("seq", 0)),
                    taker_pays=self._format_amount(o.get("taker_pays")),
                    taker_gets=self._format_amount(o.get("taker_gets")),
                    quality=str(o.get("quality", "")),
                )
                for o in offers
            ]
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
                ledger_index=result.get("ledger_index"),
                memos=_decode_memos(memos_raw),
                validated=result.get("validated", False),
                raw=result,
            )
        except TimeoutError:
            return TxInfo(
                txid=txid,
                result_code="fetch_error: Timed out fetching transaction. Try again.",
            )
        except Exception as exc:
            return TxInfo(txid=txid, result_code=f"fetch_error: {_friendly_error(exc)}")

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
