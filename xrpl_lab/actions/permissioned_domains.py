"""Permissioned Domains & Gated DEX actions (XLS-80 / XLS-81).

FC-004 — the compliance / gated-trading primitive that COMPOSES with credentials
(XLS-70). The end-to-end recipe: an issuer creates and a subject accepts a
credential (the XLS-70 primitives reused from ``credentials.py``); a domain owner
creates a **Permissioned Domain** (``PermissionedDomainSet``, XLS-80) listing that
``{Issuer, CredentialType}``; the credentialed account then places a
**permissioned offer** (``OfferCreate`` + ``DomainID``, XLS-81) which succeeds
because it holds an accepted credential — while an un-credentialed account's
permissioned offer FAILS.

Two facts this module makes concrete and teaches:

* **Full replace.** ``AcceptedCredentials`` is REPLACED wholesale on every
  ``PermissionedDomainSet`` (never patched): a 'modify' that forgets to re-list
  an existing entry SILENTLY REVOKES access for everyone holding the dropped
  credential type — invalidating their open permissioned offers. Always read the
  current set and submit the intended FULL set.
* **Two different rails.** Eligibility to TRADE in a domain is proven by holding
  an accepted credential the domain lists, referenced via ``DomainID`` on the
  offer — NOT by ``CredentialIDs`` (the deposit-authorization rail). Putting
  CredentialIDs on an OfferCreate does nothing for permissioned trading.

``PermissionedDomainDelete`` is the named compensator: it frees the owner-reserve
slot the domain consumed (a domain blocks owner-account deletion until deleted).
Each unique (Owner, Sequence) yields a DISTINCT ``DomainID`` — re-running create
makes a NEW domain, it does not idempotently return the old one; track the
``DomainID`` off-ledger after creation.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import (
    OfferInfo,
    PermissionedDomainInfo,
    SubmitResult,
    Transport,
)


def _type_to_hex(credential_type: str) -> str:
    """Hex-encode a CredentialType string (e.g. 'over21' -> '6F7665723231').

    Mirrors ``actions.credentials._type_to_hex`` so a domain's accepted-set
    entries match the hex the credential primitives store on-ledger. If the
    caller already passed hex (even length, all hex digits), it is used as-is.
    """
    s = (credential_type or "").strip()
    if s and len(s) % 2 == 0:
        try:
            bytes.fromhex(s)
            return s.upper()
        except ValueError:
            pass
    return s.encode("utf-8").hex().upper()


def _accepted_pairs(
    accepted: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Normalize an accepted-credentials list to (issuer, type_hex) pairs.

    The plaintext ``CredentialType`` tag is hex-encoded so a caller can pass
    ``[(issuer, "over21")]`` and have it match the on-ledger hex form.
    """
    return [(issuer, _type_to_hex(ctype)) for issuer, ctype in accepted]


async def set_permissioned_domain(
    transport: Transport,
    owner_seed: str,
    accepted_credentials: list[tuple[str, str]],
    domain_id: str = "",
    owner_address: str = "",
) -> SubmitResult:
    """Create or modify a Permissioned Domain (PermissionedDomainSet, XLS-80).

    Omit ``domain_id`` to CREATE a new domain (a fresh DomainID is derived from
    Owner + Sequence and returned on ``SubmitResult.domain_id``); pass it to
    MODIFY that existing domain (owner-only). ``accepted_credentials`` is the FULL
    intended accepted set — it REPLACES the prior list wholesale.
    """
    return await transport.submit_permissioned_domain_set(
        owner_seed,
        _accepted_pairs(accepted_credentials),
        domain_id=domain_id,
        owner_address=owner_address,
    )


async def delete_permissioned_domain(
    transport: Transport,
    owner_seed: str,
    domain_id: str,
    owner_address: str = "",
) -> SubmitResult:
    """Delete a Permissioned Domain, freeing its reserve (PermissionedDomainDelete).

    The named compensator for a create: frees the owner-reserve slot. Only the
    owner may delete; the domain blocks owner-account deletion until removed.
    """
    return await transport.submit_permissioned_domain_delete(
        owner_seed, domain_id, owner_address=owner_address
    )


async def create_permissioned_offer(
    transport: Transport,
    wallet_seed: str,
    taker_pays_currency: str,
    taker_pays_value: str,
    taker_pays_issuer: str,
    taker_gets_currency: str,
    taker_gets_value: str,
    taker_gets_issuer: str,
    domain_id: str,
    hybrid: bool = False,
    wallet_address: str = "",
) -> SubmitResult:
    """Place a permissioned offer scoped to a domain (OfferCreate + DomainID, XLS-81).

    The placing account must hold a valid credential the domain accepts, or the
    offer fails. ``hybrid=True`` sets ``tfHybrid`` so the offer also matches the
    open DEX; ``hybrid=False`` (plain permissioned) matches ONLY the domain book.
    """
    return await transport.submit_permissioned_offer_create(
        wallet_seed=wallet_seed,
        taker_pays_currency=taker_pays_currency,
        taker_pays_value=taker_pays_value,
        taker_pays_issuer=taker_pays_issuer,
        taker_gets_currency=taker_gets_currency,
        taker_gets_value=taker_gets_value,
        taker_gets_issuer=taker_gets_issuer,
        domain_id=domain_id,
        hybrid=hybrid,
        wallet_address=wallet_address,
    )


async def get_permissioned_domains(
    transport: Transport,
    owner: str,
) -> list[PermissionedDomainInfo]:
    """List Permissioned Domains owned by an account."""
    return await transport.get_permissioned_domains(owner)


@dataclass
class DomainVerifyResult:
    """Result of verifying a Permissioned Domain on-ledger."""

    found: bool
    domain: PermissionedDomainInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return self.found and len(self.failures) == 0


async def verify_domain(
    transport: Transport,
    owner: str,
    domain_id: str,
    expect_issuer: str = "",
    expect_credential_type: str = "",
) -> DomainVerifyResult:
    """Verify a Permissioned Domain exists and lists the expected credential.

    Reads the owner's domains, matches on ``domain_id``, and (when given)
    asserts the domain's accepted set includes ``(expect_issuer,
    expect_credential_type)`` — the check a gate would run to confirm a domain
    still admits a given credential BEFORE relying on a quote in it.
    """
    checks: list[str] = []
    failures: list[str] = []

    domains = await transport.get_permissioned_domains(owner)
    match: PermissionedDomainInfo | None = None
    for d in domains:
        if d.domain_id == domain_id:
            match = d
            break

    if match is None:
        failures.append(
            f"No Permissioned Domain {domain_id[:16]}... owned by "
            f"{owner[:16]}... — it was never created (or was deleted)"
        )
        return DomainVerifyResult(False, None, checks, failures)

    checks.append(f"Domain found: {domain_id[:16]}...")
    checks.append(f"Owner: {match.owner[:16]}...")
    checks.append(
        f"Accepted credentials: {len(match.accepted_credentials)} "
        f"entr{'y' if len(match.accepted_credentials) == 1 else 'ies'}"
    )

    if expect_issuer or expect_credential_type:
        want = (expect_issuer, _type_to_hex(expect_credential_type))
        listed = [
            (iss, ctype) for iss, ctype in match.accepted_credentials
        ]
        if want in listed:
            checks.append(
                f"Accepts credential {{{expect_issuer[:12]}..., "
                f"{expect_credential_type}}} — eligible holders can trade"
            )
        else:
            failures.append(
                f"Domain does NOT accept {{{expect_issuer[:12]}..., "
                f"{expect_credential_type}}} — a full-replace modify may have "
                f"dropped it, silently revoking access for its holders"
            )

    return DomainVerifyResult(True, match, checks, failures)


@dataclass
class PermissionedOfferVerifyResult:
    """Result of verifying a permissioned offer's placement outcome."""

    placed: bool
    offer: OfferInfo | None
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


async def verify_permissioned_offer(
    transport: Transport,
    address: str,
    offer_sequence: int,
    expect_placed: bool = True,
) -> PermissionedOfferVerifyResult:
    """Verify a permissioned offer landed (or, for the un-credentialed case, did NOT).

    ``expect_placed=True`` asserts the offer with ``offer_sequence`` is resting in
    the account's active offers (the credentialed placement succeeded).
    ``expect_placed=False`` asserts the account has NO such resting offer (the
    un-credentialed placement was rejected before it could rest) — the eligibility
    gate in action.
    """
    checks: list[str] = []
    failures: list[str] = []

    offers = await transport.get_account_offers(address)
    match: OfferInfo | None = None
    for o in offers:
        if o.sequence == offer_sequence:
            match = o
            break

    if expect_placed:
        if match is None:
            failures.append(
                f"Permissioned offer seq {offer_sequence} is not resting — "
                f"expected it to be placed (the account holds an accepted credential)"
            )
            return PermissionedOfferVerifyResult(False, None, checks, failures)
        checks.append(f"Permissioned offer resting: seq {offer_sequence}")
        checks.append(f"Taker pays: {match.taker_pays}")
        checks.append(f"Taker gets: {match.taker_gets}")
        return PermissionedOfferVerifyResult(True, match, checks, failures)

    # expect_placed is False: the offer must be ABSENT (rejected).
    if match is not None:
        failures.append(
            f"Permissioned offer seq {offer_sequence} is resting — expected it "
            f"to be REJECTED (the account does not hold an accepted credential)"
        )
        return PermissionedOfferVerifyResult(True, match, checks, failures)

    checks.append(
        f"Un-credentialed permissioned offer confirmed absent (seq "
        f"{offer_sequence}) — the domain's eligibility gate rejected it"
    )
    return PermissionedOfferVerifyResult(False, None, checks, failures)
