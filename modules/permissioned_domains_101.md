---
id: permissioned_domains_101
title: "Permissioned Domains & Gated DEX (XLS-80/81): Compliant, Credential-Gated Trading"
track: identity
kb_source: permissioned-domain-set
summary: Create a credential-gated Permissioned Domain, place a permissioned offer that succeeds because you hold an accepted credential, watch an un-credentialed offer fail, and learn the full-replace revocation gotcha.
order: 52
time: 25-35 min
level: advanced
mode: testnet
requires:
  - credentials_101
produces:
  - txid
  - report
checks:
  - "Credential issued and accepted (composes with credentials_101)"
  - "Permissioned Domain created (DomainID produced)"
  - "Domain verified — accepts the listed credential"
  - "Credentialed account's permissioned offer placed (succeeds)"
  - "Permissioned offer verified resting on-ledger"
  - "Un-credentialed account's permissioned offer rejected (eligibility gate)"
  - "Non-owner modify rejected (owner-only)"
  - "Full-replace modify drops the credential (silent revocation gotcha)"
  - "Domain deleted — reserve freed (compensator)"
---

**Permissioned Domains (XLS-80, amendment `PermissionedDomains`)** went mainnet-live on
**2026-02-04**, and **Permissioned Offers (XLS-81, amendment `PermissionedDEX`)** on
**2026-02-18**. Together they are the XRPL's **compliance / gated-trading primitive**: a
domain gates access to a trading book by **credential**, and an offer tagged with that
domain's `DomainID` only rests if the placing account holds a credential the domain accepts.

This is how you build a **region-locked or regulated game economy**: vet players off-chain,
issue them signed credentials (the previous module), stand up one domain per access tier, and
run the marketplace as a **permissioned DEX**. Compliance is enforced by the **ledger** — when
a credential lapses or a region is removed, the player's offers stop matching, with no
server-side sweep.

This module **composes with Credentials 101** — you need an accepted credential to trade in a
domain. It runs on testnet, free and disposable.

## Step 1: Ensure your wallet is ready

Your wallet plays two roles here: the credential **ISSUER** and the domain **OWNER** (a
studio's compliance/ops account).

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Creating a domain costs a fee plus an owner reserve while it exists (free on testnet).

<!-- action: ensure_funded -->

## Step 3: Create the subject (player) wallet

The **SUBJECT** is the player being attested — and, once credentialed, the eligible trader.

<!-- action: create_subject_wallet -->

## Step 4: Issue the credential (provisional)

Reusing the XLS-70 primitive from the previous module: the issuer attests a `region-EU`
credential about the funded subject. It starts **provisional** — not valid until accepted.

<!-- action: create_credential credential_type="region-EU" -->

## Step 5: Subject accepts the credential

Only the subject can accept. Acceptance makes the credential **valid** and moves the owner
reserve to the subject. This is the credential the domain will require.

<!-- action: accept_credential -->

## Step 6: Create the Permissioned Domain

Now the owner runs **`PermissionedDomainSet`**. Because we **omit** `DomainID`, this **creates**
a new domain (the `DomainID` is derived from the owner's address + sequence). Its
`AcceptedCredentials` lists exactly one `{ Issuer, CredentialType }` — the `region-EU`
credential the subject just accepted.

Each unique `(Owner, Sequence)` yields a **distinct** `DomainID` — re-running create makes a
**NEW** domain, it does not idempotently return the old one, so track the `DomainID`
off-ledger after creation.

<!-- action: create_permissioned_domain -->

## Step 7: Verify the domain accepts the credential

Read the domain back. It should exist, be owned by you, and list the `region-EU` credential in
its accepted set — the check a gate runs before relying on a quote in it.

<!-- action: verify_domain -->

## Step 8: Place a permissioned offer (credentialed — succeeds)

The **credentialed subject** places an `OfferCreate` carrying the `DomainID`. Because it holds
a valid accepted credential the domain lists, the offer is **eligible** and rests on the
domain's permissioned book.

**CredentialIDs vs DomainID — the conflation to avoid:** eligibility to trade is proven by
holding an accepted credential, referenced via **`DomainID`** — **NOT** by `CredentialIDs`.
`CredentialIDs` is the **deposit-authorization** rail (gating inbound value); putting it on an
`OfferCreate` does **nothing** for permissioned trading. Different rails.

<!-- action: create_permissioned_offer pays_currency=LAB pays_value=50 gets_currency=XRP gets_value=10 -->

## Step 9: Verify the permissioned offer is resting

Confirm the offer landed on-ledger in the subject's active offers.

<!-- action: verify_permissioned_offer -->

## Step 10: Create an un-credentialed (outsider) wallet

A second funded account that holds **no** credential the domain accepts — to demonstrate the
eligibility gate.

<!-- action: create_uncredentialed_wallet -->

## Step 11: Un-credentialed permissioned offer (FAILS)

The outsider places the **same** permissioned offer scoped to the `DomainID`. Because it holds
no accepted credential, the offer is **rejected** before it can rest. The `DomainID` rail is
the gate.

<!-- action: create_permissioned_offer_uncredentialed pays_currency=LAB pays_value=50 gets_currency=XRP gets_value=10 -->

## Step 12: Non-owner tries to modify the domain (rejected)

Only the **original owner** may modify a domain. The outsider attempts a
`PermissionedDomainSet` against your `DomainID` and is rejected — plan domain-owner key custody
as carefully as an issuer's.

<!-- action: modify_domain_nonowner -->

## Step 13: The full-replace revocation gotcha

`AcceptedCredentials` is **REPLACED wholesale** on every `PermissionedDomainSet` — it is never
patched. Here the owner modifies the domain with a **decoy** credential and, in doing so,
**drops** the original `region-EU` entry. This **silently revokes** access for everyone holding
the dropped type, invalidating their open permissioned offers.

The lesson: to add or drop an eligible credential you resubmit the **full intended list** —
always read the current set first, or you'll strand your players.

<!-- action: modify_domain_drop_credential replacement_type="region-XX" -->

## Step 14: Verify the credential is no longer accepted

Read the domain back. It no longer lists `region-EU` — the previously-eligible subject is now
excluded. A resting permissioned offer can be invalidated post-placement exactly this way
(accepted-set change), alongside credential expiry/revocation and domain deletion.

<!-- action: verify_domain -->

## Step 15: Delete the domain (compensator, reclaim reserve)

`PermissionedDomainDelete` is the **named compensator**: it frees the owner-reserve slot the
domain consumed. A domain blocks owner-account deletion until it is removed — to sunset a
region, delete its domain.

<!-- action: delete_permissioned_domain -->

## Checkpoint: What you proved

You ran the full XLS-80/81 gated-trading lifecycle, composed on top of credentials:

1. **Credential issued + accepted** — the eligibility proof (XLS-70)
2. **PermissionedDomainSet (create)** — a credential-gated domain, DomainID tracked off-ledger
3. **Permissioned offer (credentialed)** — placed because the account holds an accepted credential
4. **Permissioned offer (un-credentialed)** — rejected by the eligibility gate
5. **Non-owner modify** — rejected (owner-only)
6. **Full-replace modify** — dropped the credential, silently revoking access
7. **PermissionedDomainDelete** — the compensator; freed the reserve

Key concepts to remember:

- **Two rails, don't conflate them** — `DomainID` gates **trading** (proven by a held accepted
  credential); `CredentialIDs` gates inbound **value** (deposit authorization). CredentialIDs on
  an offer does nothing for permissioned trading.
- **Full replace, not patch** — `AcceptedCredentials` is replaced wholesale on every set; a
  modify that forgets an entry silently revokes it. Read the current set, submit the full one.
- **DomainID is not idempotent** — each `(Owner, Sequence)` yields a distinct id; track it
  off-ledger, re-creating makes a new domain.
- **`tfHybrid`** — with a DomainID, a hybrid offer matches BOTH the domain book AND the open
  DEX; a plain permissioned offer matches only the domain book. Open offers (no DomainID) never
  match the permissioned-only book.
- **Ledger-enforced compliance** — a resting permissioned offer can be invalidated after
  placement by credential expiry/revocation, an accepted-set change, or domain deletion; surface
  "no longer eligible" in the player UI.
- **PermissionedDomainDelete is the compensator** — it frees the reserve and unblocks
  owner-account deletion.

Run `xrpl-lab proof-pack` when you're ready to export your work.
