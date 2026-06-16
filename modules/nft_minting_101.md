---
id: nft_minting_101
title: "NFT Minting 101: Your First Game Asset"
track: nfts
kb_source: nftokenmint
summary: Mint an NFToken on the XRPL and verify you own it — your first on-ledger game asset.
order: 20
time: 15-20 min
level: beginner
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "NFToken minted (txid produced)"
  - "NFTokenID captured from the mint"
  - "Ownership verified on-ledger: issuer, taxon, transferable"
  - "NFToken burned (txid produced)"
  - "NFToken gone from the ledger — reserve freed"
---

On the XRPL an NFT is a **native ledger object** — no smart contract required. The
`NFTokenMint` transaction creates one and assigns it to your account, locking in its
permanent properties: a collection id (taxon), an optional metadata URI, a royalty
(TransferFee), and flags like *transferable*. This is the single entry point for putting
a game asset on the ledger.

Everything here runs on the testnet — free, disposable, and safe to repeat.

## Step 1: Ensure your wallet is ready

You need a funded wallet to mint. If you completed an earlier module it loads automatically.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Minting costs a small fee plus an owner reserve (NFTs are stored in NFTokenPage objects
holding up to 32 each; each page costs reserve on mainnet — free on testnet).

<!-- action: ensure_funded -->

## Step 3: Mint your game asset

Now the core operation. You will mint a **transferable** NFToken with a metadata URI and
a collection taxon. The `transfer_fee` sets a secondary-sale royalty (in 0.001% steps) —
it only takes effect because the NFT is transferable.

Permanent-once-minted: flags and TransferFee can **never** change after this, and the URI
is stored as hex and is not validated — so pin your metadata somewhere durable.

<!-- action: mint_nft uri="ipfs://bafy-example/sword-of-dawn.json" taxon=7 transfer_fee=500 transferable=true -->

## Step 4: Verify you own it

Read the NFT back from the ledger via `account_nfts`. You should see your new NFTokenID,
the issuer (you), the taxon (collection id 7), and that it is transferable.

<!-- action: verify_nft -->

## Step 5: Burn the asset

Minting is only half the lifecycle — you should also know how to **destroy** an asset and reclaim
what it costs. `NFTokenBurn` permanently removes the NFToken. When the last NFT in an
`NFTokenPage` is burned, that page object is deleted and its owner reserve is freed (the same
"free your reserve" lesson from *Account Hygiene*). The issuer can always burn their own NFT;
they can also burn one they minted as `transferable` even after it has moved on.

<!-- action: burn_nft -->

## Step 6: Verify it's gone

Read `account_nfts` once more. The NFTokenID you minted should be absent — the asset is destroyed
and the reserve it consumed is freed back to spendable.

<!-- action: verify_nft_burned -->

## Checkpoint: What you proved

You minted a native NFT, verified ownership, then burned it — the full lifecycle:

1. **NFTokenMint** — created an NFT with permanent properties in one transaction
2. **Collection identity** — the (issuer, taxon) pair is how the XRPL groups a collection; there is no native "collection" object
3. **Royalties** — TransferFee enforces a creator royalty at the protocol level
4. **Verified** — `account_nfts` shows you as the owner
5. **NFTokenBurn** — destroyed the asset and freed its reserve

Key concepts to remember:

- **Permanent at mint**: flags + TransferFee can't change later — use mutable-URI / dynamic NFTs (XLS-46) if the asset must evolve (e.g. leveling gear)
- **Reserve cost**: each NFTokenPage (up to 32 NFTs) costs owner reserve on mainnet
- **Fungible game items belong in MPTs, not NFTs** — reserve NFTs for genuinely unique assets
- **URI is unvalidated hex** — pin metadata to IPFS/Arweave so the link doesn't die

Run `xrpl-lab proof-pack` when you're ready to export your work.
