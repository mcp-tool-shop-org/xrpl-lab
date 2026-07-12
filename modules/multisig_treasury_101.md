---
id: multisig_treasury_101
title: "Multisig Treasury (SignerListSet): N-of-M Control of the Studio Wallet"
track: foundations
kb_source: multisign-signerlistset
summary: Put N-of-M signer control on your treasury with a native SignerList — install a 2-of-3 quorum, move funds with a multi-signed payment the treasury key never touches, and watch the ledger refuse a below-quorum attempt (tefBAD_QUORUM).
order: 5
time: 25-30 min
level: advanced
mode: testnet
requires:
  - receipt_literacy
produces:
  - txid
  - report
checks:
  - "A 2-of-3 signer list installed on the treasury (SignerListSet — quorum 2, three weighted signers, txid produced)"
  - "The signer list read back from the ledger — quorum and roster match what was installed"
  - "A multi-signed Payment meeting quorum validated (two co-signatures, combined weight 2 >= quorum 2; fee scaled per-signature; txid produced)"
  - "A below-quorum multi-signed payment was rejected with tefBAD_QUORUM (the failure a learner hits)"
  - "Signer list deleted (SignerQuorum=0 with SignerEntries omitted) and verified gone — owner reserve freed"
---

A game studio's hot wallet is one leaked laptop away from an empty treasury —
as long as a **single key** can move funds, every payout run, every contractor
with deploy access, and every phishing email is a full-treasury risk. XRPL's
answer is native and **mainnet-live** (no amendment to wait for):
**multi-signing**. A **`SignerListSet`** transaction attaches a **SignerList**
to your account — up to 32 signers, each with a **`SignerWeight`**, plus a
**`SignerQuorum`** — and from then on transactions can be authorized by any
combination of listed keyholders whose **combined weight meets the quorum**.
No single person can move the money; N-of-M must agree.

The mechanics you will exercise:

1. **The list is the policy.** `SignerEntries` holds 1-32 `(Account,
   SignerWeight)` pairs — no duplicates, and the account **cannot list
   itself** (`temBAD_SIGNER`). The quorum can never exceed the sum of the
   weights (`temBAD_QUORUM`) — otherwise no combination of signatures could
   ever authorize anything. There is one signer list per account
   (`SignerListID` is currently always 0), and it holds ~0.2 XRP of owner
   reserve while it exists.
2. **A multi-signed transaction looks different.** It carries a `Signers[]`
   array — one `{Account, SigningPubKey, TxnSignature}` per co-signer — and
   the transaction's own top-level `SigningPubKey` is **empty ("")**. That
   emptiness is how the ledger knows to check the signer list instead of the
   account's own key. The fee scales too: **base_fee × (1 + number of
   signatures)** — every co-signature is paid for.
3. **Quorum is arithmetic, not a vote count.** The ledger sums the weights of
   the valid co-signatures. Individually-valid signatures whose combined
   weight falls short fail **`tefBAD_QUORUM`** — you will hit this on purpose.

This lesson runs on testnet — free and disposable. Your wallet plays the
**treasury**; three fresh keyholder wallets play your co-signers.

## Step 1: Ensure your treasury wallet is ready

Your wallet is the **treasury** — the account that will surrender single-key
control.

<!-- action: ensure_wallet -->

## Step 2: Fund the treasury

The signer list costs a small owner reserve (~0.2 XRP), the multisig payments
below move real (testnet) XRP, and each multi-signed submission pays the
scaled fee. Free on testnet.

<!-- action: ensure_funded -->

## Step 3: Create three keyholder wallets

Three fresh wallets play your keyholders — think CEO, CFO, lead engineer.
They are deliberately **not funded**: a signer entry does not need to be a
funded on-ledger account. The ledger verifies each co-signature against the
key that derives the listed address, so cold keys that have never touched the
ledger work fine — keyholder onboarding is free.

<!-- action: create_signer_wallets count=3 -->

## Step 4: Install the 2-of-3 signer list

The treasury submits **`SignerListSet`**: quorum **2**, three signers at
weight **1** each. Any two keyholders can authorize; no one can act alone.
(Weights let you express richer policies — give a lead weight 2 and they
could act alone while juniors at weight 1 must pair up. This lesson keeps
everyone equal.)

The install itself is a normal single-signed transaction — the treasury key
still controls the account today and is *adding* the delegation. Note what
the network would refuse here: listing the treasury itself
(`temBAD_SIGNER`), a duplicate signer (`temBAD_SIGNER`), a zero weight
(`temBAD_WEIGHT`), or a quorum above the summed weights (`temBAD_QUORUM`).

<!-- action: set_signer_list quorum=2 weights=1,1,1 -->

## Step 5: Read the signer list back from the ledger

Trust the ledger, not your notes. Fetch the account's SignerList object and
confirm the quorum and the full roster — accounts *and* weights — match what
you installed. Every `SignerListSet` **replaces the whole list**, so this
read-back is exactly how you audit a rotation later.

<!-- action: verify_signer_list -->

## Step 6: Move funds with a multi-signed payment

Payroll time. Two keyholders co-sign a 10 XRP payment — combined weight 2
meets the quorum — and the treasury's own key **never signs**. Under the
hood each signer signs the *same* prepared transaction; the signatures are
merged into the `Signers[]` array, the transaction's own `SigningPubKey`
stays empty, and the fee is base × (1 + 2 signatures).

The payout lands on keyholder 1's (so far unfunded) wallet: on XRPL, a
payment at or above the base reserve **creates** the destination account —
the treasury's first payout doubles as account activation.

<!-- action: send_multisig_payment amount=10 signer_count=2 -->

## Step 7: Verify the payment on-ledger

Pull the transaction by its hash and confirm it validated with `tesSUCCESS`.
This is the treasury's receipt: a payment authorized by quorum arithmetic,
not by the account's master key.

<!-- action: verify_tx -->

## Step 8: See the failure — one signature is not enough

Learn by hitting the wall. One keyholder tries to move funds alone: the
signature is **individually valid**, but combined weight 1 < quorum 2 and
the network refuses with **`tefBAD_QUORUM`**. Read the code carefully — it is
not `tefBAD_SIGNATURE` (a signer who isn't on the list at all); it is the
*combination* that failed. This distinction is your first diagnostic when a
real multisig payout bounces.

<!-- action: send_multisig_payment_expect_fail signer_count=1 -->

## Step 9: Delete the signer list

Wind the delegation back down. The delete shape is exact: **`SignerQuorum=0`
AND `SignerEntries` omitted** — doing only one of the two is
`temMALFORMED`. The owner reserve the list held is freed.

One safety rule to carry to mainnet: an account whose master key is disabled
and that has no regular key **cannot** delete its signer list — the network
refuses with `tecNO_ALTERNATIVE_KEY` rather than let an account sign away
its last key. (This treasury never disabled its master key, so the delete is
safe. On a production treasury you *would* disable the master key after
installing the list — that is what makes the quorum binding.)

<!-- action: delete_signer_list -->

## Step 10: Verify the list is gone

Read the account's objects one more time: no SignerList. The treasury is
back to single-key control and the quorum rules no longer apply.

<!-- action: verify_signer_list_deleted -->

## Checkpoint: What you proved

You took a treasury from single-key risk to N-of-M control and back, with
receipts for every claim:

1. **Installed a 2-of-3 signer list** — `SignerListSet` with a quorum and
   weighted entries, and read it back from the ledger
2. **Moved funds by quorum** — a multi-signed Payment with two co-signatures
   validated while the treasury key never signed
3. **Hit the quorum wall** — a single valid signature below quorum failed
   `tefBAD_QUORUM`, and you can tell that apart from `tefBAD_SIGNATURE`
4. **Deleted the list correctly** — `SignerQuorum=0` with `SignerEntries`
   omitted, reserve freed, deletion verified on-ledger

Key concepts to remember:

- **The quorum is weight arithmetic** — the ledger sums the `SignerWeight`
  of the valid co-signatures and compares against `SignerQuorum`. Below
  quorum → `tefBAD_QUORUM`, even when every signature is valid.
- **A multi-signed tx carries `Signers[]` and an empty `SigningPubKey`** —
  and pays base_fee × (1 + number of signatures). Budget for it in payout
  tooling.
- **The list is replaced wholesale, never patched** — every `SignerListSet`
  ships the FULL roster; a rotation that forgets an entry silently revokes
  that keyholder. Always read the list back after a change.
- **Signers don't need funded accounts** — entries are verified by key, so
  cold keyholders cost nothing to onboard. The account can never list
  itself, 1-32 entries, one list per account (`SignerListID` 0), ~0.2 XRP
  owner reserve while it exists.
- **Delete = quorum 0 + entries omitted** — half a delete is `temMALFORMED`,
  and a treasury with a disabled master key and no regular key cannot delete
  its list at all (`tecNO_ALTERNATIVE_KEY`).

Run `xrpl-lab proof-pack` when you're ready to export your work.
