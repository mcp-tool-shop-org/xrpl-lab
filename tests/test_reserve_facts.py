"""Reserve-fact drift guard (re-swarm v3, RESERVE-FACT).

The pre-2024 reserve figures (10 XRP base / 2 XRP owner) survived two prior
swarms in doctor.py prose and strategy.py constants even though the network
reduced them to 1 XRP / 0.2 XRP on 2024-12-02 — and modules/reserves_101.md
already taught the correct 1 XRP. These tests single-source the canonical
values and prove the doctor's explanations and the strategy estimate cannot
silently drift back to the stale figures.

Non-vacuity: reverting doctor.py to "10 XRP" (or strategy.py to the 10/2
drops constants) makes these fail — the guard goes RED on the exact
regression it exists to catch.
"""

import re
from decimal import Decimal
from pathlib import Path

import pytest

from xrpl_lab import reserves
from xrpl_lab.actions.strategy import _BASE_RESERVE_DROPS, _OWNER_RESERVE_DROPS
from xrpl_lab.doctor import explain_result_code

_MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"

# Modules that teach a reserve figure in prose (PTC-003). Stage A guarded the
# reserve values in CODE (reserves.py / doctor.py / strategy.py); the module
# markdown was correct but UNguarded, so it could drift independently.
_RESERVE_MODULES = [
    "dex_literacy.md",
    "dex_market_making_101.md",
    "trust_lines_101.md",
    "reserves_101.md",
]

# The pre-2024 stale figures, matched only where they'd be a RESERVE claim.
# `(?<!\d\.)` keeps "0.2 XRP" from matching as "2 XRP".
_STALE_OWNER = re.compile(r"(?<!\d\.)\b2 XRP\b")
_STALE_BASE = re.compile(r"\b10 XRP\b")


class TestReserveConstants:
    def test_canonical_values_are_current(self):
        # Current mainnet values since the 2024-12-02 reduction.
        assert reserves.BASE_RESERVE_XRP == 1
        assert Decimal("0.2") == reserves.OWNER_RESERVE_XRP
        assert reserves.BASE_RESERVE_DROPS == 1_000_000
        assert reserves.OWNER_RESERVE_DROPS == 200_000

    def test_strategy_uses_shared_constants(self):
        # strategy.py must not carry its own divergent copy.
        assert _BASE_RESERVE_DROPS == reserves.BASE_RESERVE_DROPS
        assert _OWNER_RESERVE_DROPS == reserves.OWNER_RESERVE_DROPS


class TestDoctorReserveProse:
    def test_no_dst_states_correct_base_reserve(self):
        info = explain_result_code("tecNO_DST")
        assert "1 XRP" in info["action"]
        # Drift guard: the stale figure must not reappear as a reserve claim.
        assert "10 XRP" not in info["action"]

    def test_no_dst_insuf_xrp_states_correct_base_reserve(self):
        info = explain_result_code("tecNO_DST_INSUF_XRP")
        assert "1 XRP" in info["meaning"]
        assert "10 XRP" not in info["meaning"]
        assert "10 XRP" not in info["action"]


class TestSingleSourceInvariant:
    def test_doctor_and_strategy_agree_on_base_reserve(self):
        # The whole point of xrpl_lab/reserves.py: prose and math share one truth.
        doctor_meaning = explain_result_code("tecNO_DST_INSUF_XRP")["meaning"]
        assert f"{reserves.BASE_RESERVE_XRP} XRP" in doctor_meaning
        assert _BASE_RESERVE_DROPS == reserves.BASE_RESERVE_XRP * 1_000_000


class TestModuleProseReserveDrift:
    """PTC-003 — the curriculum prose must track the canonical reserve values,
    not just the code. Scoped to reserve-context lines so a legit non-reserve
    amount (e.g. an offer 'ask (2 XRP)') is never mistaken for a reserve claim."""

    @staticmethod
    def _reserve_lines(text: str) -> list[str]:
        return [ln for ln in text.splitlines() if "reserve" in ln.lower()]

    @pytest.mark.parametrize(
        "module", ["dex_literacy.md", "dex_market_making_101.md", "trust_lines_101.md"]
    )
    def test_owner_reserve_prose_is_canonical(self, module):
        content = (_MODULES_DIR / module).read_text(encoding="utf-8")
        owner = f"{reserves.OWNER_RESERVE_XRP} XRP"  # "0.2 XRP"
        assert owner in content, f"{module} should teach the owner reserve as {owner}"
        for line in self._reserve_lines(content):
            assert not _STALE_OWNER.search(line), f"{module}: stale owner reserve in: {line!r}"

    def test_base_reserve_prose_is_canonical(self):
        content = (_MODULES_DIR / "reserves_101.md").read_text(encoding="utf-8")
        assert f"{reserves.BASE_RESERVE_XRP} XRP" in content  # "1 XRP"
        for line in self._reserve_lines(content):
            assert not _STALE_BASE.search(line), f"reserves_101.md: stale base reserve in: {line!r}"
