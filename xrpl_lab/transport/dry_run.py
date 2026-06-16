"""Dry-run transport — no network, deterministic outputs for testing and --dry-run."""

from __future__ import annotations

import hashlib
import time
from decimal import ROUND_HALF_UP, Decimal, getcontext

from .base import (
    AccountSnapshot,
    AmmInfo,
    DIDInfo,
    EscrowInfo,
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

# F-BRIDGE-B-AMM-ZERO-LP edge case 3: Decimal context precision sanity check.
# AMM math (e.g. sqrt of 1e17 * 1e17 at the XRPL drop-supply ceiling) needs
# at least 18 digits to avoid silent precision loss. The stdlib default is
# 28; this assertion catches a future module-level caller that lowers it
# (e.g. ``getcontext().prec = 6``) before we'd otherwise discover the drift
# through a downstream rounding bug.
assert getcontext().prec >= 18, (
    f"Decimal precision must be >=18 for AMM math; got {getcontext().prec}"
)

# Deterministic fake data for offline use
_FAKE_TXID_PREFIX = "DRYRUN"
# Genesis account — valid XRPL base58 address (no invalid chars like 0 or I)
_FAKE_ADDRESS = "rHb9CJAWyB4rj91VRWn96DkukG4bwdtyTh"

# Canonical offline wallet address for all dry-run seeds.
# Kept as a separate constant from _FAKE_ADDRESS so test fixtures that
# reference this literal string continue to work without modification.
_DRY_RUN_WALLET_ADDRESS = "rDRYRUN1234567890ABCDEFGHIJK"


def _address_from_seed(wallet_seed: str) -> str:
    """Derive a deterministic fake address from a seed (no network needed).

    In dry-run mode all seeds map to the same canonical offline address
    because no real key derivation is possible without a valid XRPL seed.
    """
    return _DRY_RUN_WALLET_ADDRESS


class _PerAddressStore(dict):
    """Dict keyed by address that also supports legacy list-like access.

    Legacy callers (e.g., tests) that call `transport._trust_lines.append(item)`
    will route the item into a ``_LEGACY`` bucket.  ``len()`` returns the total
    item count across all addresses (matching old flat-list semantics).
    """

    _LEGACY_KEY = "__legacy__"

    def append(self, item):  # noqa: ANN001, ANN201
        self.setdefault(self._LEGACY_KEY, []).append(item)

    def __len__(self) -> int:  # type: ignore[override]
        return sum(len(v) for v in dict.values(self))

    def __iter__(self):  # noqa: ANN204
        """Iterate over all items across all addresses (legacy flat-list compat)."""
        for items in dict.values(self):
            yield from items

    def __getitem__(self, key):  # noqa: ANN001, ANN204
        """Support both dict[address] and list-style int indexing."""
        if isinstance(key, int):
            # Legacy flat-list index access
            flat = list(self)
            return flat[key]
        return dict.__getitem__(self, key)


class DryRunTransport(Transport):
    """Offline transport that simulates XRPL responses without network access."""

    def __init__(self, fail_next: bool = False) -> None:
        self._fail_next = fail_next
        self._counter = 0  # per-instance txid counter (CORE-004)
        # Per-address XRP balances in drops (CORE-010)
        self._balances: dict[str, int] = {}
        self._funded_addresses: set[str] = set()
        self._trust_lines: _PerAddressStore = _PerAddressStore()
        self._offers: _PerAddressStore = _PerAddressStore()
        self._offer_seq = 100  # starting sequence for fake offers
        # Per-address owned-object counts (TRANSPORT-A-002). On testnet
        # OwnerCount is strictly per-account; this dict is keyed by the acting
        # wallet's derived address. The legacy ``self._owner_count`` global is
        # preserved as a property aliasing the dry-run wallet's count so direct
        # assignment (``transport._owner_count = N``) and the get_account_info
        # fallback for arbitrary addresses keep working.
        self._owner_counts: dict[str, int] = {}
        self._tx_fixtures: dict[str, TxInfo] = {}  # txid -> TxInfo for audit testing
        # AMM state
        self._amm_pools: dict[str, dict] = {}  # pair_key -> pool state
        self._lp_balances: dict[str, dict[str, str]] = {}  # address -> {lp_key: balance}
        # NFT state — minted NFTokens per owner address
        self._nfts: _PerAddressStore = _PerAddressStore()
        # NFT offer book: offer_index -> dict(nft_id, amount, owner, destination,
        # is_sell, currency, issuer). Mirrors the testnet nft_sell_offers /
        # nft_buy_offers ledger objects so the marketplace module's offer-read,
        # ownership-transfer, and royalty-split stay in parity with testnet.
        self._nft_offers: dict[str, dict] = {}
        self._nft_offer_seq = 0
        # Issuer addresses that have enabled clawback (asfAllowTrustLineClawback).
        # A Clawback against an issuer NOT in this set fails with tecNO_PERMISSION,
        # matching the testnet engine result for clawback-without-the-flag.
        self._clawback_enabled: set[str] = set()
        # Escrow / DID / MPT state
        self._escrows: _PerAddressStore = _PerAddressStore()
        self._mpts: _PerAddressStore = _PerAddressStore()
        self._dids: dict[str, DIDInfo] = {}  # one DID per account
        # Deterministic clock for EscrowFinish/EscrowCancel time-gating.
        # XRPL gates EscrowFinish on FinishAfter and EscrowCancel on
        # CancelAfter, both in ripple-epoch seconds. Wall-clock would make
        # the offline lifecycle test flaky (a short-FinishAfter escrow might
        # or might not be finishable depending on how fast the test runs), so
        # the dry-run transport reads time from this settable clock instead.
        # Default: a far-future ripple time so a freshly-created escrow is
        # immediately finishable AND cancellable, keeping the happy-path
        # offline test deterministic regardless of wall-clock. Tests set it
        # (via set_dry_clock) to a moment BEFORE FinishAfter/CancelAfter to
        # exercise the not-yet-finishable / not-yet-cancellable error paths.
        self._dry_clock: int = 4_000_000_000  # ~ripple-epoch year 2126

    def _next_txid(self) -> str:
        """Generate a unique deterministic transaction ID (per-instance counter)."""
        self._counter += 1
        raw = f"{_FAKE_TXID_PREFIX}-{self._counter}-{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest().upper()[:64]

    # ── Owner-count bookkeeping (TRANSPORT-A-002) ────────────────────────
    #
    # OwnerCount is per-account on testnet. We track it per derived address in
    # ``self._owner_counts`` and increment/decrement under the acting wallet's
    # address in each object-creating/removing method. ``self._owner_count``
    # stays as a property aliasing the dry-run wallet's count (every dry-run
    # seed collapses to ``_DRY_RUN_WALLET_ADDRESS`` via ``_address_from_seed``),
    # so older code/tests that read or set the global keep working.

    @property
    def _owner_count(self) -> int:
        return self._owner_counts.get(_DRY_RUN_WALLET_ADDRESS, 0)

    @_owner_count.setter
    def _owner_count(self, value: int) -> None:
        self._owner_counts[_DRY_RUN_WALLET_ADDRESS] = value

    def _inc_owner(self, address: str) -> None:
        self._owner_counts[address] = self._owner_counts.get(address, 0) + 1

    def _dec_owner(self, address: str) -> None:
        self._owner_counts[address] = max(0, self._owner_counts.get(address, 0) - 1)

    @property
    def network_name(self) -> str:
        return "dry-run"

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
        self._balances[address] = 1_000_000_000  # 1000 XRP in drops
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

        try:
            numeric_amount = Decimal(amount)
        except Exception:
            return SubmitResult(
                success=False,
                txid="",
                result_code="temBAD_AMOUNT",
                fee="0",
                error=f"[dry-run] Invalid amount: {amount}",
            )

        sender = _address_from_seed(wallet_seed)
        drops = int(numeric_amount * Decimal("1000000"))

        # F-BRIDGE-B-DRY-NEG-BAL: pre-validate sender balance before debiting.
        # Previously the debit ran unconditionally, allowing a funded sender's
        # balance to go negative; ``get_balance()`` then clamped the display
        # to "0" and masked the violation. We now match testnet behavior and
        # return tecUNFUNDED_PAYMENT.
        #
        # Scope guard: only enforce when the sender has a tracked balance
        # (i.e., was funded or previously transacted). Unfunded senders have
        # never been balance-checked in this transport — leaving that path
        # alone preserves existing test fixtures that submit_payment without
        # first calling fund_from_faucet.
        if sender in self._balances:
            current_balance = self._balances[sender]
            if drops > current_balance:
                return SubmitResult(
                    success=False,
                    txid="",
                    result_code="tecUNFUNDED_PAYMENT",
                    fee="12",
                    error=(
                        f"[dry-run] insufficient XRP balance: "
                        f"have {current_balance}, need {drops}"
                    ),
                )

        txid = self._next_txid()
        self._balances[sender] = self._balances.get(sender, 0) - drops
        self._balances[destination] = self._balances.get(destination, 0) + drops
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="",  # dry-run tx is simulated — no public explorer
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

        txid = self._next_txid()
        wallet_address = _address_from_seed(wallet_seed)
        addr_lines = self._trust_lines.setdefault(wallet_address, [])

        # Find existing trust line for this currency + issuer
        existing = None
        for tl in addr_lines:
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
                    explorer_url="",  # dry-run tx is simulated — no public explorer
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
            addr_lines.remove(existing)
            self._dec_owner(wallet_address)
        elif existing:
            # Update existing trust line limit (don't create duplicate)
            existing.limit = limit
        else:
            # Create new trust line using the wallet's derived address (CORE-005)
            addr_lines.append(
                TrustLineInfo(
                    account=wallet_address,
                    peer=issuer,
                    currency=currency,
                    balance="0",
                    limit=limit,
                )
            )
            self._inc_owner(wallet_address)

        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="",  # dry-run tx is simulated — no public explorer
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

        # Realistic validation: the DESTINATION holds the trust line, so credit
        # the destination's own line (TRANSPORT-A-001). Previously this scanned
        # ALL addresses and credited the first currency+issuer match regardless
        # of destination — with 2+ holders of the same currency/issuer the wrong
        # holder was credited. We now resolve the destination's live trust-line
        # objects first (its explicit per-address bucket if present), and only
        # fall back to the legacy/single-wallet collapsed bucket when the
        # destination has no bucket of its own (preserves dry-run parity with
        # testnet, where the destination's line is the one that moves).
        matching_tl = None
        for tl in self._live_lines_for(destination):
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

        try:
            numeric_balance = Decimal(matching_tl.balance)
        except Exception:
            numeric_balance = Decimal("0")
        try:
            numeric_amount = Decimal(amount)
        except Exception:
            return SubmitResult(
                success=False,
                txid="",
                result_code="temBAD_AMOUNT",
                fee="0",
                error=f"[dry-run] Invalid amount: {amount}",
            )

        txid = self._next_txid()
        new_balance = numeric_balance + numeric_amount
        # Preserve integer representation when the result is a whole number
        matching_tl.balance = (
            str(int(new_balance)) if new_balance == int(new_balance) else str(new_balance)
        )
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="",  # dry-run tx is simulated — no public explorer
        )

    def _live_lines_for(self, address: str) -> list[TrustLineInfo]:
        """Return the LIVE trust-line list backing *address* (mutations persist).

        Resolution order mirrors ``_resolve_lines`` but returns the underlying
        list object rather than a copy, so callers that credit a balance
        (e.g. ``submit_issued_payment``) write through to the stored line:

        1. The destination's own explicit per-address bucket (the testnet
           reality — the holder's line is the one that moves).
        2. The legacy flat bucket (tests that ``.append`` directly).
        3. The single-wallet collapse fallback (``_address_from_seed`` maps
           every dry-run seed to one address, so a trust line set via a seed
           and a payment to an arbitrary destination still resolve to it).
        """
        if address in self._trust_lines:
            return self._trust_lines[address]
        legacy = self._trust_lines.get(_PerAddressStore._LEGACY_KEY)
        if legacy:
            return legacy
        real = {k: v for k, v in self._trust_lines.items()
                if k != _PerAddressStore._LEGACY_KEY}
        if len(real) == 1:
            return next(iter(real.values()))
        return []

    def _resolve_lines(self, address: str) -> list[TrustLineInfo]:
        """Return trust lines for *address*, checking legacy bucket too."""
        return list(self._live_lines_for(address))

    async def get_trust_lines(self, address: str) -> list[TrustLineInfo]:
        return self._resolve_lines(address)

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

        txid = self._next_txid()
        seq = self._offer_seq
        self._offer_seq += 1
        wallet_address = _address_from_seed(wallet_seed)

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

        self._offers.setdefault(wallet_address, []).append(
            OfferInfo(
                sequence=seq,
                taker_pays=pays_str,
                taker_gets=gets_str,
            )
        )
        self._inc_owner(wallet_address)
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="",  # dry-run tx is simulated — no public explorer
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

        txid = self._next_txid()
        wallet_address = _address_from_seed(wallet_seed)
        addr_offers = self._offers.get(wallet_address, [])
        # Remove the offer from tracked list and decrement owner count
        before = len(addr_offers)
        addr_offers = [o for o in addr_offers if o.sequence != offer_sequence]
        if len(addr_offers) < before:
            self._dec_owner(wallet_address)
        self._offers[wallet_address] = addr_offers
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="",  # dry-run tx is simulated — no public explorer
        )

    async def get_account_offers(self, address: str) -> list[OfferInfo]:
        if address in self._offers:
            return list(self._offers[address])
        legacy = self._offers.get(_PerAddressStore._LEGACY_KEY, [])
        if legacy:
            return list(legacy)
        # Single-wallet fallback: if only one real address, return those
        real = {k: v for k, v in self._offers.items()
                if k != _PerAddressStore._LEGACY_KEY}
        if len(real) == 1:
            return list(next(iter(real.values())))
        return []

    async def get_account_info(self, address: str) -> AccountSnapshot:
        if address in self._balances:
            balance_drops = str(self._balances[address])
        elif address in self._funded_addresses:
            # Backward compat: address funded via direct _funded_addresses manipulation
            balance_drops = "1000000000"
        else:
            balance_drops = "0"
        # Owner count is per-account (TRANSPORT-A-002). Return this address's
        # tracked count when it has one; otherwise fall back to the dry-run
        # wallet's count via the ``_owner_count`` global alias. The fallback
        # preserves the long-standing dry-run idiom where an object is created
        # under a seed (collapsed to _DRY_RUN_WALLET_ADDRESS) and the count is
        # then queried for an arbitrary display address.
        if address in self._owner_counts:
            owner_count = self._owner_counts[address]
        else:
            owner_count = self._owner_count
        return AccountSnapshot(
            address=address,
            balance_drops=balance_drops,
            owner_count=owner_count,
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
        if address in self._balances:
            drops = self._balances[address]
            if drops <= 0:
                return "0"
            from xrpl.utils import drops_to_xrp as _drops_to_xrp
            return str(_drops_to_xrp(str(drops)))
        # Backward compat: address funded via direct _funded_addresses manipulation
        return "1000.000000" if address in self._funded_addresses else "0"

    # ── AMM methods ──────────────────────────────────────────────────

    @staticmethod
    def _amm_pair_key(
        a_currency: str, a_issuer: str,
        b_currency: str, b_issuer: str,
    ) -> str:
        """Canonical key for an asset pair (sorted so order doesn't matter)."""
        a = f"{a_currency}/{a_issuer}" if a_issuer else a_currency
        b = f"{b_currency}/{b_issuer}" if b_issuer else b_currency
        return "|".join(sorted([a, b]))

    async def get_amm_info(
        self,
        asset_a_currency: str,
        asset_a_issuer: str,
        asset_b_currency: str,
        asset_b_issuer: str,
    ) -> AmmInfo | None:
        key = self._amm_pair_key(
            asset_a_currency, asset_a_issuer,
            asset_b_currency, asset_b_issuer,
        )
        pool = self._amm_pools.get(key)
        if not pool:
            return None
        return AmmInfo(
            asset_a=pool["asset_a"],
            asset_b=pool["asset_b"],
            pool_a=pool["pool_a"],
            pool_b=pool["pool_b"],
            lp_token_currency=pool["lp_currency"],
            lp_token_issuer=pool["lp_issuer"],
            lp_supply=pool["lp_supply"],
            trading_fee=pool["trading_fee"],
            asset_a_issuer=pool.get("a_issuer", ""),
            asset_b_issuer=pool.get("b_issuer", ""),
        )

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
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False,
                result_code="tecAMM_FAILED",
                fee="12",
                error="[dry-run] Simulated failure: AMM creation failed",
            )

        key = self._amm_pair_key(
            asset_a_currency, asset_a_issuer,
            asset_b_currency, asset_b_issuer,
        )
        if key in self._amm_pools:
            return SubmitResult(
                success=False,
                result_code="tecDUPLICATE",
                fee="12",
                error="[dry-run] AMM already exists for this asset pair",
            )

        txid = self._next_txid()
        amm_account = f"rAMM{hashlib.sha256(key.encode()).hexdigest()[:24].upper()}"
        lp_currency = hashlib.sha256(key.encode()).hexdigest()[:3].upper()
        # Guard against LP currency colliding with "XRP" (CORE-015)
        if lp_currency == "XRP":
            lp_currency = "LPX"

        # Label assets for display
        a_label = (
            asset_a_currency if asset_a_currency == "XRP"
            else f"{asset_a_currency}/{asset_a_issuer[:12]}"
        )
        b_label = (
            asset_b_currency if asset_b_currency == "XRP"
            else f"{asset_b_currency}/{asset_b_issuer[:12]}"
        )

        # Initial LP supply = sqrt(a * b)
        _six = Decimal("0.000001")
        raw_lp = (Decimal(asset_a_value) * Decimal(asset_b_value)).sqrt()
        initial_lp = str(raw_lp.quantize(_six, rounding=ROUND_HALF_UP))

        self._amm_pools[key] = {
            "asset_a": a_label,
            "asset_b": b_label,
            "pool_a": asset_a_value,
            "pool_b": asset_b_value,
            "lp_currency": lp_currency,
            "lp_issuer": amm_account,
            "lp_supply": initial_lp,
            "trading_fee": str(trading_fee),
            "a_currency": asset_a_currency,
            "a_issuer": asset_a_issuer,
            "b_currency": asset_b_currency,
            "b_issuer": asset_b_issuer,
        }

        # Creator gets all initial LP tokens
        lp_key = f"{lp_currency}/{amm_account}"
        creator_address = _address_from_seed(wallet_seed)
        self._lp_balances.setdefault(creator_address, {})[lp_key] = initial_lp

        self._inc_owner(creator_address)  # AMM position

        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="",  # dry-run tx is simulated — no public explorer
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
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False,
                result_code="tecAMM_BALANCE",
                fee="12",
                error="[dry-run] Simulated failure: AMM deposit failed",
            )

        key = self._amm_pair_key(
            asset_a_currency, asset_a_issuer,
            asset_b_currency, asset_b_issuer,
        )
        pool = self._amm_pools.get(key)
        if not pool:
            return SubmitResult(
                success=False,
                result_code="tecAMM_NOT_FOUND",
                fee="12",
                error="[dry-run] No AMM found for this asset pair",
            )

        txid = self._next_txid()

        # AMM deposit math:
        #   First-LP (lp_supply == 0): Uniswap V2 sqrt(a*b).
        #   Subsequent: binding-ratio min(da/pa, db/pb), refund non-binding side
        #   (matches XRPL AMM testnet behavior).
        _six = Decimal("0.000001")
        old_a = Decimal(pool["pool_a"])
        old_b = Decimal(pool["pool_b"])
        old_lp = Decimal(pool["lp_supply"])
        deposit_a = Decimal(asset_a_value)
        deposit_b = Decimal(asset_b_value)

        if old_lp == 0:
            # First-liquidity case: Uniswap V2 first-LP formula.
            # The depositor sets the initial price by depositing both sides
            # in full; LP minted = sqrt(deposit_a * deposit_b).
            lp_minted = (deposit_a * deposit_b).sqrt().quantize(
                _six, rounding=ROUND_HALF_UP,
            )
            actual_a_taken = deposit_a
            actual_b_taken = deposit_b
        else:
            # Subsequent-liquidity case: binding ratio + refund.
            # The non-binding side is refunded to the depositor (i.e. not
            # debited from their wallet); the pool only grows by the
            # binding-ratio share on each side.
            ratio_a = deposit_a / old_a if old_a > 0 else Decimal("0")
            ratio_b = deposit_b / old_b if old_b > 0 else Decimal("0")
            binding_ratio = min(ratio_a, ratio_b)
            lp_minted = (old_lp * binding_ratio).quantize(
                _six, rounding=ROUND_HALF_UP,
            )
            actual_a_taken = (old_a * binding_ratio).quantize(
                _six, rounding=ROUND_HALF_UP,
            )
            actual_b_taken = (old_b * binding_ratio).quantize(
                _six, rounding=ROUND_HALF_UP,
            )

        # F-BRIDGE-B-AMM-ZERO-LP edge case 1: deposit too small for 6-decimal
        # LP precision. If the quantized lp_minted is 0 (and there was a real
        # deposit attempt), reject — otherwise balances debit and the
        # depositor receives nothing in exchange. The ``deposit_a > 0 or
        # deposit_b > 0`` guard preserves the genuinely-zero-deposit no-op
        # path (already covered by other validation upstream).
        if lp_minted == Decimal("0") and (deposit_a > 0 or deposit_b > 0):
            return SubmitResult(
                success=False,
                result_code="tecAMM_INVALID_TOKENS",
                fee="12",
                error=(
                    "[dry-run] deposit too small: would mint 0 LP at "
                    "6-decimal precision; deposit a larger amount"
                ),
            )

        # Update pool balances by the actually-taken amounts (refund of the
        # non-binding side stays with the depositor and is never debited).
        pool["pool_a"] = str((old_a + actual_a_taken).quantize(_six, rounding=ROUND_HALF_UP))
        pool["pool_b"] = str((old_b + actual_b_taken).quantize(_six, rounding=ROUND_HALF_UP))
        new_lp = old_lp + lp_minted
        pool["lp_supply"] = str(new_lp.quantize(_six, rounding=ROUND_HALF_UP))

        # Credit LP tokens to depositor
        lp_key = f"{pool['lp_currency']}/{pool['lp_issuer']}"
        depositor_address = _address_from_seed(wallet_seed)
        balances = self._lp_balances.setdefault(depositor_address, {})
        current = Decimal(balances.get(lp_key, "0"))
        balances[lp_key] = str((current + lp_minted).quantize(_six, rounding=ROUND_HALF_UP))

        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="",  # dry-run tx is simulated — no public explorer
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
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False,
                result_code="tecAMM_BALANCE",
                fee="12",
                error="[dry-run] Simulated failure: AMM withdraw failed",
            )

        key = self._amm_pair_key(
            asset_a_currency, asset_a_issuer,
            asset_b_currency, asset_b_issuer,
        )
        pool = self._amm_pools.get(key)
        if not pool:
            return SubmitResult(
                success=False,
                result_code="tecAMM_NOT_FOUND",
                fee="12",
                error="[dry-run] No AMM found for this asset pair",
            )

        lp_key = f"{pool['lp_currency']}/{pool['lp_issuer']}"
        withdrawer_address = _address_from_seed(wallet_seed)
        balances = self._lp_balances.get(withdrawer_address, {})
        current_lp = Decimal(balances.get(lp_key, "0"))

        # Determine how much LP to burn
        burn_lp = Decimal(lp_token_value) if lp_token_value else current_lp
        if burn_lp <= 0 or burn_lp > current_lp:
            return SubmitResult(
                success=False,
                result_code="tecAMM_BALANCE",
                fee="12",
                error=(
                    f"[dry-run] Insufficient LP tokens: "
                    f"have {current_lp}, need {burn_lp}"
                ),
            )

        # Calculate proportional withdrawal
        _six = Decimal("0.000001")
        total_lp = Decimal(pool["lp_supply"])

        # F-BRIDGE-B-AMM-ZERO-LP edge case 2: post-withdraw dust state. If the
        # raw remaining lp_supply would be positive but below the 6-decimal
        # floor (0.000001), the pool is unrecoverable — subsequent deposits
        # would div-by-near-zero on binding_ratio, and further withdraws
        # can't extract anything meaningful. Reject and tell the caller to
        # withdraw all remaining LP instead. Check is on the raw (un-quantized)
        # value so we catch deltas that would round down to zero or up to the
        # dust floor.
        raw_lp_after = total_lp - burn_lp
        if raw_lp_after > Decimal("0") and raw_lp_after < Decimal("0.000001"):
            return SubmitResult(
                success=False,
                result_code="tecAMM_BALANCE",
                fee="12",
                error=(
                    "[dry-run] withdraw would leave pool in dust state "
                    "(lp_supply < 0.000001); withdraw all remaining LP instead"
                ),
            )

        txid = self._next_txid()

        ratio = burn_lp / total_lp if total_lp > 0 else Decimal("0")

        keep = Decimal("1") - ratio
        pool["pool_a"] = str(
            (Decimal(pool["pool_a"]) * keep).quantize(_six, rounding=ROUND_HALF_UP),
        )
        pool["pool_b"] = str(
            (Decimal(pool["pool_b"]) * keep).quantize(_six, rounding=ROUND_HALF_UP),
        )
        pool["lp_supply"] = str((total_lp - burn_lp).quantize(_six, rounding=ROUND_HALF_UP))

        # Debit LP tokens from withdrawer
        new_lp = (current_lp - burn_lp).quantize(_six, rounding=ROUND_HALF_UP)
        if new_lp <= 0:
            balances.pop(lp_key, None)
        else:
            balances[lp_key] = str(new_lp)

        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="",  # dry-run tx is simulated — no public explorer
        )

    async def get_lp_token_balance(
        self,
        address: str,
        lp_token_currency: str,
        lp_token_issuer: str,
    ) -> str:
        lp_key = f"{lp_token_currency}/{lp_token_issuer}"
        balances = self._lp_balances.get(address, {})
        return balances.get(lp_key, "0")

    # ── NFT methods ──────────────────────────────────────────────────

    async def submit_nft_mint(
        self,
        wallet_seed: str,
        uri: str,
        taxon: int = 0,
        transfer_fee: int = 0,
        transferable: bool = True,
        mutable: bool = False,
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False,
                result_code="temINVALID_FLAG",
                fee="12",
                error="[dry-run] Simulated failure: invalid NFTokenMint",
            )

        # XRPL parity: a non-zero TransferFee (royalty) requires tfTransferable
        # — the ledger rejects a royalty on a non-transferable NFT with
        # temBAD_NFTOKEN_TRANSFER_FEE.
        if transfer_fee and not transferable:
            return SubmitResult(
                success=False,
                result_code="temBAD_NFTOKEN_TRANSFER_FEE",
                fee="12",
                error=(
                    "[dry-run] TransferFee (royalty) requires the NFT to be "
                    "transferable — set transferable=true."
                ),
            )

        owner = _address_from_seed(wallet_seed)
        txid = self._next_txid()
        nft_id = hashlib.sha256(
            f"{owner}-{uri}-{taxon}-{self._counter}".encode()
        ).hexdigest().upper()[:64]
        # flags: tfTransferable=0x8, tfMutable=0x10 (XLS-46)
        flags = (0x8 if transferable else 0) | (0x10 if mutable else 0)
        owned = self._nfts.setdefault(owner, [])
        owned.append(
            NFTInfo(
                nft_id=nft_id,
                issuer=owner,
                taxon=taxon,
                uri=uri,
                flags=flags,
                transfer_fee=transfer_fee,
                serial=len(owned) + 1,
            )
        )
        self._inc_owner(owner)
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url="",  # dry-run tx is simulated — no public explorer
            nft_id=nft_id,
        )

    async def submit_nft_burn(
        self,
        wallet_seed: str,
        nftoken_id: str,
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False, result_code="tecNO_PERMISSION", fee="12",
                error="[dry-run] Simulated failure: NFTokenBurn",
            )
        owner = _address_from_seed(wallet_seed)
        # Find the NFT in the owner's bucket (with legacy / single-wallet
        # fallbacks, same resolution get_account_nfts uses).
        target_bucket = None
        target = None
        candidates = []
        if owner in self._nfts:
            candidates.append(owner)
        candidates.append(_PerAddressStore._LEGACY_KEY)
        real = {k: v for k, v in self._nfts.items()
                if k != _PerAddressStore._LEGACY_KEY}
        if owner not in self._nfts and len(real) == 1:
            candidates.append(next(iter(real.keys())))
        for key in candidates:
            bucket = self._nfts.get(key, [])
            for n in bucket:
                if n.nft_id == nftoken_id:
                    target_bucket = bucket
                    target = n
                    break
            if target is not None:
                break
        if target is None:
            # No such NFT — mirror testnet's tecNO_ENTRY for a burn of an
            # NFTokenID the account does not own.
            return SubmitResult(
                success=False, result_code="tecNO_ENTRY", fee="12",
                error=("[dry-run] No NFToken found with that NFTokenID — it does "
                       "not exist or you do not own it."),
            )
        target_bucket.remove(target)
        self._dec_owner(owner)
        return SubmitResult(
            success=True, txid=self._next_txid(), result_code="tesSUCCESS", fee="12",
            ledger_index=99999999, explorer_url="",
        )

    async def get_account_nfts(self, address: str) -> list[NFTInfo]:
        if address in self._nfts:
            return list(self._nfts[address])
        legacy = self._nfts.get(_PerAddressStore._LEGACY_KEY, [])
        if legacy:
            return list(legacy)
        real = {k: v for k, v in self._nfts.items()
                if k != _PerAddressStore._LEGACY_KEY}
        if len(real) == 1:
            return list(next(iter(real.values())))
        return []

    def _find_nft_bucket(self, nftoken_id: str) -> tuple[list | None, NFTInfo | None]:
        """Locate (bucket, NFTInfo) holding *nftoken_id* across all owner buckets."""
        for key in list(self._nfts.keys()):
            bucket = dict.__getitem__(self._nfts, key)
            for n in bucket:
                if n.nft_id == nftoken_id:
                    return bucket, n
        return None, None

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
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False, result_code="tecNO_PERMISSION", fee="12",
                error="[dry-run] Simulated failure: NFTokenCreateOffer",
            )

        # A sell offer requires the seller to actually own the NFT.
        if sell:
            _bucket, nft = self._find_nft_bucket(nftoken_id)
            if nft is None:
                return SubmitResult(
                    success=False, result_code="tecNO_ENTRY", fee="12",
                    error=(
                        "[dry-run] Cannot list a sell offer — you do not own "
                        f"NFToken {nftoken_id[:16]}..."
                    ),
                )
            offer_owner = owner or _address_from_seed(wallet_seed)
        else:
            offer_owner = owner or _address_from_seed(wallet_seed)

        self._nft_offer_seq += 1
        # Deterministic offer index (parity stand-in for the ledger object id).
        offer_index = hashlib.sha256(
            f"offer-{nftoken_id}-{self._nft_offer_seq}".encode()
        ).hexdigest().upper()[:64]
        # Display string for the price, matching testnet _format_amount shape.
        amount_disp = (
            amount if currency == "XRP"
            else f"{amount}/{currency}/{issuer[:12]}"
        )
        self._nft_offers[offer_index] = {
            "nft_id": nftoken_id,
            "amount": amount,
            "amount_disp": amount_disp,
            "owner": offer_owner,
            "destination": destination,
            "is_sell": sell,
            "currency": currency,
            "issuer": issuer,
        }
        self._inc_owner(offer_owner)
        return SubmitResult(
            success=True, txid=self._next_txid(), result_code="tesSUCCESS",
            fee="12", ledger_index=99999999, explorer_url="",
            nft_offer_index=offer_index,
        )

    async def get_nft_offers(
        self,
        nftoken_id: str,
        sell: bool = True,
    ) -> list[NFTOfferInfo]:
        out: list[NFTOfferInfo] = []
        for idx, o in self._nft_offers.items():
            if o["nft_id"] != nftoken_id or o["is_sell"] != sell:
                continue
            out.append(NFTOfferInfo(
                offer_index=idx,
                nft_id=o["nft_id"],
                amount=o.get("amount_disp", o["amount"]),
                owner=o["owner"],
                destination=o.get("destination", ""),
                is_sell=o["is_sell"],
            ))
        return out

    async def submit_nft_accept_offer(
        self,
        wallet_seed: str,
        sell_offer: str = "",
        buy_offer: str = "",
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False, result_code="tecNO_PERMISSION", fee="12",
                error="[dry-run] Simulated failure: NFTokenAcceptOffer",
            )

        offer_index = sell_offer or buy_offer
        if not offer_index:
            return SubmitResult(
                success=False, result_code="temMALFORMED", fee="12",
                error="[dry-run] NFTokenAcceptOffer requires a sell_offer or buy_offer index.",
            )
        offer = self._nft_offers.get(offer_index)
        if offer is None:
            # Mirror testnet's engine result for accepting a nonexistent offer.
            return SubmitResult(
                success=False, result_code="tecOBJECT_NOT_FOUND", fee="12",
                error=(
                    "[dry-run] No such NFTokenOffer — it does not exist, or it "
                    "was already accepted/cancelled."
                ),
            )

        nft_id = offer["nft_id"]
        bucket, nft = self._find_nft_bucket(nft_id)
        if nft is None or bucket is None:
            return SubmitResult(
                success=False, result_code="tecNO_ENTRY", fee="12",
                error=f"[dry-run] NFToken {nft_id[:16]}... no longer exists.",
            )

        acceptor = _address_from_seed(wallet_seed)
        seller = offer["owner"] if offer["is_sell"] else None
        # For a sell offer: the acceptor (buyer) receives the NFT from the seller.
        # For a buy offer: the acceptor (owner) sends the NFT to the buyer.
        #
        # Dry-run nuance: every seed collapses to one address via
        # _address_from_seed, so a directed offer's ``destination`` (the
        # intended buyer/seller — a real distinct wallet the marketplace module
        # creates) is the reliable counterparty identity. We prefer it when set,
        # falling back to the collapsed acceptor for untargeted offers. On
        # testnet the real tx signer is the counterparty, so behavior matches.
        directed = offer.get("destination", "")
        if offer["is_sell"]:
            buyer = directed or acceptor
            new_owner = buyer
            price_payer = buyer
        else:
            buyer = offer["owner"]
            new_owner = buyer
            price_payer = buyer
            seller = directed or acceptor

        # ── Royalty (TransferFee) split — Decimal-exact ──────────────────
        # TransferFee is in 0.001% steps (e.g. 5000 = 5.000%). The issuer earns
        # royalty = price * (transfer_fee / 100000); seller nets the remainder.
        #
        # XLS-20 rule (load-bearing): the TransferFee is charged ONLY when the
        # seller is NOT the issuer. The FIRST sale (issuer -> buyer) pays no
        # royalty; the fee is enforced on every SECONDARY sale (resale). The
        # marketplace module is therefore built as a resale so the royalty is
        # observably non-zero.
        price = Decimal(offer["amount"])
        fee_units = Decimal(nft.transfer_fee or 0)
        seller_is_issuer = bool(seller) and seller == nft.issuer
        royalty = (
            Decimal("0") if seller_is_issuer
            else price * fee_units / Decimal("100000")
        )
        # Quantize royalty to drops (6 dp) for XRP, exact otherwise. The
        # seller's net (price - royalty) is computed below in drops at the
        # settlement site so the integer-drop math is the single source of truth.
        if offer.get("currency", "XRP") == "XRP":
            _q = Decimal("0.000001")
            royalty = royalty.quantize(_q, rounding=ROUND_HALF_UP)

        # Move the NFT to the new owner's bucket.
        bucket.remove(nft)
        # Decrement the previous holder's owner-count, increment the new one.
        # The previous holder is the issuer's collapsed bucket key — best effort.
        self._nfts.setdefault(new_owner, []).append(nft)
        self._inc_owner(new_owner)
        # The seller no longer holds it; in the collapsed dry-run model the
        # previous bucket key is the seller, so decrement there.
        if seller:
            self._dec_owner(seller)

        # Settle XRP balances for the parity-observable money movement (only
        # meaningful for XRP-priced offers; issued-currency settlement is left
        # to trust-line balances which the marketplace module doesn't read).
        if offer.get("currency", "XRP") == "XRP":
            payer_drops = int(price * Decimal("1000000"))
            royalty_drops = int(royalty * Decimal("1000000"))
            seller_drops = payer_drops - royalty_drops
            issuer_addr = nft.issuer
            self._balances[price_payer] = self._balances.get(price_payer, 0) - payer_drops
            if seller:
                self._balances[seller] = self._balances.get(seller, 0) + seller_drops
            self._balances[issuer_addr] = self._balances.get(issuer_addr, 0) + royalty_drops

        # Consume the accepted offer (and clean up the offer's owner-count).
        del self._nft_offers[offer_index]
        self._dec_owner(offer["owner"])

        return SubmitResult(
            success=True, txid=self._next_txid(), result_code="tesSUCCESS",
            fee="12", ledger_index=99999999, explorer_url="",
        )

    async def submit_nft_modify(
        self,
        wallet_seed: str,
        nftoken_id: str,
        uri: str,
        owner: str = "",
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False, result_code="tecNO_PERMISSION", fee="12",
                error="[dry-run] Simulated failure: NFTokenModify",
            )

        _bucket, nft = self._find_nft_bucket(nftoken_id)
        if nft is None:
            return SubmitResult(
                success=False, result_code="tecNO_ENTRY", fee="12",
                error=(
                    f"[dry-run] No NFToken {nftoken_id[:16]}... found — it does "
                    "not exist or you do not own it."
                ),
            )
        # tfMutable is flag 0x10 (XLS-46). Modifying a non-mutable NFT fails.
        if not (nft.flags & 0x10):
            return SubmitResult(
                success=False, result_code="tecNO_PERMISSION", fee="12",
                error=(
                    "[dry-run] NFToken is not mutable — it was minted without "
                    "tfMutable, so its URI can never change. Mint with "
                    "mutable=true to allow leveling/evolving."
                ),
            )
        # Mutate the URI in place; the NFTokenID is unchanged (same asset).
        nft.uri = uri
        return SubmitResult(
            success=True, txid=self._next_txid(), result_code="tesSUCCESS",
            fee="12", ledger_index=99999999, explorer_url="",
        )

    # ── Clawback methods ─────────────────────────────────────────────

    async def submit_account_set_clawback(
        self,
        wallet_seed: str,
        issuer_address: str = "",
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False, result_code="tecOWNERS", fee="12",
                error="[dry-run] Simulated failure: AccountSet clawback",
            )
        # Key the flag by the issuer's REAL address when supplied. Every dry-run
        # seed collapses to one synthetic address, so without the real address
        # we could not tell a clawback-enabled issuer apart from a second issuer
        # that never opted in (the failure-case module needs exactly that
        # distinction). Fall back to the collapsed seed-address otherwise.
        issuer = issuer_address or _address_from_seed(wallet_seed)
        self._clawback_enabled.add(issuer)
        return SubmitResult(
            success=True, txid=self._next_txid(), result_code="tesSUCCESS",
            fee="12", ledger_index=99999999, explorer_url="",
        )

    async def submit_clawback(
        self,
        issuer_seed: str,
        holder_address: str,
        currency: str,
        amount: str,
        issuer_address: str = "",
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(
                success=False, result_code="tecNO_PERMISSION", fee="12",
                error="[dry-run] Simulated failure: Clawback",
            )

        # Find the HOLDER's trust line for this currency. When the issuer's real
        # address is known we match on it; otherwise (collapsed-seed unit tests)
        # we match by currency alone and treat the line's peer as the issuer.
        matching_tl = None
        for tl in self._live_lines_for(holder_address):
            if tl.currency != currency:
                continue
            if issuer_address and tl.peer != issuer_address:
                continue
            matching_tl = tl
            break
        if matching_tl is None:
            return SubmitResult(
                success=False, result_code="tecNO_LINE", fee="12",
                error=(
                    f"[dry-run] No {currency} trust line from holder "
                    f"{holder_address[:12]}... to this issuer — nothing to claw back."
                ),
            )

        # The authoritative issuer identity is the real address when supplied,
        # else the line's peer (which carries the real issuer on every path).
        issuer = issuer_address or matching_tl.peer or _address_from_seed(issuer_seed)
        # Clawback requires asfAllowTrustLineClawback to have been set first.
        # Accept either the real-address key or the collapsed seed-address key
        # (the latter for unit tests that enable via seed without a real addr).
        if (
            issuer not in self._clawback_enabled
            and _address_from_seed(issuer_seed) not in self._clawback_enabled
        ):
            return SubmitResult(
                success=False, result_code="tecNO_PERMISSION", fee="12",
                error=(
                    "[dry-run] Clawback refused — the issuer never enabled "
                    "asfAllowTrustLineClawback (AccountSet) before issuing. "
                    "That flag must be set on a fresh issuer before any tokens "
                    "are issued; it cannot be enabled retroactively."
                ),
            )

        try:
            have = Decimal(matching_tl.balance)
            claw = Decimal(amount)
        except Exception:
            return SubmitResult(
                success=False, result_code="temBAD_AMOUNT", fee="12",
                error=f"[dry-run] Invalid clawback amount: {amount}",
            )
        # XRPL clamps a clawback to the holder's balance (you can't claw more
        # than they hold). Debit exactly min(amount, balance).
        clawed = claw if claw <= have else have
        new_balance = have - clawed
        matching_tl.balance = (
            str(int(new_balance)) if new_balance == int(new_balance) else str(new_balance)
        )
        return SubmitResult(
            success=True, txid=self._next_txid(), result_code="tesSUCCESS",
            fee="12", ledger_index=99999999, explorer_url="",
        )

    # ── Escrow / DID / MPT methods ───────────────────────────────────

    @staticmethod
    def _resolve(store: _PerAddressStore, address: str) -> list:
        """Per-address fetch with the legacy + single-wallet fallbacks (shared shape)."""
        if address in store:
            return list(store[address])
        legacy = store.get(_PerAddressStore._LEGACY_KEY, [])
        if legacy:
            return list(legacy)
        real = {k: v for k, v in store.items() if k != _PerAddressStore._LEGACY_KEY}
        if len(real) == 1:
            return list(next(iter(real.values())))
        return []

    def set_dry_clock(self, ripple_time: int) -> None:
        """Set the deterministic clock used to gate EscrowFinish/EscrowCancel.

        ``ripple_time`` is ripple-epoch seconds (same units as FinishAfter /
        CancelAfter). Tests set this BEFORE a FinishAfter to exercise the
        not-yet-finishable error path, or BEFORE a CancelAfter to exercise the
        not-yet-cancellable path. The default (far future) makes a fresh escrow
        immediately finishable/cancellable so the happy path is deterministic.
        """
        self._dry_clock = int(ripple_time)

    async def submit_escrow_create(
        self,
        wallet_seed: str,
        amount: str,
        destination: str,
        finish_after: int,
        cancel_after: int | None = None,
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(success=False, result_code="tecNO_PERMISSION", fee="12",
                                error="[dry-run] Simulated failure: escrow create")
        owner = _address_from_seed(wallet_seed)
        txid = self._next_txid()
        seq = 1000 + self._counter
        self._escrows.setdefault(owner, []).append(
            EscrowInfo(sequence=seq, amount=amount, destination=destination,
                       finish_after=finish_after, cancel_after=cancel_after)
        )
        self._inc_owner(owner)
        # Mirror testnet: return the create sequence as the SubmitResult.fee?
        # No — fee is a string of drops. Expose the create-sequence via
        # result_code? No. The contract is that get_escrows() carries it in
        # EscrowInfo.sequence; callers read it from there (parity with testnet,
        # where the sequence is derived from the Escrow's create tx, not the
        # submit response). Keep SubmitResult shape identical to testnet.
        return SubmitResult(success=True, txid=txid, result_code="tesSUCCESS", fee="12",
                            ledger_index=99999999, explorer_url="")

    async def get_escrows(self, address: str) -> list[EscrowInfo]:
        return self._resolve(self._escrows, address)

    def _find_escrow(self, owner: str, offer_sequence: int) -> EscrowInfo | None:
        """Locate the live EscrowInfo for *owner* + create-sequence, or None."""
        for e in self._resolve(self._escrows, owner):
            if e.sequence == offer_sequence:
                return e
        return None

    def _remove_escrow(self, owner: str, escrow: EscrowInfo) -> None:
        """Remove *escrow* from the owner's live bucket and free its reserve."""
        # _resolve may return the legacy or single-wallet fallback bucket, so
        # mutate whichever real list actually contains this object.
        for key in list(self._escrows.keys()):
            bucket = dict.__getitem__(self._escrows, key)
            if escrow in bucket:
                bucket.remove(escrow)
                break
        # Owner-reserve is tracked under the derived dry-run address (every
        # seed collapses to it), matching where submit_escrow_create incremented.
        self._dec_owner(owner)

    async def submit_escrow_finish(
        self,
        wallet_seed: str,
        owner: str,
        offer_sequence: int,
        condition: str = "",
        fulfillment: str = "",
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(success=False, result_code="tecNO_PERMISSION", fee="12",
                                error="[dry-run] Simulated failure: escrow finish")
        target = self._find_escrow(owner, offer_sequence)
        if target is None:
            # No such escrow (wrong sequence / already finished / nonexistent).
            # Mirror testnet's engine result for a missing Escrow ledger entry.
            return SubmitResult(success=False, result_code="tecNO_TARGET", fee="12",
                                error=("[dry-run] No escrow found for owner+sequence "
                                       f"{offer_sequence} — wrong OfferSequence, or it "
                                       "was already finished/cancelled."))
        # Time gate: EscrowFinish can only succeed at/after FinishAfter.
        if target.finish_after is not None and self._dry_clock < target.finish_after:
            return SubmitResult(success=False, result_code="tecNO_PERMISSION", fee="12",
                                error=("[dry-run] EscrowFinish before FinishAfter — the "
                                       "release time has not elapsed yet."))
        txid = self._next_txid()
        # Release the locked XRP to the destination, then remove the object.
        # target.amount is the XRP value the create handler passed (e.g. "10").
        # Credit the destination so the lifecycle test can observe the release.
        try:
            drops = int(Decimal(target.amount) * Decimal("1000000"))
        except Exception:
            drops = 0
        if target.destination:
            self._balances[target.destination] = (
                self._balances.get(target.destination, 0) + drops
            )
        self._remove_escrow(owner, target)
        return SubmitResult(success=True, txid=txid, result_code="tesSUCCESS", fee="12",
                            ledger_index=99999999, explorer_url="")

    async def submit_escrow_cancel(
        self,
        wallet_seed: str,
        owner: str,
        offer_sequence: int,
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(success=False, result_code="tecNO_PERMISSION", fee="12",
                                error="[dry-run] Simulated failure: escrow cancel")
        target = self._find_escrow(owner, offer_sequence)
        if target is None:
            return SubmitResult(success=False, result_code="tecNO_TARGET", fee="12",
                                error=("[dry-run] No escrow found for owner+sequence "
                                       f"{offer_sequence} — wrong OfferSequence, or it "
                                       "was already finished/cancelled."))
        # Time gate: EscrowCancel can only succeed at/after CancelAfter.
        if target.cancel_after is not None and self._dry_clock < target.cancel_after:
            return SubmitResult(success=False, result_code="tecNO_PERMISSION", fee="12",
                                error=("[dry-run] EscrowCancel before CancelAfter — the "
                                       "cancel time has not elapsed yet."))
        txid = self._next_txid()
        # Cancel returns the locked XRP to the OWNER (reclaim path), then removes.
        try:
            drops = int(Decimal(target.amount) * Decimal("1000000"))
        except Exception:
            drops = 0
        self._balances[owner] = self._balances.get(owner, 0) + drops
        self._remove_escrow(owner, target)
        return SubmitResult(success=True, txid=txid, result_code="tesSUCCESS", fee="12",
                            ledger_index=99999999, explorer_url="")

    async def submit_did_set(self, wallet_seed: str, uri: str = "", data: str = "") -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(success=False, result_code="temEMPTY_DID", fee="12",
                                error="[dry-run] Simulated failure: DID set")
        owner = _address_from_seed(wallet_seed)
        if owner not in self._dids:
            self._inc_owner(owner)
        self._dids[owner] = DIDInfo(account=owner, uri=uri, data=data)
        return SubmitResult(success=True, txid=self._next_txid(), result_code="tesSUCCESS",
                            fee="12", ledger_index=99999999, explorer_url="")

    async def submit_did_delete(self, wallet_seed: str) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(success=False, result_code="tecNO_PERMISSION", fee="12",
                                error="[dry-run] Simulated failure: DID delete")
        owner = _address_from_seed(wallet_seed)
        # Resolve the DID under the owner, with the single-DID fallback that
        # get_did uses (dry-run seeds collapse to one address).
        key = None
        if owner in self._dids:
            key = owner
        elif len(self._dids) == 1:
            key = next(iter(self._dids.keys()))
        if key is None:
            # Nothing to delete — mirror testnet's tecNO_ENTRY for DIDDelete
            # on an account that has no DID object.
            return SubmitResult(success=False, result_code="tecNO_ENTRY", fee="12",
                                error="[dry-run] No DID to delete for this account.")
        del self._dids[key]
        self._dec_owner(key)
        return SubmitResult(success=True, txid=self._next_txid(), result_code="tesSUCCESS",
                            fee="12", ledger_index=99999999, explorer_url="")

    async def get_did(self, address: str) -> DIDInfo | None:
        if address in self._dids:
            return self._dids[address]
        if len(self._dids) == 1:
            return next(iter(self._dids.values()))
        return None

    async def submit_mpt_issuance_create(
        self,
        wallet_seed: str,
        maximum_amount: str,
        asset_scale: int = 0,
        transfer_fee: int = 0,
        can_transfer: bool = True,
    ) -> SubmitResult:
        if self._fail_next:
            self._fail_next = False
            return SubmitResult(success=False, result_code="temMALFORMED", fee="12",
                                error="[dry-run] Simulated failure: MPT issuance create")
        owner = _address_from_seed(wallet_seed)
        txid = self._next_txid()
        iid = hashlib.sha256(f"{owner}-mpt-{self._counter}".encode()).hexdigest().upper()[:48]
        self._mpts.setdefault(owner, []).append(
            MPTIssuanceInfo(issuance_id=iid, maximum_amount=maximum_amount, asset_scale=asset_scale,
                            transfer_fee=transfer_fee, flags=0x20 if can_transfer else 0)
        )
        self._inc_owner(owner)
        return SubmitResult(success=True, txid=txid, result_code="tesSUCCESS", fee="12",
                            ledger_index=99999999, explorer_url="")

    async def get_mpt_issuances(self, address: str) -> list[MPTIssuanceInfo]:
        return self._resolve(self._mpts, address)
