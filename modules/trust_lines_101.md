---
id: trust_lines_101
title: "Trust Lines 101: Issued Currencies as Relationships"
track: foundations
summary: Create a trust line, issue tokens, and verify the relationship on-ledger.
order: 3
time: 15-20 min
level: beginner
mode: testnet
requires: []
produces:
  - txid
  - report
checks:
  - "Trust line set successfully"
  - "Tokens issued and received"
  - "Trust line verified: currency, issuer, balance"
---

Welcome to Trust Lines 101. In this module you will learn how issued currencies
work on the XRPL — not as abstract tokens, but as relationships between accounts.

On the XRPL, only XRP is native. Every other currency (USD, EUR, your own token)
exists as a balance on a **trust line** between two accounts. Setting a trust line
means: "I trust this issuer for up to X units of this currency."

By the end you will understand: what a trust line is, how to create one, how tokens
are issued, and how to verify the result on-ledger.

## Step 1: Ensure your wallet is ready

You need a funded wallet to set trust lines and receive tokens. If you have one
from a previous module, it will be loaded automatically.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

Trust line operations require XRP for transaction fees and the owner reserve
(each trust line increases the reserve by 2 XRP on mainnet, free on testnet).

<!-- action: ensure_funded -->

## Step 3: Create an issuer wallet

On the XRPL, anyone can issue a currency. The issuer is just another account.
In production, issuers would be businesses or institutions. For learning, we
create a second wallet to act as the issuer.

This wallet will issue a currency called **LAB** — your first issued token.

<!-- action: create_issuer_wallet -->

## Step 4: Fund the issuer

The issuer also needs XRP to pay transaction fees.

<!-- action: fund_issuer -->

## Step 5: Set a trust line

Now the important part. Before you can receive LAB tokens, you must explicitly
trust the issuer. This is a **TrustSet** transaction from your wallet, saying:

> "I trust [issuer address] for up to 1000 LAB."

This is the fundamental difference from most blockchains: you must opt in to
receiving a token. No one can airdrop unwanted tokens to your wallet.

<!-- action: set_trust_line currency=LAB limit=1000 -->

## Step 6: Issue tokens

Now the issuer sends you 100 LAB. This is a regular Payment transaction, but
instead of XRP, it sends an **issued currency amount**.

The issuer can create LAB tokens out of nothing — that is the privilege (and
responsibility) of being an issuer. The trust line is what makes this possible.

<!-- action: issue_token currency=LAB amount=100 -->

## Step 7: Verify your trust line

Let's verify the trust line on the ledger. You should see:

- **Currency**: LAB
- **Issuer**: the issuer address from Step 3
- **Limit**: 1000 (what you set in Step 5)
- **Balance**: 100 (what the issuer sent in Step 6)

<!-- action: verify_trust_line currency=LAB -->

## Checkpoint: What you proved

You just completed the trust line lifecycle:

1. **Created an issuer** — any XRPL account can issue currencies
2. **Set a trust line** — you opted in to receiving LAB tokens
3. **Received issued tokens** — the issuer sent you 100 LAB
4. **Verified on-ledger** — the trust line shows the correct balance

This is the same mechanism used for stablecoins, loyalty points, and any
tokenized asset on the XRPL. The trust line is a consent mechanism: you
decide who you trust and for how much.

Key concepts to remember:
- **Trust lines are directional**: you trust the issuer, not the other way around
- **Issuers can create tokens**: the balance is an obligation from issuer to holder
- **Reserve costs**: each trust line increases your account reserve (2 XRP on mainnet)
- **No surprise tokens**: unlike other chains, you cannot receive tokens you didn't agree to

Your report and transaction IDs are saved. Run `xrpl-lab proof-pack` to
export a shareable proof of what you did here.
