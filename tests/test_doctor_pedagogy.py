"""F-TESTS-C-005: pin the humanized doctor / error-catalog pedagogy.

This file is intentionally siloed from ``tests/test_api_contract.py`` to
avoid the wave-1 collision pattern (Bridge agent owns that file's P2
work). The pedagogical contract being protected here:

* The result-code catalog (``RESULT_CODE_INFO``) backs both the CLI
  ``xrpl-lab doctor`` surface AND the ``GET /api/doctor`` HTTP endpoint.
  Whichever surface a learner uses, the same humanized strings teach
  XRPL concepts (reserve activation, trust-line directionality, fee
  dynamics).
* The trust-line failure hint in ``handlers.py`` is the runtime
  teaching moment — when a learner's transfer fails with tecNO_LINE,
  the on-screen message must say "trust lines are directional" and
  point at the recipient's setup step.

Substring-only tests, no snapshot library — the test reads as the
pedagogical contract at a glance.
"""

from __future__ import annotations

from xrpl_lab.doctor import RESULT_CODE_INFO, explain_result_code


class TestResultCodeCatalogStructure:
    """The catalog is the single source of truth for both the CLI and
    HTTP doctor surfaces. Pin the keys and the schema-shape so a
    refactor that drops one of the four humanized entries (or drops
    the action/meaning fields) regresses loud."""

    def test_humanized_catalog_entries_present(self):
        """The four wave-3 humanized result codes must remain in the
        catalog (Backend P1 commit 76f3ac1)."""
        assert "tecNO_DST" in RESULT_CODE_INFO
        assert "tecNO_DST_INSUF_XRP" in RESULT_CODE_INFO
        assert "tecNO_LINE" in RESULT_CODE_INFO
        assert "telINSUF_FEE_P" in RESULT_CODE_INFO

    def test_each_entry_has_meaning_and_action(self):
        """Every catalog entry must carry both the explanation
        (meaning) and the recovery instruction (action). A future
        refactor that drops 'action' would silently regress the
        learner's "what do I do?" surface."""
        for code, info in RESULT_CODE_INFO.items():
            assert "meaning" in info, f"{code} missing 'meaning'"
            assert "action" in info, f"{code} missing 'action'"
            assert "category" in info, f"{code} missing 'category'"
            assert info["meaning"], f"{code} has empty meaning"
            assert info["action"], f"{code} has empty action"


class TestDoctorPedagogyHumanized:
    """Pin the load-bearing pedagogical strings for the four humanized
    catalog entries. These are the concept markers a future refactor
    must keep — full sentence equality would over-constrain."""

    def test_tec_no_dst_teaches_account_activation(self):
        info = explain_result_code("tecNO_DST")
        meaning = info["meaning"].lower()
        action = info["action"]
        # Concept: destination not on ledger / never funded.
        assert "ledger" in meaning or "exist" in meaning
        # Concept: send 10 XRP first to activate the account.
        assert "10 XRP" in action
        # Concept: 10 XRP is the base reserve, not arbitrary.
        assert "base reserve" in action or "activate" in action

    def test_tec_no_dst_insuf_xrp_teaches_minimum_balance_concept(self):
        info = explain_result_code("tecNO_DST_INSUF_XRP")
        meaning = info["meaning"]
        # Concept: the reserve is locked, not consumed.
        assert "lock" in meaning.lower()
        # Concept: 10 XRP is the floor.
        assert "10 XRP" in meaning
        # Concept: it's a minimum balance, distinct from a fee.
        assert "minimum balance" in meaning
        assert "not a fee" in meaning

    def test_tec_no_line_teaches_directional_trust_lines(self):
        info = explain_result_code("tecNO_LINE")
        meaning = info["meaning"]
        action = info["action"]
        # Concept: opt-in is required for issued tokens.
        assert "opt-in" in meaning or "opt in" in meaning
        # Concept: this is a security model — recipient chooses what
        # to accept.
        assert "security" in meaning.lower() or "decide" in meaning.lower()
        # Concept: the recipient must run 'set trust line' first.
        assert "set trust line" in action

    def test_tel_insuf_fee_teaches_dynamic_fees(self):
        info = explain_result_code("telINSUF_FEE_P")
        meaning = info["meaning"]
        action = info["action"]
        # Concept: testnet fee floor moves with load.
        assert "dynamically" in meaning
        # Concept: testnet spikes recover quickly.
        assert "testnet" in meaning.lower()
        # Concept: wait briefly is the canonical first response.
        assert "Wait" in action or "wait" in action


class TestTrustLineDirectionalHint:
    """Pin the wave-3 humanized trust-line failure hint in
    ``handlers.py`` (F-BACKEND-C-003). When a tecNO_LINE fires from
    the issuer's submit_payment side, the printed hint must teach the
    directional-trust-line concept inline.

    We don't run the handler end-to-end (that needs a transport mock);
    instead we read the source and assert the pedagogical phrase is
    present on the tecNO_LINE branch. This is a low-cost contract
    test that survives any refactor as long as the phrase stays in
    that file."""

    def test_handlers_py_teaches_trust_line_directionality(self):
        """The hint must contain the pedagogical phrase 'Trust lines
        are directional' AND point at the 'set trust line' step."""
        from pathlib import Path

        handlers_src = (
            Path(__file__).parent.parent / "xrpl_lab" / "handlers.py"
        ).read_text(encoding="utf-8")
        # Pedagogy: the directional concept.
        assert "Trust lines are directional" in handlers_src
        # Pedagogy: recipient sets up the trust line FIRST.
        assert "BEFORE you can send" in handlers_src
        # Pedagogy: the canonical step name.
        assert "set trust line" in handlers_src
