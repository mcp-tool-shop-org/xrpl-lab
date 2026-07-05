"""Credential actions — on-ledger KYC / age attestations (XLS-70).

Credentials (amendment ``Credentials``, mainnet-live 2025-09-04) let a trusted
ISSUER make an on-ledger attestation about a SUBJECT (e.g. KYC-passed,
over-21, region-eligible). The lifecycle is a TWO-PARTY handshake:

  1. ``CredentialCreate`` — the issuer mints a PROVISIONAL credential naming the
     subject and a ``CredentialType`` tag. It is NOT valid yet.
  2. ``CredentialAccept`` — ONLY the subject can accept it. Acceptance clears
     the provisional state (marks it valid) and transfers the owner reserve
     from the issuer to the subject ("you hold your own passport").
  3. ``CredentialDelete`` — either party can remove it, reclaiming the reserve
     (this is also the revocation mechanism).

``CredentialType`` is an opaque hex blob (1-64 bytes); this module hex-encodes
a human string like ``"over21"`` so the caller can pass plain text. The tuple
(subject, issuer, CredentialType) is UNIQUE per issuer — a second identical
credential fails ``tecDUPLICATE``. A ``URI`` (optional, points to an off-chain
verifiable credential) is IMMUTABLE after create.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import CredentialInfo, SubmitResult, Transport


def _type_to_hex(credential_type: str) -> str:
    """Hex-encode a CredentialType string (e.g. 'over21' -> '6F76657232 31').

    The ledger stores CredentialType as an arbitrary 1-64 byte hex blob; issuer
    and verifier agree on the plaintext tag out-of-band. If the caller already
    passed hex (even length, all hex digits), it is used as-is so a raw blob can
    still be supplied.
    """
    s = (credential_type or "").strip()
    if s and len(s) % 2 == 0:
        try:
            bytes.fromhex(s)
            return s.upper()
        except ValueError:
            pass
    return s.encode("utf-8").hex().upper()


async def create_credential(
    transport: Transport,
    issuer_seed: str,
    subject: str,
    credential_type: str,
    uri: str = "",
    expiration: int | None = None,
    issuer_address: str = "",
) -> SubmitResult:
    """Issuer attests a credential about *subject* (CredentialCreate).

    The credential is PROVISIONAL until the subject accepts it. Fails
    ``tecNO_TARGET`` when *subject* is unfunded, ``tecDUPLICATE`` when an
    identical (subject, issuer, type) credential already exists.
    """
    return await transport.submit_credential_create(
        issuer_seed,
        subject,
        _type_to_hex(credential_type),
        uri=uri,
        expiration=expiration,
        issuer_address=issuer_address,
    )


async def accept_credential(
    transport: Transport,
    subject_seed: str,
    issuer: str,
    credential_type: str,
    subject_address: str = "",
) -> SubmitResult:
    """Subject accepts a provisional credential, making it valid (CredentialAccept).

    ONLY the subject can accept. Acceptance moves the owner reserve from the
    issuer to the subject.
    """
    return await transport.submit_credential_accept(
        subject_seed,
        issuer,
        _type_to_hex(credential_type),
        subject_address=subject_address,
    )


async def delete_credential(
    transport: Transport,
    wallet_seed: str,
    issuer: str,
    subject: str,
    credential_type: str,
    wallet_address: str = "",
) -> SubmitResult:
    """Delete a credential, reclaiming its reserve (CredentialDelete).

    Either the issuer or the subject may delete it — this is the revocation
    path. ``wallet_seed`` signs the removal; ``issuer`` / ``subject`` identify
    the credential.
    """
    return await transport.submit_credential_delete(
        wallet_seed,
        issuer,
        subject,
        _type_to_hex(credential_type),
        wallet_address=wallet_address,
    )


@dataclass
class CredentialVerifyResult:
    """Result of verifying a credential is accepted/valid on-ledger."""

    found: bool
    credential: CredentialInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.found and len(self.failures) == 0


async def verify_credential(
    transport: Transport,
    subject: str,
    issuer: str,
    credential_type: str,
) -> CredentialVerifyResult:
    """Verify *subject* holds a VALID (accepted) credential from *issuer*.

    A provisional (created-but-not-yet-accepted) credential is reported as
    found-but-NOT-valid: the ``accepted`` flag must be set. This is the
    on-ledger check a gate would run before granting age/region-restricted
    content.
    """
    type_hex = _type_to_hex(credential_type)
    cred = await transport.get_credential(subject, issuer, type_hex)
    checks: list[str] = []
    failures: list[str] = []

    if cred is None:
        failures.append(
            "No credential found for this (subject, issuer, type) — "
            "the issuer never created it (or it was deleted)"
        )
        return CredentialVerifyResult(False, None, checks, failures)

    checks.append(f"Credential found: subject {cred.subject[:16]}...")
    checks.append(f"Issuer: {cred.issuer[:16]}...")
    checks.append(f"CredentialType: {cred.credential_type}")
    if cred.uri:
        checks.append(f"URI: {cred.uri}")

    if cred.accepted:
        checks.append("Accepted: the subject ran CredentialAccept — VALID")
    else:
        failures.append(
            "Credential is PROVISIONAL — the subject has not run "
            "CredentialAccept yet, so it is NOT valid for gating"
        )

    return CredentialVerifyResult(True, cred, checks, failures)
