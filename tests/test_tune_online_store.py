"""Online selection store persistence."""

from __future__ import annotations

from harnesslab.tune.online.store import OnlineSelectionStore


def test_record_and_reset(tmp_path) -> None:
    path = tmp_path / "online_selection.json"
    store = OnlineSelectionStore(path)
    assert store.get("a").trials == 0
    st = store.record("a", success=True)
    assert st.successes == 1 and st.trials == 1
    st2 = store.record("a", success=False)
    assert st2.successes == 1 and st2.trials == 2
    store.reset("a")
    assert store.get("a").trials == 0


def test_reset_all(tmp_path) -> None:
    path = tmp_path / "online_selection.json"
    store = OnlineSelectionStore(path)
    store.record("a", success=True)
    store.reset()
    assert not path.is_file()
