"""Tests for strategy actions — snapshots, offers, hygiene, last_run."""

import json
import time
from datetime import datetime

import pytest

from xrpl_lab.actions.strategy import (
    PositionSnapshot,
    cancel_module_offers,
    check_inventory,
    compare_positions,
    hygiene_summary,
    snapshot_position,
    strategy_memo,
    write_last_run,
)
from xrpl_lab.transport.base import AccountSnapshot, OfferInfo, TrustLineInfo
from xrpl_lab.transport.dry_run import _FAKE_ADDRESS, DryRunTransport

# ── Memo tests ──────────────────────────────────────────────────────


class TestStrategyMemo:
    def test_memo_format(self):
        memo = strategy_memo("MM101", "OFFER_BID", "run123")
        assert memo == "XRPLLAB|STRAT|MM101|OFFER_BID|run123"

    def test_memo_auto_run_id(self):
        memo = strategy_memo("MM101", "OFFER_ASK")
        assert memo.startswith("XRPLLAB|STRAT|MM101|OFFER_ASK|")
        # Auto-generated run ID should be a timestamp
        parts = memo.split("|")
        assert len(parts) == 5
        datetime.fromisoformat(parts[4])  # Raises ValueError if not valid ISO timestamp

    def test_memo_prefix(self):
        memo = strategy_memo("FOO", "BAR", "x")
        assert memo.startswith("XRPLLAB|STRAT|")


# ── PositionSnapshot tests ──────────────────────────────────────────


class TestPositionSnapshot:
    def test_spendable_estimate_basic(self):
        snap = PositionSnapshot(
            timestamp=time.time(),
            account=AccountSnapshot(
                address="rTEST",
                balance_drops="50000000",  # 50 XRP
                owner_count=2,
            ),
            trust_lines=[],
            offers=[],
            xrp_balance="50000000",
            owner_count=2,
            offer_count=0,
        )
        # base reserve = 10 XRP, owner reserve = 2 XRP * 2 = 4 XRP
        # total reserved = 14 XRP = 14_000_000 drops
        # spendable = 50_000_000 - 14_000_000 = 36_000_000
        assert snap.spendable_estimate_drops == 36_000_000

    def test_spendable_zero_when_under_reserve(self):
        snap = PositionSnapshot(
            timestamp=time.time(),
            account=AccountSnapshot(
                address="rTEST",
                balance_drops="5000000",  # 5 XRP (below 10 XRP base reserve)
                owner_count=0,
            ),
            trust_lines=[],
            offers=[],
            xrp_balance="5000000",
            owner_count=0,
            offer_count=0,
        )
        assert snap.spendable_estimate_drops == 0

    def test_spendable_with_many_objects(self):
        snap = PositionSnapshot(
            timestamp=time.time(),
            account=AccountSnapshot(
                address="rTEST",
                balance_drops="100000000",  # 100 XRP
                owner_count=10,
            ),
            trust_lines=[],
            offers=[],
            xrp_balance="100000000",
            owner_count=10,
            offer_count=0,
        )
        # reserved = 10 XRP + 10*2 XRP = 30 XRP = 30_000_000
        # spendable = 100_000_000 - 30_000_000 = 70_000_000
        assert snap.spendable_estimate_drops == 70_000_000


@pytest.mark.asyncio
class TestSnapshotPosition:
    async def test_snapshot_populated(self):
        transport = DryRunTransport()
        transport._funded_addresses.add(_FAKE_ADDRESS)

        # Add some state
        transport._trust_lines.append(
            TrustLineInfo(
                account=_FAKE_ADDRESS,
                peer="rISSUER",
                currency="LAB",
                balance="100",
                limit="1000",
            )
        )
        transport._offers.append(
            OfferInfo(sequence=100, taker_pays="10", taker_gets="1")
        )
        transport._owner_count = 2

        snap = await snapshot_position(transport, _FAKE_ADDRESS)

        assert snap.account.address == _FAKE_ADDRESS
        assert snap.xrp_balance == "1000000000"
        assert snap.owner_count == 2
        assert snap.offer_count == 1
        assert len(snap.trust_lines) == 1
        assert len(snap.offers) == 1
        assert snap.timestamp > 0

    async def test_snapshot_unfunded(self):
        transport = DryRunTransport()
        snap = await snapshot_position(transport, "rNOBODY")
        assert snap.xrp_balance == "0"
        assert snap.offer_count == 0


# ── Compare positions tests ─────────────────────────────────────────


class TestComparePositions:
    def _make_snap(self, owner_count=0, offer_count=0) -> PositionSnapshot:
        return PositionSnapshot(
            timestamp=time.time(),
            account=AccountSnapshot(
                address="rTEST",
                balance_drops="50000000",
                owner_count=owner_count,
            ),
            trust_lines=[],
            offers=[OfferInfo(sequence=i, taker_pays="1", taker_gets="1")
                    for i in range(offer_count)],
            xrp_balance="50000000",
            owner_count=owner_count,
            offer_count=offer_count,
        )

    def test_no_change(self):
        before = self._make_snap(owner_count=2, offer_count=1)
        after = self._make_snap(owner_count=2, offer_count=1)
        result = compare_positions(before, after)

        assert result.owner_count_delta == 0
        assert result.offer_count_delta == 0
        assert result.clean
        assert "unchanged" in result.checks[0].lower()

    def test_owner_count_increased(self):
        before = self._make_snap(owner_count=1)
        after = self._make_snap(owner_count=3)
        result = compare_positions(before, after, label="offers")

        assert result.owner_count_delta == 2
        assert not result.clean
        assert "increased" in result.checks[0].lower()

    def test_owner_count_decreased(self):
        before = self._make_snap(owner_count=5)
        after = self._make_snap(owner_count=3)
        result = compare_positions(before, after)

        assert result.owner_count_delta == -2
        assert "decreased" in result.checks[0].lower()

    def test_offer_count_delta(self):
        before = self._make_snap(offer_count=0)
        after = self._make_snap(offer_count=2)
        result = compare_positions(before, after)

        assert result.offer_count_delta == 2
        assert "increased" in result.checks[1].lower()

    def test_label_in_explanation(self):
        before = self._make_snap(owner_count=1)
        after = self._make_snap(owner_count=3)
        result = compare_positions(before, after, label="placement")

        assert "placement" in result.explanation.lower()


# ── Cancel module offers tests ──────────────────────────────────────


@pytest.mark.asyncio
class TestCancelModuleOffers:
    async def test_cancel_all(self):
        transport = DryRunTransport()
        # Create 2 offers
        await transport.submit_offer_create(
            "seed", "LAB", "10", "rISSUER", "XRP", "1", "",
        )
        await transport.submit_offer_create(
            "seed", "LAB", "20", "rISSUER", "XRP", "2", "",
        )
        assert len(transport._offers) == 2

        seqs = [o.sequence for o in transport._offers]
        results = await cancel_module_offers(transport, "seed", seqs)

        assert len(results) == 2
        assert all(success for _, success in results)
        assert len(transport._offers) == 0

    async def test_cancel_partial_failure(self):
        transport = DryRunTransport()
        await transport.submit_offer_create(
            "seed", "LAB", "10", "rISSUER", "XRP", "1", "",
        )
        seqs = [transport._offers[0].sequence, 999]  # 999 doesn't exist
        results = await cancel_module_offers(transport, "seed", seqs)

        assert len(results) == 2
        # First succeeds, second "succeeds" in dry-run (no-op for nonexistent)
        assert results[0][1] is True

    async def test_cancel_empty_list(self):
        transport = DryRunTransport()
        results = await cancel_module_offers(transport, "seed", [])
        assert results == []


# ── Hygiene summary tests ───────────────────────────────────────────


class TestHygieneSummary:
    def _make_snap(self, owner_count=0, offer_count=0, tl_count=0) -> PositionSnapshot:
        return PositionSnapshot(
            timestamp=time.time(),
            account=AccountSnapshot(
                address="rTEST",
                balance_drops="50000000",
                owner_count=owner_count,
            ),
            trust_lines=[TrustLineInfo(
                account="rTEST", peer="rP", currency=f"C{i}",
            ) for i in range(tl_count)],
            offers=[OfferInfo(sequence=i, taker_pays="1", taker_gets="1")
                    for i in range(offer_count)],
            xrp_balance="50000000",
            owner_count=owner_count,
            offer_count=offer_count,
        )

    def test_clean_summary(self):
        baseline = self._make_snap(owner_count=1)
        final = self._make_snap(owner_count=1)
        summary = hygiene_summary(baseline, final, offers_cancelled=2)

        assert summary.clean
        assert summary.offers_remaining == 0
        assert summary.owner_count_delta == 0
        assert any("no open offers" in c.lower() for c in summary.checks)
        assert any("baseline" in c.lower() for c in summary.checks)
        assert any("cancelled" in c.lower() for c in summary.checks)

    def test_dirty_offers_remaining(self):
        baseline = self._make_snap(owner_count=1)
        final = self._make_snap(owner_count=3, offer_count=2)
        summary = hygiene_summary(baseline, final)

        assert not summary.clean
        assert summary.offers_remaining == 2
        assert summary.owner_count_delta == 2
        assert any("warning" in c.lower() for c in summary.checks)

    def test_trust_lines_created(self):
        baseline = self._make_snap(tl_count=0)
        final = self._make_snap(tl_count=2)
        summary = hygiene_summary(baseline, final)

        assert summary.trust_lines_created == 2

    def test_owner_count_decreased(self):
        baseline = self._make_snap(owner_count=5)
        final = self._make_snap(owner_count=3)
        summary = hygiene_summary(baseline, final)

        assert summary.clean  # owner_count_delta <= 0 is clean
        assert summary.owner_count_delta == -2


# ── Write last run tests ────────────────────────────────────────────


class TestWriteLastRun:
    def test_writes_files(self, tmp_path):
        ws = tmp_path / ".xrpl-lab"
        txids = ["TX_AAA", "TX_BBB", "TX_CCC"]

        result_path = write_last_run(
            txids=txids,
            module_id="dex_market_making_101",
            run_id="test-run-1",
            preset="strategy_mm101",
            endpoint="dry-run",
            workspace=ws,
        )

        assert result_path.exists()
        content = result_path.read_text(encoding="utf-8")
        assert "TX_AAA" in content
        assert "TX_BBB" in content
        assert "TX_CCC" in content

        meta_path = ws / "last_run_meta.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["module"] == "dex_market_making_101"
        assert meta["run_id"] == "test-run-1"
        assert meta["preset"] == "strategy_mm101"
        assert meta["endpoint"] == "dry-run"
        assert meta["txid_count"] == 3

    def test_auto_run_id(self, tmp_path):
        ws = tmp_path / ".xrpl-lab"
        write_last_run(
            txids=["TX_X"],
            module_id="test",
            workspace=ws,
        )
        meta = json.loads((ws / "last_run_meta.json").read_text(encoding="utf-8"))
        datetime.fromisoformat(meta["run_id"])  # Raises ValueError if not valid ISO timestamp

    def test_overwrites_previous(self, tmp_path):
        ws = tmp_path / ".xrpl-lab"
        write_last_run(txids=["TX_1"], module_id="first", workspace=ws)
        write_last_run(txids=["TX_2", "TX_3"], module_id="second", workspace=ws)

        content = (ws / "last_run_txids.txt").read_text(encoding="utf-8")
        assert "TX_2" in content
        assert "TX_1" not in content

        meta = json.loads((ws / "last_run_meta.json").read_text(encoding="utf-8"))
        assert meta["module"] == "second"
        assert meta["txid_count"] == 2


# ── Full lifecycle test ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestStrategyLifecycle:
    async def test_full_mm_cycle(self):
        """Simulate a market-making lifecycle: snapshot -> offers -> cancel -> hygiene."""
        transport = DryRunTransport()
        transport._funded_addresses.add(_FAKE_ADDRESS)

        # 1. Baseline snapshot
        baseline = await snapshot_position(transport, _FAKE_ADDRESS)
        assert baseline.offer_count == 0
        assert baseline.owner_count == 0

        # 2. Place bid offer
        bid_result = await transport.submit_offer_create(
            "seed", "LAB", "10", "rISSUER", "XRP", "1", "",
        )
        assert bid_result.success

        # 3. Place ask offer
        ask_result = await transport.submit_offer_create(
            "seed", "LAB", "10", "rISSUER", "XRP", "2", "",
        )
        assert ask_result.success

        # 4. After-offers snapshot
        after_offers = await snapshot_position(transport, _FAKE_ADDRESS)
        assert after_offers.offer_count == 2
        assert after_offers.owner_count == 2

        # 5. Compare positions
        comparison = compare_positions(baseline, after_offers, label="offers")
        assert comparison.owner_count_delta == 2
        assert comparison.offer_count_delta == 2
        assert not comparison.clean

        # 6. Cancel all offers
        seqs = [o.sequence for o in transport._offers]
        results = await cancel_module_offers(transport, "seed", seqs)
        assert all(success for _, success in results)

        # 7. Final snapshot
        final = await snapshot_position(transport, _FAKE_ADDRESS)
        assert final.offer_count == 0
        assert final.owner_count == 0

        # 8. Hygiene summary
        summary = hygiene_summary(baseline, final, offers_cancelled=2)
        assert summary.clean
        assert summary.offers_remaining == 0
        assert summary.owner_count_delta == 0

    async def test_inventory_guarded_cycle(self):
        """Simulate inventory-guarded quoting: only safe sides placed."""
        transport = DryRunTransport()
        transport._funded_addresses.add(_FAKE_ADDRESS)

        # Add LAB trust line with balance
        transport._trust_lines.append(
            TrustLineInfo(
                account=_FAKE_ADDRESS,
                peer="rISSUER",
                currency="LAB",
                balance="500",
                limit="10000",
            )
        )
        transport._owner_count = 1

        snap = await snapshot_position(transport, _FAKE_ADDRESS)

        # Check with reasonable thresholds
        inv = check_inventory(snap, "LAB", min_xrp_drops=20_000_000, min_token_balance=10)
        assert inv.can_bid  # 1000 XRP funded, plenty spendable
        assert inv.can_ask  # 500 LAB > 10 threshold
        assert inv.sides_allowed == ["bid", "ask"]
        assert inv.any_allowed

    async def test_lifecycle_with_trust_line(self):
        """Verify trust lines are tracked in snapshots."""
        transport = DryRunTransport()
        transport._funded_addresses.add(_FAKE_ADDRESS)

        baseline = await snapshot_position(transport, _FAKE_ADDRESS)

        # Set trust line
        await transport.submit_trust_set("seed", "rISSUER", "LAB", "1000")

        after = await snapshot_position(transport, _FAKE_ADDRESS)
        assert len(after.trust_lines) == 1
        assert after.owner_count == 1

        summary = hygiene_summary(baseline, after)
        assert summary.trust_lines_created == 1
        assert summary.owner_count_delta == 1


# ── Inventory check tests ───────────────────────────────────────────


class TestCheckInventory:
    def _make_snap(
        self, balance_drops="1000000000", owner_count=0,
        lab_balance="500", has_lab=True,
    ) -> PositionSnapshot:
        tls = []
        if has_lab:
            tls.append(TrustLineInfo(
                account="rTEST", peer="rISSUER", currency="LAB",
                balance=lab_balance, limit="10000",
            ))
        return PositionSnapshot(
            timestamp=time.time(),
            account=AccountSnapshot(
                address="rTEST",
                balance_drops=balance_drops,
                owner_count=owner_count,
            ),
            trust_lines=tls,
            offers=[],
            xrp_balance=balance_drops,
            owner_count=owner_count,
            offer_count=0,
        )

    def test_both_sides_healthy(self):
        snap = self._make_snap(balance_drops="1000000000", lab_balance="500")
        inv = check_inventory(snap, "LAB")
        assert inv.can_bid
        assert inv.can_ask
        assert inv.sides_allowed == ["bid", "ask"]
        assert inv.any_allowed

    def test_xrp_too_low_blocks_bid(self):
        # 15 XRP total, base reserve 10 XRP = 5 XRP spendable < 20 XRP threshold
        snap = self._make_snap(balance_drops="15000000", lab_balance="500")
        inv = check_inventory(snap, "LAB", min_xrp_drops=20_000_000)
        assert not inv.can_bid
        assert inv.can_ask
        assert inv.sides_allowed == ["ask"]

    def test_token_too_low_blocks_ask(self):
        snap = self._make_snap(balance_drops="1000000000", lab_balance="5")
        inv = check_inventory(snap, "LAB", min_token_balance=10)
        assert inv.can_bid
        assert not inv.can_ask
        assert inv.sides_allowed == ["bid"]

    def test_both_too_low(self):
        snap = self._make_snap(balance_drops="5000000", lab_balance="1")
        inv = check_inventory(snap, "LAB", min_xrp_drops=20_000_000, min_token_balance=10)
        assert not inv.can_bid
        assert not inv.can_ask
        assert inv.sides_allowed == []
        assert not inv.any_allowed

    def test_no_trust_line_blocks_ask(self):
        snap = self._make_snap(balance_drops="1000000000", has_lab=False)
        inv = check_inventory(snap, "LAB", min_token_balance=10)
        assert inv.can_bid
        assert not inv.can_ask
        assert inv.sides_allowed == ["bid"]

    def test_checks_have_ok_or_blocked(self):
        snap = self._make_snap(balance_drops="1000000000", lab_balance="500")
        inv = check_inventory(snap, "LAB")
        assert any("OK" in c for c in inv.checks)

    def test_custom_thresholds(self):
        snap = self._make_snap(balance_drops="50000000", lab_balance="50")
        inv = check_inventory(
            snap, "LAB",
            min_xrp_drops=100_000_000,  # 100 XRP minimum
            min_token_balance=100,  # 100 LAB minimum
        )
        assert not inv.can_bid  # 50 XRP total - 10 reserve = 40 spendable < 100
        assert not inv.can_ask  # 50 LAB < 100


# ── Last-run CLI test ───────────────────────────────────────────────


class TestLastRunCLI:
    def test_last_run_no_data(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from xrpl_lab.cli import main

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(main, ["last-run"])
        assert result.exit_code == 0
        assert "No last run" in result.output

    def test_last_run_with_data(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        from xrpl_lab.cli import main

        monkeypatch.chdir(tmp_path)
        ws = tmp_path / ".xrpl-lab"
        write_last_run(
            txids=["TX_1", "TX_2"],
            module_id="dex_market_making_101",
            run_id="test-run-1",
            preset="strategy_mm101",
            workspace=ws,
        )
        # Also create the preset file for the audit hint
        presets_dir = tmp_path / "presets"
        presets_dir.mkdir()
        (presets_dir / "strategy_mm101.json").write_text("{}", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(main, ["last-run"])
        assert result.exit_code == 0
        assert "dex_market_making_101" in result.output
        assert "test-run-1" in result.output
        assert "2" in result.output  # txid_count
        assert "audit" in result.output  # audit command hint
