"""Wave-2 core-state regression test — support-bundle credential redaction.

F-d7ed6541: ``workshop.generate_support_bundle()`` embedded the raw,
unsanitized ``XRPL_LAB_RPC_URL`` / ``XRPL_LAB_FAUCET_URL`` values into the
``SupportBundle`` dataclass (``rpc_url=get_rpc_url()``,
``faucet_url=get_faucet_url()``) with no call to
``reporting.sanitize_endpoint()`` — even though this is the exact class of
bug RA-002/F-60b2df48 fixed everywhere else (reporting.py, audit.py,
doctor.py, and feedback.py all strip basic-auth userinfo / path tokens /
query API keys before an endpoint enters a shareable artifact).

``generate_support_bundle()`` backs the two LIVE CLI commands
``xrpl-lab feedback`` and ``xrpl-lab support-bundle``, and the bundle's own
``to_markdown()`` output explicitly tells the learner to paste the block
into a public GitHub issue — so the raw credential was one copy-paste away
from a public forum.

This mirrors tests/test_feedback.py::test_feedback_strips_rpc_credentials
but calls the REAL ``generate_support_bundle()`` and asserts on the REAL
``.to_json()`` / ``.to_markdown()`` output. No prior test called
``generate_support_bundle()`` at all — a repo-wide grep for the symbol
turns up only ``xrpl_lab/cli.py`` (the two call sites) and ``workshop.py``
(the definition) — so there was no existing coverage of this path to
repair, vacuous or otherwise; this test is net-new.
"""

from __future__ import annotations

import json

from xrpl_lab.state import LabState
from xrpl_lab.workshop import generate_support_bundle


def _bare_state() -> LabState:
    """Minimal LabState — avoids touching disk via load_state()."""
    return LabState(wallet_address="rTestAddr123", completed_modules=[], tx_index=[])


def test_support_bundle_strips_rpc_and_faucet_credentials(tmp_path, monkeypatch):
    # Same env + monkeypatch shape as test_feedback.py's analogous test —
    # generate_support_bundle() calls get_learner_status() (-> get_workspace_dir())
    # and run_doctor() (-> get_home_dir()/get_workspace_dir()) internally even
    # when an explicit `state` is passed, so both modules' dir lookups must be
    # redirected off the real home directory.
    monkeypatch.setattr("xrpl_lab.state.DEFAULT_HOME_DIR", tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_home_dir", lambda: tmp_path)
    monkeypatch.setattr("xrpl_lab.doctor.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr("xrpl_lab.workshop.get_workspace_dir", lambda: tmp_path / "ws")
    monkeypatch.setenv(
        "XRPL_LAB_RPC_URL",
        "https://user:hunter2@rpc.example.com:51234/?api_key=abc",
    )
    monkeypatch.setenv(
        "XRPL_LAB_FAUCET_URL",
        "https://tok3n@faucet.example.com/accounts?key=zzz",
    )

    bundle = generate_support_bundle(_bare_state())

    # The dataclass fields themselves must already be sanitized, not just
    # the rendered text — to_dict()/to_json() serialize these fields
    # directly, so the field is the actual boundary, not a formatting step.
    assert bundle.rpc_url == "https://rpc.example.com:51234"
    assert bundle.faucet_url == "https://faucet.example.com"
    assert "hunter2" not in bundle.rpc_url
    assert "api_key" not in bundle.rpc_url
    assert "tok3n" not in bundle.faucet_url
    assert "key=zzz" not in bundle.faucet_url

    as_json = bundle.to_json()
    as_md = bundle.to_markdown()
    for blob in (as_json, as_md):
        assert "hunter2" not in blob
        assert "api_key=abc" not in blob
        assert "tok3n" not in blob
        assert "key=zzz" not in blob
        # The diagnostic host must survive redaction.
        assert "rpc.example.com" in blob
        assert "faucet.example.com" in blob

    # Belt-and-suspenders: re-serialize to_dict() directly (not just the
    # to_json() string) so a future field added to to_dict() that forgets
    # to route through the already-sanitized dataclass fields still fails
    # here rather than passing because to_json()/to_markdown() happened to
    # only read the safe fields.
    dumped = json.dumps(bundle.to_dict())
    assert "hunter2" not in dumped
    assert "tok3n" not in dumped
