---
id: token_escrow_101
title: "Token Escrow (XLS-85): Locking IOUs, Not Just XRP"
track: payments
kb_source: token-escrow-xls85
summary: Lock an issued token (IOU) in a time-based escrow — the XLS-85 upgrade that lets you escrow your own currency, not just XRP, with a mandatory CancelAfter and issuer opt-in.
order: 42
time: 20-25 min
level: intermediate
mode: testnet
requires:
  - trust_lines_101
  - escrow_101
produces:
  - txid
  - report
checks:
  - "Issuer opted in to token escrow (AccountSet asfAllowTrustLineLocking)"
  - "A token escrow WITHOUT opt-in was rejected with tecNO_PERMISSION (the failure a learner hits)"
  - "Holder escrowed N of the issued token to a recipient with a mandatory CancelAfter (txid produced)"
  - "Recipient finished the escrow (EscrowFinish, txid produced)"
  - "The escrowed IOU moved: the recipient's issued balance increased by the escrowed amount"
---

**Escrow 101** locked *XRP*. But until 2026, that was the only thing you could
escrow — you could not time-lock your own game currency, a stablecoin, or any
issued token. The **TokenEscrow** amendment (**XLS-85**) changed that. It went
**mainnet-live on 2026-02-12**, extending the native escrow object so the locked
`Amount` can be an **issued currency (IOU)** or a Multi-Purpose Token (MPT),
not just XRP. This is what makes deferred value in your *own* token real: vesting
schedules, conditional grants, and escrow-secured trades no longer have to be
priced in XRP.

The escrow *lifecycle* — create, finish, cancel — is mechanically identical to
XRP escrow. What is different is the asset and **three rules the network enforces
at `EscrowCreate`** that XRP escrow never had:

1. **Issuer opt-in is mandatory, per-asset.** For an IOU, the token's **issuer**
   must set the account flag **`asfAllowTrustLineLocking`** (ledger flag
   `lsfAllowTrustLineLocking`) via `AccountSet` **before anyone can escrow that
   token**. Miss it and `EscrowCreate` fails **`tecNO_PERMISSION`**.
2. **The issuer cannot be the escrow source.** An issuer escrowing its *own*
   token as sender fails `tecNO_PERMISSION`. So the flow is: the issuer opts in
   and issues to a **holder**; the **holder** escrows the token to a third party.
3. **`CancelAfter` is mandatory.** Unlike XRP, there is **no open-ended token
   escrow** — every token escrow *must* carry a `CancelAfter` expiration.

This lesson runs on testnet — free and disposable. You are the **holder**: you
hold an issued token and escrow it to a **recipient**, then the recipient
finishes it and we prove the token moved.

## Step 1: Ensure your wallet is ready

You are the **holder** in this module — the account that escrows the token.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Creating an escrow still costs a small XRP owner reserve (0.2 XRP) **plus** the
locked token — you need XRP on hand even though the escrowed value is in another
asset. Free on testnet.

<!-- action: ensure_funded -->

## Step 3: Create the issuer

A second wallet acts as the **issuer** of a game currency called **GLD**.

**Issuer reuse:** this step loads `.xrpl-lab/issuer_wallet.json` when present
and reuses that issuer — it does not mint a fresh wallet on resume or re-run.
Minting a new issuer would orphan trust lines (and their owner reserve) against
the previous address. Leftover lines from earlier currencies still lock reserve
until balance is 0 and you remove them; run **Account Hygiene**
(`account_hygiene`) for the taught cleanup loop.

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

<!-- action: fund_issuer -->

## Step 5: Issuer opts in to token escrow

This is the rule that has no XRP equivalent. The issuer sets
**`asfAllowTrustLineLocking`** on its account (an `AccountSet` flag). Until this
is on, *no one* can escrow GLD — a `EscrowCreate` for it fails
`tecNO_PERMISSION`. This flag is the issuer's per-asset consent lever: the issuer
decides whether its token can be locked in escrow at all.

<!-- action: set_allow_trustline_locking -->

## Step 6: Trust the issuer

Opt in to hold GLD (a `TrustSet`). The trust line is the *holder's* half of the
consent: you decide whose token you are willing to hold, and up to what limit.
Until it exists, the issuer cannot send you a single GLD.

<!-- action: set_trust_line currency=GLD limit=1000 -->

## Step 7: Receive GLD from the issuer

Now the issuer sends 100 GLD down that trust line. You are now the holder with a
real balance — the thing you will escrow.

<!-- action: issue_token currency=GLD amount=100 -->

## Step 8: Create the recipient

A **third-party** wallet is the escrow's destination. It sets its own trust line
for GLD so the released token has a line to land on. (The token's issuer can
*never* be the escrow source — that is rule #2 — so a distinct holder → recipient
flow is the only valid shape.)

<!-- action: create_token_recipient currency=GLD limit=1000 -->

## Step 9: Snapshot the recipient's balance (before)

Capture the recipient's GLD balance now — it should be 0. We compare against it
at the end to prove the escrowed token actually moved.

<!-- action: snapshot_recipient_balance currency=GLD label=before -->

## Step 10: Escrow the token to the recipient (with a mandatory CancelAfter)

You (the holder) escrow **50 GLD** to the recipient. Because this is a *token*
escrow, a `CancelAfter` is **required** — we set one a day out. The 50 GLD leaves
your spendable balance and is locked on-ledger until the escrow is finished or
cancelled.

> **Transfer fees:** if the issuer had set a `TransferRate`/`TransferFee`, it is
> snapshotted at `EscrowCreate` and applied at `EscrowFinish` — the recipient
> would receive *less* than the 50 GLD face amount (net of the captured fee).
> This demo keeps GLD fee-free, so the recipient receives the full 50.

<!-- action: create_token_escrow currency=GLD amount=50 cancel_seconds=86400 -->

## Step 11: Create an issuer that never opted in

`asfAllowTrustLineLocking` is an **account-wide** flag, not a per-currency one. The
moment the issuer in Step 5 opted in, *every* token it issues became escrowable — so
the "I forgot the opt-in" wall can never appear against that issuer, no matter which
currency you try.

To meet the real failure you need a *different* issuer that never set the flag. This
step creates and funds one, then issues you **NOP** from it: a token whose issuer
holds no escrow permission at all.

<!-- action: create_noopt_issuer currency=NOP amount=50 -->

## Step 12: See the failure — a token escrow WITHOUT opt-in

Learn by hitting the wall. Now escrow the **NOP** you just received, whose issuer
never set `asfAllowTrustLineLocking`. The network refuses with
**`tecNO_PERMISSION`** — exactly the error you get when you forget the issuer
opt-in, and the single most common token-escrow mistake.

Note what changed between this step and Step 10: not the currency, and not your
account — the *issuer's* account flag. Escrow permission for an IOU lives with
whoever issued it, not with whoever holds it.

<!-- action: create_token_escrow_expect_fail currency=NOP amount=50 -->

## Step 13: Recipient finishes the escrow

The recipient submits `EscrowFinish`, releasing the locked GLD to itself. (For a
time-based escrow, either party may finish it after the release time — the funds
always go to the destination regardless of who submits. In `--dry-run` the
release time is simulated as already elapsed, so it succeeds immediately.)

<!-- action: finish_token_escrow -->

## Step 14: Snapshot the recipient's balance (after)

<!-- action: snapshot_recipient_balance currency=GLD label=after -->

## Checkpoint: prove the token moved

Confirm the recipient's GLD balance rose by exactly the escrowed amount — the
IOU that was locked in escrow is now the recipient's.

<!-- action: verify_token_moved -->

## Checkpoint: What you proved

You locked an **issued token** in a time-based escrow and released it to a third
party — something impossible before XLS-85:

1. **Issuer opt-in** — set `asfAllowTrustLineLocking` so GLD could be escrowed at
   all; saw `tecNO_PERMISSION` when a token lacked it
2. **Holder → recipient escrow** — escrowed 50 GLD (the issuer can never be the
   source) with a **mandatory `CancelAfter`**
3. **EscrowFinish** — the recipient released the locked IOU
4. **Verified** — the recipient's issued balance increased by the escrowed amount

Key concepts to remember:

- **Issuer opt-in is per-asset and mandatory** — `asfAllowTrustLineLocking`
  (IOUs) is the issuer's consent that its token may be locked. No flag, no escrow
  (`tecNO_PERMISSION`).
- **The issuer is never the source** — the token's issuer cannot escrow its own
  token as sender; a holder escrows to a third party.
- **`CancelAfter` is required** — unlike XRP, there is no open-ended token
  escrow. Every token escrow carries a cancel/reclaim deadline.
- **Transfer fees are captured at create, applied at finish** — with a non-zero
  `TransferRate`, the recipient receives the amount *net* of the fee, less than
  the locked face.
- **MPTs too** — XLS-85 also escrows Multi-Purpose Tokens; there the issuer opts
  in with `tfMPTCanEscrow` (+ `tfMPTCanTransfer`) at issuance instead of the
  trust-line flag. This lesson used the IOU path.

Run `xrpl-lab proof-pack` when you're ready to export your work.
</content>
</invoke>
