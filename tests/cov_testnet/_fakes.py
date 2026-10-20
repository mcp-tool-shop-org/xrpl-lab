"""Offline fakes shared by the testnet-transport coverage tests.

No socket ever opens: ``_rpc_client`` is replaced with a fake client that
routes canned results by request class name, ``submit_and_wait`` records the
transaction it was handed, and ``get_next_valid_seq_number`` / ``autofill`` /
``asyncio.sleep`` are stubbed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from xrpl.wallet import Wallet

from xrpl_lab.transport import xrpl_testnet as xt
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

SEED = "sEdTM1uX8pu2do5XvTnutH6HsouMaM2"
SEED2 = "sEd7T2TvAQ6iTni8BPvkJYit21gvcqm"
SEED3 = "sEdTSR39xK2NxGrW6UR7CDv1wVXYuuX"
WALLET = Wallet.from_seed(SEED)
WALLET2 = Wallet.from_seed(SEED2)
WALLET3 = Wallet.from_seed(SEED3)
ADDR = WALLET.address
ADDR2 = WALLET2.address
ADDR3 = WALLET3.address
DEST = "rnUGL8j64E24NVpAQJerRhAsdosNxSUZju"
ISSUER = "rQBCBmLJU5TUKnDfwXViwv4QVCUNxBLGBs"
HOLDER = "raqdJMwygZxnRLmTzptHmV7PvYpHqEPgzJ"
HASH64 = "AB" * 32
HASH64_B = "CD" * 32
MPT_ID = "00" * 4 + "AB" * 20  # 48 hex
CRED_TYPE = "4B5943"  # "KYC"
PINNED_SEQ = 5_010_042
TXID = "E3FE" + "0" * 60


class FakeResponse:
    def __init__(self, result: dict) -> None:
        self.result = result


class FakeClient:
    """Routes canned results by request class name.

    A value may be a dict (returned as the result), an Exception (raised), or
    a callable ``req -> dict | Exception`` (for pagination / per-request
    answers). Every request object is recorded in ``requests``.
    """

    def __init__(self, results: dict | None = None) -> None:
        self.results = dict(results or {})
        self.requests: list = []

    def names(self) -> list[str]:
        return [type(r).__name__ for r in self.requests]

    def of(self, name: str) -> list:
        return [r for r in self.requests if type(r).__name__ == name]

    async def request(self, req, *args, **kwargs):
        self.requests.append(req)
        value = self.results.get(type(req).__name__, {})
        if callable(value):
            value = value(req)
        if isinstance(value, BaseException):
            raise value
        return FakeResponse(value)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def submit_ok(txid: str = TXID, meta: dict | None = None, **tx_extra) -> dict:
    """An API-v2 validated tesSUCCESS submit response."""
    m = {"TransactionResult": "tesSUCCESS"}
    m.update(meta or {})
    return {
        "hash": txid,
        "ledger_index": 12345678,
        "meta": m,
        "tx_json": {"Fee": "12", "Sequence": PINNED_SEQ, **tx_extra},
        "validated": True,
    }


@dataclass
class Env:
    client: FakeClient
    submitted: list = field(default_factory=list)  # (tx, wallet-or-None)
    behaviours: list = field(default_factory=list)
    autofill_calls: list = field(default_factory=list)

    @property
    def tx(self):
        assert self.submitted, "submit_and_wait was never called"
        return self.submitted[-1][0]

    def xrpl(self) -> dict:
        return self.tx.to_xrpl()


def _fill(tx, signers_count: int = 0):
    base = 10 * (1 + signers_count)
    d = tx.to_dict()
    d.setdefault("fee", str(base))
    d["fee"] = d.get("fee") or str(base)
    if d.get("sequence") is None:
        d["sequence"] = PINNED_SEQ
    d["last_ledger_sequence"] = 99_999_999
    return type(tx).from_dict(d)


def install(
    monkeypatch: pytest.MonkeyPatch,
    results: dict | None = None,
    submit: list | dict | Exception | None = None,
    autofill: str = "raise",
    url: str | None = None,
) -> Env:
    """Patch every network seam; return the Env capturing submitted txs.

    ``submit`` is a response (dict), an exception, or a list of them consumed
    one per submit_and_wait call (the last repeats). ``autofill`` is
    ``"raise"`` (pre-sign unavailable -> unsigned submit path) or ``"fill"``
    (real local signing against a fabricated fee/ledger window).
    """
    if url is None:
        monkeypatch.delenv("XRPL_LAB_RPC_URL", raising=False)
    else:
        monkeypatch.setenv("XRPL_LAB_RPC_URL", url)
    monkeypatch.delenv("XRPL_LAB_ALLOW_LOCAL", raising=False)
    client = FakeClient(results)
    env = Env(client=client)
    behaviours = submit if isinstance(submit, list) else [submit or submit_ok()]
    env.behaviours = list(behaviours)

    monkeypatch.setattr(xt, "_rpc_client", lambda u: client)

    async def _submit_and_wait(tx, c, wallet=None):
        env.submitted.append((tx, wallet))
        idx = min(len(env.submitted) - 1, len(env.behaviours) - 1)
        b = env.behaviours[idx]
        if isinstance(b, BaseException):
            raise b
        return FakeResponse(b)

    async def _next_seq(account, c, *a, **k):
        return PINNED_SEQ

    async def _autofill(tx, c, signers_count=None):
        env.autofill_calls.append(tx)
        if autofill == "raise":
            raise RuntimeError("autofill unavailable")
        return _fill(tx, signers_count or 0)

    async def _no_sleep(_s):
        return None

    monkeypatch.setattr(xt, "submit_and_wait", _submit_and_wait)
    monkeypatch.setattr(xt, "get_next_valid_seq_number", _next_seq)
    monkeypatch.setattr(xt, "autofill", _autofill)
    monkeypatch.setattr(xt.asyncio, "sleep", _no_sleep)
    return env


def make_transport() -> XRPLTestnetTransport:
    return XRPLTestnetTransport()
