"""Facilitator commands: cohort-status, session-export, reset, curriculum manifest."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from tests.cov_cli._helpers import all_module_ids, invoke, make_state
from xrpl_lab.curriculum import build_graph
from xrpl_lab.curriculum_manifest import build_manifest
from xrpl_lab.errors import LabException, state_locked
from xrpl_lab.modules import load_all_modules
from xrpl_lab.state import LabState, load_state, state_path

ORDER = list(build_graph(load_all_modules()).canonical_order())


def _learner(
    cohort: Path,
    name: str,
    *,
    completed: list[str] | None = None,
    unverified: tuple[str, ...] = (),
    wallet: str | None = "rWALLET",
    proof: bool = False,
    cert: bool = False,
    raw_state: str | None = None,
) -> Path:
    ws = cohort / name / ".xrpl-lab"
    ws.mkdir(parents=True)
    if raw_state is not None:
        (ws / "state.json").write_text(raw_state, encoding="utf-8")
    else:
        st = LabState()
        st.wallet_address = wallet
        for mid in completed or []:
            st.complete_module(mid, txids=["T"], verified=mid not in unverified)
        (ws / "state.json").write_text(st.model_dump_json(indent=2), encoding="utf-8")
    if proof or cert:
        (ws / "proofs").mkdir()
    if proof:
        (ws / "proofs" / "xrpl_lab_proof_pack.json").write_text("{}", encoding="utf-8")
    if cert:
        (ws / "proofs" / "xrpl_lab_certificate.json").write_text("{}", encoding="utf-8")
    return ws


@pytest.fixture()
def cohort(lab) -> Path:
    c = lab.work / "cohort"
    c.mkdir()
    return c


# ── cohort-status ─────────────────────────────────────────────────────


def test_cohort_status_json_rows_are_sorted_and_carry_artifact_flags(lab, cohort):
    _learner(cohort, "zed", completed=ORDER[:2], proof=True)
    _learner(cohort, "amy", completed=ORDER[:1], unverified=(ORDER[0],), cert=True)
    (cohort / "no_workspace").mkdir()  # skipped silently: no state.json
    (cohort / "stray.txt").write_text("not a dir", encoding="utf-8")

    r = invoke(["cohort-status", "--dir", str(cohort), "--format", "json"])
    assert r.exit_code == 0, r.output
    d = json.loads(r.stdout)
    assert d["cohort_dir"] == "cohort"  # basename only, never the absolute path
    assert str(lab.tmp) not in r.stdout
    assert d["warnings"] == []
    assert [x["learner_id"] for x in d["learners"]] == ["amy", "zed"]
    amy, zed = d["learners"]
    assert amy["completed_count"] == 1 and zed["completed_count"] == 2
    assert amy["total_modules"] == len(ORDER)
    assert amy["all_verified"] is False and amy["unverified_modules"] == [ORDER[0]]
    assert zed["all_verified"] is True
    assert (amy["has_proof_pack"], amy["has_certificate"]) == (False, True)
    assert (zed["has_proof_pack"], zed["has_certificate"]) == (True, False)
    assert zed["current_module"] == ORDER[2]
    assert zed["last_activity"] is not None


def test_cohort_status_corrupt_state_becomes_a_warning_not_an_abort(lab, cohort):
    _learner(cohort, "good", completed=ORDER[:1])
    _learner(cohort, "bad", raw_state="{ truncated")
    r = invoke(["cohort-status", "--dir", str(cohort), "--format", "json"])
    assert r.exit_code == 0
    d = json.loads(r.stdout)
    assert [x["learner_id"] for x in d["learners"]] == ["good"]
    assert d["warnings"] == [{"learner_id": "bad", "error": "ValueError"}]


def test_cohort_status_unreadable_state_reports_type_name_only(
    lab, cohort, monkeypatch,
):
    _learner(cohort, "locked", completed=[])
    _learner(cohort, "fine", completed=[])
    import xrpl_lab.state as state_mod

    real = state_mod.load_state_from_path

    def _selective(path):
        if "locked" in str(path):
            raise PermissionError(f"denied: {path}")
        return real(path)

    monkeypatch.setattr(state_mod, "load_state_from_path", _selective)
    r = invoke(["cohort-status", "--dir", str(cohort), "--format", "json"])
    assert r.exit_code == 0
    d = json.loads(r.stdout)
    assert d["warnings"] == [{"learner_id": "locked", "error": "PermissionError"}]
    assert "denied" not in r.stdout and str(lab.tmp) not in r.stdout


def test_cohort_status_table_renders_progress_verification_and_warnings(
    lab, cohort, monkeypatch,
):
    monkeypatch.setenv("COLUMNS", "220")  # keep table cells on one line
    _learner(cohort, "ann", completed=ORDER[:2], unverified=(ORDER[1],), proof=True)
    _learner(cohort, "cal", completed=ORDER)
    _learner(cohort, "dud", raw_state="][")
    r = invoke(["cohort-status", "--dir", str(cohort)])
    assert r.exit_code == 0
    out = r.stdout
    assert "Cohort Status — cohort" in out
    assert "ann" in out and "cal" in out and "dud" in out
    assert f"2/{len(ORDER)}" in out
    assert "1 UNVERIFIED" in out
    assert "all verified" in out
    assert "(complete)" in out
    assert "proof" in out and "no-cert" in out
    assert "warning: ValueError" in out
    assert "1 learner(s) had unreadable state" in out


def test_cohort_status_csv_is_gradebook_ready_and_warnings_go_to_stderr(lab, cohort):
    _learner(cohort, "ann", completed=ORDER[:2], unverified=(ORDER[1],), proof=True)
    _learner(cohort, "bob", completed=[], wallet=None)
    _learner(cohort, "dud", raw_state="nope")
    r = invoke(["cohort-status", "--dir", str(cohort), "--format", "csv"])
    assert r.exit_code == 0
    rows = list(csv.DictReader(io.StringIO(r.stdout)))
    assert [x["learner_id"] for x in rows] == ["ann", "bob"]
    ann, bob = rows
    assert ann["completed_count"] == "2"
    assert ann["all_verified"] == "false"
    assert ann["unverified_modules"] == ORDER[1]
    assert ann["unverified_count"] == "1"
    assert ann["has_proof_pack"] == "true" and ann["has_certificate"] == "false"
    assert bob["wallet_address"] == "" and bob["all_verified"] == "true"
    assert bob["blockers"].startswith("No wallet yet")
    assert "warning: dud: ValueError" in r.stderr
    assert "dud" not in r.stdout


def test_cohort_status_single_shared_workspace_is_one_cohort_row(lab, cohort):
    _learner(cohort.parent, "cohort", completed=ORDER[:1])  # <cohort>/.xrpl-lab
    r = invoke(["cohort-status", "--dir", str(cohort), "--format", "json"])
    assert r.exit_code == 0
    d = json.loads(r.stdout)
    assert [x["learner_id"] for x in d["learners"]] == ["_cohort"]
    assert d["learners"][0]["completed_count"] == 1


def test_cohort_status_empty_directory_says_so(lab, cohort):
    text = invoke(["cohort-status", "--dir", str(cohort)])
    assert text.exit_code == 0
    assert "No learner workspaces found under cohort." in text.stdout
    js = json.loads(invoke(["cohort-status", "--dir", str(cohort), "--format", "json"]).stdout)
    assert js["learners"] == [] and js["warnings"] == []


def test_cohort_status_rejects_a_missing_directory_and_bad_format(lab):
    missing = invoke(["cohort-status", "--dir", str(lab.work / "nope")])
    assert missing.exit_code == 2
    assert "does not exist" in missing.output
    bad = invoke(["cohort-status", "--format", "xml"])
    assert bad.exit_code == 2
    assert "Invalid value for '--format'" in bad.output


# ── session-export ────────────────────────────────────────────────────


def _artifacts(cohort: Path, name: str) -> dict[str, bytes]:
    ws = cohort / name / ".xrpl-lab"
    files = {
        "proofs/xrpl_lab_proof_pack.json": b'{"p": 1}',
        "reports/m1.md": b"# report one\n",
        "audit_packs/a1.json": b'{"a": 1}',
        "certificates/c1.json": b'{"c": 1}',
    }
    for rel, data in files.items():
        f = ws / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    # secrets that must never ride into a cohort archive
    (ws / "proofs" / "wallet.json.bak").write_text("SEED", encoding="utf-8")
    (ws / "reports" / "State.json").write_text("PRIVATE", encoding="utf-8")
    (ws / "logs").mkdir(exist_ok=True)
    (ws / "logs" / "doctor.log").write_text("log", encoding="utf-8")
    return files


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def test_session_export_tar_gz_manifest_matches_the_archived_bytes(lab, cohort):
    files = _artifacts(cohort, "amy")
    out = lab.work / "out" / "session.tar.gz"
    r = invoke(["session-export", "--dir", str(cohort), "--outfile", str(out)])
    assert r.exit_code == 0, r.output
    assert "Exported 1 learner(s), 5 file(s)" in r.stdout.replace("\n", " ")
    with tarfile.open(out, "r:gz") as tar:
        names = sorted(tar.getnames())
        manifest = json.load(tar.extractfile("MANIFEST.json"))
        assert names == sorted(["MANIFEST.json", *(f"amy/{k}" for k in files)])
        for entry in manifest["files"]:
            assert _sha(tar.extractfile(entry["path"]).read()) == entry["sha256"]
    assert manifest["cohort_dir"] == "cohort"
    assert manifest["learners"] == ["amy"]
    assert {e["path"] for e in manifest["files"]} == {f"amy/{k}" for k in files}
    assert str(lab.tmp) not in json.dumps(manifest)
    assert not out.with_name(out.name + ".tmp").exists()


def test_session_export_zip_format_excludes_secret_name_variants(lab, cohort):
    files = _artifacts(cohort, "amy")
    _artifacts(cohort, "bob")
    out = lab.work / "session.zip"
    r = invoke(["session-export", "--dir", str(cohort), "--format", "zip",
                "--outfile", str(out)])
    assert r.exit_code == 0, r.output
    assert "Exported 2 learner(s), 9 file(s)" in r.stdout.replace("\n", " ")
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
        assert zf.read("amy/proofs/xrpl_lab_proof_pack.json") == files[
            "proofs/xrpl_lab_proof_pack.json"
        ]
        manifest = json.loads(zf.read("MANIFEST.json"))
    assert not any("wallet.json" in n or "state.json" in n.lower() for n in names)
    assert not any(n.endswith("doctor.log") for n in names)
    assert manifest["learners"] == ["amy", "bob"]


def test_session_export_default_name_lands_in_the_working_directory(lab, cohort):
    _artifacts(cohort, "amy")
    r = invoke(["session-export", "--dir", str(cohort)])
    assert r.exit_code == 0, r.output
    made = list(lab.work.glob("xrpl_lab_session_*.tar.gz"))
    assert len(made) == 1
    assert tarfile.is_tarfile(made[0])
    z = invoke(["session-export", "--dir", str(cohort), "--format", "zip"])
    assert z.exit_code == 0
    assert len(list(lab.work.glob("xrpl_lab_session_*.zip"))) == 1


def test_session_export_with_no_learners_writes_an_empty_manifest(lab, cohort):
    out = lab.work / "empty.tar.gz"
    r = invoke(["session-export", "--dir", str(cohort), "--outfile", str(out)])
    assert r.exit_code == 0
    assert "No learner workspaces found" in r.stdout
    assert "empty MANIFEST.json" in r.stdout.replace("\n", " ")
    with tarfile.open(out, "r:gz") as tar:
        assert tar.getnames() == ["MANIFEST.json"]
        manifest = json.load(tar.extractfile("MANIFEST.json"))
    assert manifest["learners"] == [] and manifest["files"] == []


def test_session_export_single_shared_workspace_is_keyed_cohort(lab, cohort):
    _artifacts(cohort.parent, "cohort")  # creates <cohort>/.xrpl-lab/...
    out = lab.work / "shared.zip"
    r = invoke(["session-export", "--dir", str(cohort), "--format", "zip",
                "--outfile", str(out)])
    assert r.exit_code == 0, r.output
    with zipfile.ZipFile(out) as zf:
        names = set(zf.namelist())
    assert "_cohort/proofs/xrpl_lab_proof_pack.json" in names
    assert not any(n.startswith("cohort/") for n in names)


# ── reset ─────────────────────────────────────────────────────────────


def test_reset_module_unknown_id_exits_2_before_any_change(lab):
    make_state(completed=ORDER[:1])
    r = invoke(["reset", "--module", "not_a_module", "--confirm"])
    assert r.exit_code == 2
    assert "Unknown module ID: 'not_a_module'" in r.stdout
    assert load_state().is_module_completed(ORDER[0])


def test_reset_module_not_completed_is_exit_1(lab):
    make_state(completed=[])
    r = invoke(["reset", "--module", ORDER[0], "--confirm"])
    assert r.exit_code == 1
    assert "not in completed_modules" in r.stdout


def test_reset_module_with_confirm_clears_only_that_module(lab):
    a, b = ORDER[0], ORDER[1]
    make_state(completed=[a, b], tx=[("TXA", a, True), ("TXB", b, True)], wallet="rKEEP")
    (lab.ws / "reports").mkdir(parents=True)
    (lab.ws / "reports" / f"{a}.md").write_text("# a", encoding="utf-8")
    (lab.ws / "reports" / f"{b}.md").write_text("# b", encoding="utf-8")
    r = invoke(["reset", "--module", a, "--confirm"])
    assert r.exit_code == 0, r.output
    assert f"Module '{a}' reset." in r.stdout
    assert "Cleared 1 tx record(s); report removed: True." in r.stdout
    st = load_state()
    assert not st.is_module_completed(a)
    assert st.is_module_completed(b)
    assert [t.txid for t in st.tx_index] == ["TXB"]
    assert st.wallet_address == "rKEEP"
    assert not (lab.ws / "reports" / f"{a}.md").exists()
    assert (lab.ws / "reports" / f"{b}.md").exists()


def test_reset_module_requires_typing_the_exact_module_id(lab):
    a = ORDER[0]
    make_state(completed=[a])
    wrong = invoke(["reset", "--module", a], input="nope\n")
    assert wrong.exit_code == 0
    assert "Cancelled. (Must type exactly:" in wrong.stdout
    assert load_state().is_module_completed(a)

    eof = invoke(["reset", "--module", a], input="")
    assert eof.exit_code == 0 and "Cancelled." in eof.stdout
    assert load_state().is_module_completed(a)

    ok = invoke(["reset", "--module", a], input=f"{a}\n")
    assert ok.exit_code == 0, ok.output
    assert "Wallet + other modules + audit packs preserved." in ok.stdout
    assert not load_state().is_module_completed(a)


def test_reset_module_lab_exception_uses_the_error_taxonomy_exit_code(lab, monkeypatch):
    make_state(completed=[ORDER[0]])

    def _locked(_module_id):
        raise LabException(state_locked())

    monkeypatch.setattr("xrpl_lab.state.reset_module", _locked)
    r = invoke(["reset", "--module", ORDER[0], "--confirm"])
    assert r.exit_code == 1  # STATE_ -> 1
    assert "STATE_LOCKED:" in r.stdout
    assert "Hint:" in r.stdout


def test_full_reset_requires_the_word_reset(lab):
    make_state(completed=ORDER[:1])
    lab.ws.mkdir()
    for typed in ("reset\n", "\n", ""):
        r = invoke(["reset"], input=typed)
        assert r.exit_code == 0
        assert "Cancelled" in r.stdout
        assert state_path().exists() and lab.ws.exists()


def test_full_reset_clears_state_and_workspace_but_keeps_the_wallet(lab):
    make_state(completed=ORDER[:1])
    wallet_file = lab.home / "wallet.json"
    wallet_file.write_text('{"seed": "s"}', encoding="utf-8")
    (lab.ws / "reports").mkdir(parents=True)
    r = invoke(["reset", "--keep-wallet"], input="RESET\n")
    assert r.exit_code == 0, r.output
    assert "State and workspace cleared." in r.stdout
    assert "--keep-wallet is redundant" in r.stdout
    assert not state_path().exists()
    assert not lab.ws.exists()
    assert wallet_file.exists()


# ── curriculum manifest ───────────────────────────────────────────────


def test_curriculum_manifest_json_is_the_canonical_manifest(lab):
    r = invoke(["curriculum", "manifest", "--json"])
    assert r.exit_code == 0
    d = json.loads(r.stdout)
    assert d == build_manifest().to_dict()
    assert [m["id"] for m in d["modules"]] == ORDER
    assert d["totals"]["modules"] == len(ORDER)


def test_curriculum_manifest_table_shows_tracks_and_totals(lab):
    r = invoke(["curriculum", "manifest"])
    assert r.exit_code == 0
    manifest = build_manifest()
    assert "XRPL Lab Curriculum Manifest" in r.stdout
    assert (
        f"Totals: {manifest.totals['modules']} modules across "
        f"{manifest.totals['tracks']} tracks"
    ) in " ".join(r.stdout.split())
    assert "Tracks:" in r.stdout
    assert all_module_ids()[0][:6] in r.stdout
