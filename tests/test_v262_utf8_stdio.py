"""2.6.2: the ``xrpl-lab`` entry point writes UTF-8 on Windows.

custodial_crediting_101 crashed with a UnicodeEncodeError when its output was
redirected under cp1252: only ``python -m xrpl_lab`` reconfigured the streams.
"""

from __future__ import annotations

import io
import sys

import pytest

import xrpl_lab.cli as cli


def _cp1252() -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252")


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_utf8_stdio_only_on_windows(monkeypatch: pytest.MonkeyPatch, platform: str) -> None:
    out, err = _cp1252(), _cp1252()
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    cli._utf8_stdio()
    expected = "utf-8" if platform == "win32" else "cp1252"
    assert out.encoding == expected and err.encoding == expected
    if platform == "win32":
        out.write("tag \u2192 player \u2713")  # the custodial lesson's arrow
        out.flush()


def test_the_cli_group_sets_utf8_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    calls: list[int] = []
    monkeypatch.setattr(cli, "_utf8_stdio", lambda: calls.append(1))
    result = CliRunner().invoke(cli.main, ["list"])
    assert result.exit_code == 0, result.output
    assert calls == [1]
