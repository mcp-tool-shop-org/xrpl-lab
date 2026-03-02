"""XRPL Testnet transport — real network interactions via xrpl-py."""

from __future__ import annotations

import os

from xrpl.asyncio.clients import AsyncJsonRpcClient
from xrpl.asyncio.ledger import get_latest_validated_ledger_sequence
from xrpl.asyncio.transaction import submit_and_wait
from xrpl.models import AccountInfo, Memo, Payment, Tx
from xrpl.utils import drops_to_xrp, xrp_to_drops
from xrpl.wallet import Wallet

from .base import (
    FundResult,
    NetworkInfo,
    SubmitResult,
    Transport,
    TxInfo,
)

DEFAULT_RPC_URL = "https://s.altnet.rippletest.net:51234"
DEFAULT_FAUCET_URL = "https://faucet.altnet.rippletest.net/accounts"
EXPLORER_BASE = "https://testnet.xrpl.org/transactions"


def _get_rpc_url() -> str:
    return os.environ.get("XRPL_LAB_RPC_URL", DEFAULT_RPC_URL)


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


class XRPLTestnetTransport(Transport):
    """Real XRPL Testnet transport using xrpl-py async client."""

    def __init__(self) -> None:
        self._rpc_url = _get_rpc_url()

    async def get_network_info(self) -> NetworkInfo:
        try:
            async with AsyncJsonRpcClient(self._rpc_url) as client:
                ledger_idx = await get_latest_validated_ledger_sequence(client)
                return NetworkInfo(
                    network="testnet",
                    rpc_url=self._rpc_url,
                    connected=True,
                    ledger_index=ledger_idx,
                )
        except Exception:
            return NetworkInfo(
                network="testnet",
                rpc_url=self._rpc_url,
                connected=False,
                ledger_index=None,
            )

    async def fund_from_faucet(self, address: str) -> FundResult:
        import httpx

        faucet_url = os.environ.get("XRPL_LAB_FAUCET_URL", DEFAULT_FAUCET_URL)
        try:
            async with httpx.AsyncClient(timeout=30) as http:
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
                return FundResult(
                    success=False,
                    address=address,
                    message=f"Faucet returned {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as exc:
            return FundResult(
                success=False,
                address=address,
                message=f"Faucet request failed: {exc}",
            )

    async def submit_payment(
        self,
        wallet_seed: str,
        destination: str,
        amount: str,
        memo: str = "",
    ) -> SubmitResult:
        try:
            wallet = Wallet.from_seed(wallet_seed)
            payment = Payment(
                account=wallet.address,
                destination=destination,
                amount=xrp_to_drops(float(amount)),
                memos=_memo_field(memo) or None,
            )
            async with AsyncJsonRpcClient(self._rpc_url) as client:
                response = await submit_and_wait(payment, client, wallet)

            result = response.result
            meta = result.get("meta", {})
            result_code = meta.get("TransactionResult", result.get("engine_result", "unknown"))
            txid = result.get("hash", "")
            fee = result.get("Fee", "0")
            ledger_idx = result.get("ledger_index") or meta.get("ledger_index")

            success = result_code == "tesSUCCESS"
            return SubmitResult(
                success=success,
                txid=txid,
                result_code=result_code,
                fee=fee,
                ledger_index=ledger_idx,
                explorer_url=f"{EXPLORER_BASE}/{txid}" if txid else "",
                error="" if success else f"Transaction failed: {result_code}",
            )
        except Exception as exc:
            return SubmitResult(
                success=False,
                result_code="local_error",
                error=str(exc),
            )

    async def fetch_tx(self, txid: str) -> TxInfo:
        try:
            async with AsyncJsonRpcClient(self._rpc_url) as client:
                response = await client.request(Tx(transaction=txid))

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
        except Exception as exc:
            return TxInfo(txid=txid, result_code=f"fetch_error: {exc}")

    async def get_balance(self, address: str) -> str:
        try:
            async with AsyncJsonRpcClient(self._rpc_url) as client:
                response = await client.request(
                    AccountInfo(account=address, ledger_index="validated")
                )
            balance_drops = response.result.get("account_data", {}).get("Balance", "0")
            return str(drops_to_xrp(balance_drops))
        except Exception:
            return "0"
