"""DID actions — set a Decentralized Identifier and verify it on-ledger (XLS-40)."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import DIDInfo, SubmitResult, Transport


async def set_did(
    transport: Transport,
    wallet_seed: str,
    uri: str = "",
    data: str = "",
) -> SubmitResult:
    """Create or update the account's DID (DIDSet)."""
    return await transport.submit_did_set(wallet_seed, uri, data)


async def delete_did(transport: Transport, wallet_seed: str) -> SubmitResult:
    """Delete the account's DID, freeing its owner reserve (DIDDelete)."""
    return await transport.submit_did_delete(wallet_seed)


@dataclass
class DIDVerifyResult:
    """Result of verifying a DID on-ledger."""

    found: bool
    did: DIDInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_did(
    transport: Transport,
    address: str,
    expected_uri: str | None = None,
) -> DIDVerifyResult:
    """Verify the account has a DID (optionally matching a URI)."""
    did = await transport.get_did(address)
    checks: list[str] = []
    failures: list[str] = []
    if did is None:
        failures.append("No DID found for this account")
        return DIDVerifyResult(False, None, checks, failures)

    checks.append(f"DID found for {did.account[:16]}...")
    if did.uri:
        checks.append(f"URI: {did.uri}")
    if did.data:
        checks.append(f"Data: {did.data}")

    if expected_uri and did.uri != expected_uri:
        failures.append(f"URI mismatch: expected {expected_uri}, got {did.uri}")
    return DIDVerifyResult(True, did, checks, failures)


@dataclass
class DIDGoneResult:
    """Result of verifying a DID has been removed from the ledger."""

    gone: bool
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.gone and len(self.failures) == 0


async def verify_did_deleted(transport: Transport, address: str) -> DIDGoneResult:
    """Verify the account no longer has a DID (identity revoked, reserve freed)."""
    did = await transport.get_did(address)
    checks: list[str] = []
    failures: list[str] = []
    if did is not None:
        failures.append("DID is still on-ledger — DIDDelete did not remove it")
        return DIDGoneResult(False, checks, failures)
    checks.append("DID is gone — identity revoked, owner reserve freed")
    return DIDGoneResult(True, checks, failures)
