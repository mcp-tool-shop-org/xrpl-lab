"""Custodial player crediting — destination tags on a pooled treasury.

The standard custodial backend pattern every game with a shared hot wallet
needs (mainnet-live, native — no amendment): ONE studio-controlled XRPL
account pools every player's funds, and each incoming deposit carries a
32-bit unsigned ``DestinationTag`` that the backend maps to a specific
player sub-account. This is exactly how exchanges run "hosted accounts".
``SourceTag`` is the mirror-image hint: it tells the recipient where to
route a refund/bounce.

The rules this module's actions encode:

  * **The tag is a routing hint, NOT authentication.** Tags have no
    on-ledger meaning — anyone can send any tag — so the backend must
    validate the claimed player against its OWN issued-tag registry. An
    unknown tag means "hold for manual review", never "invent a player".
    The tag→player map is load-bearing and lives entirely off-ledger; back
    it up.
  * **ALWAYS enable ``asfRequireDest`` on a custodial pool.** The account
    flag (ledger flag ``lsfRequireDestTag``) makes the pool REJECT any
    untagged incoming Payment with ``tecDST_TAG_NEEDED`` — failing closed
    beats an unattributable deposit and the support ticket it becomes.
  * **Credit from ``delivered_amount``, never ``Amount``.** ``Amount``
    (API-v2 ``DeliverMax``) is only the requested cap; ``delivered_amount``
    is the validated-metadata figure that actually arrived (the
    delivered_amount_101 lesson this module composes). Only trust it after
    ``tesSUCCESS`` AND ``validated: true``.
  * **Tags are 32-bit** (0..4294967295). xrpl-py rejects an out-of-range
    tag at model construction; these actions reject it locally with a
    structured error so both transports behave identically. X-addresses
    bundle address + tag into one string to prevent the forgotten-tag /
    copy-error class of lost deposits.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..transport.base import SubmitResult, Transport, TxInfo

# The network's ceiling for DestinationTag / SourceTag (32-bit unsigned).
MAX_TAG = 0xFFFF_FFFF  # 4294967295


def _validate_tag(label: str, tag: int | None) -> SubmitResult | None:
    """Reject a non-integer or out-of-range tag locally; None means it passes.

    xrpl-py's Payment model raises at construction for a tag outside the
    32-bit unsigned range (the testnet transport surfaces that as an opaque
    local_error), so this preflight rejects the same set with a TEACHING
    message before either transport ever sees it.
    """
    if tag is None:
        return None
    try:
        value = int(tag)
    except (TypeError, ValueError):
        return SubmitResult(
            success=False,
            result_code="local_error",
            error=(
                f"{label} {tag!r} is not an integer — tags are 32-bit "
                f"unsigned integers (0..{MAX_TAG})."
            ),
        )
    if not 0 <= value <= MAX_TAG:
        return SubmitResult(
            success=False,
            result_code="local_error",
            error=(
                f"{label} {value} is out of range — tags are 32-bit unsigned "
                f"integers (0..{MAX_TAG}). A tag outside that range never "
                "reaches the ledger: xrpl-py refuses to build the Payment."
            ),
        )
    return None


async def enable_require_dest(
    transport: Transport,
    wallet_seed: str,
    wallet_address: str = "",
    enable: bool = True,
) -> SubmitResult:
    """Enable (or clear) ``asfRequireDest`` on the pooled account (AccountSet).

    With the flag set, the ledger rejects any incoming Payment that lacks a
    ``DestinationTag`` with ``tecDST_TAG_NEEDED`` — the fail-closed posture
    every custodial pool needs. ``enable=False`` clears the flag (the named
    compensator). ``wallet_address`` is forwarded for the dry-run transport's
    per-account flag state (the testnet path derives the account from the
    seed).
    """
    return await transport.submit_require_dest(
        wallet_seed, enable=enable, wallet_address=wallet_address
    )


async def send_tagged_deposit(
    transport: Transport,
    sender_seed: str,
    destination: str,
    amount: str,
    destination_tag: int | None = None,
    source_tag: int | None = None,
    memo: str = "",
) -> SubmitResult:
    """A player sends an XRP deposit to the pooled treasury, tagged (or not).

    ``destination_tag`` routes the deposit to the player's sub-account in the
    backend registry; ``source_tag`` is the player's own return/bounce hint.
    Passing ``destination_tag=None`` sends UNTAGGED — against a RequireDest
    pool that is exactly the ``tecDST_TAG_NEEDED`` failure the module has the
    learner hit on purpose. Out-of-range tags are rejected locally with a
    structured error (see :func:`_validate_tag`).
    """
    for label, tag in (
        ("DestinationTag", destination_tag),
        ("SourceTag", source_tag),
    ):
        rejected = _validate_tag(label, tag)
        if rejected is not None:
            return rejected
    return await transport.submit_payment(
        sender_seed,
        destination,
        amount,
        memo=memo,
        destination_tag=int(destination_tag) if destination_tag is not None else None,
        source_tag=int(source_tag) if source_tag is not None else None,
    )


@dataclass
class PlayerCreditResult:
    """Result of attributing a pooled deposit to a player and crediting it.

    ``player`` is the registry entry the tag resolved to ("" when
    unattributable). ``amount_field`` is what a naive backend would have
    credited (the cap), kept for the contrast.

    F-c918543c (HIGH): ``delivered_amount`` is XRP-or-issued-currency
    polymorphic — the transports' ``_format_amount`` renders XRP as a bare
    drops integer string ("25000000") but an issued currency as
    ``"value/currency/issuer"`` ("50/LAB/rIssuer12345678..."), NEVER a bare
    integer. The pre-fix code read that string straight into
    ``credited_drops`` and hard-coded "drops" in the check message
    regardless of currency, so a non-XRP deposit produced a nonsensical
    "Credited 50/LAB/rIssuer... drops" message. Credit is now derived from
    the real delivered value WITH its correct currency/issuer:

    * ``currency`` — "XRP" or the 3-40 char issued-currency code.
    * ``issuer`` — "" for XRP, the issuer address for an issued currency.
    * ``credited_value`` — the numeric value credited, in ITS OWN currency
      (drops for XRP, the issued-currency's decimal value otherwise).
      Currency-agnostic — always populated, always the right unit.
    * ``credited_drops`` — kept for backward compatibility with existing
      XRP-only callers/tests. Populated ONLY when ``currency == "XRP"``;
      left "" for an issued currency so a non-drops value can never again
      land in a field whose very name promises drops. New code should read
      ``credited_value`` + ``currency`` instead.
    """

    player: str
    tag: int | None
    credited_drops: str
    amount_field: str
    checks: list[str]
    failures: list[str]
    currency: str = "XRP"
    issuer: str = ""
    credited_value: str = ""

    @property
    def passed(self) -> bool:
        return len(self.failures) == 0


def _split_delivered_amount(delivered: str) -> tuple[str, str, str]:
    """Split a ``delivered_amount`` display string into (value, currency, issuer).

    Mirrors the shape ``Transport._format_amount`` produces on the read
    side (xrpl_testnet.py / dry_run.py): XRP is a bare drops integer
    string with no ``/`` — returned as ``(drops, "XRP", "")``. An issued
    currency is formatted as ``"value/currency/issuer"`` — split into its
    three parts. A delivered string that contains a ``/`` but doesn't
    split into exactly 3 parts is not a shape either transport emits
    today; it is returned as ``("", delivered, "")`` (the whole string
    preserved as "currency") rather than raising, so a future transport
    bug surfaces as an odd-looking-but-honest credit instead of an
    unhandled exception in the crediting path.
    """
    if "/" not in delivered:
        return delivered, "XRP", ""
    parts = delivered.split("/", 2)
    if len(parts) == 3:
        value, currency, issuer = parts
        return value, currency, issuer
    return "", delivered, ""


async def credit_player_deposit(
    transport: Transport,
    txid: str,
    tag_registry: dict[int, str],
    expected_drops: str | None = None,
) -> PlayerCreditResult:
    """Attribute a validated deposit via its DestinationTag and credit it.

    The full custodial receiving discipline, in order:

      1. Gate on ``tesSUCCESS`` AND ``validated: true`` — nothing about an
         unvalidated tx is authoritative.
      2. Read the ``DestinationTag`` — an absent tag is unattributable
         (RequireDest exists to prevent this ever occurring).
      3. Look the tag up in the backend's OWN registry — the tag is a routing
         hint, not authentication; an unknown tag is held for manual review,
         never guessed.
      4. Credit ``delivered_amount`` — the validated-metadata figure that
         actually arrived — never the ``Amount`` field (the cap).

    ``expected_drops``, when given, must equal the credited figure exactly
    (the module's checkpoint assertion).
    """
    tx: TxInfo = await transport.fetch_tx(txid)
    checks: list[str] = []
    failures: list[str] = []

    # A read-back failure is NOT a tx failure (TXBCD-002 semantics) — but a
    # backend cannot credit what it cannot read, so it is an honest failed
    # credit here (retry the read, don't guess).
    if tx.fetch_error:
        failures.append(
            "Couldn't fetch the deposit to attribute it (network issue): "
            f"{tx.fetch_error}"
        )
        return PlayerCreditResult("", None, "", "", checks, failures)

    # Gate 1: tesSUCCESS + validated. Crediting anything earlier is the same
    # class of bug as crediting the Amount field.
    if tx.result_code != "tesSUCCESS":
        failures.append(
            f"Deposit is not tesSUCCESS (got {tx.result_code or 'not found'}) "
            "— never credit a failed or unknown transaction."
        )
        return PlayerCreditResult("", tx.destination_tag, "", tx.amount, checks, failures)
    checks.append("Result: tesSUCCESS")

    if not tx.validated:
        failures.append(
            "Deposit is not validated yet — wait for validated:true before "
            "crediting anything."
        )
        return PlayerCreditResult("", tx.destination_tag, "", tx.amount, checks, failures)
    checks.append("Validated: yes")

    # Gate 2: the tag must be present.
    tag = tx.destination_tag
    if tag is None:
        failures.append(
            "No DestinationTag on the deposit — the funds arrived but cannot "
            "be attributed to any player. This is exactly what asfRequireDest "
            "prevents: enable it on every custodial pool."
        )
        return PlayerCreditResult("", None, "", tx.amount, checks, failures)
    checks.append(f"DestinationTag present: {tag}")

    # Gate 3: the tag must resolve in OUR registry. A tag is a routing hint,
    # not authentication — anyone can send any tag, so an unknown one is held
    # for manual review, never trusted into a fresh account.
    player = tag_registry.get(tag, "")
    if not player:
        failures.append(
            f"Tag {tag} is not in the backend registry — a tag is a routing "
            "hint, NOT authentication (anyone can send any tag). Hold this "
            "deposit for manual review; never credit an unregistered tag."
        )
        return PlayerCreditResult("", tag, "", tx.amount, checks, failures)
    checks.append(
        f"Tag {tag} -> player '{player}' (validated against OUR registry — "
        "the tag alone proves nothing)"
    )

    # Gate 4: credit delivered_amount, never Amount.
    credited = tx.delivered_amount
    if not credited or credited == "unavailable":
        failures.append(
            "delivered_amount is absent/unavailable on this deposit — do NOT "
            "fall back to the Amount field (the cap); that is the "
            "partial-payment exploit."
        )
        return PlayerCreditResult(player, tag, "", tx.amount, checks, failures)

    # F-c918543c: delivered_amount is XRP-or-issued-currency polymorphic
    # (see _split_delivered_amount / the PlayerCreditResult docstring). Do
    # NOT assume drops — derive the real value with its correct
    # currency/issuer, and only ever call it "drops" when it actually is.
    value, currency, issuer = _split_delivered_amount(credited)
    is_xrp = currency == "XRP"
    unit_desc = "drops" if is_xrp else (
        f"{currency} (issuer {issuer})" if issuer else currency
    )
    checks.append(
        f"Credited {value} {unit_desc} to '{player}' from delivered_amount "
        f"(the Amount field claimed {tx.amount} — equal here, but a correct "
        "backend reads delivered_amount every time, not just when they differ)"
    )

    if tx.source_tag is not None:
        checks.append(
            f"SourceTag {tx.source_tag} present — the sender's return/bounce "
            "routing hint; echo it as the DestinationTag on any refund"
        )

    if expected_drops is not None and credited != str(expected_drops):
        failures.append(
            f"Credited amount mismatch: expected {expected_drops} drops, "
            f"delivered_amount says {credited}"
        )

    return PlayerCreditResult(
        player=player,
        tag=tag,
        credited_drops=value if is_xrp else "",
        amount_field=tx.amount,
        checks=checks,
        failures=failures,
        currency=currency,
        issuer=issuer,
        credited_value=value,
    )
