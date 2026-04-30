"""Dry-run transport — no network, deterministic outputs for testing and --dry-run."""

from __future__ import annotations

import hashlib
import time
from decimal import ROUND_HALF_UP, Decimal, getcontext

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
        self._owner_count = 0  # tracks owned objects (trust lines, offers)
        self._tx_fixtures: dict[str, TxInfo] = {}  # txid -> TxInfo for audit testing
        # AMM state
        self._amm_pools: dict[str, dict] = {}  # pair_key -> pool state
        self._lp_balances: dict[str, dict[str, str]] = {}  # address -> {lp_key: balance}

    def _next_txid(self) -> str:
        """Generate a unique deterministic transaction ID (per-instance counter)."""
        self._counter += 1
        raw = f"{_FAKE_TXID_PREFIX}-{self._counter}-{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest().upper()[:64]

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
            addr_lines.remove(existing)
            self._owner_count = max(0, self._owner_count - 1)
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

        # Realistic validation: check trust line exists on destination
        # Search all addresses for a matching trust line (destination holds the trust line)
        matching_tl = None
        for addr_lines in self._trust_lines.values():
            for tl in addr_lines:
                if tl.currency == currency and tl.peer == issuer:
                    matching_tl = tl
                    break
            if matching_tl is not None:
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
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
        )

    def _resolve_lines(self, address: str) -> list[TrustLineInfo]:
        """Return trust lines for *address*, checking legacy bucket too."""
        if address in self._trust_lines:
            return list(self._trust_lines[address])
        legacy = self._trust_lines.get(_PerAddressStore._LEGACY_KEY, [])
        if legacy:
            return list(legacy)
        # Single-wallet fallback: if only one real address, return those
        real = {k: v for k, v in self._trust_lines.items()
                if k != _PerAddressStore._LEGACY_KEY}
        if len(real) == 1:
            return list(next(iter(real.values())))
        return []

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

        txid = self._next_txid()
        wallet_address = _address_from_seed(wallet_seed)
        addr_offers = self._offers.get(wallet_address, [])
        # Remove the offer from tracked list and decrement owner count
        before = len(addr_offers)
        addr_offers = [o for o in addr_offers if o.sequence != offer_sequence]
        if len(addr_offers) < before:
            self._owner_count = max(0, self._owner_count - 1)
        self._offers[wallet_address] = addr_offers
        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
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
        return AccountSnapshot(
            address=address,
            balance_drops=balance_drops,
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

        self._owner_count += 1  # AMM position

        return SubmitResult(
            success=True,
            txid=txid,
            result_code="tesSUCCESS",
            fee="12",
            ledger_index=99999999,
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
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
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
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
            explorer_url=f"https://testnet.xrpl.org/transactions/{txid}",
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
