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
    """Result of a faucet funding request.

    ``code`` is an optional structured LabError code (e.g.
    ``RUNTIME_FAUCET_RATE_LIMITED``) so callers — primarily the
    dashboard's facilitator UI — can route specific failure modes to
    distinct treatments without string-matching ``message``. Empty
    string means "no specific code" (success path, or a generic
    failure that doesn't map to a LabError taxonomy entry yet).
    Additive: existing readers of {success, address, balance, message}
    keep working unchanged.
    """

    success: bool
    address: str
    balance: str = "0"
    message: str = ""
    code: str = ""


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
    nft_id: str = ""  # NFTokenID, set on a successful NFTokenMint
    nft_offer_index: str = ""  # NFTokenOffer ledger index, set on NFTokenCreateOffer


@dataclass
class TxInfo:
    """Full transaction details from the ledger.

    ``fetch_error`` (TXBCD-002) is distinct from ``result_code``: it is set
    ONLY when the read-back itself failed (timeout / network / RPC error)
    BEFORE we ever learned the on-ledger result. A populated ``fetch_error``
    means "we could not determine the tx's fate", NOT "the tx failed" — a tx
    that genuinely succeeded on-ledger can still produce a ``fetch_error`` if
    the verification read-back times out. Callers (e.g. ``verify_tx``) MUST
    special-case ``fetch_error`` and surface a non-failure-attributing message
    rather than comparing ``result_code`` against ``tesSUCCESS``. Defaults
    None so the dry-run transport and every success path stay unchanged.
    """

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
    fetch_error: str | None = None


@dataclass
class TrustLineInfo:
    """A single trust line between two accounts."""

    account: str
    peer: str
    currency: str
    balance: str = "0"
    limit: str = "0"


@dataclass
class NFTInfo:
    """A single NFToken owned by an account."""

    nft_id: str
    issuer: str = ""
    taxon: int = 0
    uri: str = ""  # decoded UTF-8 if possible, else hex
    flags: int = 0
    transfer_fee: int = 0
    serial: int = 0


@dataclass
class NFTOfferInfo:
    """A single NFTokenOffer on the ledger (sell or buy).

    ``offer_index`` is the ledger object id (the value NFTokenAcceptOffer
    consumes as ``NFTokenSellOffer`` / ``NFTokenBuyOffer``). ``is_sell`` is
    True for sell offers (tfSellNFToken set). ``amount`` is the offer price as
    a display string (drops for XRP, ``value/CUR/issuer`` for issued).
    """

    offer_index: str
    nft_id: str = ""
    amount: str = "0"
    owner: str = ""  # account that created the offer
    destination: str = ""  # optional restricted buyer/seller
    is_sell: bool = True


@dataclass
class EscrowInfo:
    """A single Escrow object owned by an account.

    Contract note (TRANSPORT-A-003, resolved in v2.0.0): ``sequence`` is the
    EscrowCreate transaction sequence — the value EscrowFinish/EscrowCancel
    consume as ``OfferSequence``. Both transports now populate it: the dry-run
    transport sets a synthetic create-sequence, and the testnet transport
    derives the real one by reading the EscrowCreate tx via ``account_tx``
    (the ``account_objects`` Escrow ledger entry does NOT carry the originating
    sequence, so it must come from the tx, not the object). A 0 here means the
    create-sequence could not be resolved (e.g. the tx history was unreadable);
    finish/cancel will then need the sequence supplied explicitly.
    """

    sequence: int = 0  # EscrowCreate tx sequence (OfferSequence for finish/cancel)
    amount: str = "0"  # XRP drops (or token amount)
    destination: str = ""
    finish_after: int | None = None  # ripple-epoch seconds
    cancel_after: int | None = None
    condition: str = ""


@dataclass
class DIDInfo:
    """The DID ledger object for an account (one per account)."""

    account: str
    uri: str = ""  # decoded UTF-8 if possible, else hex
    data: str = ""
    did_document: str = ""


@dataclass
class MPTIssuanceInfo:
    """A Multi-Purpose Token issuance created by an account."""

    issuance_id: str = ""
    maximum_amount: str = "0"
    asset_scale: int = 0
    transfer_fee: int = 0
    flags: int = 0
    outstanding_amount: str = "0"


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
    asset_a_issuer: str = ""  # full canonical issuer for asset A
    asset_b_issuer: str = ""  # full canonical issuer for asset B


class Transport(ABC):
    """Abstract base for XRPL network operations."""

    @property
    @abstractmethod
    def network_name(self) -> str:
        """Return a short identifier for this transport's network.

        Examples: ``"testnet"``, ``"dry-run"``, ``"mainnet"``.
        Use this to identify the active network without making a live call.
        """

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

    @abstractmethod
    async def submit_nft_mint(
        self,
        wallet_seed: str,
        uri: str,
        taxon: int = 0,
        transfer_fee: int = 0,
        transferable: bool = True,
        mutable: bool = False,
    ) -> SubmitResult:
        """Mint an NFToken (NFTokenMint). Returns SubmitResult with nft_id set on success.

        ``transfer_fee`` (0..50000, in 0.001% steps) is a protocol-enforced
        royalty the issuer earns on every resale; it requires ``transferable``.
        ``mutable`` sets the tfMutable flag (XLS-46), allowing the URI to be
        changed later via NFTokenModify — the basis for evolving/leveling game
        items.
        """

    @abstractmethod
    async def submit_nft_burn(
        self,
        wallet_seed: str,
        nftoken_id: str,
    ) -> SubmitResult:
        """Burn (permanently destroy) an NFToken, freeing reserve (NFTokenBurn)."""

    @abstractmethod
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
        """Create an NFTokenCreateOffer (sell or buy) for an NFToken.

        ``sell=True`` lists the caller's own NFT for sale (tfSellNFToken set);
        ``sell=False`` is a buy offer for someone else's NFT and requires
        ``owner`` (the current holder). ``amount`` is the price in XRP (or in
        the issued ``currency``/``issuer`` when ``currency != "XRP"``).
        Returns SubmitResult with ``nft_offer_index`` set on success.
        """

    @abstractmethod
    async def submit_nft_accept_offer(
        self,
        wallet_seed: str,
        sell_offer: str = "",
        buy_offer: str = "",
    ) -> SubmitResult:
        """Accept an existing NFTokenOffer, settling the trade (NFTokenAcceptOffer).

        Pass exactly one of ``sell_offer`` (the buyer accepts a seller's sell
        offer) or ``buy_offer`` (the owner accepts a buyer's offer). The royalty
        (TransferFee) is split off to the issuer atomically by the protocol.
        """

    @abstractmethod
    async def submit_nft_modify(
        self,
        wallet_seed: str,
        nftoken_id: str,
        uri: str,
        owner: str = "",
    ) -> SubmitResult:
        """Change a mutable NFToken's URI (NFTokenModify, XLS-46).

        Only works if the NFT was minted with tfMutable; otherwise the ledger
        returns a tec error. The NFTokenID is unchanged — same asset, new state
        (e.g. a leveled-up game item). ``owner`` defaults to the caller.
        """

    @abstractmethod
    async def get_nft_offers(
        self,
        nftoken_id: str,
        sell: bool = True,
    ) -> list[NFTOfferInfo]:
        """List open sell (or buy) offers for an NFToken (nft_sell_offers / nft_buy_offers)."""

    @abstractmethod
    async def get_account_nfts(self, address: str) -> list[NFTInfo]:
        """List NFTokens owned by an address (account_nfts)."""

    @abstractmethod
    async def submit_account_set_clawback(
        self,
        wallet_seed: str,
        issuer_address: str = "",
    ) -> SubmitResult:
        """Enable clawback on the issuer account (AccountSet asfAllowTrustLineClawback).

        MUST be set BEFORE the account issues any tokens — XRPL refuses to
        enable clawback on an issuer that already has issued balances
        outstanding. This is the consent/governance lever that makes
        ``submit_clawback`` possible.

        ``issuer_address`` is the issuer's real classic address. The testnet
        transport ignores it (it derives the address from the seed); the
        dry-run transport uses it to key per-issuer flag state, because every
        dry-run seed otherwise collapses to one synthetic address and could not
        distinguish a clawback-enabled issuer from one that never opted in.
        """

    @abstractmethod
    async def submit_clawback(
        self,
        issuer_seed: str,
        holder_address: str,
        currency: str,
        amount: str,
        issuer_address: str = "",
    ) -> SubmitResult:
        """Forcibly recall issued tokens from a holder (Clawback, XLS-39).

        Only succeeds if the issuer previously set asfAllowTrustLineClawback.
        XRPL quirk: the ``Amount`` field's ``issuer`` sub-field carries the
        HOLDER address (not the issuer) — the token being clawed is identified
        by currency + the clawing account, and the holder rides in Amount.issuer.
        Both transports encode this the same way.

        ``issuer_address`` (the issuer's real classic address) is used by the
        dry-run transport to resolve the holder's trust line and the per-issuer
        flag; the testnet transport ignores it and derives identity from the
        seed.
        """

    @abstractmethod
    async def submit_escrow_create(
        self,
        wallet_seed: str,
        amount: str,
        destination: str,
        finish_after: int,
        cancel_after: int | None = None,
    ) -> SubmitResult:
        """Create a time-based XRP Escrow (EscrowCreate)."""

    @abstractmethod
    async def submit_escrow_finish(
        self,
        wallet_seed: str,
        owner: str,
        offer_sequence: int,
        condition: str = "",
        fulfillment: str = "",
    ) -> SubmitResult:
        """Finish a time-based Escrow past its FinishAfter (EscrowFinish).

        ``owner`` is the EscrowCreate's account; ``offer_sequence`` is the
        EscrowCreate transaction's sequence (``EscrowInfo.sequence``). For a
        pure time-based escrow leave ``condition`` / ``fulfillment`` empty.
        """

    @abstractmethod
    async def submit_escrow_cancel(
        self,
        wallet_seed: str,
        owner: str,
        offer_sequence: int,
    ) -> SubmitResult:
        """Cancel an Escrow past its CancelAfter, reclaiming funds (EscrowCancel).

        ``owner`` is the EscrowCreate's account; ``offer_sequence`` is the
        EscrowCreate transaction's sequence (``EscrowInfo.sequence``).
        """

    @abstractmethod
    async def get_escrows(self, address: str) -> list[EscrowInfo]:
        """List Escrow objects owned by an address."""

    @abstractmethod
    async def submit_did_set(
        self,
        wallet_seed: str,
        uri: str = "",
        data: str = "",
    ) -> SubmitResult:
        """Set (create or update) the account's DID (DIDSet)."""

    @abstractmethod
    async def submit_did_delete(self, wallet_seed: str) -> SubmitResult:
        """Delete the account's DID, freeing its owner reserve (DIDDelete)."""

    @abstractmethod
    async def get_did(self, address: str) -> DIDInfo | None:
        """Get the account's DID object, or None."""

    @abstractmethod
    async def submit_mpt_issuance_create(
        self,
        wallet_seed: str,
        maximum_amount: str,
        asset_scale: int = 0,
        transfer_fee: int = 0,
        can_transfer: bool = True,
    ) -> SubmitResult:
        """Create a Multi-Purpose Token issuance (MPTokenIssuanceCreate)."""

    @abstractmethod
    async def get_mpt_issuances(self, address: str) -> list[MPTIssuanceInfo]:
        """List MPT issuances created by an address."""
