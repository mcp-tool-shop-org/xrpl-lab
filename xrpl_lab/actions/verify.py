"""Transaction verification action."""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import Transport, TxInfo


@dataclass
class VerifyResult:
    """Result of verifying a transaction against expected fields."""

    passed: bool
    tx_info: TxInfo
    checks: list[str]
    failures: list[str]


async def verify_tx(
    transport: Transport,
    txid: str,
    expected_destination: str | None = None,
    expected_amount: str | None = None,
    expected_success: bool = True,
) -> VerifyResult:
    """Fetch a transaction and verify it against expected fields."""
    tx = await transport.fetch_tx(txid)
    checks: list[str] = []
    failures: list[str] = []

    # TXBCD-002: a READ-BACK failure (timeout / network / RPC error) is NOT a
    # transaction failure. When fetch_tx couldn't reach the ledger it sets the
    # distinct ``fetch_error`` field (NOT result_code), so we must NOT compare
    # result_code against tesSUCCESS — doing so would report a tx that actually
    # SUCCEEDED on-ledger as a verification FAILURE merely because the
    # verification read-back timed out. Surface a distinct, non-failure-
    # attributing message and return early without populating any failure that
    # blames the transaction.
    if tx.fetch_error:
        return VerifyResult(
            passed=False,
            tx_info=tx,
            checks=[],
            failures=[
                "Couldn't fetch the transaction to verify (network issue) — "
                "it may still have succeeded on-ledger; retry verification. "
                f"(details: {tx.fetch_error})"
            ],
        )

    # Check result code
    if expected_success:
        if tx.result_code == "tesSUCCESS":
            checks.append("Result: tesSUCCESS")
        else:
            failures.append(f"Expected tesSUCCESS, got {tx.result_code}")
    else:
        if tx.result_code != "tesSUCCESS":
            checks.append(f"Result: {tx.result_code} (expected failure)")
        else:
            failures.append("Expected failure but got tesSUCCESS")

    # Check destination
    if expected_destination:
        if tx.destination == expected_destination:
            checks.append(f"Destination: {expected_destination}")
        else:
            failures.append(
                f"Destination mismatch: expected {expected_destination}, got {tx.destination}"
            )

    # Check amount
    if expected_amount:
        if tx.amount == expected_amount:
            checks.append(f"Amount: {expected_amount}")
        else:
            failures.append(f"Amount mismatch: expected {expected_amount}, got {tx.amount}")

    # Always report fee and ledger
    checks.append(f"Fee: {tx.fee} drops")
    if tx.ledger_index:
        checks.append(f"Ledger index: {tx.ledger_index}")
    if tx.validated:
        checks.append("Validated: yes")

    return VerifyResult(
        passed=len(failures) == 0,
        tx_info=tx,
        checks=checks,
        failures=failures,
    )
