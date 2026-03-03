"""Dry-run transport — no network, deterministic outputs for testing and --dry-run."""

from __future__ import annotations

import hashlib
import time

from .base import (
    AccountSnapshot,
    FundResult,
    NetworkInfo,
    OfferInfo,
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
        self._offers: list[OfferInfo] = []
        self._offer_seq = 100  # starting sequence for fake offers
        self._owner_count = 0  # tracks owned objects (trust lines, offers)
        self._tx_fixtures: dict[str, TxInfo] = {}  # txid -> TxInfo for audit testing

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

        # Find existing trust line for this currency + issuer
        existing = None
        for tl in self._trust_lines:
            if tl.currency == currency and tl.peer == issuer:
                existing = tl
                break

        if limit == "0":
            # Removing a trust line
            if existing is None:
                # No trust line to remove — success (no-op)
                return SubmitResult(
                    success=True,
                    txid=txid,
                    result_code="tesSUCCESS",
                    fee="12",
                    ledger_index=99999999,
                    explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
                )
            if existing.balance != "0":
                # Can't remove with non-zero balance
                return SubmitResult(
                    success=False,
                    result_code="tecNO_PERMISSION",
                    fee="12",
                    error=(
                        f"[dry-run] Cannot remove trust line — "
                        f"balance is {existing.balance} (must be 0)"
                    ),
                )
            # Remove trust line and decrement owner count
            self._trust_lines.remove(existing)
            self._owner_count = max(0, self._owner_count - 1)
        elif existing:
            # Update existing trust line limit (don't create duplicate)
            existing.limit = limit
        else:
            # Create new trust line
            self._trust_lines.append(
                TrustLineInfo(
                    account=_FAKE_ADDRESS,
                    peer=issuer,
                    currency=currency,
                    balance="0",
                    limit=limit,
                )
            )
            self._owner_count += 1

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

        # Realistic validation: check trust line exists
        matching_tl = None
        for tl in self._trust_lines:
            if tl.currency == currency and tl.peer == issuer:
                matching_tl = tl
                break

        if matching_tl is None:
            return SubmitResult(
                success=False,
                result_code="tecPATH_DRY",
                fee="12",
                error=(
                    "[dry-run] No trust line for "
                    f"{currency}/{issuer[:12]}... — "
                    "recipient must set a trust line first"
                ),
            )

        txid = _next_txid()
        matching_tl.balance = amount
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
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False,
                result_code="tecUNFUNDED_OFFER",
                fee="12",
                error="[dry-run] Simulated failure: unfunded offer",
            )

        txid = _next_txid()
        seq = self._offer_seq
        self._offer_seq += 1

        # Format taker_pays / taker_gets for display
        if taker_pays_currency == "XRP":
            pays_str = taker_pays_value
        else:
            pays_str = (
                f"{taker_pays_value}/{taker_pays_currency}"
                f"/{taker_pays_issuer[:12]}"
            )
        if taker_gets_currency == "XRP":
            gets_str = taker_gets_value
        else:
            gets_str = (
                f"{taker_gets_value}/{taker_gets_currency}"
                f"/{taker_gets_issuer[:12]}"
            )

        self._offers.append(
            OfferInfo(
                sequence=seq,
                taker_pays=pays_str,
                taker_gets=gets_str,
            )
        )
        self._owner_count += 1
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
        )

    async def submit_offer_cancel(
        self,
        wallet_seed: str,
        offer_sequence: int,
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False,
                result_code="tecNO_ENTRY",
                fee="12",
                error="[dry-run] Simulated failure: offer not found",
            )

        txid = _next_txid()
        # Remove the offer from tracked list and decrement owner count
        before = len(self._offers)
        self._offers = [o for o in self._offers if o.sequence != offer_sequence]
        if len(self._offers) < before:
            self._owner_count = max(0, self._owner_count - 1)
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
        )

    async def get_account_offers(self, address: str) -> list[OfferInfo]:
        return list(self._offers)

    async def get_account_info(self, address: str) -> AccountSnapshot:
        balance = self._balance if address in self._funded_addresses else "0"
        return AccountSnapshot(
            address=address,
            balance_drops=balance,
            owner_count=self._owner_count,
            sequence=42,
        )

    def set_tx_fixtures(self, fixtures: dict[str, TxInfo]) -> None:
        """Load tx fixtures for audit testing."""
        self._tx_fixtures = dict(fixtures)

    async def fetch_tx(self, txid: str) -> TxInfo:
        # Check fixtures first (for audit testing)
        if txid in self._tx_fixtures:
            return self._tx_fixtures[txid]
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
