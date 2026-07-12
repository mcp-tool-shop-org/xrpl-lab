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
    mpt_issuance_id: str = ""  # MPTokenIssuanceID, set on a successful MPTokenIssuanceCreate
    channel_id: str = ""  # PayChannel id, set on a successful PaymentChannelCreate
    domain_id: str = ""  # DomainID (Hash256), set on a successful PermissionedDomainSet (create)
    check_id: str = ""  # Check ledger-object id (Hash256 hex), set on a successful CheckCreate
    offer_sequence: int | None = None  # placing tx Sequence, set on a permissioned OfferCreate
    # The submitted transaction's Sequence (the value OfferCancel /
    # EscrowFinish / EscrowCancel consume). The testnet transport reads it
    # from the validated submit response (API v2: ``tx_json.Sequence``); the
    # dry-run transport sets the synthetic create-sequence on the methods
    # whose sequence is consumed downstream (offer/escrow creates). ``None``
    # means the transport could not resolve it — callers keep their existing
    # read-back fallbacks.
    sequence: int | None = None


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
    # FC-003 (delivered_amount / partial-payment exploit): the ACTUAL amount
    # delivered, a METADATA field on a VALIDATED transaction — distinct from the
    # ``amount`` field above (the tx's Amount / API-v2 DeliverMax, which is only
    # the requested CAP). When tfPartialPayment is set, delivery is REDUCED and
    # ``delivered_amount`` is what really moved; ``amount`` still shows the full
    # requested cap. Crediting a user from ``amount`` instead of
    # ``delivered_amount`` IS the #1 XRPL integration bug. For XRP this is a
    # drops string; for tokens it is a ``value/currency/issuer`` display string.
    # Legacy pre-2014 partial payments can carry the literal string
    # "unavailable". Empty string means the field was absent (a non-partial tx
    # where delivered == Amount, or a transport that did not populate it).
    delivered_amount: str = ""
    # Custodial crediting (destination tags): ``DestinationTag`` routes a
    # payment to a sub-account/player behind ONE shared receiving address;
    # ``SourceTag`` is the sender-side return/bounce routing hint. Both are
    # OPTIONAL 32-bit unsigned ints with NO on-ledger meaning beyond the
    # asfRequireDest presence gate — the tag→player map lives entirely in the
    # receiving backend, and a tag is a ROUTING HINT, not authentication
    # (anyone can send any tag). ``None`` means the field was absent.
    destination_tag: int | None = None
    source_tag: int | None = None


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
class CredentialInfo:
    """A Credential ledger object (XLS-70) — an issuer's attestation about a subject.

    A credential is owned (reserve-wise) by the issuer while PROVISIONAL and by
    the subject once ACCEPTED. ``accepted`` reflects the ``lsfAccepted`` flag:
    the subject must run CredentialAccept for the credential to become valid.
    ``credential_type`` is the raw hex tag (opaque; issuer + verifier agree on
    the plaintext out-of-band). ``uri`` is decoded UTF-8 if possible, else hex,
    and is IMMUTABLE after create. ``credential_id`` is the Credential ledger
    object's index (a Hash256 hex string) — this is the value a sender attaches
    to a Payment's ``CredentialIDs`` field to satisfy a DepositPreauth
    credential-based gate (deposit_gate_101); empty when unknown/unresolved.
    """

    subject: str
    issuer: str
    credential_type: str  # hex tag as stored on-ledger
    accepted: bool = False
    uri: str = ""
    expiration: int | None = None
    credential_id: str = ""


@dataclass
class PermissionedDomainInfo:
    """A PermissionedDomain ledger object (XLS-80) — a credential-gated domain.

    A domain gates access to a permissioned book: an account may place a
    permissioned offer (or fund a gated treasury) in the domain only if it
    holds a VALID credential the domain lists in ``accepted_credentials``.
    ``domain_id`` is the Hash256 the ledger derives from (Owner, Sequence) at
    create time — distinct per (owner, sequence), NOT idempotent, so it must be
    tracked off-ledger after creation. ``accepted_credentials`` is the full
    accepted set as ``(issuer, credential_type_hex)`` pairs; the list is
    REPLACED wholesale on every PermissionedDomainSet (never patched), so a
    'modify' that forgets to re-list an entry silently revokes it.
    """

    domain_id: str
    owner: str
    accepted_credentials: list[tuple[str, str]]  # [(issuer, credential_type_hex), ...]


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
class ChannelInfo:
    """A Payment Channel owned by an account (XRP-only on mainnet).

    ``amount`` is the total XRP (drops) deposited into the channel;
    ``balance`` is the cumulative amount (drops) already claimed by the
    destination. The claimable-but-unclaimed amount is ``amount - balance``.
    """

    channel_id: str
    amount: str = "0"  # total deposited, drops
    balance: str = "0"  # cumulative claimed, drops
    destination: str = ""
    settle_delay: int = 0
    public_key: str = ""
    expiration: int | None = None
    cancel_after: int | None = None


@dataclass
class SignerListInfo:
    """The SignerList ledger object attached to an account (SignerListSet).

    ``signer_quorum`` is the minimum COMBINED weight of signatures required to
    authorize a multi-signed transaction for the account. ``entries`` is the
    signer roster as ``(account, weight)`` pairs — 1..32 entries, no duplicate
    accounts, and the owning account can never appear in its own list. There
    is currently exactly one signer list per account (``SignerListID`` 0), and
    it costs one owner-reserve increment (~0.2 XRP) while it exists.
    """

    signer_quorum: int
    entries: list[tuple[str, int]]  # [(signer account, SignerWeight), ...]


@dataclass
class FreezeStatus:
    """Whether an issuer has frozen a holder's trust line and/or globally.

    ``individual_frozen`` is the per-trust-line freeze the issuer set on the
    (currency, holder) line via TrustSet tfSetFreeze. ``global_frozen`` is the
    account-wide asfGlobalFreeze on the issuer (halts ALL its tokens).
    ``found`` is False when the holder has no trust line for the currency
    (so the individual-freeze read is undefined, not "unfrozen").
    """

    individual_frozen: bool = False
    global_frozen: bool = False
    found: bool = False


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
        destination_tag: int | None = None,
        source_tag: int | None = None,
        credential_ids: list[str] | None = None,
        wallet_address: str = "",
    ) -> SubmitResult:
        """Submit a payment transaction.

        ``destination_tag`` / ``source_tag`` are the optional 32-bit unsigned
        routing tags (custodial crediting): the destination tag tells the
        RECEIVING backend which player/sub-account to credit when many users
        share one pooled address; the source tag is the sender's own
        return/bounce routing hint. Both transports enforce the network's
        RequireDest rule identically: an UNTAGGED payment to an account with
        ``asfRequireDest`` set fails ``tecDST_TAG_NEEDED``. Out-of-range tags
        (outside 0..2^32-1) are a local error — xrpl-py's model rejects them
        at construction, and the dry-run mirrors that so a dry-run pass never
        masks a testnet failure.

        ``credential_ids`` (deposit_gate_101, XLS-70 extension) is an optional
        list of 1-8 Credential ledger-object ids the SENDER attaches to satisfy
        a destination's DepositAuth/DepositPreauth gate by credential (see
        :meth:`submit_deposit_preauth`). Both transports enforce the same
        DepositAuth rule: a Payment to a destination with ``asfDepositAuth``
        set fails ``tecNO_PERMISSION`` unless the sender is preauthorized —
        either its address was directly authorized, or it attaches a currently
        valid (accepted, unexpired) credential matching one the destination
        authorized via ``AuthorizeCredentials``. An empty or >8-entry or
        duplicate-containing list is a local error, mirroring xrpl-py's own
        ``credential_ids`` validation so a dry-run pass never masks a testnet
        failure. As an emergency exemption (so a DepositAuth account can never
        get permanently stuck), a destination whose OWN balance is at or below
        the base reserve may still receive an XRP Payment of at most the base
        reserve from ANYONE, preauthorized or not.

        ``wallet_address`` is the SENDER's real classic address — a dry-run
        keying aid (every dry-run seed collapses to one synthetic address, so
        distinguishing multiple senders in the SAME dry-run session against a
        shared DepositAuth/DepositPreauth policy needs this, exactly like
        every other multi-party action). The testnet transport derives the
        sender from the seed and ignores it.
        """

    @abstractmethod
    async def submit_deposit_auth(
        self,
        wallet_seed: str,
        enable: bool = True,
        wallet_address: str = "",
    ) -> SubmitResult:
        """Enable (or clear) asfDepositAuth on the account (AccountSet, SetFlag 9).

        ``asfDepositAuth`` (ledger flag ``lsfDepositAuth``) makes the account
        REJECT any unsolicited incoming Payment from a sender that is not
        preauthorized, failing ``tecNO_PERMISSION``. It blocks Payments ONLY —
        pull-style transactions the recipient itself initiates (CheckCash,
        EscrowFinish, PaymentChannelClaim, OfferCreate) still work, and so does
        the sub-reserve exemption documented on :meth:`submit_payment`.
        ``enable=False`` clears the flag (the named compensator, symmetric with
        :meth:`submit_require_dest`). ``wallet_address`` is the account's real
        classic address, used by the dry-run transport to key per-account flag
        state (every dry-run seed collapses to one synthetic address); the
        testnet transport derives the account from the seed and ignores it.
        """

    @abstractmethod
    async def submit_deposit_preauth(
        self,
        wallet_seed: str,
        authorize: str = "",
        unauthorize: str = "",
        authorize_credentials: list[tuple[str, str]] | None = None,
        unauthorize_credentials: list[tuple[str, str]] | None = None,
        wallet_address: str = "",
    ) -> SubmitResult:
        """Preauthorize (or revoke) a sender for DepositAuth (DepositPreauth, XLS-70 extension).

        Exactly ONE of ``authorize`` / ``unauthorize`` / ``authorize_credentials``
        / ``unauthorize_credentials`` must be set — xrpl-py's model raises at
        construction otherwise (surfaced as ``local_error``, mirrored by the
        dry-run transport for parity).

        ``authorize`` / ``unauthorize`` whitelist (or revoke) a SINGLE sender
        ADDRESS: ``temCANNOT_PREAUTH_SELF`` if it names the account's own
        address, ``tecDUPLICATE`` authorizing an address already authorized,
        ``tecNO_ENTRY`` revoking one that was never authorized (or already
        revoked). Each preauthorized address is its own ledger object (one
        owner-reserve increment).

        ``authorize_credentials`` / ``unauthorize_credentials`` are 1-8
        ``(issuer, credential_type_hex)`` pairs describing which CREDENTIAL(S)
        a sender may hold instead of being individually whitelisted — a
        depositor satisfies the gate by holding just ONE currently valid
        (accepted, unexpired) credential matching ANY ONE listed pair (OR
        semantics, exactly like Permissioned Domains' ``AcceptedCredentials``).
        The sender then attaches the credential's on-ledger id via
        ``Payment.credential_ids`` (see :meth:`submit_payment`). Preauth-by-
        credential is currency-agnostic, one-directional, and cannot
        preauthorize the account itself.

        ``wallet_address`` is a dry-run keying aid (every dry-run seed
        collapses to one synthetic address); the testnet transport derives the
        account from the seed and ignores it.
        """

    @abstractmethod
    async def submit_require_dest(
        self,
        wallet_seed: str,
        enable: bool = True,
        wallet_address: str = "",
    ) -> SubmitResult:
        """Enable (or clear) asfRequireDest on the account (AccountSet).

        ``asfRequireDest`` (ledger flag ``lsfRequireDestTag``) makes the
        account REJECT any incoming Payment that lacks a ``DestinationTag``
        with ``tecDST_TAG_NEEDED``. This is the operational-hygiene switch for
        a custodial/pooled treasury: without it an untagged deposit lands
        unattributable — funds arrive but the backend cannot tell whose they
        are. ALWAYS enable it on a shared hot wallet. ``enable=False`` clears
        the flag (the named compensator). ``wallet_address`` is the account's
        real classic address, used by the dry-run transport to key per-account
        flag state (every dry-run seed collapses to one synthetic address);
        the testnet transport derives the account from the seed and ignores it.
        """

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
        """Submit an issued-currency Payment with the tfPartialPayment flag.

        FC-003 — the partial-payment exploit. ``tfPartialPayment`` (0x00020000)
        tells the ledger to REDUCE delivery instead of failing the whole tx: the
        constraint is ``DeliverMin <= delivered <= amount`` (Amount is the cap /
        DeliverMax) and total source spent ``<= SendMax``. The tx can then return
        ``tesSUCCESS`` while delivering FAR LESS than ``amount`` claims — a naive
        backend that credits ``amount`` loses money.

        XRP-to-XRP partial payments are FORBIDDEN (``temBAD_SEND_XRP_PARTIAL``),
        so this method is issued-currency only. Both transports set the flag and
        surface the reduced ``delivered_amount`` on the resulting validated tx.
        """

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
    async def submit_allow_trustline_locking(
        self,
        issuer_seed: str,
        issuer_address: str = "",
    ) -> SubmitResult:
        """Enable asfAllowTrustLineLocking on the issuer (AccountSet — XLS-85).

        This is the per-asset opt-in that makes an issuer's IOU escrowable. It
        MUST be set on the ISSUER account before any holder can create a token
        escrow of that currency; a token EscrowCreate against an issuer that
        never set it fails ``tecNO_PERMISSION``.

        ``issuer_address`` is the issuer's real classic address. The testnet
        transport ignores it (it derives the address from the seed); the dry-run
        transport uses it to key per-issuer flag state, because every dry-run
        seed collapses to one synthetic address and could not otherwise tell an
        opted-in issuer apart from one that never opted in.
        """

    @abstractmethod
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
        """Create a token (IOU) escrow — EscrowCreate with an issued Amount (XLS-85).

        Locks ``value`` of ``currency``/``issuer`` from the source account to
        ``destination``. The network enforces three preconditions this method
        surfaces as tec/tem-shaped results: the token issuer must have opted in
        (``asfAllowTrustLineLocking``, else ``tecNO_PERMISSION``); the token's
        issuer cannot be the escrow source (else ``tecNO_PERMISSION``); and a
        ``CancelAfter`` is mandatory. ``source_address`` is the source's real
        classic address, used by the dry-run transport to resolve the source's
        trust line and check the issuer-as-source rule (the testnet path derives
        the source from the seed and ignores it).
        """

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
    async def submit_check_create(
        self,
        wallet_seed: str,
        destination: str,
        send_max: str,
        expiration: int | None = None,
        destination_tag: int | None = None,
        invoice_id: str = "",
        wallet_address: str = "",
    ) -> SubmitResult:
        """Write a Check authorizing *destination* to pull up to *send_max* (CheckCreate).

        The deferred-pull contrast to Escrow: this writes a Check ledger object
        naming the Destination and a ``SendMax`` ceiling, but moves and locks
        NOTHING — the writer's spendable balance is unchanged the instant this
        validates (unlike ``submit_escrow_create``, which debits the locked
        amount immediately). ``send_max`` is an XRP amount string; it caps what
        this Check can ever deliver, not a guarantee that amount will still be
        there when the destination gets around to cashing it. ``expiration``
        (optional, ripple-epoch seconds) makes the Check un-cashable (but still
        cancellable by anyone) once passed. Returns ``SubmitResult.check_id``
        (the 64-hex Check object id) on success — the value ``submit_check_cash``
        / ``submit_check_cancel`` need. ``wallet_address`` is a dry-run keying
        aid (every dry-run seed collapses to one synthetic address); the
        testnet transport derives the writer from the seed and ignores it.
        """

    @abstractmethod
    async def submit_check_cash(
        self,
        wallet_seed: str,
        check_id: str,
        amount: str | None = None,
        deliver_min: str | None = None,
        wallet_address: str = "",
    ) -> SubmitResult:
        """Redeem a Check for an exact ``amount`` or a flexible ``deliver_min`` (CheckCash).

        Exactly one of ``amount`` / ``deliver_min`` must be set — xrpl-py's
        model raises "either amount or deliver_min... not both" at
        construction if both or neither are given (surfaced as
        ``local_error``); the dry-run transport mirrors the same rejection so
        a dry-run pass never masks a testnet failure.

        Only the Check's Destination may cash it — any other signer fails
        ``tecNO_PERMISSION``. A Check past its ``Expiration`` can only be
        cancelled, never cashed (``tecEXPIRED``). A wrong/already-consumed
        ``check_id`` fails ``tecNO_ENTRY``. And because ``CheckCreate`` never
        locked anything, the writer's CURRENT balance is checked only now, at
        cash time — insufficient funds fails ``tecUNFUNDED`` (or
        ``tecPATH_PARTIAL`` on the token-check path); a CheckCreate that
        returned ``tesSUCCESS`` is never a guaranteed payout. xrpl.org names
        CheckCash explicitly as a transaction type whose own amount field is
        not authoritative — callers MUST credit from the resulting validated
        tx's ``delivered_amount`` metadata, never from ``amount`` /
        ``deliver_min`` / the Check's ``SendMax`` (the delivered_amount_101
        discipline, reused here unchanged). ``wallet_address`` is a dry-run
        keying aid; the testnet transport derives the casher from the seed and
        ignores it.
        """

    @abstractmethod
    async def submit_check_cancel(
        self,
        wallet_seed: str,
        check_id: str,
        wallet_address: str = "",
    ) -> SubmitResult:
        """Void an unredeemed Check, freeing the WRITER's reserve (CheckCancel).

        While the Check is live, either the writer or the Destination may
        cancel it (any other signer fails ``tecNO_PERMISSION``); once it has
        expired, ANY address may clean it up. A wrong/already-consumed
        ``check_id`` fails ``tecNO_ENTRY``. Unlike ``submit_escrow_cancel``
        (which refunds the locked amount to the owner), this credits NOBODY —
        ``CheckCreate`` never moved or locked anything, so there is nothing to
        refund; only the Check object's owner-reserve slot is freed, to the
        WRITER (the reserve is always charged to whoever wrote the Check,
        never the destination). ``wallet_address`` is a dry-run keying aid;
        the testnet transport derives the canceller from the seed and ignores
        it.
        """

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
    async def submit_credential_create(
        self,
        issuer_seed: str,
        subject: str,
        credential_type: str,
        uri: str = "",
        expiration: int | None = None,
        issuer_address: str = "",
    ) -> SubmitResult:
        """Issuer attests a credential about *subject* (CredentialCreate, XLS-70).

        Mints a PROVISIONAL credential the subject must later accept. ``subject``
        is the account being attested and MUST be funded (else ``tecNO_TARGET``).
        ``credential_type`` is a hex tag (1-64 bytes). ``uri`` (optional, 1-256
        bytes, hex-encoded here) points at an off-chain verifiable credential and
        is IMMUTABLE once set. A duplicate (subject, issuer, type) fails
        ``tecDUPLICATE``. ``issuer_address`` is a dry-run keying aid — the testnet
        transport derives the issuer from the seed and ignores it.
        """

    @abstractmethod
    async def submit_credential_accept(
        self,
        subject_seed: str,
        issuer: str,
        credential_type: str,
        subject_address: str = "",
    ) -> SubmitResult:
        """Subject accepts a provisional credential (CredentialAccept, XLS-70).

        ONLY the subject account can accept. Acceptance clears the provisional
        state (sets ``lsfAccepted``) and transfers the owner reserve from the
        issuer to the subject. ``subject_address`` is a dry-run keying aid;
        the testnet transport derives the subject from the seed and ignores it.
        """

    @abstractmethod
    async def submit_credential_delete(
        self,
        wallet_seed: str,
        issuer: str,
        subject: str,
        credential_type: str,
        wallet_address: str = "",
    ) -> SubmitResult:
        """Delete a credential, reclaiming its reserve (CredentialDelete, XLS-70).

        Either the issuer or the subject may delete it (revocation). ``wallet_seed``
        signs; ``issuer`` / ``subject`` / ``credential_type`` identify the object.
        ``wallet_address`` is a dry-run keying aid, ignored by the testnet path.
        """

    @abstractmethod
    async def get_credential(
        self,
        subject: str,
        issuer: str,
        credential_type: str,
    ) -> CredentialInfo | None:
        """Read the (subject, issuer, credential_type) Credential object, or None.

        ``credential_type`` is the hex tag. Returns the object whether provisional
        or accepted; the caller inspects ``CredentialInfo.accepted`` for validity.
        """

    @abstractmethod
    async def submit_permissioned_domain_set(
        self,
        owner_seed: str,
        accepted_credentials: list[tuple[str, str]],
        domain_id: str = "",
        owner_address: str = "",
    ) -> SubmitResult:
        """Create or modify a Permissioned Domain (PermissionedDomainSet, XLS-80).

        ``accepted_credentials`` is the FULL intended accepted set — a list of
        1-10 ``(issuer, credential_type_hex)`` pairs, no duplicates. It COMPLETELY
        REPLACES the domain's prior list (partial updates are not supported), so a
        modify that drops an entry silently revokes access for everyone holding
        that credential. Omit ``domain_id`` to CREATE a new domain (the ledger
        derives a fresh Hash256 from Owner + Sequence; the created id is returned
        on ``SubmitResult.domain_id``); pass ``domain_id`` to MODIFY that existing
        domain (owner-only — a non-owner modify fails an ownership error). No
        transaction-specific flags. ``owner_address`` is a dry-run keying aid; the
        testnet transport derives the owner from the seed and ignores it.
        """

    @abstractmethod
    async def submit_permissioned_domain_delete(
        self,
        owner_seed: str,
        domain_id: str,
        owner_address: str = "",
    ) -> SubmitResult:
        """Delete a Permissioned Domain (PermissionedDomainDelete, XLS-80).

        The named compensator for ``submit_permissioned_domain_set`` (create):
        it frees the owner-reserve slot the domain consumed. A domain blocks its
        owner's account deletion until it is deleted. Only the owner may delete.
        ``owner_address`` is a dry-run keying aid, ignored by the testnet path.
        """

    @abstractmethod
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
        """Place a permissioned DEX offer scoped to a domain (OfferCreate + DomainID, XLS-81).

        Setting ``domain_id`` scopes the offer to a permissioned domain: the
        placing account MUST hold a valid credential the domain accepts, or the
        offer fails. A plain permissioned offer (``hybrid=False``) matches ONLY the
        domain's permissioned book; a hybrid offer (``hybrid=True`` → the
        ``tfHybrid`` flag) matches BOTH the domain book AND the open DEX.

        NOTE the rail distinction this method makes concrete: eligibility is proven
        by ``DomainID`` (holding an accepted credential), NOT by ``CredentialIDs``
        (the deposit-authorization rail) — putting CredentialIDs on an OfferCreate
        does nothing for permissioned trading. ``wallet_address`` is a dry-run
        keying aid, ignored by the testnet path. On success the placing tx's
        Sequence is returned on ``SubmitResult.offer_sequence``.
        """

    @abstractmethod
    async def get_permissioned_domains(
        self, owner: str
    ) -> list[PermissionedDomainInfo]:
        """List Permissioned Domains owned by an account (account_objects PermissionedDomain)."""

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

    @abstractmethod
    async def submit_mpt_authorize(
        self,
        holder_seed: str,
        issuance_id: str,
        unauthorize: bool = False,
    ) -> SubmitResult:
        """Holder opts in to hold an MPT issuance (MPTokenAuthorize, XLS-33).

        The MPT analog of a trust line: a holder must authorize an issuance
        before it can receive that token. ``unauthorize=True`` opts back out
        (tfMPTUnauthorize), allowed only at a zero balance.
        """

    @abstractmethod
    async def submit_mpt_payment(
        self,
        issuer_seed: str,
        destination: str,
        issuance_id: str,
        amount: str,
    ) -> SubmitResult:
        """Pay an amount of an MPT to a holder (Payment with an MPT Amount).

        Distributes the issued game currency to a player. The holder must have
        authorized the issuance first (else tecNO_AUTH).
        """

    @abstractmethod
    async def get_mpt_balance(self, holder: str, issuance_id: str) -> str:
        """Read a holder's balance of an MPT issuance ("0" if none / unauthorized)."""

    @abstractmethod
    async def submit_set_freeze(
        self,
        issuer_seed: str,
        holder: str,
        currency: str,
        freeze: bool,
        issuer_address: str = "",
    ) -> SubmitResult:
        """Freeze (or unfreeze) an individual holder's trust line for a currency.

        The ISSUER submits a TrustSet on the (currency, holder) line with
        ``tfSetFreeze`` (or ``tfClearFreeze``) — Individual Freeze, the
        per-holder sanction lever below clawback. ``issuer_address`` (the
        issuer's real classic address) is used by the dry-run transport to key
        per-issuer line state; the testnet transport derives it from the seed.
        """

    @abstractmethod
    async def submit_global_freeze(
        self,
        issuer_seed: str,
        enable: bool,
        issuer_address: str = "",
    ) -> SubmitResult:
        """Enable (or clear) Global Freeze on the issuer (AccountSet asfGlobalFreeze).

        Global Freeze halts ALL transfers of every token the account issues —
        the economy-wide circuit breaker. ``issuer_address`` keys the dry-run
        transport's per-issuer flag state.
        """

    @abstractmethod
    async def get_freeze_status(
        self,
        issuer_address: str,
        holder: str,
        currency: str,
    ) -> FreezeStatus:
        """Read whether the issuer froze the holder's (currency) trust line, and
        whether the issuer has Global Freeze set on its account."""

    @abstractmethod
    async def submit_payment_channel_create(
        self,
        wallet_seed: str,
        amount_xrp: str,
        destination: str,
        settle_delay: int,
        public_key: str,
        cancel_after: int | None = None,
    ) -> SubmitResult:
        """Open an XRP payment channel (PaymentChannelCreate). Returns SubmitResult
        with ``channel_id`` set on success. ``public_key`` is the channel's signing
        key (the sender's wallet public key) used to verify off-ledger claims."""

    @abstractmethod
    async def submit_payment_channel_fund(
        self,
        wallet_seed: str,
        channel_id: str,
        amount_xrp: str,
        expiration: int | None = None,
    ) -> SubmitResult:
        """Add XRP to an existing channel (PaymentChannelFund)."""

    @abstractmethod
    async def submit_payment_channel_claim(
        self,
        wallet_seed: str,
        channel_id: str,
        balance_xrp: str = "",
        amount_xrp: str = "",
        signature: str = "",
        public_key: str = "",
        close: bool = False,
    ) -> SubmitResult:
        """Settle and/or close a channel (PaymentChannelClaim).

        The destination redeems a signed off-ledger claim by submitting the
        cumulative ``balance``; the source can also ``close`` the channel.
        """

    @abstractmethod
    async def get_account_channels(
        self, address: str, destination: str = ""
    ) -> list[ChannelInfo]:
        """List payment channels the account is the SOURCE of (account_channels)."""

    @abstractmethod
    async def authorize_payment_channel_claim(
        self, wallet_seed: str, channel_id: str, amount_xrp: str
    ) -> str:
        """Sign an OFF-LEDGER channel claim for a cumulative amount; returns the
        signature hex. No network — this is the 'sign many, settle once' core of
        a payment channel. Signs over the drops amount per the protocol."""

    @abstractmethod
    async def verify_payment_channel_claim(
        self, channel_id: str, amount_xrp: str, public_key: str, signature: str
    ) -> bool:
        """Verify an off-ledger channel claim signature against the channel's
        public key. No network."""

    @abstractmethod
    async def submit_signer_list_set(
        self,
        owner_seed: str,
        quorum: int,
        entries: list[tuple[str, int]],
        owner_address: str = "",
    ) -> SubmitResult:
        """Create, replace, or delete the account's signer list (SignerListSet).

        ``entries`` is the full intended roster as ``(account, weight)`` pairs —
        the ledger REPLACES the whole list on every SignerListSet, never patches
        it. ``quorum`` is the minimum combined weight that authorizes a
        multi-signed transaction. Passing ``quorum=0`` with an EMPTY ``entries``
        DELETES the list (freeing its owner reserve); mixing the two — a zero
        quorum WITH entries, or a non-zero quorum WITHOUT entries — is
        ``temMALFORMED``. Other network preflight rules both transports must
        reject identically: 1..32 entries, no duplicate signer accounts, the
        owner cannot list itself (``temBAD_SIGNER``), every weight must be
        positive (``temBAD_WEIGHT``), and the quorum cannot exceed the sum of
        the weights (``temBAD_QUORUM``). ``owner_address`` is a dry-run keying
        aid (every dry-run seed collapses to one synthetic address); the
        testnet transport derives the owner from the seed and ignores it.
        """

    @abstractmethod
    async def submit_multisig_payment(
        self,
        owner_address: str,
        destination: str,
        amount: str,
        signer_seeds: list[str],
        signer_addresses: list[str] | None = None,
        memo: str = "",
    ) -> SubmitResult:
        """Submit a MULTI-SIGNED XRP Payment from ``owner_address``.

        Deliberately takes NO owner seed — that is the whole point of a signer
        list: the treasury account's own key never signs. Each seed in
        ``signer_seeds`` produces one entry in the transaction's ``Signers``
        array (``{Account, SigningPubKey, TxnSignature}``); the transaction's
        own top-level ``SigningPubKey`` stays EMPTY (""), which is how the
        ledger knows to check the signer list instead of the master key.

        Cost rule both transports model: the fee is base_fee × (1 + number of
        signatures) — every co-signature is paid for. Failure parity the
        dry-run must keep with the network: no signer list on the account →
        ``tefNOT_MULTI_SIGNING``; a signer not on the list (or duplicated) →
        ``tefBAD_SIGNATURE``; combined weight below the quorum →
        ``tefBAD_QUORUM``. ``signer_addresses`` is the dry-run keying aid for
        the signers (parallel to ``signer_seeds``); the testnet transport
        derives each address from its seed and ignores it.
        """

    @abstractmethod
    async def get_signer_list(self, address: str) -> SignerListInfo | None:
        """Read the account's SignerList ledger object, or None if it has none."""
