"""Canonical XRPL reserve values — single source of truth.

The XRP Ledger locks a **base reserve** per account and an **owner reserve**
per owned object (trust line, offer, escrow, check, payment channel, ...).
These are network-governed: validators lowered them via fee-vote on
2024-12-02 (base 10 → 1 XRP, owner 2 → 0.2 XRP), and they can change again.

Historically these values were duplicated as prose in ``doctor.py`` and as
drops constants in ``actions/strategy.py`` — and they drifted (both carried
the pre-2024 ``10 XRP`` / ``2 XRP`` figures long after the reduction, while
``modules/reserves_101.md`` correctly taught ``1 XRP``). Single-sourcing them
here means the doctor's explanations and the strategy spendable-estimate can
never disagree again.

Long-term (Stage B TODO): these should be read live from ``server_state``
(``reserve_base_xrp`` / ``reserve_inc_xrp``) rather than hardcoded, since they
are amendment-tunable. The transport ``NetworkInfo`` struct carries no reserve
fields yet, so these current-mainnet values (which testnet matches) stand in.
"""

from decimal import Decimal

# Current values (mainnet, post-2024-12-02 reduction; testnet matches).
BASE_RESERVE_XRP = 1
OWNER_RESERVE_XRP = Decimal("0.2")

# Same values expressed in drops (1 XRP = 1_000_000 drops).
BASE_RESERVE_DROPS = 1_000_000
OWNER_RESERVE_DROPS = 200_000
