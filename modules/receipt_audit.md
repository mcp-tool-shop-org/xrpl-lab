---
id: receipt_audit
title: "Audit Mode: Verify Receipts at Scale"
track: audit
summary: Batch-verify a set of transactions and produce an audit report.
order: 8
time: 10-15 min
level: intermediate
mode: testnet
requires:
  - receipt_literacy
produces:
  - report
  - audit_pack
checks:
  - "Transactions fetched and verified"
  - "Pass/fail verdicts generated"
  - "Audit report produced"
  - "Audit pack with integrity hash"
---

Earlier modules taught you to verify one transaction at a time. Now you
learn to verify them in batch — the way operators, support teams, and
auditors actually work.

You give the audit engine a list of transaction IDs. It fetches each one,
checks it against rules (validated? succeeded? correct type? memo present?),
and produces a pass/fail report with evidence.

## Step 1: Ensure your wallet is ready

You need a funded wallet so we can create transactions to audit.

<!-- action: ensure_wallet -->

## Step 2: Fund your wallet

<!-- action: ensure_funded -->

## Step 3: Submit a payment

First, let's create a transaction we can audit later. This sends a small
amount to yourself with a memo tagged for XRPL Lab.

<!-- action: submit_payment destination=self amount=1 memo=XRPLLAB|AUDIT_TEST -->

## Step 4: Submit a second payment

One more — so we have multiple transactions to batch-audit.

<!-- action: submit_payment destination=self amount=1 memo=XRPLLAB|AUDIT_TEST_2 -->

## Step 5: Run the audit

Now we'll audit all the transactions from this session. The audit engine
fetches each tx, checks that it's validated and successful, and produces
a verdict.

<!-- action: run_audit -->

## Step 6: Understand the results

The audit produced three things:

1. **Console summary** — total checked, pass, fail, not found
2. **Markdown report** — table with per-tx details and failure reasons
3. **Audit pack** — JSON file with full evidence and SHA-256 integrity hash

The audit pack is what you'd attach to an issue or hand to an auditor.
It proves exactly what you checked and what the ledger said.

## Step 7: What about failures?

**Why audits matter.** Auditing turns raw transaction data into *evidence* — a stable artifact that pairs each txid with the expectation you had for it and the verdict the ledger actually returned. That triple (txid + expectation + verdict) is what a facilitator uses to verify a learner's batch run, what an operator uses to confirm a deploy went through cleanly, and what a compliance hand-off attaches to a case file. Crucially, expectations encode *intent*: "this txid SHOULD have failed with `tecPATH_DRY` because the pool was empty" is a much stronger claim than "this txid failed," and an expectations-aware audit can mark it as a pass. The failure vocabulary below is what those verdicts look like when reality and expectation diverge.

In a real audit, some transactions might fail checks:

- **NOT_FOUND** — the txid doesn't exist on this network
- **NOT_VALIDATED** — the tx exists but hasn't been validated yet
- **ENGINE_RESULT_MISMATCH** — expected tesSUCCESS but got something else
- **TYPE_DISALLOWED** — transaction type not in your allowed list
- **MEMO_MISSING** — expected a memo prefix but didn't find one

You can use an **expectations file** (`--expect expect.json`) to override
defaults per-tx. For example, if you know a specific txid was supposed
to fail with `tecPATH_DRY`, you can mark that in the expectations file
and the audit will treat it as a pass.

## Checkpoint: What you proved

You just ran a batch audit:

1. **Created test transactions** with memo tags
2. **Audited them programmatically** — not by eyeballing an explorer
3. **Generated evidence** — report + audit pack with integrity hash
4. **Learned the failure vocabulary** — the exact reasons a tx can fail audit

Operator takeaway:
- **Batch audits replace manual checks** — one command, any number of txids
- **Expectations let you encode intent** — "this one should have failed"
- **Audit packs are shareable proof** — attach to issues, hand to auditors
- **The CLI command**: `xrpl-lab audit --txids txids.txt`

This is the skill that turns transaction data into evidence.
