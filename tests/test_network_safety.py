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


@pytest.mark.parametrize(
    "call",
    [
        lambda t: t.submit_payment("sEdSEED", "rDEST", "10"),
        lambda t: t.submit_trust_set("sEdSEED", "rISSUER", "USD", "100"),
        lambda t: t.submit_issued_payment("sEdSEED", "rDEST", "USD", "rISSUER", "5"),
        lambda t: t.submit_offer_create("sEdSEED", "USD", "5", "rISSUER", "XRP", "10", ""),
        lambda t: t.submit_offer_cancel("sEdSEED", 1),
    ],
    ids=["payment", "trust_set", "issued_payment", "offer_create", "offer_cancel"],
)
def test_all_write_methods_refuse_mainnet(monkeypatch, call) -> None:
    # The guard must be present on EVERY fund-moving method, not just the two
    # the basic suite exercised — pins the family so a refactor can't silently
    # drop it from a sibling (verify-wave contract-completeness probe).
    monkeypatch.setenv("XRPL_LAB_RPC_URL", _MAINNET_RPC)
    res = asyncio.run(call(XRPLTestnetTransport()))
    assert res.success is False
    assert "Refusing" in res.error
    assert not res.txid


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
