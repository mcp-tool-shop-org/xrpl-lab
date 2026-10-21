"""2.7.0: xrpl-py 5.2, and seeds that sign as the account they're recorded under.

xrpl-py 5.0 infers a seed's algorithm from its prefix; 4.x derived ED25519 from
every seed. xrpl-lab's own ``sEd...`` wallets derive the same address on both.
A secp256k1 ``s...`` seed imported under 4.x was recorded under its ED25519
address, so ``wallet_from_seed`` keeps that account when it's the expected one,
and fails closed when neither derivation matches (Argon, 2.6.2 round 1, Q4).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from xrpl.constants import CryptoAlgorithm
from xrpl.core.keypairs import generate_seed, is_valid_message
from xrpl.wallet import Wallet

import xrpl_lab.actions.wallet as wallet_mod
from xrpl_lab.errors import LabException
from xrpl_lab.transport.xrpl_testnet import XRPLTestnetTransport

# Fixed throwaway seeds from fixed entropy; never funded on any network.
_ENTROPY = "00112233445566778899aabbccddeeff"
SECP = generate_seed(entropy=_ENTROPY, algorithm=CryptoAlgorithm.SECP256K1)
ED = generate_seed(entropy=_ENTROPY, algorithm=CryptoAlgorithm.ED25519)
SECP_ADDR = Wallet.from_seed(SECP, algorithm=CryptoAlgorithm.SECP256K1).address
LEGACY_ADDR = Wallet.from_seed(SECP, algorithm=CryptoAlgorithm.ED25519).address  # 4.x's
OTHER_ADDR = Wallet.from_seed(ED).address if Wallet.from_seed(ED).address not in (
    SECP_ADDR, LEGACY_ADDR) else "rPT1Sjq2YGrBMTttX4GZHjKu9dyfzbpAYe"


def test_the_seeds_differ_as_measured() -> None:
    assert SECP.startswith("s") and not SECP.startswith("sEd")
    assert ED.startswith("sEd")
    assert SECP_ADDR != LEGACY_ADDR
    assert Wallet.from_seed(SECP).address == SECP_ADDR  # 5.x infers secp256k1


@pytest.mark.parametrize(
    ("seed", "expected", "address"),
    [
        (ED, None, Wallet.from_seed(ED).address),
        (SECP, None, SECP_ADDR),
        (SECP, SECP_ADDR, SECP_ADDR),
        (SECP, LEGACY_ADDR, LEGACY_ADDR),  # imported under 4.x: keeps its account
    ],
)
def test_wallet_from_seed_picks_the_expected_account(seed, expected, address) -> None:
    assert wallet_mod.wallet_from_seed(seed, expected).address == address


def test_wallet_from_seed_fails_closed() -> None:
    with pytest.raises(LabException) as exc:
        wallet_mod.wallet_from_seed(SECP, OTHER_ADDR, where="wallet.json")
    assert exc.value.error.code == "STATE_WALLET_KEY_MISMATCH"
    assert OTHER_ADDR in exc.value.error.message
    assert SECP not in exc.value.error.message + exc.value.error.hint  # no seed leaks
    assert exc.value.exit_code == 1


def _write(path: Path, seed: str, address: str) -> Path:
    path.write_text(json.dumps({"seed": seed, "address": address}), encoding="utf-8")
    return path


def test_load_wallet_keeps_a_4x_import_and_raises_on_a_mismatch(tmp_path: Path) -> None:
    legacy = wallet_mod.load_wallet(_write(tmp_path / "legacy.json", SECP, LEGACY_ADDR))
    assert legacy is not None and legacy.address == LEGACY_ADDR
    with pytest.raises(LabException):
        wallet_mod.load_wallet(_write(tmp_path / "bad.json", SECP, OTHER_ADDR))


@pytest.mark.asyncio
async def test_ensure_wallet_never_replaces_a_mismatched_wallet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller treats None as "no wallet" and makes a new one; the mismatch
    must raise instead, leaving the learner's file as it was."""
    import io

    from rich.console import Console

    import xrpl_lab.runtime as runtime
    from xrpl_lab.state import LabState
    from xrpl_lab.transport.dry_run import DryRunTransport

    path = _write(tmp_path / "wallet.json", SECP, OTHER_ADDR)
    before = path.read_bytes()
    monkeypatch.setattr(runtime, "save_state", lambda state: None)
    state = LabState(wallet_path=str(path), wallet_address=OTHER_ADDR)
    with pytest.raises(LabException):
        await runtime.ensure_wallet(state, DryRunTransport(), Console(file=io.StringIO()))
    assert path.read_bytes() == before


def test_signing_uses_the_bound_address_first() -> None:
    t = XRPLTestnetTransport()
    assert t._wallet(SECP).address == SECP_ADDR
    t.bind_wallet(SECP, LEGACY_ADDR)
    # A stale dry-run hint can't override a bound signer.
    assert t._wallet(SECP, "rIGNOREDHINT").address == LEGACY_ADDR
    assert XRPLTestnetTransport()._wallet(SECP, LEGACY_ADDR).address == LEGACY_ADDR
    with pytest.raises(LabException):
        XRPLTestnetTransport()._wallet(SECP, OTHER_ADDR)


@pytest.mark.asyncio
async def test_a_mismatched_seed_signs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    t = XRPLTestnetTransport()
    t.bind_wallet(SECP, OTHER_ADDR)
    submitted = []

    async def _no_submit(*args, **kwargs):
        submitted.append(args)
        raise AssertionError("signed and submitted with a mismatched key")

    async def _guard(*args, **kwargs):
        return None

    monkeypatch.setattr(t, "_submit_tx", _no_submit)
    monkeypatch.setattr(t, "_guard_write", _guard, raising=False)
    result = await t.submit_payment(wallet_seed=SECP, destination=SECP_ADDR, amount="1")
    assert result.success is False and result.validated is False
    assert "doesn't sign as its recorded address" in result.error
    assert submitted == []


@pytest.mark.asyncio
async def test_a_channel_claim_is_signed_by_the_account_key() -> None:
    """derive_keypair read the prefix while 4.x's Wallet.from_seed assumed
    ED25519; the claim now uses the same key as the transaction signer."""
    t = XRPLTestnetTransport()
    t.bind_wallet(SECP, LEGACY_ADDR)
    channel = "C" * 64
    sig = await t.authorize_payment_channel_claim(SECP, channel, "1")
    legacy = Wallet.from_seed(SECP, algorithm=CryptoAlgorithm.ED25519)
    from xrpl.core.binarycodec import encode_for_signing_claim

    blob = encode_for_signing_claim({"channel": channel, "amount": "1000000"})
    assert is_valid_message(bytes.fromhex(blob), bytes.fromhex(sig), legacy.public_key)
