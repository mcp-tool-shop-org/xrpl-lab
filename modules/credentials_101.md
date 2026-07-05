---
id: credentials_101
title: "Credentials 101 (XLS-70): On-Ledger KYC & Age Attestations"
track: identity
kb_source: credential-transactions
summary: Issue an on-ledger KYC/age attestation, have the subject accept it, and verify it's valid — the two-party credential handshake.
order: 51
time: 15-20 min
level: intermediate
mode: testnet
requires:
  - did_101
produces:
  - txid
  - report
checks:
  - "Unfunded subject rejected (tecNO_TARGET)"
  - "Credential created (provisional, txid produced)"
  - "Duplicate rejected (tecDUPLICATE)"
  - "Only the subject can accept (issuer accept rejected)"
  - "Subject accepted — reserve moved to subject (txid produced)"
  - "Credential verified VALID on-ledger (accepted)"
  - "Credential deleted — reserve reclaimed (txid produced)"
---

**Credentials (XLS-70, amendment `Credentials`)** went mainnet-live on **2025-09-04**.
A credential is an **on-ledger attestation an ISSUER makes about a SUBJECT** — KYC-passed,
over-21, region-eligible. Only *proof* of the attestation lives on-chain; the personal data
stays off-ledger (paired with the **DID** you anchored in the previous module). This is the
foundation for age-gating content, region-locking, and compliant real-money cash-out in a game.

The key idea is a **two-party handshake**: the issuer *creates* a credential (it's
**provisional** and not yet valid), and the subject must *accept* it. That "you hold your own
passport" design is what makes a credential trustworthy — the subject consented, and the
attestation lives under the subject's control.

This runs on testnet — free and disposable.

## Step 1: Ensure your wallet is ready

Your wallet is the **ISSUER** — the trusted party (a KYC/age-verification partner, or the
studio itself) making the attestation.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Creating a credential costs a fee plus an owner reserve while it's provisional (free on testnet).

<!-- action: ensure_funded -->

## Step 3: Create the subject (player) wallet

A credential needs a second account — the **SUBJECT** being attested. We create and fund it so
it's a real target on-ledger.

<!-- action: create_subject_wallet -->

## Step 4: Try attesting an UNFUNDED subject (tecNO_TARGET)

Before the happy path, learn the guardrail. The `Subject` of a `CredentialCreate` must be a
**funded** account — you can't attest an account that doesn't exist yet. Attesting an unfunded
address fails **`tecNO_TARGET`**.

<!-- action: create_credential_unfunded credential_type="over21" -->

## Step 5: Create the credential (provisional)

Now attest the funded subject. `CredentialCreate` sets `Account` = you (issuer), `Subject` =
the player, and `CredentialType` = an opaque tag (we use `over21`, hex-encoded for you). You can
optionally attach a `URI` pointing to an off-chain verifiable credential — but note it is
**immutable** after create (delete + re-issue to change it). The credential is now **provisional**:
created, but NOT valid until the subject accepts it.

<!-- action: create_credential credential_type="over21" uri="ipfs://bafy-example/over21-vc.json" -->

## Step 6: Try to create a duplicate (tecDUPLICATE)

The tuple **(subject, issuer, CredentialType)** is unique per issuer — you can't stack two
identical live credentials. Re-attesting the same one fails **`tecDUPLICATE`**.

<!-- action: create_credential_duplicate credential_type="over21" -->

## Step 7: Watch the issuer FAIL to accept it

`CredentialAccept` can be submitted by **only the subject**. Here the issuer (you) tries to
accept its own credential — and the ledger rejects it. This is the consent rule: the issuer
cannot force a credential to become valid; the subject must opt in.

<!-- action: accept_credential_wrong_party -->

## Step 8: Subject accepts the credential

Now the subject runs `CredentialAccept` (naming the `Issuer` and matching `CredentialType`).
This clears the provisional state, marks the credential **valid**, and **transfers the owner
reserve from the issuer to the subject** — the subject now pays the reserve and controls the
attestation.

<!-- action: accept_credential -->

## Step 9: Verify the credential is VALID on-ledger

Read the credential back. It must show **accepted** — a gate checking "is this player over 21?"
would pass only now, never while the credential was provisional.

<!-- action: verify_credential -->

## Step 10: Delete the credential (revoke, reclaim reserve)

Either party can run `CredentialDelete` — this is the **revocation** mechanism and it frees the
owner reserve. The subject deletes it here to reclaim the reserve it started paying at accept.

<!-- action: delete_credential -->

## Checkpoint: What you proved

You ran the full XLS-70 credential lifecycle — the two-party handshake, both guardrails, and revocation:

1. **CredentialCreate** — the issuer attested a subject; the credential started **provisional**
2. **tecNO_TARGET** — you can't attest an unfunded subject
3. **tecDUPLICATE** — (subject, issuer, type) is unique per issuer
4. **Subject-only accept** — the issuer cannot accept; only the subject can
5. **CredentialAccept** — made it valid and moved the owner reserve to the subject
6. **Verified** — the credential reads back as accepted/valid on-ledger
7. **CredentialDelete** — revoked it and reclaimed the reserve

Key concepts to remember:

- **Two-party by design** — a credential is provisional until the subject accepts; acceptance is consent, and it moves the reserve to the subject ("you hold your own passport").
- **CredentialType is opaque** — an arbitrary hex tag (1-64 bytes); issuer and verifier agree on its meaning (`kyc`, `over21`, `region-US`) out-of-band.
- **URI is immutable** — the off-chain-VC pointer can't change after create; delete and re-issue to update it.
- **PII stays off-ledger** — only the attestation *proof* is on-chain. Pairs with **DIDs** (identity anchor) and gates value flows via **DepositPreauth / Permissioned Domains**.
- **Delete = revoke** — either party can remove a credential to revoke it and free the reserve.

Run `xrpl-lab proof-pack` when you're ready to export your work.
