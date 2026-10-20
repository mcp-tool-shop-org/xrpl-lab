---
id: bad_amm_no_label
title: AMM Without Dry Run Label
track: amm
summary: Uses AMM actions without a dry-run label — allowed since #30 went testnet.
order: 1
time: 5 min
level: advanced
---

This module uses AMM actions without ``mode: dry-run``. Historically that
warned ("not marked dry_run_only"); since AMM went testnet-capable the
linter accepts either mode for the amm track.

## Step 1: Set up wallet

<!-- action: ensure_wallet -->

## Step 2: Check AMM pair

<!-- action: ensure_amm_pair -->
