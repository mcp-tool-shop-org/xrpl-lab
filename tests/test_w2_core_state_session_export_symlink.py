"""Wave-2 core-state regression tests — session-export directory-symlink
containment bypass.

F-e0127180: the RA-003 (F-a39c228a) realpath-containment gate in
``_collect_learner_artifacts`` computed its comparison root from
``workspace.resolve()`` (``workspace = learner_dir / ".xrpl-lab"``) AFTER
``workspace.is_dir()`` / ``.resolve()`` had already transparently followed
any symlink planted AT that position (``workspace.is_symlink()`` was never
checked). A submitted learner directory whose ``.xrpl-lab`` entry is a
DIRECTORY symlink to an arbitrary path made ``workspace_root`` become the
attacker-chosen TARGET itself, so every file under
``<target>/{proofs,reports,audit_packs,certificates}`` passed the
containment check trivially and was archived under the learner's name —
exfiltrating arbitrary facilitator-machine files into the shared cohort
archive produced by ``write_session_export`` / ``xrpl-lab session-export``.

This is a DIFFERENT, higher-up shape than
tests/test_reswarm4_reporting_audit.py::TestSessionExportSymlinkDefense::
test_symlinked_directory_contents_never_archived, which plants the symlink
one level deeper (``proofs/sub`` -> secret dir) and only happens to pass on
the installed Python 3.13 because ``Path.rglob`` defaults to
``recurse_symlinks=False`` — an incidental stdlib hardening this code does
not invoke or depend on. The symlink planted here sits ABOVE the
``rglob()`` call's root (at ``.xrpl-lab`` itself, and separately at the
learner directory itself), where ``recurse_symlinks`` has no effect at all:
the OS transparently resolves the leading symlink component before
``rglob`` ever starts walking, so this shape is unaffected by that stdlib
default either way and must be stopped by this module's own containment
logic.

Per the wave-2 advisor contract for F-e0127180: the containment root must
become ``learner_dir.resolve()``, not ``workspace.resolve()``; directory
symlinks on ``.xrpl-lab`` or any ``SESSION_EXPORT_INCLUDE_DIRS`` entry must
be SKIPPED, not followed; and the fix must not be a name denylist.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from xrpl_lab.reporting import _collect_learner_artifacts, write_session_export

SECRET_CONTENT = "TOP SECRET DATA THAT SHOULD NEVER LEAVE THIS MACHINE"


def _symlink_or_skip(link: Path, target: Path) -> None:
    """Create a directory symlink or skip where the platform forbids it
    (Windows without Developer Mode / SeCreateSymbolicLinkPrivilege)."""
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - env
        pytest.skip(f"symlinks unavailable on this platform: {exc}")


def _build_cohort_with_symlinked_workspace(tmp_path: Path) -> Path:
    """cohort/mallory/.xrpl-lab -> secret_area (a DIRECTORY symlink).

    ``secret_area/proofs/other_persons_secret.txt`` holds sentinel content
    that must never be reachable through learner "mallory". This is the
    exact shape from the audit's empirical proof for F-e0127180.
    """
    secret_area = tmp_path / "secret_area"
    (secret_area / "proofs").mkdir(parents=True)
    (secret_area / "proofs" / "other_persons_secret.txt").write_text(
        SECRET_CONTENT, encoding="utf-8"
    )

    cohort = tmp_path / "cohort"
    mallory = cohort / "mallory"
    mallory.mkdir(parents=True)
    _symlink_or_skip(mallory / ".xrpl-lab", secret_area)
    return cohort


class TestWorkspaceItselfSymlinked:
    """F-e0127180 — ``.xrpl-lab`` itself is a directory symlink."""

    def test_collect_learner_artifacts_skips_symlinked_workspace(self, tmp_path):
        cohort = _build_cohort_with_symlinked_workspace(tmp_path)
        items = _collect_learner_artifacts(cohort / "mallory")
        assert items == []

    def test_session_export_never_archives_through_symlinked_workspace(
        self, tmp_path
    ):
        cohort = _build_cohort_with_symlinked_workspace(tmp_path)
        outfile = tmp_path / "session.tar.gz"
        summary = write_session_export(cohort, outfile, archive_format="tar.gz")

        with tarfile.open(outfile, "r:gz") as tar:
            names = tar.getnames()
            assert not any("other_persons_secret" in n for n in names)
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                fobj = tar.extractfile(member)
                assert fobj is not None
                content = fobj.read().decode("utf-8", errors="replace")
                assert SECRET_CONTENT not in content, member.name

        # The manifest must not carry the secret file either (metadata leak
        # + manifest/archive divergence, mirroring the existing RA-003
        # zip/tar.gz tests' manifest assertions).
        manifest = summary["manifest"]
        assert all(
            "other_persons_secret" not in f["path"] for f in manifest["files"]
        )


class TestLearnerDirectoryItselfSymlinked:
    """F-e0127180 — the learner submission directory itself is a symlink.

    Same root cause: ``write_session_export``'s per-learner ``iterdir()``
    loop calls ``sub.is_dir()``, which follows a symlink at ``sub`` just as
    transparently as ``workspace.is_dir()`` did for ``.xrpl-lab``.
    """

    def test_session_export_skips_symlinked_learner_directory(self, tmp_path):
        secret_area = tmp_path / "secret_area2"
        proofs = secret_area / ".xrpl-lab" / "proofs"
        proofs.mkdir(parents=True)
        (proofs / "other_persons_secret2.txt").write_text(
            SECRET_CONTENT, encoding="utf-8"
        )

        cohort = tmp_path / "cohort2"
        cohort.mkdir()
        _symlink_or_skip(cohort / "mallory2", secret_area)

        outfile = tmp_path / "session2.tar.gz"
        write_session_export(cohort, outfile, archive_format="tar.gz")

        with tarfile.open(outfile, "r:gz") as tar:
            names = tar.getnames()
            assert not any("other_persons_secret2" in n for n in names)
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                fobj = tar.extractfile(member)
                assert fobj is not None
                content = fobj.read().decode("utf-8", errors="replace")
                assert SECRET_CONTENT not in content, member.name


class TestLegitimateWorkspaceStillWorks:
    """Non-regression: an ordinary, non-symlinked learner workspace must
    still export normally after the containment-root fix."""

    def test_ordinary_learner_files_still_archived(self, tmp_path):
        cohort = tmp_path / "cohort3"
        ws = cohort / "alice" / ".xrpl-lab"
        (ws / "proofs").mkdir(parents=True)
        (ws / "proofs" / "real.json").write_text('{"ok": 1}', encoding="utf-8")

        outfile = tmp_path / "session3.tar.gz"
        summary = write_session_export(cohort, outfile, archive_format="tar.gz")

        with tarfile.open(outfile, "r:gz") as tar:
            names = set(tar.getnames())
        assert "alice/proofs/real.json" in names
        assert summary["files"] == 2  # MANIFEST.json + real.json
