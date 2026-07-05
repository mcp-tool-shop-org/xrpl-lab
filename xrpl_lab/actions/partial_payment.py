"""Partial-payment action + delivered_amount verification (FC-003).

Teaches the #1 XRPL integration bug: reading the ``Amount`` field (or the
API-v2 rename ``DeliverMax``) instead of the ``delivered_amount`` metadata
field when crediting a user. A sender sets ``tfPartialPayment``, the tx returns
``tesSUCCESS``, but far less was delivered than ``Amount`` claims — a naive
backend credits the full ``Amount`` and loses money.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import SubmitResult, Transport, TxInfo


async def send_partial_payment(
    transport: Transport,
    issuer_seed: str,
    destination: str,
    currency: str,
    issuer_address: str,
    amount: str,
    deliver_min: str,
    send_max: str,
    memo: str = "",
) -> SubmitResult:
    """Send an issued-currency Payment WITH tfPartialPayment that under-delivers.

    ``amount`` is the requested cap (the tx's ``Amount`` / API-v2 ``DeliverMax``),
    ``deliver_min`` is the floor the sender will accept, and ``send_max`` caps the
    total source spent. When the flag reduces delivery, ``delivered_amount`` on
    the validated tx is the ACTUAL amount that moved — always less than or equal
    to ``amount``.
    """
    return await transport.submit_partial_payment(
        issuer_seed=issuer_seed,
        destination=destination,
        currency=currency,
        issuer=issuer_address,
        amount=amount,
        deliver_min=deliver_min,
        send_max=send_max,
        memo=memo,
    )


@dataclass
class DeliveredAmountResult:
    """Result of contrasting the tx's Amount field with delivered_amount.

    ``amount_field`` is what a naive backend would (wrongly) credit — the tx's
    ``Amount`` / ``DeliverMax`` cap. ``delivered_amount`` is the honest metadata
    field: what actually moved. ``exploit_demonstrated`` is True when the two
    differ (the partial payment under-delivered), which is the whole lesson.
    """

    amount_field: str
    delivered_amount: str
    exploit_demonstrated: bool
    checks: list[str]
    failures: list[str]

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


def _amount_value(display: str) -> str:
    """Extract the numeric value from a ``value/currency/issuer`` display string.

    XRP amounts are a bare drops string (no slashes); issued amounts are
    ``value/CUR/issuer``. Returns the leading ``value`` component for comparison.
    """
    if not display:
        return ""
    return display.split("/", 1)[0]


async def verify_delivered_amount(
    transport: Transport,
    txid: str,
    expected_delivered: str | None = None,
) -> DeliveredAmountResult:
    """Read a validated tx and prove delivered_amount is the field to trust.

    Confirms the tx is ``tesSUCCESS`` + ``validated`` FIRST (only then is
    ``delivered_amount`` authoritative), then contrasts the ``Amount`` field
    with ``delivered_amount``. When they differ, the partial-payment exploit is
    demonstrated: a backend crediting ``Amount`` would over-credit.
    """
    tx: TxInfo = await transport.fetch_tx(txid)
    checks: list[str] = []
    failures: list[str] = []

    # A fetch-back failure is NOT a tx failure (TXBCD-002 semantics) — but for
    # this lesson we cannot read delivered_amount without the tx, so it is an
    # honest failed verification here.
    if tx.fetch_error:
        failures.append(
            "Couldn't fetch the transaction to read delivered_amount "
            f"(network issue): {tx.fetch_error}"
        )
        return DeliveredAmountResult("", "", False, checks, failures)

    # Gate on tesSUCCESS + validated: delivered_amount is only authoritative on
    # a VALIDATED, successful transaction. Reading it before confirming both is
    # itself a bug (RECEIVING lesson).
    if tx.result_code != "tesSUCCESS":
        failures.append(
            f"Transaction is not tesSUCCESS (got {tx.result_code}) — "
            "delivered_amount is not authoritative until the tx succeeds."
        )
        return DeliveredAmountResult(tx.amount, tx.delivered_amount, False, checks, failures)
    checks.append("Result: tesSUCCESS")

    if not tx.validated:
        failures.append(
            "Transaction is not validated yet — wait for validated:true before "
            "trusting delivered_amount."
        )
        return DeliveredAmountResult(tx.amount, tx.delivered_amount, False, checks, failures)
    checks.append("Validated: yes")

    amount_field = tx.amount
    delivered = tx.delivered_amount
    checks.append(f"Amount field (a.k.a. DeliverMax) — the CAP: {amount_field}")
    checks.append(f"delivered_amount metadata — what ACTUALLY moved: {delivered or '(absent)'}")

    if not delivered:
        failures.append(
            "delivered_amount was absent — this transport did not expose it; "
            "cannot prove the exploit."
        )
        return DeliveredAmountResult(amount_field, delivered, False, checks, failures)

    amount_val = _amount_value(amount_field)
    delivered_val = _amount_value(delivered)
    exploit = amount_val != delivered_val

    if exploit:
        checks.append(
            f"delivered_amount ({delivered_val}) < Amount ({amount_val}) — a backend "
            "crediting the Amount field would OVER-CREDIT. Always read "
            "delivered_amount."
        )
    else:
        checks.append(
            "delivered_amount equals Amount — full delivery this time; but a "
            "correct backend must STILL read delivered_amount, not assume equality."
        )

    if expected_delivered is not None and delivered_val != str(expected_delivered):
        failures.append(
            f"delivered_amount mismatch: expected {expected_delivered}, got {delivered_val}"
        )

    return DeliveredAmountResult(amount_field, delivered, exploit, checks, failures)
