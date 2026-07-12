---
id: custodial_crediting_101
title: "Custodial Player Crediting: One Pooled Wallet, Many Players (Destination Tags)"
track: payments
kb_source: destination-tag-subaccounts
summary: Run the custodial backend pattern every live-service game needs — one pooled treasury address, every deposit routed to a player by a 32-bit DestinationTag, untagged deposits rejected by asfRequireDest, and every credit taken from delivered_amount, never Amount.
order: 47
time: 20-25 min
level: intermediate
mode: testnet
requires:
  - delivered_amount_101
produces:
  - txid
  - report
checks:
  - "asfRequireDest enabled on the pooled treasury (AccountSet — untagged deposits now bounce, txid produced)"
  - "A deposit tag assigned to a player in the OFF-LEDGER registry (the load-bearing tag -> player map)"
  - "A TAGGED deposit (DestinationTag) validated on-ledger and attributed to the right player via the registry"
  - "The player credited from delivered_amount — never from the Amount field"
  - "An UNTAGGED deposit was rejected with tecDST_TAG_NEEDED (the failure a learner hits)"
---

Your game has ten thousand players and ONE hot wallet. That is not a design
mistake — it is how every exchange and every custodial game backend actually
runs: a single studio-controlled XRPL account pools all player funds, and the
backend keeps its own ledger of who owns what. The question this module
answers is the one that decides whether that architecture works at all:
**when a deposit lands in the pool, whose is it?**

XRPL's answer is native and mainnet-live (no amendment to wait for): the
**DestinationTag** — an optional **32-bit unsigned integer** (0 to
4,294,967,295) riding on the Payment. You assign each player a tag, publish
"send to `<pool address>` with tag `<N>`", and on each validated deposit you
look up tag → player in your own registry and credit them. The mirror-image
field, **SourceTag**, is the sender's return-routing hint: echo it as the
DestinationTag on any refund you bounce back.

Three rules make the difference between a working custody backend and a
support-ticket factory:

1. **A tag is a routing hint, NOT authentication.** Tags have no on-ledger
   meaning — the ledger neither validates nor interprets them, and anyone can
   send any tag. The deposit's *value* is real; the *claimed player* is not
   proven until your backend checks the tag against the registry **it**
   issued. An unknown tag is held for manual review, never guessed. And that
   tag→player map lives entirely off-ledger, which makes it load-bearing:
   lose it and every pooled deposit becomes unattributable. Back it up.
2. **ALWAYS enable `asfRequireDest` on a custodial pool.** This account flag
   (ledger flag `lsfRequireDestTag`, set via `AccountSet`) makes the pool
   **reject any untagged incoming Payment with `tecDST_TAG_NEEDED`** — the
   deposit bounces instead of landing as orphaned funds. Fail-closed beats
   unattributable. You will hit this wall on purpose below.
3. **Credit from `delivered_amount`, never `Amount`.** You proved in
   Delivered Amount 101 that `Amount` (API-v2 `DeliverMax`) is only the
   requested cap; **`delivered_amount`** — metadata on a **validated** tx —
   is what actually arrived. A custodial backend that credits `Amount` is
   running the partial-payment exploit against itself. Gate every credit on
   `tesSUCCESS` AND `validated: true`, then read `delivered_amount`.

This lesson runs on testnet — free and disposable. Your wallet plays the
**pooled treasury**; a fresh wallet plays a **player** making deposits.

## Step 1: Ensure your treasury wallet is ready

You are the studio. Your wallet is the **pool** — the one address every
player will deposit into.

<!-- action: ensure_wallet -->

## Step 2: Fund the treasury

The AccountSet below costs a normal transaction fee, and the account itself
holds the usual base reserve. Free on testnet.

<!-- action: ensure_funded -->

## Step 3: Enable RequireDest — the pool fails closed

Before a single player deposits, flip the switch: `AccountSet` with
`SetFlag: asfRequireDest`. From this moment the ledger itself refuses any
incoming Payment that lacks a `DestinationTag` (`tecDST_TAG_NEEDED`), so an
unattributable deposit can never land. This is one transaction, no
amendment, and it is non-negotiable custody hygiene — turn it on the day the
pool goes live, because once real senders exist, untagged deposits WILL
arrive.

<!-- action: enable_require_dest -->

## Step 4: Create the player

A fresh, funded wallet plays a real player. Deposits must be genuine
third-party Payments into the pool — exactly the traffic your production
backend will see.

<!-- action: create_player_wallet -->

## Step 5: Assign the player a deposit tag (off-ledger)

Now the backend work. Assign tag **1001** to player **arya** in the
registry. Notice what this step does NOT do: no transaction, no ledger
object, nothing on-chain. The tag→player map is *your database table* — the
ledger will carry the integer, but only your registry gives it meaning. Two
production rules ride on that: the map is load-bearing (back it up), and a
tag is never reused for a second player while the first mapping is alive.

<!-- action: assign_player_tag tag=1001 player=arya -->

## Step 6: The player sends a tagged deposit

Arya deposits 25 XRP to the pool with `DestinationTag: 1001` — and a
`SourceTag: 9001`, her own return-routing hint (if you ever refund her, echo
9001 back as the refund's DestinationTag). The tag rides the validated
transaction on-ledger, in plaintext, for anyone to read.

In production you would surface this destination to players as an
**X-address** — the format that packs address + tag into ONE string — because
the #1 cause of lost custodial deposits is a player pasting the address and
forgetting the tag.

<!-- action: send_tagged_deposit amount=25 tag=1001 source_tag=9001 -->

## Step 7: Attribute and credit — the receiving discipline

The deposit is on-ledger; now run the credit path a real backend runs, in
order: confirm **`tesSUCCESS`** and **`validated: true`** (nothing about an
unvalidated tx is authoritative), read the **`DestinationTag`** off the tx,
resolve it against **your registry** (routing hint, not authentication —
tag 1001 is credited to arya because YOUR table says so), and credit
**`delivered_amount`** — never the `Amount` field. For a plain XRP deposit
the two happen to match; a correct backend reads `delivered_amount` every
time anyway, because the one day they differ is the day it matters.

<!-- action: credit_player_deposit expected=25 -->

## Step 8: See the failure — the untagged deposit

Learn by hitting the wall. The player sends a deposit with **no tag**. The
pool's RequireDest flag makes the network refuse it with
**`tecDST_TAG_NEEDED`** — the funds bounce back to the sender instead of
landing as an orphan the support team has to reconcile by hand. Read the
code carefully: this is the ledger enforcing *presence* of a tag. It never
checks *validity* — a deposit tagged 9999999 sails through and fails in YOUR
registry lookup instead. Presence is the ledger's job; meaning is yours.

<!-- action: send_untagged_deposit_expect_fail amount=10 -->

## Checkpoint: What you proved

You ran the full custodial crediting loop with receipts for every claim:

1. **Fail-closed pool** — enabled `asfRequireDest` on the treasury so
   untagged deposits can never land unattributable
2. **Off-ledger registry** — assigned tag 1001 → arya in the backend's own
   map, the load-bearing table the ledger knows nothing about
3. **Tagged deposit attributed** — a validated Payment carried
   `DestinationTag: 1001` and the backend credited the right player by
   registry lookup, not by trust
4. **Credited `delivered_amount`** — the credit came from validated-tx
   metadata, never the `Amount` cap
5. **Hit the wall** — an untagged deposit bounced `tecDST_TAG_NEEDED`,
   proving the flag does its job

Key concepts to remember:

- **A tag is a routing hint, not authentication** — anyone can send any tag;
  only your registry lookup makes it mean something. Unknown tag → hold for
  manual review, never credit.
- **The tag→player map is load-bearing and off-ledger** — the ledger stores
  the integer, you store the meaning. Back the map up; never reuse a live
  tag.
- **`asfRequireDest` on every custodial pool, day one** — untagged →
  `tecDST_TAG_NEEDED`. It enforces tag *presence* only; validity stays your
  job.
- **Credit `delivered_amount` after `tesSUCCESS` + `validated: true`** —
  the Delivered Amount 101 discipline, now applied where it earns its keep.
- **SourceTag is refund routing** — echo the deposit's SourceTag as your
  refund's DestinationTag.
- **Show players X-addresses** — address + tag in one string kills the
  forgotten-tag failure mode at the UX layer.

Run `xrpl-lab proof-pack` when you're ready to export your work.
