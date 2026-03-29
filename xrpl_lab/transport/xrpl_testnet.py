"""XRPL Testnet transport — real network interactions via xrpl-py."""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.ledger import get_latest_validated_ledger_sequence
from xrpl.asyncio.transaction import submit_and_wait
from xrpl.models import (
    AccountInfo,
    AccountLines,
    AccountOffers,
    IssuedCurrencyAmount,
    Memo,
    OfferCancel,
    OfferCreate,
    Payment,
    TrustSet,
    Tx,
)
from xrpl.utils import drops_to_xrp, xrp_to_drops
from xrpl.wallet import Wallet

from .base import (
    AccountSnapshot,
    AmmInfo,
    FundResult,
    NetworkInfo,
    OfferInfo,
    SubmitResult,
    Transport,
    TrustLineInfo,
    TxInfo,
)

DEFAULT_RPC_URL = "https://s.altnet.rippletest.net:51234"
DEFAULT_FAUCET_URL = "https://faucet.altnet.rippletest.net/accounts"
EXPLORER_BASE = "https://testnet.xrpl.org/transactions"

# Timeouts and retries
RPC_TIMEOUT = 30  # seconds per RPC call
FAUCET_TIMEOUT = 30
SUBMIT_TIMEOUT = 60  # submissions can take a few ledger closes
MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds between retries


def get_rpc_url() -> str:
    return os.environ.get("XRPL_LAB_RPC_URL", DEFAULT_RPC_URL)


def get_faucet_url() -> str:
    return os.environ.get("XRPL_LAB_FAUCET_URL", DEFAULT_FAUCET_URL)


def _memo_field(text: str) -> list[Memo]:
    """Create a memo from plain text."""
    if not text:
        return []
    return [Memo(memo_data=text.encode("utf-8").hex())]


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


class XRPLTestnetTransport(Transport):
    """Real XRPL Testnet transport using xrpl-py async client."""

    def __init__(self) -> None:
        self._rpc_url = get_rpc_url()

    @property
    def network_name(self) -> str:
        return "testnet"

    async def get_network_info(self) -> NetworkInfo:
        try:
            async with AsyncJsonRpcClient(self._rpc_url) as client:
                ledger_idx = await asyncio.wait_for(
                    get_latest_validated_ledger_sequence(client),
                    timeout=RPC_TIMEOUT,
                )
                return NetworkInfo(
                    network="testnet",
                    rpc_url=self._rpc_url,
                    connected=True,
                    ledger_index=ledger_idx,
                )
        except Exception:
            logger.debug("get_network_info failed", exc_info=True)
            return NetworkInfo(
                network="testnet",
                rpc_url=self._rpc_url,
                connected=False,
                ledger_index=None,
            )

    async def fund_from_faucet(self, address: str) -> FundResult:
        import httpx

        faucet_url = get_faucet_url()
        last_error = ""

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
                        last_error = "Rate limited by faucet. Wait a minute and try again."
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                            continue
                    last_error = f"Faucet returned {resp.status_code}: {resp.text[:200]}"
            except httpx.TimeoutException:
                last_error = "Faucet timed out. The testnet faucet may be down."
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
                    continue
            except Exception as exc:
                last_error = _friendly_error(exc)
                break

        return FundResult(success=False, address=address, message=last_error)

    async def submit_payment(
        self,
        wallet_seed: str,
        destination: str,
        amount: str,
        memo: str = "",
    ) -> SubmitResult:
        try:
            amount_f = float(amount)
        except (ValueError, TypeError):
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
                    amount=xrp_to_drops(amount_f),
                    memos=_memo_field(memo) or None,
                )
                async with AsyncJsonRpcClient(self._rpc_url) as client:
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
                    explorer_url=f"{EXPLORER_BASE}/{txid}" if txid else "",
                    error=error_msg,
                )

            except TimeoutError:
                last_error = (
                    "Transaction submission timed out. The ledger may be under load. "
                    "Try again in a minute."
                )
                if attempt < MAX_RETRIES:
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
                async with AsyncJsonRpcClient(self._rpc_url) as client:
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
                    explorer_url=f"{EXPLORER_BASE}/{txid}" if txid else "",
                    error=error_msg,
                )

            except TimeoutError:
                last_error = (
                    "TrustSet submission timed out. Try again in a minute."
                )
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
                async with AsyncJsonRpcClient(self._rpc_url) as client:
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
                    explorer_url=f"{EXPLORER_BASE}/{txid}" if txid else "",
                    error=error_msg,
                )

            except TimeoutError:
                last_error = (
                    "Issued payment timed out. Try again in a minute."
                )
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

        return SubmitResult(
            success=False,
            result_code="local_error",
            error=last_error,
        )

    async def get_trust_lines(self, address: str) -> list[TrustLineInfo]:
        try:
            async with AsyncJsonRpcClient(self._rpc_url) as client:
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
            logger.debug("get_trust_lines failed for %s", address, exc_info=True)
            return []

    def _amount_obj(
        self, currency: str, value: str, issuer: str
    ) -> str | IssuedCurrencyAmount:
        """Build an XRP drops string or IssuedCurrencyAmount."""
        if currency == "XRP":
            try:
                return xrp_to_drops(float(value))
            except (ValueError, TypeError):
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
                async with AsyncJsonRpcClient(self._rpc_url) as client:
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
                    explorer_url=f"{EXPLORER_BASE}/{txid}" if txid else "",
                    error=error_msg,
                )

            except TimeoutError:
                last_error = (
                    "OfferCreate timed out. Try again in a minute."
                )
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
        last_error = ""

        for attempt in range(MAX_RETRIES + 1):
            try:
                wallet = Wallet.from_seed(wallet_seed)
                cancel = OfferCancel(
                    account=wallet.address,
                    offer_sequence=offer_sequence,
                )
                async with AsyncJsonRpcClient(self._rpc_url) as client:
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
                    explorer_url=f"{EXPLORER_BASE}/{txid}" if txid else "",
                    error=error_msg,
                )

            except TimeoutError:
                last_error = (
                    "OfferCancel timed out. Try again in a minute."
                )
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

        return SubmitResult(
            success=False,
            result_code="local_error",
            error=last_error,
        )

    async def get_account_offers(self, address: str) -> list[OfferInfo]:
        try:
            async with AsyncJsonRpcClient(self._rpc_url) as client:
                response = await asyncio.wait_for(
                    client.request(
                        AccountOffers(account=address, ledger_index="validated")
                    ),
                    timeout=RPC_TIMEOUT,
                )
            offers = response.result.get("offers", [])
            return [
                OfferInfo(
                    sequence=o.get("seq", 0),
                    taker_pays=self._format_amount(o.get("taker_pays")),
                    taker_gets=self._format_amount(o.get("taker_gets")),
                    quality=str(o.get("quality", "")),
                )
                for o in offers
            ]
        except Exception:
            logger.debug("get_account_offers failed for %s", address, exc_info=True)
            return []

    async def get_account_info(self, address: str) -> AccountSnapshot:
        try:
            async with AsyncJsonRpcClient(self._rpc_url) as client:
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
            logger.debug("get_account_info failed for %s", address, exc_info=True)
            return AccountSnapshot(address=address)

    async def fetch_tx(self, txid: str) -> TxInfo:
        try:
            async with AsyncJsonRpcClient(self._rpc_url) as client:
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
            async with AsyncJsonRpcClient(self._rpc_url) as client:
                response = await asyncio.wait_for(
                    client.request(
                        AccountInfo(account=address, ledger_index="validated")
                    ),
                    timeout=RPC_TIMEOUT,
                )
            balance_drops = response.result.get("account_data", {}).get("Balance", "0")
            return str(drops_to_xrp(balance_drops))
        except Exception:
            logger.debug("get_balance failed for %s", address, exc_info=True)
            return "0"

    # ── AMM stubs (not yet implemented for testnet) ──────────────────

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
            error="AMM not yet implemented for testnet transport. Use --dry-run.",
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
            error="AMM not yet implemented for testnet transport. Use --dry-run.",
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
            error="AMM not yet implemented for testnet transport. Use --dry-run.",
        )

    async def get_lp_token_balance(
        self,
        address: str,
        lp_token_currency: str,
        lp_token_issuer: str,
    ) -> str:
        return "0"
