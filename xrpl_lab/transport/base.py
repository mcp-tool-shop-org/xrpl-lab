"""Transport interface — abstraction over XRPL network interactions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class NetworkInfo:
    """Basic network health info."""

    network: str
    rpc_url: str
    connected: bool
    ledger_index: int | None = None


@dataclass
class FundResult:
    """Result of a faucet funding request."""

    success: bool
    address: str
    balance: str = "0"
    message: str = ""


@dataclass
class SubmitResult:
    """Result of a transaction submission."""

    success: bool
    txid: str = ""
    result_code: str = ""
    fee: str = "0"
    ledger_index: int | None = None
    error: str = ""
    explorer_url: str = ""


@dataclass
class TxInfo:
    """Full transaction details from the ledger."""

    txid: str
    tx_type: str = ""
    account: str = ""
    destination: str = ""
    amount: str = "0"
    fee: str = "0"
    result_code: str = ""
    ledger_index: int | None = None
    memos: list[str] | None = None
    validated: bool = False
    raw: dict | None = None


@dataclass
class TrustLineInfo:
    """A single trust line between two accounts."""

    account: str
    peer: str
    currency: str
    balance: str = "0"
    limit: str = "0"


@dataclass
class AccountSnapshot:
    """Account state at a point in time — balance, owner count, reserves."""

    address: str
    balance_drops: str = "0"
    owner_count: int = 0
    sequence: int = 0


@dataclass
class OfferInfo:
    """A single DEX offer on the ledger."""

    sequence: int
    taker_pays: str  # e.g. "10/LAB/rISSUER..." or "1000000" (drops for XRP)
    taker_gets: str  # e.g. "1000000" (drops for XRP) or "10/LAB/rISSUER..."
    quality: str = ""


@dataclass
class AmmInfo:
    """AMM pool state for an asset pair."""

    asset_a: str  # e.g. "XRP" or "LAB/rISSUER..."
    asset_b: str
    pool_a: str = "0"  # pool balance for asset A
    pool_b: str = "0"  # pool balance for asset B
    lp_token_currency: str = ""
    lp_token_issuer: str = ""  # AMM account that issues LP tokens
    lp_supply: str = "0"
    trading_fee: str = "0"


class Transport(ABC):
    """Abstract base for XRPL network operations."""

    @abstractmethod
    async def get_network_info(self) -> NetworkInfo:
        """Check network connectivity and return info."""

    @abstractmethod
    async def fund_from_faucet(self, address: str) -> FundResult:
        """Request testnet XRP from the faucet."""

    @abstractmethod
    async def submit_payment(
        self,
        wallet_seed: str,
        destination: str,
        amount: str,
        memo: str = "",
    ) -> SubmitResult:
        """Submit a payment transaction."""

    @abstractmethod
    async def submit_trust_set(
        self,
        wallet_seed: str,
        issuer: str,
        currency: str,
        limit: str,
    ) -> SubmitResult:
        """Submit a TrustSet transaction."""

    @abstractmethod
    async def submit_issued_payment(
        self,
        wallet_seed: str,
        destination: str,
        currency: str,
        issuer: str,
        amount: str,
        memo: str = "",
    ) -> SubmitResult:
        """Submit a payment of issued currency (not XRP)."""

    @abstractmethod
    async def get_trust_lines(self, address: str) -> list[TrustLineInfo]:
        """Get trust lines for an address."""

    @abstractmethod
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
        """Submit an OfferCreate transaction on the DEX."""

    @abstractmethod
    async def submit_offer_cancel(
        self,
        wallet_seed: str,
        offer_sequence: int,
    ) -> SubmitResult:
        """Submit an OfferCancel transaction."""

    @abstractmethod
    async def get_account_offers(self, address: str) -> list[OfferInfo]:
        """Get active offers for an address."""

    @abstractmethod
    async def get_account_info(self, address: str) -> AccountSnapshot:
        """Get account info including balance, owner count, and sequence."""

    @abstractmethod
    async def fetch_tx(self, txid: str) -> TxInfo:
        """Fetch full transaction details by txid."""

    @abstractmethod
    async def get_balance(self, address: str) -> str:
        """Get XRP balance for an address."""

    @abstractmethod
    async def get_amm_info(
        self,
        asset_a_currency: str,
        asset_a_issuer: str,
        asset_b_currency: str,
        asset_b_issuer: str,
    ) -> AmmInfo | None:
        """Get AMM pool info for an asset pair. Returns None if no AMM exists."""

    @abstractmethod
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
        """Create an AMM pool for an asset pair (AMMCreate)."""

    @abstractmethod
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
        """Deposit both assets into an AMM pool (AMMDeposit)."""

    @abstractmethod
    async def submit_amm_withdraw(
        self,
        wallet_seed: str,
        asset_a_currency: str,
        asset_a_issuer: str,
        asset_b_currency: str,
        asset_b_issuer: str,
        lp_token_value: str = "",
    ) -> SubmitResult:
        """Withdraw from an AMM pool by returning LP tokens (AMMWithdraw)."""

    @abstractmethod
    async def get_lp_token_balance(
        self,
        address: str,
        lp_token_currency: str,
        lp_token_issuer: str,
    ) -> str:
        """Get LP token balance for an address. Returns '0' if none."""
