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
