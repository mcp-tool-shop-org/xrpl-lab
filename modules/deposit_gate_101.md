---
id: deposit_gate_101
title: "Deposit Gate (DepositAuth + DepositPreauth): Credential-Gated Treasury Deposits"
track: identity
kb_source: deposit-auth-credential-preauth
summary: Enable Deposit Authorization on a treasury, preauthorize senders by address and by held credential (DepositPreauth + XLS-70 AuthorizeCredentials), and prove the gate blocks everyone else — the KYC-gated deposits pattern for a regulated reward payout.
order: 53
time: 30-40 min
level: advanced
mode: testnet
requires:
  - credentials_101
produces:
  - txid
  - report
checks:
  - "asfDepositAuth enabled on the treasury (AccountSet, txid produced)"
  - "A non-preauthorized sender's Payment rejected — tecNO_PERMISSION"
  - "Self-preauthorization rejected — temCANNOT_PREAUTH_SELF"
  - "Sender preauthorized BY ADDRESS (DepositPreauth Authorize, txid produced)"
  - "Duplicate address preauthorization rejected — tecDUPLICATE"
  - "The address-preauthorized sender's Payment lands (tesSUCCESS)"
  - "KYC credential issued and accepted for the player (composes with credentials_101)"
  - "Treasury preauthorizes BY CREDENTIAL (DepositPreauth AuthorizeCredentials)"
  - "The KYC'd player's Payment — carrying CredentialIDs — lands"
  - "A non-credentialed, non-preauthorized outsider's Payment stays blocked — tecNO_PERMISSION"
  - "Address preauthorization revoked (compensator, reserve freed)"
  - "Revoking a non-existent preauthorization rejected — tecNO_ENTRY"
---

**Deposit Authorization (`asfDepositAuth`)** has been mainnet-live since 2018:
flip this account flag and the ledger itself **rejects every unsolicited
incoming Payment** from a sender you have not cleared — no server-side sweep,
no "did we remember to check" bug, the network enforces it in preclaim.
**DepositPreauth** (also 2018) is how you clear senders — by address, one at a
time. And since **Credentials (XLS-70) went mainnet-live on 2025-09-04**,
DepositPreauth grew a second, scalable clearance path: **`AuthorizeCredentials`**.
Instead of whitelisting individual addresses, you authorize anyone holding a
specific credential from a trusted issuer. A sender then attaches that
credential's on-ledger id to a Payment via **`CredentialIDs`**, and the gate
opens for anyone who qualifies — no per-player allow-list required.

This is the **KYC-gated deposits pattern** — the last piece of the XLS-70 arc.
`credentials_101` minted an attestation; `permissioned_domains_101` gated a
**trading book** with it (via `DomainID`). This module gates **inbound value to
a treasury** with it. Keep this account separate from your **payout** (outbound
rewards) wallet in production — Deposit Authorization only ever governs what
comes IN; it has nothing to say about what the treasury sends out.

This runs on testnet — free and disposable. Your wallet plays **two roles**:
the protected **TREASURY** under Deposit Authorization, and the credential
**ISSUER** (the KYC/compliance authority) — the same dual-role pattern
`permissioned_domains_101` used for its owner+issuer.

## Step 1: Ensure your wallet is ready

Your wallet is the **TREASURY** — the account that will stop accepting money
from strangers — and doubles as the credential **ISSUER**.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Enabling Deposit Authorization and installing each preauthorization cost a fee
plus a small owner reserve (free on testnet).

<!-- action: ensure_funded -->

## Step 3: Enable Deposit Authorization

Flip the switch: `AccountSet` with `SetFlag: asfDepositAuth` (9). From this
transaction on, the treasury rejects any Payment from a sender you have not
cleared, failing **`tecNO_PERMISSION`** — enforced in preclaim, before the
payment ever touches a balance. Note what still works even with the flag on:
pull-style transactions the treasury itself initiates — `CheckCash`,
`EscrowFinish` (as destination), `PaymentChannelClaim`, `OfferCreate` — because
the recipient chose to receive those. Only unsolicited *pushes* are blocked.

<!-- action: enable_deposit_auth -->

## Step 4: Create the sender wallet

A fresh, funded wallet plays an ordinary player the treasury has not cleared
yet — a real third-party Payment, exactly like production traffic.

<!-- action: create_sender_wallet -->

## Step 5: Watch the sender's Payment get BLOCKED

With Deposit Authorization on and no preauthorization installed, the sender's
Payment is exactly the traffic the flag exists to stop. It fails
**`tecNO_PERMISSION`** — a **`tec`**-class result (the transaction claimed a fee
and a sequence but did nothing else), not a `tem` malformed rejection.

<!-- action: send_sender_payment_expect_blocked amount=10 -->

## Step 6: Try preauthorizing the treasury itself (guardrail)

Before clearing the real sender, learn a guardrail. `DepositPreauth`'s
`Authorize` field can never name the account's OWN address — preauthorizing
yourself is meaningless (you always trust your own transactions). The network
refuses with **`temCANNOT_PREAUTH_SELF`**, a `tem`-class result caught before it
ever reaches consensus.

<!-- action: preauthorize_self_expect_fail -->

## Step 7: Preauthorize the sender BY ADDRESS

Now clear the real sender. `DepositPreauth` with `Authorize` = the sender's
address whitelists exactly that one account — currency-agnostic,
one-directional (it does not let the treasury pay THEM back), and it costs one
owner-reserve increment as a ledger object.

<!-- action: authorize_sender_address -->

## Step 8: Try the same preauthorization again (guardrail)

The DepositPreauth object already exists for this (treasury, sender) pair —
resubmitting the identical `Authorize` fails **`tecDUPLICATE`**. There is
nothing new to add.

<!-- action: authorize_sender_address_duplicate -->

## Step 9: The preauthorized sender's Payment lands

Same sender, same amount — the only thing that changed is the DepositPreauth
object now standing between them and `tecNO_PERMISSION`. The Payment validates
**`tesSUCCESS`**.

<!-- action: send_sender_payment amount=10 -->

## Step 10: Create the KYC'd player (subject) wallet

Address-by-address clearance does not scale to a real player base — every new
depositor needs its own DepositPreauth object and its own owner-reserve
increment. The credential path is the answer. A fresh SUBJECT wallet plays the
player about to get KYC'd.

<!-- action: create_subject_wallet -->

## Step 11: Issuer mints a KYC credential for the player

Reusing the XLS-70 primitive unchanged from `credentials_101`: the issuer
(your wallet, wearing its second hat) attests a `kyc-deposit` credential about
the funded subject. It starts **PROVISIONAL** — not valid until the subject
accepts it.

<!-- action: create_credential credential_type="kyc-deposit" -->

## Step 12: Player accepts the credential

Only the subject can accept. Acceptance clears the provisional state, moves
the owner reserve to the subject, and makes this the credential the deposit
gate will actually check.

<!-- action: accept_credential -->

## Step 13: Treasury preauthorizes BY CREDENTIAL

Now the scalable path: `DepositPreauth` with `AuthorizeCredentials` =
`[{Issuer, CredentialType}]`. This does **not** name any specific sender
address — it authorizes ANYONE who can present a currently valid (accepted,
unexpired) `kyc-deposit` credential from this issuer. Onboard a thousand
players and you install this ONE rule, not a thousand `Authorize` objects.

<!-- action: authorize_kyc_credential -->

## Step 14: The KYC'd player attaches CredentialIDs and pays

The player's Payment carries **`CredentialIDs`** — the on-ledger id(s) of the
Credential object(s) it holds. The gate checks: is the attached credential
CURRENTLY valid (accepted, unexpired), and does its (issuer, CredentialType)
match something the treasury authorized? Both are true here, so the Payment
lands.

**CredentialIDs vs DomainID — the conflation to avoid:** `permissioned_domains_101`'s
`DomainID` rail proves eligibility to **trade**; `CredentialIDs` proves
eligibility to **deposit**. Different fields, on different transactions,
checked by different rules — neither substitutes for the other.

<!-- action: send_kyc_payment amount=10 -->

## Step 15: Create an outsider wallet

A third funded wallet: no address preauthorization, no credential the
treasury accepts. It exists to prove the credential-based gate does not
quietly become a bypass for everyone.

<!-- action: create_uncredentialed_wallet -->

## Step 16: The outsider stays BLOCKED

Same treasury, same `asfDepositAuth`, same two live preauthorization
policies — and this account qualifies for neither. Its Payment fails
**`tecNO_PERMISSION`**, exactly like the very first sender did before you
cleared it. Two independent policies, one shared gate.

<!-- action: send_outsider_payment_expect_blocked amount=10 -->

## Step 17: Revoke the sender's address preauthorization (compensator)

Wind the address-based clearance back down: `DepositPreauth` with
`Unauthorize` = the sender's address removes that DepositPreauth object and
frees the owner reserve it held. The credential-based clearance from Step 13
is untouched — the two paths are independent, each with its own revoke.

<!-- action: unauthorize_sender_address -->

## Step 18: Revoke it again (guardrail)

There is nothing left to revoke — the object from Step 17 is already gone.
The network refuses with **`tecNO_ENTRY`**, the same "nothing there" result
`credentials_101`'s `CredentialDelete` and `permissioned_domains_101`'s
domain-delete both teach: revoking something that does not exist is a named
failure, not a silent no-op.

<!-- action: unauthorize_sender_address_duplicate -->

## Checkpoint: What you proved

You ran the full DepositAuth + DepositPreauth gate, both clearance paths, and
their guardrails, with receipts for every claim:

1. **`asfDepositAuth` enabled** — the treasury now rejects unsolicited Payments
2. **`tecNO_PERMISSION`** — an uncleared sender's Payment is blocked
3. **`temCANNOT_PREAUTH_SELF`** — an account can never preauthorize itself
4. **DepositPreauth `Authorize`** — cleared one sender by address
5. **`tecDUPLICATE`** — re-authorizing the same address is rejected
6. **Address-cleared Payment lands** — `tesSUCCESS`
7. **Credential issued + accepted** — the XLS-70 handshake, reused unchanged
8. **DepositPreauth `AuthorizeCredentials`** — cleared ANY holder of a
   `kyc-deposit` credential from this issuer, no per-address whitelist
9. **`CredentialIDs`-carrying Payment lands** — the credential path works
10. **Outsider stays blocked** — neither policy covers it; `tecNO_PERMISSION` again
11. **`Unauthorize`** — the compensator; reserve freed
12. **`tecNO_ENTRY`** — revoking a non-existent preauthorization fails honestly

Key concepts to remember:

- **DepositAuth blocks Payments only** — pull-style transactions the recipient
  itself initiates (`CheckCash`, `EscrowFinish`, `PaymentChannelClaim`,
  `OfferCreate`) still work. A sub-reserve account is exempted for a small XRP
  Payment (at most the base reserve) so it can never get permanently stuck.
- **Two clearance paths, independent revokes.** Address-based (`Authorize`/
  `Unauthorize`) suits a small, known set of senders; credential-based
  (`AuthorizeCredentials`/`UnauthorizeCredentials`) is the scalable KYC gate —
  one rule admits every qualifying holder. Revoking one never touches the other.
- **`CredentialIDs` (deposit) vs `DomainID` (trading)** — two separate rails
  built on the same XLS-70 credentials. Putting a `DomainID` on a Payment or
  `CredentialIDs` on an `OfferCreate` does nothing.
- **A credential must be currently valid to satisfy the gate** — accepted
  (not merely provisional) AND unexpired. Expiry or revocation on the issuer's
  side can turn a previously-admitted depositor into a blocked one with no
  change on the treasury's end.
- **Keep payout and treasury separate.** DepositAuth only governs *inbound*
  value; a studio's outbound reward-payout wallet is a different account with
  a different threat model.
- **Named compensators, both paths.** `Unauthorize` / `UnauthorizeCredentials`
  free the owner reserve a preauthorization held; revoking something already
  gone is `tecNO_ENTRY`, not a no-op.

Run `xrpl-lab proof-pack` when you're ready to export your work.
