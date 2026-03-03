"""Dry-run transport — no network, deterministic outputs for testing and --dry-run."""

from __future__ import annotations

import hashlib
import time

from .base import (
    FundResult,
    NetworkInfo,
    SubmitResult,
    Transport,
    TrustLineInfo,
    TxInfo,
)

# Deterministic fake data for offline use
_FAKE_TXID_PREFIX = "DRYRUN"
_FAKE_ADDRESS = "rDRYRUN1234567890ABCDEFGHIJK"
_COUNTER = 0


def _next_txid() -> str:
    global _COUNTER
    _COUNTER += 1
    raw = f"{_FAKE_TXID_PREFIX}-{_COUNTER}-{time.time()}"
    return hashlib.sha256(raw.encode()).hexdigest().upper()[:64]


class DryRunTransport(Transport):
    """Offline transport that simulates XRPL responses without network access."""

    def __init__(self, fail_next: bool = False) -> None:
        self._fail_next = fail_next
        self._balance = "1000000000"  # 1000 XRP in drops
        self._funded_addresses: set[str] = set()
        self._trust_lines: list[TrustLineInfo] = []

    def set_fail_next(self, fail: bool = True) -> None:
        """Configure the next submission to fail (for failure_literacy module)."""
        self._fail_next = fail

    async def get_network_info(self) -> NetworkInfo:
        return NetworkInfo(
            network="dry-run",
            rpc_url="none",
            connected=True,
            ledger_index=99999999,
        )

    async def fund_from_faucet(self, address: str) -> FundResult:
        self._funded_addresses.add(address)
        return FundResult(
            success=True,
            address=address,
            balance="1000.000000",
            message="[dry-run] Funded with 1000 XRP",
        )

    async def submit_payment(
        self,
        wallet_seed: str,
        destination: str,
        amount: str,
        memo: str = "",
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False,
                txid="",
                result_code="tecUNFUNDED_PAYMENT",
                fee="12",
                error="[dry-run] Simulated failure: insufficient funds",
            )

        txid = _next_txid()
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
        )

    async def submit_trust_set(
        self,
        wallet_seed: str,
        issuer: str,
        currency: str,
        limit: str,
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False,
                result_code="tecNO_DST",
                fee="12",
                error="[dry-run] Simulated failure: issuer not found",
            )

        txid = _next_txid()
        # Track the trust line
        self._trust_lines.append(
            TrustLineInfo(
                account=_FAKE_ADDRESS,
                peer=issuer,
                currency=currency,
                balance="0",
                limit=limit,
            )
        )
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
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
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False,
                result_code="tecPATH_DRY",
                fee="12",
                error="[dry-run] Simulated failure: no trust line",
            )

        txid = _next_txid()
        # Update trust line balance
        for tl in self._trust_lines:
            if tl.currency == currency and tl.peer == issuer:
                tl.balance = amount
                break
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
        )

    async def get_trust_lines(self, address: str) -> list[TrustLineInfo]:
        return list(self._trust_lines)

    async def fetch_tx(self, txid: str) -> TxInfo:
        return TxInfo(
            txid=txid,
            tx_type="Payment",
            account=_FAKE_ADDRESS,
            destination="rFAKEDESTINATION123456789AB",
            amount="10000000",
            fee="12",
            result_code="tesSUCCESS",
            ledger_index=99999999,
            memos=["XRPLLAB|dry-run"],
            validated=True,
        )

    async def get_balance(self, address: str) -> str:
        return "1000.000000" if address in self._funded_addresses else "0"
