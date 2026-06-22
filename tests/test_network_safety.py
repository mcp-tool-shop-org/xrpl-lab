"""Testnet-only invariant — the transport refuses mainnet/unknown endpoints.

The product's headline hard invariant is "testnet-only, no mainnet". The
endpoint is env-overridable (XRPL_LAB_RPC_URL / XRPL_LAB_FAUCET_URL), so this
suite pins the enforcement:

  - ``classify_network`` maps hosts to networks correctly,
  - the default endpoints classify as testnet,
  - ``network_name`` reflects the ACTUAL endpoint (not a hard-coded label), and
  - the write path refuses to sign/submit against a non-testnet endpoint
    WITHOUT touching the wallet seed or the network.

Before the F-BRIDGE-A-001 fix this invariant was enforced nowhere in code —
only by a default value plus documentation — so a mainnet override would sign
and submit real-fund transactions while every label still said "testnet".
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from xrpl_lab.transport.xrpl_testnet import (
    DEFAULT_FAUCET_URL,
    DEFAULT_RPC_URL,
    SAFE_NETWORKS,
    XRPLTestnetTransport,
    classify_network,
)


class TestClassifyNetwork:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://s.altnet.rippletest.net:51234", "testnet"),
            ("https://faucet.altnet.rippletest.net/accounts", "testnet"),
            ("https://s.devnet.rippletest.net:51234", "devnet"),
            ("http://localhost:5005", "local"),
            ("http://127.0.0.1:5005", "local"),
            ("https://s1.ripple.com:51234", "mainnet"),
            ("https://s2.ripple.com:51234", "mainnet"),
            ("https://xrplcluster.com", "mainnet"),
            ("https://example.com", "unknown"),
            ("not a url", "unknown"),
            ("", "unknown"),
        ],
    )
    def test_classify(self, url: str, expected: str) -> None:
        assert classify_network(url) == expected

    def test_defaults_are_testnet(self) -> None:
        assert classify_network(DEFAULT_RPC_URL) == "testnet"
        assert classify_network(DEFAULT_FAUCET_URL) == "testnet"

    def test_safe_networks_excludes_mainnet_and_unknown(self) -> None:
        assert "mainnet" not in SAFE_NETWORKS
        assert "unknown" not in SAFE_NETWORKS
        assert {"testnet", "devnet", "local"} <= SAFE_NETWORKS


class TestNetworkNameReflectsEndpoint:
    def test_default_is_testnet(self, monkeypatch) -> None:
        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
        assert XRPLTestnetTransport().network_name == "testnet"

    def test_mainnet_override_reflected(self, monkeypatch) -> None:
        monkeypatch.setenv("XRPL_LAB_RPC_URL", "https://s1.ripple.com:51234")
        assert XRPLTestnetTransport().network_name == "mainnet"


class TestWritePathRefusesNonTestnet:
    """Load-bearing guarantee: a mainnet/unknown override never signs/submits."""

    def _transport(self, monkeypatch, url: str) -> XRPLTestnetTransport:
        monkeypatch.setenv("XRPL_LAB_RPC_URL", url)
        return XRPLTestnetTransport()

    def test_submit_payment_refused_on_mainnet(self, monkeypatch) -> None:
        t = self._transport(monkeypatch, "https://s1.ripple.com:51234")
        res = asyncio.run(t.submit_payment("sEdSEEDDOESNOTMATTER", "rDEST", "10"))
        assert res.success is False
        assert "Refusing" in res.error
        assert not res.txid

    def test_submit_trust_set_refused_on_unknown(self, monkeypatch) -> None:
        t = self._transport(monkeypatch, "https://evil.example.com:51234")
        res = asyncio.run(t.submit_trust_set("sEdSEED", "rISSUER", "USD", "100"))
        assert res.success is False
        assert "Refusing" in res.error

    def test_faucet_refused_on_mainnet(self, monkeypatch) -> None:
        t = self._transport(monkeypatch, "https://s1.ripple.com:51234")
        res = asyncio.run(t.fund_from_faucet("rDEST"))
        assert res.success is False
        assert "Refusing" in res.message

    def test_guard_does_not_fire_for_default_testnet(self, monkeypatch) -> None:
        # Sanity: the guard does NOT fire for the default testnet endpoint
        # (asserted on the helper to avoid a real network call).
        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
        assert XRPLTestnetTransport()._network_guard() is None


_MAINNET_RPC = "https://s1.ripple.com:51234"


# ── Mainnet-refusal coverage: name → call closure ────────────────────
#
# Keyed by method name so the reflection completeness test below can
# assert this set is EXACTLY the set of signing methods on the transport
# (minus the explicitly-waived AMM stubs). Adding a new signing method
# without a row here makes ``test_mainnet_refusal_covers_every_signing_method``
# FAIL — closing TESTS-A-001 against future drift.
_MAINNET_REFUSAL_CALLS = {
    "submit_payment": lambda t: t.submit_payment("sEdSEED", "rDEST", "10"),
    "submit_trust_set": lambda t: t.submit_trust_set("sEdSEED", "rISSUER", "USD", "100"),
    "submit_issued_payment": (
        lambda t: t.submit_issued_payment("sEdSEED", "rDEST", "USD", "rISSUER", "5")
    ),
    "submit_offer_create": (
        lambda t: t.submit_offer_create("sEdSEED", "USD", "5", "rISSUER", "XRP", "10", "")
    ),
    "submit_offer_cancel": lambda t: t.submit_offer_cancel("sEdSEED", 1),
    # ── v1.8.0 fund-moving methods (TESTS-A-001) — previously UNTESTED ──
    "submit_nft_mint": lambda t: t.submit_nft_mint("sEdSEED", "ipfs://example", 0),
    "submit_escrow_create": (
        lambda t: t.submit_escrow_create("sEdSEED", "10", "rDEST", 999999999)
    ),
    "submit_did_set": lambda t: t.submit_did_set("sEdSEED", "did:example:123", ""),
    "submit_mpt_issuance_create": (
        lambda t: t.submit_mpt_issuance_create("sEdSEED", "1000000", 2, 0)
    ),
    # ── v2.0.0 lifecycle-closing signing methods (f1-engine) ──
    # Each MUST call _network_guard() before Wallet.from_seed, exactly like the
    # create-side methods above. These finish the broken lifecycles: escrow
    # finish/cancel (XRP no longer locked forever), DID delete (identity can
    # be revoked), NFT burn (reserve can be freed).
    "submit_escrow_finish": (
        lambda t: t.submit_escrow_finish("sEdSEED", "rOWNER", 12)
    ),
    "submit_escrow_cancel": (
        lambda t: t.submit_escrow_cancel("sEdSEED", "rOWNER", 12)
    ),
    "submit_did_delete": lambda t: t.submit_did_delete("sEdSEED"),
    "submit_nft_burn": lambda t: t.submit_nft_burn("sEdSEED", "00080000ABC"),
    # ── v2.0.0 game-economy CONTROL signing methods (f2-engine) ──
    # Clawback (XLS-39), NFT marketplace (XLS-20), dynamic NFT (XLS-46). Each
    # MUST call _network_guard() before Wallet.from_seed, exactly like the
    # create/lifecycle methods above. These move real value (recall tokens,
    # settle trades, mutate assets), so the testnet-only invariant applies.
    "submit_account_set_clawback": (
        lambda t: t.submit_account_set_clawback("sEdSEED")
    ),
    "submit_clawback": (
        lambda t: t.submit_clawback("sEdSEED", "rHOLDER", "GOLD", "30")
    ),
    "submit_set_freeze": (
        lambda t: t.submit_set_freeze("sEdSEED", "rHOLDER", "GLD", True)
    ),
    "submit_global_freeze": (
        lambda t: t.submit_global_freeze("sEdSEED", True)
    ),
    "submit_nft_create_offer": (
        lambda t: t.submit_nft_create_offer("sEdSEED", "00080000ABC", "100")
    ),
    "submit_nft_accept_offer": (
        lambda t: t.submit_nft_accept_offer("sEdSEED", sell_offer="0" * 64)
    ),
    "submit_nft_modify": (
        lambda t: t.submit_nft_modify("sEdSEED", "00080000ABC", "ipfs://x")
    ),
}

# AMM submit_* methods are stubs that return result_code="notSupported"
# WITHOUT ever signing or reaching the network (see xrpl_testnet.py AMM
# stub block). They never touch a wallet seed, so the mainnet-refusal
# invariant is moot for them — an explicit waiver, not an oversight. If
# AMM is ever implemented for real, drop the relevant name from here and
# the completeness test below will demand a refusal-coverage row for it.
_AMM_STUB_WAIVERS = frozenset({
    "submit_amm_create",
    "submit_amm_deposit",
    "submit_amm_withdraw",
})


@pytest.mark.parametrize(
    "call",
    list(_MAINNET_REFUSAL_CALLS.values()),
    ids=list(_MAINNET_REFUSAL_CALLS.keys()),
)
def test_all_write_methods_refuse_mainnet(monkeypatch, call) -> None:
    # The guard must be present on EVERY fund-moving method, not just the
    # five the basic suite exercised — pins the family so a refactor can't
    # silently drop it from a sibling (verify-wave contract-completeness
    # probe). The four v1.8.0 methods (nft_mint / escrow_create / did_set /
    # mpt_issuance_create) are now covered: each calls _network_guard()
    # first, so deleting that call (e.g. dropping the guard from
    # submit_nft_mint) makes that case FAIL — success would be True/error
    # would be empty and a real wallet+network call would be attempted.
    monkeypatch.setenv("XRPL_LAB_RPC_URL", _MAINNET_RPC)
    res = asyncio.run(call(XRPLTestnetTransport()))
    assert res.success is False
    assert "Refusing" in res.error
    assert not res.txid


def test_mainnet_refusal_covers_every_signing_method() -> None:
    """Reflection-based completeness gate (TESTS-A-001).

    Enumerate every ``submit_*`` / ``fund_*`` method on
    ``XRPLTestnetTransport``, subtract the AMM stubs that return
    'notSupported' WITHOUT signing (explicit waiver), and assert the
    remaining set is EXACTLY the set covered by the mainnet-refusal
    parametrize above. A future signing method therefore CANNOT be added
    without either (a) a refusal-coverage row in ``_MAINNET_REFUSAL_CALLS``
    or (b) an explicit waiver in ``_AMM_STUB_WAIVERS`` — closing the gap
    permanently rather than for just today's nine methods.

    Would-FAIL demonstration: if a new ``submit_foo`` signing method were
    added to the transport and NOT listed in either set, ``signing_methods``
    would contain ``"submit_foo"`` while ``covered`` would not — the final
    equality assertion fails with the offending name in the diff. Likewise,
    if ``submit_nft_mint`` were removed from ``_MAINNET_REFUSAL_CALLS`` (a
    regression in coverage), ``covered`` would shrink and the assertion
    would fail.
    """
    # fund_from_faucet refuses via its own faucet-URL guard and is pinned
    # by the dedicated faucet tests above (mainnet RPC + mainnet faucet),
    # so it is intentionally NOT part of the submit-refusal parametrize.
    _FUND_WAIVERS = frozenset({"fund_from_faucet"})

    discovered = {
        name
        for name, _member in inspect.getmembers(
            XRPLTestnetTransport, predicate=inspect.isfunction
        )
        if name.startswith("submit_") or name.startswith("fund_")
    }

    signing_methods = discovered - _AMM_STUB_WAIVERS - _FUND_WAIVERS
    covered = set(_MAINNET_REFUSAL_CALLS.keys())

    assert signing_methods == covered, (
        "mainnet-refusal coverage drift: signing methods on the transport "
        "do not match the parametrized refusal set.\n"
        f"  uncovered (signing but no refusal row): {signing_methods - covered}\n"
        f"  stale (refusal row but method gone): {covered - signing_methods}\n"
        "Add a row to _MAINNET_REFUSAL_CALLS for a new signing method, or "
        "an explicit waiver to _AMM_STUB_WAIVERS / _FUND_WAIVERS if it does "
        "not sign."
    )


def test_faucet_refused_when_faucet_url_is_mainnet_even_if_rpc_is_testnet(monkeypatch) -> None:
    # The faucet URL is independently overridable; a mainnet faucet override
    # must be refused even when the RPC stays on the default testnet, so the
    # user's address is never POSTed to an attacker host (verify-wave finding).
    monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)  # default testnet RPC
    monkeypatch.setenv("XRPL_LAB_FAUCET_URL", "https://s1.ripple.com/accounts")
    res = asyncio.run(XRPLTestnetTransport().fund_from_faucet("rDEST"))
    assert res.success is False
    assert "Refusing" in res.message
    assert "faucet" in res.message.lower()


@pytest.mark.parametrize(
    "url",
    [
        "https://altnet.rippletest.net.evil.com",
        "https://s.altnet.rippletest.net.attacker.com:51234",
        "https://rippletest.net.attacker.com",
        "https://devnet.rippletest.net.evil.org:51234",
    ],
)
def test_classify_rejects_suffix_spoofed_testnet_hosts(url: str) -> None:
    # A host that merely CONTAINS a testnet domain as a non-suffix segment must
    # NOT read as SAFE — only true *.altnet/*.devnet.rippletest.net subdomains
    # (Ripple-controlled) match. classify_network must fail closed.
    assert classify_network(url) not in SAFE_NETWORKS


def test_classify_userinfo_does_not_mask_mainnet() -> None:
    # user@host — the host is mainnet; userinfo must not be mistaken for the host.
    assert classify_network("https://user:pass@s1.ripple.com:51234") == "mainnet"
