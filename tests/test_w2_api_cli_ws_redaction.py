"""Wave-2 api-cli AMEND regression — F-d4a0435c (HIGH).

``_redact_output_text()`` is the ONLY sanitizer applied to the WS
``{"type": "output"}`` channel (``_QueueFile.write()``,
``xrpl_lab/api/runner_ws.py``), and it is structurally incapable of
catching a credential-bearing URL: its own module comment (above
``_PATH_START``) explains that the path-detection lookbehind exists
SPECIFICALLY so ``http://`` / ``https://`` text is never mistaken for a
path — proven by the paired ``test_does_not_mangle_urls`` regression test
in ``tests/test_reswarm4_api.py``, which pins that a bare explorer/faucet
URL passes through completely untouched. Because the function cannot tell
"safe default URL" from "operator-overridden URL with embedded
basic-auth", it provided zero defense once a credential-bearing URL
reached it (see F-9f0aa836's runtime.py call site for a confirmed
reachable instance, and handlers.py's ~30 similar ``console.print()``
sites — a different domain's file, not edited here).

Per the wave-2 advisor contract, the fix does NOT add a second,
independent URL-redaction scheme (that duplication is how the path-only
gate went unnoticed in the first place). It reuses the SAME
``xrpl_lab.reporting.sanitize_endpoint()`` already trusted for the
identical threat class on the proof-pack/doctor/feedback surfaces
(RA-002/F-60b2df48). Scope is deliberately narrow: only a URL carrying the
one UNAMBIGUOUS credential marker — embedded userinfo (``user[:pass]@``)
— is rewritten. A URL with no userinfo (including one with a meaningful
path, like a txid explorer link) must keep passing through byte-for-byte
untouched, because this channel's whole point is to show those links —
truncating a harmless path would be a regression of
``test_does_not_mangle_urls``, not a fix.

Run in isolation:
    python -m pytest tests/test_w2_api_cli_ws_redaction.py -q
"""

from __future__ import annotations

from xrpl_lab.api.runner_ws import _redact_output_text


def test_strips_userinfo_and_query_credentials_from_embedded_url() -> None:
    """Userinfo-bearing URL (query may ride along on the same span).

    F-cbd44005: this fixture alone does NOT prove query-key detection —
    the query token was previously stripped only because the userinfo
    match spanned the whole URL. Independent path-token and query-key
    fixtures live in tests/test_w4_api_cli_ws_redaction_shapes.py.
    """
    text = (
        "  Last response: Refusing to contact faucet: XRPL_LAB_FAUCET_URL "
        "points at a 'mainnet' endpoint "
        "(https://facilitator:hunter2@evil.example.com:8443/fund?token=SECRETTOKEN). "
        "XRPL Lab is testnet-only."
    )
    redacted = _redact_output_text(text)
    assert "hunter2" not in redacted, f"password leaked: {redacted!r}"
    assert "facilitator" not in redacted, f"username leaked: {redacted!r}"
    assert "SECRETTOKEN" not in redacted, f"query token leaked: {redacted!r}"
    # Reduced to scheme://host:port — the same reduction sanitize_endpoint()
    # already performs on the proof-pack/doctor/feedback surfaces.
    assert "https://evil.example.com:8443" in redacted


def test_strips_userinfo_only_url_with_no_password() -> None:
    """Userinfo without a password (``user@host``) is still a credential
    marker and must be stripped, not just the ``user:pass@`` shape."""
    text = "RPC: https://facilitator@rpc.example.com/v1 is unreachable"
    redacted = _redact_output_text(text)
    assert "facilitator@" not in redacted
    assert "facilitator" not in redacted
    assert "https://rpc.example.com" in redacted


def test_does_not_mangle_credential_free_urls_with_meaningful_paths() -> None:
    """Regression guard re-verifying test_does_not_mangle_urls under the
    NEW pass: a URL with NO userinfo — including one with a meaningful
    path, like a txid explorer link — must survive completely untouched.
    Reducing on sight (the way F-9f0aa836's runtime.py site correctly
    does for its OWN narrower, path-free context) would truncate the very
    path that makes this channel's links useful, which is exactly the
    regression the advisor contract forbids."""
    text = (
        "Explorer: https://testnet.xrpl.org/transactions/ABCDEF01 "
        "Faucet: https://faucet.altnet.rippletest.net/accounts"
    )
    assert _redact_output_text(text) == text


def test_does_not_mangle_url_path_segment_matching_a_redacted_dirname() -> None:
    """Re-verifies the existing path-redaction guarantee still holds when
    composed with the new URL-credential pass: a URL path segment shaped
    like a POSIX top-level directory name must not be caught by either
    pass when there is no userinfo present."""
    text = "See https://testnet.xrpl.org/etc/foo for details"
    assert _redact_output_text(text) == text


def test_path_redaction_still_applies_after_url_pass() -> None:
    """The two passes must compose: a genuine absolute path elsewhere in
    the same line is still redacted even when a credential-bearing URL
    was also present and rewritten."""
    text = (
        r"saved to C:\Users\mikey\.xrpl-lab\state.json after contacting "
        "https://facilitator:hunter2@evil.example.com/fund"
    )
    redacted = _redact_output_text(text)
    assert "mikey" not in redacted
    assert "<path-redacted>" in redacted
    assert "hunter2" not in redacted
    assert "https://evil.example.com" in redacted
