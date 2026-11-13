"""'Last completed' on a clock tie.

On Windows before Python 3.13, ``time.time()`` moves in ticks of about 15 ms,
so modules completed in quick succession share a ``completed_at``. A plain
``max`` then returned the first tied module. These tests force the tie, so
they hold on every platform and Python.
"""

from __future__ import annotations

from xrpl_lab import state as state_mod
from xrpl_lab.state import CompletedModule, LabState
from xrpl_lab.workshop import get_learner_status

TIE = 1_794_500_000.0


def _tied_state(monkeypatch, ids: list[str]) -> LabState:
    monkeypatch.setattr(state_mod.time, "time", lambda: TIE)
    state = LabState()
    for mid in ids:
        state.complete_module(mid, txids=[f"TX_{mid}"])
    return state


def test_no_completed_modules_gives_none():
    assert LabState().latest_completed() is None


def test_a_tie_names_the_module_completed_last(monkeypatch):
    state = _tied_state(monkeypatch, ["first", "second", "third"])
    assert {m.completed_at for m in state.completed_modules} == {TIE}
    assert state.latest_completed().module_id == "third"


def test_a_later_time_beats_list_position():
    state = LabState()
    state.completed_modules = [
        CompletedModule(module_id="newest", completed_at=TIE + 5),
        CompletedModule(module_id="older", completed_at=TIE),
        CompletedModule(module_id="tied_older", completed_at=TIE),
    ]
    assert state.latest_completed().module_id == "newest"


def test_status_reports_the_last_module_on_a_tie(monkeypatch):
    state = _tied_state(monkeypatch, ["first", "second", "third"])
    assert get_learner_status(state).last_module == "third"
