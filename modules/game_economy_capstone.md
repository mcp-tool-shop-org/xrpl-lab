---
id: game_economy_capstone
title: "Capstone: Stand Up a Minimal Game Economy on XRPL"
track: capstone
summary: Compose everything you learned into one build — issue a game currency, mint a tradeable game asset with a royalty, sell it on the open ledger, lock and release a reward in escrow, then audit the whole trail into a single ledger-verifiable proof.
order: 90
time: 40-50 min
level: advanced
mode: testnet
requires:
  - mpt_issuance_101
  - nft_minting_101
  - escrow_101
  - receipt_audit
produces:
  - txid
  - report
  - audit_pack
checks:
  - "Game currency issued (MPTokenIssuanceCreate) and verified on-ledger"
  - "Game asset minted (NFTokenMint) with a transferable royalty and verified"
  - "Asset listed for sale and traded atomically to a second player"
  - "Reward locked in escrow (EscrowCreate) and released (EscrowFinish)"
  - "Whole session audited into an audit pack with a SHA-256 integrity hash"
---

This is the capstone. You have already issued an MPT, minted and burned an NFT,
locked XRP in escrow, and audited a batch of receipts — each in its own module,
each on its own track. **Here you compose them into one coherent build: a minimal
game economy that lives entirely on the public ledger.**

Nothing below is a new primitive. Every step is an action you have already run —
this module simply *sequences* them into the shape a real economy takes:

1. **A currency** — a capped Multi-Purpose Token, your in-game hard money.
2. **A tradeable asset** — a transferable NFT carrying a protocol-enforced creator
   royalty, so every resale pays you a cut without a marketplace's good behavior.
3. **A market** — a second player who buys the asset in one atomic settlement.
4. **A reward rail** — XRP locked in escrow and released on a timer, the building
   block for vesting, bounties, and delayed payouts.
5. **A proof** — one audit pass over the entire trail, sealed with a SHA-256 hash
   you can hand to anyone.

Because the curriculum gates this module on its four prerequisites
(`mpt_issuance_101`, `nft_minting_101`, `escrow_101`, `receipt_audit`), it is only
ever offered once you have the skills it composes. There is no new gating code —
the same prerequisite graph that orders every other module orders this one too.

Everything runs on testnet — free, disposable, and safe to repeat.

## Step 1: Ensure your wallet is ready

You are the **studio** in this build — the issuer of the currency, the creator of
the asset, and the operator who pays out rewards. If you completed the prerequisite
modules your wallet loads automatically.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Standing up an economy creates several owner objects (an MPT issuance, an NFT page,
an escrow) — each costs a small reserve on mainnet, free on testnet.

<!-- action: ensure_funded -->

## Step 3: Mint the game currency

Issue a capped Multi-Purpose Token as your in-game hard currency — supply ceiling,
two decimal places, and the **transferable** flag so players can trade it. This is
exactly the `MPTokenIssuanceCreate` from *MPT Issuance 101*, now the first pillar of
a real economy.

<!-- action: create_mpt_issuance maximum_amount=1000000 asset_scale=2 transferable=true -->

## Step 4: Verify the currency on-ledger

Read the issuance back via `account_objects` — you should see your issuance id, the
supply cap, and that it is transferable.

<!-- action: verify_mpt_issuance -->

## Step 5: Mint a tradeable game asset

Now mint a unique game asset — a **transferable** NFT carrying a 5% `transfer_fee`
royalty (5000 in the XRPL's 0.001% steps). The royalty is permanent and only takes
effect because the asset is transferable; it is the same `NFTokenMint` from
*NFT Minting 101*, now wired for a secondary market.

<!-- action: mint_nft uri="ipfs://bafy-example/relic-of-dawn.json" taxon=7 transfer_fee=5000 transferable=true -->

## Step 6: Verify you own the asset

Read the NFT back via `account_nfts` — issuer (you), taxon 7, transferable, and the
5% royalty baked in.

<!-- action: verify_nft -->

## Step 7: Bring a second player into the economy

A market needs two parties. Create and fund a second wallet — the **buyer** who will
acquire your asset.

<!-- action: create_buyer_wallet -->

## Step 8: List the asset for sale

The studio lists a sell offer directed at the buyer — `NFTokenCreateOffer` with
`tfSellNFToken`. The ledger itself is the marketplace; no contract required.

<!-- action: list_nft_sell_offer amount=100 seller=creator -->

## Step 9: Read the open offer back from the ledger

`nft_sell_offers` shows the live offer with its price and ledger index — exactly the
handle the buyer hands to `NFTokenAcceptOffer`.

<!-- action: verify_nft_offer -->

## Step 10: The buyer settles the trade

The buyer accepts the offer. Ownership moves atomically in one transaction. (This is
the first sale, from the issuer, so no royalty is charged — the royalty fires on
resales, the rule you proved in the marketplace module.)

<!-- action: accept_nft_offer buyer=buyer -->

## Step 11: Verify the asset changed hands

The NFT is now the buyer's and gone from the studio. The verifier confirms a clean
on-ledger ownership transfer.

<!-- action: verify_nft_trade -->

## Step 12: Lock a reward in escrow

Economies pay people. Lock some XRP in a short-`FinishAfter` escrow — a bounty or
quest reward held by the ledger until it matures. This is the `EscrowCreate` from
*Escrow 101*; the create step captures the create-sequence the release will need.

<!-- action: create_escrow amount=10 finish_seconds=10 -->

## Step 13: Verify the reward is locked

Read it back via `account_objects` — locked amount, destination, and the
`FinishAfter` time, with your owner count one higher while the escrow exists.

<!-- action: verify_escrow -->

## Step 14: Release the reward

Submit `EscrowFinish` after the timer matures to release the locked XRP and free the
reserve. (On testnet, re-run this step if you see `tecNO_PERMISSION` — the clock has
not elapsed yet; in `--dry-run` it succeeds immediately.)

<!-- action: finish_escrow -->

## Step 15: Verify the reward was paid

Confirm the escrow object is **gone** from `account_objects` — the reward XRP has
moved to the destination and the owner reserve is freed back to spendable.

<!-- action: verify_escrow_finished -->

## Step 16: Audit the entire trail into a proof

Finally, audit every transaction this build produced — currency issuance, asset
mint, the trade, and the escrow lifecycle — in one batch. The audit engine fetches
each txid, checks it validated and succeeded, and seals the verdicts into an audit
pack with a SHA-256 integrity hash. That pack is your single, shareable, ledger-
verifiable proof that the economy actually stood up.

<!-- action: run_audit -->

## Checkpoint: What you built

You stood up a minimal game economy on the XRPL — end to end, on the public ledger,
with one verifiable proof at the bottom:

1. **A currency** — a capped, transferable MPT (`MPTokenIssuanceCreate`)
2. **An asset** — a transferable NFT with a permanent, protocol-enforced royalty
   (`NFTokenMint` + `TransferFee`)
3. **A market** — a second player and an atomic on-ledger trade
   (`NFTokenCreateOffer` / `NFTokenAcceptOffer`)
4. **A reward rail** — XRP locked and released on a timer
   (`EscrowCreate` / `EscrowFinish`)
5. **A proof** — the whole trail batch-audited into a SHA-256-sealed audit pack

What the capstone really teaches:

- **Composition is the skill** — none of these primitives is new; the value is in
  sequencing them into a system. A real economy is exactly this set of moving parts
  wired together.
- **The ledger is the backend** — no servers, no custodians, no marketplace
  contract. Currency, assets, trades, and payouts are all native ledger objects.
- **Royalties are enforced, not promised** — the creator's cut lives in the
  protocol, not in a marketplace's terms of service.
- **Proof is the deliverable** — when you are done, you don't have a screenshot;
  you have a sealed audit pack anyone can re-verify against the live XRPL.

Run `xrpl-lab proof-pack` to export the capstone proof — your completed-module list
will carry a `capstone: true` flag, the studio's signature that the whole economy
came together.
