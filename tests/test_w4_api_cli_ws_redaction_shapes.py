"""Wave-4 api-cli AMEND regression — F-cbd44005 (HIGH).

``_redact_output_text`` / ``_redact_url_credentials`` must hand EACH of the
three credential shapes ``sanitize_endpoint`` strips to that one redactor:

1. basic-auth userinfo (``user[:pass]@``)
2. QuickNode-style path token (``https://x.quiknode.pro/<token>/``)
3. query API keys (``?api_key=`` / ``?token=``)

The wave-2 paired test only exercised userinfo; its query token was stripped
as a side effect of the userinfo span match. These fixtures isolate each
shape. Credential-free explorer/faucet links must stay byte-identical.

Run in isolation:
    python -m pytest tests/test_w4_api_cli_ws_redaction_shapes.py -q
"""

from __future__ import annotations

from xrpl_lab.api.runner_ws import _redact_output_text


def test_strips_userinfo_only_url() -> None:
    text = (
        "  Last response: Refusing to contact faucet: XRPL_LAB_FAUCET_URL "
        "points at a 'mainnet' endpoint "
        "(https://facilitator:hunter2@evil.example.com:8443/fund). "
        "XRPL Lab is testnet-only."
    )
    redacted = _redact_output_text(text)
    assert "hunter2" not in redacted, f"password leaked: {redacted!r}"
    assert "facilitator" not in redacted, f"username leaked: {redacted!r}"
    assert "https://evil.example.com:8443" in redacted


def test_strips_path_token_only_url() -> None:
    """QuikNode-style path token with NO userinfo and NO query creds."""
    text = (
        "  Last response: Refusing to contact RPC: XRPL_LAB_RPC_URL "
        "points at a 'mainnet' endpoint "
        "(https://x.quiknode.pro/AbCdEf0123456789SecretToken/). "
        "XRPL Lab is testnet-only."
    )
    redacted = _redact_output_text(text)
    assert "AbCdEf0123456789SecretToken" not in redacted, (
        f"path token leaked: {redacted!r}"
    )
    assert "https://x.quiknode.pro" in redacted


def test_strips_query_api_key_only_url() -> None:
    """Query API key with NO userinfo (the shape the vacuous w2 test missed)."""
    text = (
        "  Last response: Refusing to contact RPC: XRPL_LAB_RPC_URL "
        "points at a 'mainnet' endpoint "
        "(https://rpc.example.com:51234/rpc?api_key=SUPERSECRETKEY123). "
        "XRPL Lab is testnet-only."
    )
    redacted = _redact_output_text(text)
    assert "SUPERSECRETKEY123" not in redacted, f"api_key leaked: {redacted!r}"
    assert "https://rpc.example.com:51234" in redacted


def test_credential_free_explorer_and_faucet_links_byte_identical() -> None:
    text = (
        "Explorer: https://testnet.xrpl.org/transactions/ABCDEF01 "
        "Faucet: https://faucet.altnet.rippletest.net/accounts"
    )
    assert _redact_output_text(text) == text
