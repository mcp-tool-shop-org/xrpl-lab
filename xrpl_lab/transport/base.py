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
    async def fetch_tx(self, txid: str) -> TxInfo:
        """Fetch full transaction details by txid."""

    @abstractmethod
    async def get_balance(self, address: str) -> str:
        """Get XRP balance for an address."""
