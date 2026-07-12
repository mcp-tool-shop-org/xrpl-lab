"""Deposit Gate actions — DepositAuth + DepositPreauth (XLS-70 extension).

Completes the XLS-70 arc: ``credentials_101`` mints attestations,
``permissioned_domains_101`` gates a DEX book with them, and this module gates
**inbound value to a treasury** with them — the "regulated reward payout /
KYC-gated deposits" studio pattern.

Two mainnet-live, composable primitives:

  1. ``AccountSet asfDepositAuth`` (SetFlag 9 / ledger flag ``lsfDepositAuth``)
     — once set, the account REJECTS any unsolicited incoming Payment from a
     sender that is not preauthorized (``tecNO_PERMISSION``). It blocks
     Payments ONLY: pull-style transactions the recipient itself initiates
     (CheckCash, EscrowFinish, PaymentChannelClaim, OfferCreate) still work,
     and a sub-reserve account is exempted for a small XRP Payment so it can
     never get permanently stuck.
  2. ``DepositPreauth`` — whitelists exceptions to the gate. Exactly ONE of
     four fields: ``Authorize`` / ``Unauthorize`` (a single sender ADDRESS) or
     ``AuthorizeCredentials`` / ``UnauthorizeCredentials`` (1-8 ``{Issuer,
     CredentialType}`` pairs — the XLS-70 extension, mainnet-live 2025-09-04
     alongside Credentials). A sender satisfying the credential path attaches
     the credential's on-ledger id via ``Payment.CredentialIDs`` — a
     DIFFERENT rail from Permissioned Domains' ``DomainID`` (that gates
     TRADING; this gates DEPOSITS).

This module COMPOSES with ``credentials_101`` (reusing ``CredentialCreate`` /
``CredentialAccept`` unchanged) rather than re-implementing credential
issuance: the treasury plays both the protected account and the credential
ISSUER, exactly like ``permissioned_domains_101``'s dual owner/issuer role.
"""

from __future__ import annotations

from ..transport.base import SubmitResult, Transport


def _type_to_hex(credential_type: str) -> str:
    """Hex-encode a CredentialType string (mirrors ``actions.credentials``).

    Kept as a private per-module copy (matching ``credentials.py`` and
    ``permissioned_domains.py``) so this module's AuthorizeCredentials entries
    hex-encode identically to how the credential was minted. If the caller
    already passed hex (even length, all hex digits), it is used as-is.
    """
    s = (credential_type or "").strip()
    if s and len(s) % 2 == 0:
        try:
            bytes.fromhex(s)
            return s.upper()
        except ValueError:
            pass
    return s.encode("utf-8").hex().upper()


async def enable_deposit_auth(
    transport: Transport,
    wallet_seed: str,
    wallet_address: str = "",
    enable: bool = True,
) -> SubmitResult:
    """Enable (or clear) ``asfDepositAuth`` on the treasury (AccountSet).

    From this moment the treasury rejects any unsolicited incoming Payment
    (``tecNO_PERMISSION``) unless the sender is preauthorized — by address or
    by credential. ``enable=False`` clears the flag (the compensator).
    """
    return await transport.submit_deposit_auth(
        wallet_seed, enable=enable, wallet_address=wallet_address
    )


async def authorize_deposit_address(
    transport: Transport,
    wallet_seed: str,
    authorize: str,
    wallet_address: str = "",
) -> SubmitResult:
    """Preauthorize a single sender ADDRESS (DepositPreauth ``Authorize``).

    Fails ``temCANNOT_PREAUTH_SELF`` naming the treasury's own address,
    ``tecDUPLICATE`` if already preauthorized.
    """
    return await transport.submit_deposit_preauth(
        wallet_seed, authorize=authorize, wallet_address=wallet_address
    )


async def unauthorize_deposit_address(
    transport: Transport,
    wallet_seed: str,
    unauthorize: str,
    wallet_address: str = "",
) -> SubmitResult:
    """Revoke a single sender ADDRESS's preauthorization (DepositPreauth ``Unauthorize``).

    The named compensator for :func:`authorize_deposit_address` — frees the
    owner-reserve slot. Fails ``tecNO_ENTRY`` if no such preauthorization exists.
    """
    return await transport.submit_deposit_preauth(
        wallet_seed, unauthorize=unauthorize, wallet_address=wallet_address
    )


async def authorize_deposit_credential(
    transport: Transport,
    wallet_seed: str,
    issuer: str,
    credential_type: str,
    wallet_address: str = "",
) -> SubmitResult:
    """Preauthorize any sender holding a matching CREDENTIAL (``AuthorizeCredentials``).

    Any sender who attaches a currently valid (accepted, unexpired) credential
    of this ``credential_type`` from this ``issuer`` may now deposit — no
    per-account whitelist required. ``tecDUPLICATE`` if this exact pair is
    already authorized.
    """
    return await transport.submit_deposit_preauth(
        wallet_seed,
        authorize_credentials=[(issuer, _type_to_hex(credential_type))],
        wallet_address=wallet_address,
    )


async def unauthorize_deposit_credential(
    transport: Transport,
    wallet_seed: str,
    issuer: str,
    credential_type: str,
    wallet_address: str = "",
) -> SubmitResult:
    """Revoke a credential-based preauthorization (``UnauthorizeCredentials``).

    The named compensator for :func:`authorize_deposit_credential`. Fails
    ``tecNO_ENTRY`` if this exact pair was never authorized (or already revoked).
    """
    return await transport.submit_deposit_preauth(
        wallet_seed,
        unauthorize_credentials=[(issuer, _type_to_hex(credential_type))],
        wallet_address=wallet_address,
    )


async def send_gated_payment(
    transport: Transport,
    sender_seed: str,
    destination: str,
    amount: str,
    credential_ids: list[str] | None = None,
    memo: str = "",
    sender_address: str = "",
) -> SubmitResult:
    """Send a Payment into a (possibly DepositAuth-gated) destination.

    ``credential_ids`` (optional, 1-8 Credential ledger-object ids) is what a
    sender attaches to satisfy a credential-based preauthorization — omit it
    to rely on address-based preauthorization (or none at all, to hit the
    gate). Fails ``tecNO_PERMISSION`` when the destination has
    ``asfDepositAuth`` set and the sender is not preauthorized by either path
    (see :meth:`Transport.submit_payment` for the sub-reserve exemption).
    ``sender_address`` is a dry-run keying aid distinguishing this sender from
    others in the same session; the testnet transport derives it from the
    seed and ignores it.
    """
    return await transport.submit_payment(
        sender_seed, destination, amount, memo=memo, credential_ids=credential_ids,
        wallet_address=sender_address,
    )


async def get_credential_id(
    transport: Transport,
    subject: str,
    issuer: str,
    credential_type: str,
) -> str:
    """Resolve an accepted credential's on-ledger CredentialID for a Payment.

    Looks up the (subject, issuer, credential_type) Credential and returns its
    ledger-object id — the value ``send_gated_payment``'s ``credential_ids``
    expects. Returns ``""`` if no such credential exists (create + accept it
    first, e.g. via ``credentials_101``'s ``create_credential`` /
    ``accept_credential``).
    """
    cred = await transport.get_credential(subject, issuer, _type_to_hex(credential_type))
    return cred.credential_id if cred is not None else ""
