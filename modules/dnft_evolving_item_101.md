---
id: dnft_evolving_item_101
title: "Dynamic NFTs 101: A Game Item That Levels Up"
track: nfts
kb_source: dynamic-nft-nftokenmodify
summary: Mint a mutable NFT (tfMutable), then NFTokenModify its URI to evolve it from level 1 to level 2 — the same NFTokenID, new on-ledger state.
order: 40
time: 15-20 min
level: intermediate
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "Mutable NFT minted (tfMutable) at level 1"
  - "Ownership verified on-ledger"
  - "URI modified to level 2 (NFTokenModify)"
  - "URI advanced on the SAME NFTokenID — identity preserved"
  - "Modifying a non-mutable NFT is refused (tec error, explained)"
---

Most NFTs are frozen at mint — their metadata URI is permanent. That is fine for a
collectible, but a game item *changes*: a sword gains enchantments, armor takes damage,
a companion levels up. The XRPL handles this with **dynamic NFTs** (XLS-46): mint with
the `tfMutable` flag, and you can later change the URI with `NFTokenModify`.

The crucial property: the **NFTokenID never changes**. The same on-ledger object that a
player owns simply points at new state. Their inventory, their trade history, their
provenance — all preserved. Only the item's representation advances.

Everything here runs on the testnet — free, disposable, and safe to repeat.

## Step 1: Ensure your wallet is ready

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Mint a mutable item at level 1

Mint with `mutable=true` (tfMutable). The URI points at the item's level-1 state. Without
this flag the URI would be permanent and the rest of this module would be impossible —
that is exactly the failure case we demonstrate at the end.

<!-- action: mint_nft uri="ipfs://bafy-example/blade-level-1.json" taxon=21 mutable=true -->

## Step 4: Verify you own it

<!-- action: verify_nft -->

## Step 5: Level the item up

The item levels up. `NFTokenModify` swaps the URI to the level-2 state. Same NFTokenID,
same owner, same provenance — new representation. This is the on-ledger event behind
"your sword reached level 2."

<!-- action: modify_nft uri="ipfs://bafy-example/blade-level-2.json" -->

## Step 6: Verify the evolution

Read the NFT back. The URI now points at level 2, and — the load-bearing check — it is
still the **same NFTokenID** from Step 3. The asset's identity is preserved; only its
state advanced.

<!-- action: verify_nft_modified -->

## Step 7: The failure case — modifying a fixed NFT

Now the contrast. We mint a fresh NFT **without** tfMutable and try to modify it. The
ledger refuses with a `tec` error: a non-mutable NFT's URI was permanent the moment it
was minted. This is why you decide mutability up front, at mint time.

<!-- action: modify_nft_expect_fail -->

## Checkpoint: What you proved

You built and evolved a dynamic game item:

1. **Mutable mint** — tfMutable at mint is the prerequisite for any later change
2. **NFTokenModify** — advanced the item's URI from level 1 to level 2
3. **Identity preserved** — the NFTokenID is unchanged, so ownership and provenance survive the evolution
4. **Mutability is permanent-at-mint** — a non-mutable NFT can never be modified; the attempt is a clean tec failure

Key concepts to remember:

- **Decide mutability at mint** — tfMutable cannot be added later, just as TransferFee and transferability cannot
- **The NFTokenID is the item's soul** — modifying the URI changes state, not identity, which is exactly what leveling/evolving needs
- **URI is unvalidated hex** — pin each level's metadata to durable storage (IPFS/Arweave) so the links don't die between updates
- **Mutable is a trust decision** — a mutable item can be changed by whoever can modify it; document who holds that power in your game's rules

Run `xrpl-lab proof-pack` when you're ready to export your work.
