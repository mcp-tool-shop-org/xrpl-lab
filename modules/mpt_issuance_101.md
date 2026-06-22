---
id: mpt_issuance_101
title: "MPT Issuance 101: A Game Currency in One Transaction"
track: tokens
kb_source: mpt-issuance-create-config
summary: Issue a Multi-Purpose Token (XLS-33) as a game currency and verify it on-ledger.
order: 30
time: 15-20 min
level: intermediate
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "MPT issuance created (txid produced)"
  - "Issuance verified on-ledger: max supply, transferable"
---

A **Multi-Purpose Token (MPT, XLS-33)** is the modern way to issue a fungible token on the
XRPL — perfect for an in-game soft currency. Unlike trust-line IOUs, MPTs need **no trust line
per holder**, carry native metadata, and define their entire policy — supply cap, decimal scale,
an optional transfer fee, and capability flags — in a **single `MPTokenIssuanceCreate` transaction**.
This lesson sets a supply cap, scale, and the transferable flag, and leaves the transfer fee at
zero — you can set a transfer fee on a *future* issuance by passing `transfer_fee` (an issuance's config is immutable once created, so this mints a new one).

This runs on testnet — free and disposable.

## Step 1: Ensure your wallet is ready

You need a funded wallet to issue a token. If you completed an earlier module it loads automatically.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Issuing an MPT costs a small fee plus an owner reserve for the issuance object (free on testnet).

<!-- action: ensure_funded -->

## Step 3: Issue your game currency

Create an MPT issuance with a fixed maximum supply, an asset scale (decimal places), and the
**transferable** flag so players can trade it. The policy you set here is largely immutable.

<!-- action: create_mpt_issuance maximum_amount=1000000 asset_scale=2 transferable=true -->

## Step 4: Verify the issuance

Read it back from the ledger via `account_objects`. You should see your issuance id, the
maximum supply, and that it is transferable.

<!-- action: verify_mpt_issuance -->

## Checkpoint: What you proved

You issued a native fungible token in one transaction and verified it on-ledger:

1. **MPTokenIssuanceCreate** — defined supply cap, scale, and flags in a single tx (transfer fee left at zero)
2. **No trust lines** — holders opt in with one `MPTokenAuthorize`, not a per-token trust line
3. **Verified** — `account_objects` shows the issuance you control

Key concepts to remember:

- **MPT vs IOU** — MPT is the right primitive for a *new* game soft currency (compact, trust-line-free). Use a trust-line **IOU** when you need a currency that's **tradeable on the DEX today** — MPT DEX trading (XLS-82) is **not yet live on mainnet**.
- **Policy is set at creation** — supply cap, asset scale, and most flags can't change later; choose deliberately.
- **Hard vs soft money** — pair a capped MPT (premium/hard currency) with an uncapped earned currency for a healthy economy.

Run `xrpl-lab proof-pack` when you're ready to export your work.
