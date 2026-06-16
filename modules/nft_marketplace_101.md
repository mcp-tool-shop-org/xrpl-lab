---
id: nft_marketplace_101
title: "NFT Marketplace 101: Trading Assets with Enforced Royalties"
track: nfts
kb_source: escrowless-atomic-nft-settlement
summary: List a game-asset NFT for sale, settle the trade atomically, and watch a protocol-enforced creator royalty (TransferFee) land on the resale.
order: 30
time: 20-25 min
level: intermediate
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "NFT minted WITH a royalty (TransferFee) and transfer-enabled"
  - "Sell offer listed (NFTokenCreateOffer, tfSellNFToken)"
  - "Sell offer readable on-ledger (nft_sell_offers)"
  - "First sale settled — buyer owns the NFT (NFTokenAcceptOffer)"
  - "Resale settled — NFT returns to the creator"
  - "Royalty paid to the issuer on the resale"
  - "Accepting a nonexistent offer is refused (tec error, explained)"
---

On the XRPL, trading an NFT is two transactions: the owner publishes an
`NFTokenCreateOffer`, and a counterparty settles it atomically with
`NFTokenAcceptOffer`. No marketplace contract, no escrow service — the ledger is the
exchange. And the creator's cut is not a marketplace courtesy you have to trust:
**the `TransferFee` (royalty) is enforced by the protocol itself** on every resale.

One load-bearing rule (XLS-20): the royalty is charged **only when the seller is not
the issuer**. The *first* sale, from the creator to a buyer, pays no fee. The fee is
deducted on every *secondary* sale. So this module is a full round trip — mint, first
sale, resale — so you can watch the royalty actually move.

Everything here runs on the testnet — free, disposable, and safe to repeat.

## Step 1: Ensure your wallet is ready

You are the **creator** (and issuer) in this module.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Create a second player

A trade needs two parties. We create and fund a second wallet — the **buyer/reseller**.

<!-- action: create_buyer_wallet -->

## Step 4: Mint a game asset with a 5% royalty

Mint a **transferable** NFT carrying a `transfer_fee` of 5000 — that is 5.000% in the
XRPL's 0.001% steps. The royalty only takes effect because the NFT is transferable, and
it is permanent: flags and TransferFee can never change after mint.

<!-- action: mint_nft uri="ipfs://bafy-example/relic-of-dawn.json" taxon=11 transfer_fee=5000 transferable=true -->

## Step 5: Verify the mint

Read the NFT back: you should see the issuer (you), the taxon, transferable, and the
5% royalty baked in.

<!-- action: verify_nft -->

## Step 6: List the asset for sale (first sale)

The creator lists a sell offer. `tfSellNFToken` marks it as a sell. We direct it to the
buyer so the trade is a clean two-party demonstration.

<!-- action: list_nft_sell_offer amount=100 seller=creator -->

## Step 7: Read the offer back from the ledger

`nft_sell_offers` shows the open offer with its price and ledger index — the index is
exactly what the buyer hands to `NFTokenAcceptOffer`.

<!-- action: verify_nft_offer -->

## Step 8: The buyer accepts (first sale — no royalty)

The buyer settles the trade. Ownership moves to the buyer atomically. Because the seller
here **is** the issuer, no royalty is charged on this first sale.

<!-- action: accept_nft_offer buyer=buyer -->

## Step 9: Verify the first transfer

The NFT is now the buyer's, and gone from the creator. No royalty moved on this hop —
the verifier says so explicitly.

<!-- action: verify_nft_trade -->

## Step 10: The buyer lists a resale

Now the buyer lists the same NFT for resale, directed back to the creator. On *this* hop
the seller is not the issuer, so the protocol will skim the 5% `TransferFee`.

<!-- action: list_nft_sell_offer amount=200 seller=buyer -->

## Step 11: The creator buys it back — royalty fires

The instant this resale settles, the protocol routes the 5% royalty to the issuer (you,
the creator) — enforced by the ledger, not by any marketplace's good behavior.

<!-- action: accept_nft_offer buyer=creator -->

## Step 12: Verify ownership AND royalty

The NFT is back with the creator, gone from the reseller — and the issuer's XRP balance
went up by the enforced royalty. The verifier confirms both: clean ownership transfer and
the royalty delta arriving at the issuer.

<!-- action: verify_nft_trade -->

## Step 13: The failure case — accept a nonexistent offer

Settlement targets a specific offer ledger index. Hand `NFTokenAcceptOffer` an index that
does not exist and the ledger refuses with a `tec` error rather than guessing.

<!-- action: accept_nft_offer_expect_fail -->

## Checkpoint: What you proved

You ran a real NFT marketplace round trip on the ledger:

1. **Mint with royalty** — a transferable NFT with a permanent 5% TransferFee
2. **List + read** — `NFTokenCreateOffer` (tfSellNFToken) and `nft_sell_offers`
3. **Atomic settlement** — `NFTokenAcceptOffer` transfers ownership in one transaction
4. **Enforced royalty** — the resale paid the creator's cut at the protocol level, not by a marketplace's good behavior
5. **No-guess settlement** — accepting a missing offer is a clean tec failure

Key concepts to remember:

- **The ledger is the exchange** — no marketplace contract is required to trade or to enforce royalties
- **First sale pays no fee** — the TransferFee is charged on resales (seller ≠ issuer), the rule that makes secondary-market royalties work
- **Offers are objects** — each open offer is a ledger entry with an index; that index is the handle for settlement and cancellation
- **TransferFee is permanent** — set it at mint; it can never be raised or lowered later

Run `xrpl-lab proof-pack` when you're ready to export your work.
