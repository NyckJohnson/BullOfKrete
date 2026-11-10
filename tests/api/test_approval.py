"""Tests for `bull.Modules.api.approval`."""

from __future__ import annotations

import pytest

from bull.Modules.api.approval import authorize
from bull.Modules.api.Contracts import ApprovalNeeded
from bull.Modules.status.mocks import MockStatusStore


def _feature_store(slug: str = "add-x") -> MockStatusStore:
    store = MockStatusStore()
    store.start_feature(slug)
    store.calls.clear()
    return store


def _names(store: MockStatusStore) -> list[str]:
    return [name for name, _ in store.calls]


def test_approved_note_is_recorded_through_status_approve() -> None:
    store = MockStatusStore()
    authorize("Counter", "api change ok", store, {})
    assert ("approve", ("Counter", "api change ok")) in store.calls


def test_approved_note_is_approved_before_the_approval_is_taken() -> None:
    store = MockStatusStore()
    authorize("Counter", "note", store, {})
    names = _names(store)
    assert names.index("approve") < names.index("take_approval")


def test_approved_note_leaves_no_approval_behind() -> None:
    store = MockStatusStore()
    authorize("Counter", "note", store, {})
    assert store.status.approvals == ()


def test_stored_approval_is_taken_when_no_note_given() -> None:
    store = MockStatusStore()
    store.approve("Counter", "human said yes")
    store.calls.clear()
    authorize("Counter", None, store, {})
    assert ("take_approval", ("Counter",)) in store.calls
    assert store.status.approvals == ()


def test_stored_approval_does_not_call_approve() -> None:
    store = MockStatusStore()
    store.approve("Counter", "yes")
    store.calls.clear()
    authorize("Counter", None, store, {})
    assert "approve" not in _names(store)


def test_stored_approval_for_another_module_is_not_used() -> None:
    store = MockStatusStore()
    store.approve("Other", "yes")
    with pytest.raises(ApprovalNeeded):
        authorize("Counter", None, store, {})
    assert len(store.status.approvals) == 1


def test_stored_approval_wins_over_feature_pre_approval() -> None:
    store = _feature_store()
    store.approve("Counter", "yes")
    store.calls.clear()
    authorize("Counter", None, store, {"add-x": "new function"})
    assert "mark_contract_applied" not in _names(store)


def test_feature_mode_listed_contract_change_marks_it_applied() -> None:
    store = _feature_store()
    authorize("Counter", None, store, {"add-x": "new function"})
    assert ("mark_contract_applied", ("Counter",)) in store.calls
    assert store.status.feature is not None
    assert "Counter" in store.status.feature.applied_contracts


def test_feature_pre_approval_is_used_once_only() -> None:
    store = _feature_store()
    changes = {"add-x": "new function"}
    authorize("Counter", None, store, changes)
    with pytest.raises(ApprovalNeeded):
        authorize("Counter", None, store, changes)


def test_feature_pre_approval_for_one_module_does_not_cover_another() -> None:
    store = _feature_store()
    authorize("Counter", None, store, {"add-x": "x"})
    with pytest.raises(ApprovalNeeded):
        authorize("Store", None, store, {})


def test_feature_mode_without_listed_change_needs_approval() -> None:
    store = _feature_store()
    with pytest.raises(ApprovalNeeded):
        authorize("Counter", None, store, {})


def test_feature_mode_change_listed_for_another_feature_needs_approval() -> None:
    store = _feature_store("add-x")
    with pytest.raises(ApprovalNeeded):
        authorize("Counter", None, store, {"other-feature": "x"})


def test_app_mode_ignores_listed_contract_changes() -> None:
    store = MockStatusStore()
    with pytest.raises(ApprovalNeeded):
        authorize("Counter", None, store, {"add-x": "x"})


def test_no_approval_raises_the_exact_message() -> None:
    with pytest.raises(ApprovalNeeded) as caught:
        authorize("Counter", None, MockStatusStore(), {})
    assert caught.value.message == (
        'the Counter contract changed; the human must approve (bull status approve Counter "<note>")'
    )


def test_message_names_the_module_it_was_asked_about() -> None:
    with pytest.raises(ApprovalNeeded) as caught:
        authorize("Store", None, MockStatusStore(), {})
    assert "the Store contract changed" in caught.value.message
    assert "bull status approve Store" in caught.value.message


def test_refusal_marks_nothing_applied() -> None:
    store = _feature_store()
    with pytest.raises(ApprovalNeeded):
        authorize("Counter", None, store, {})
    assert "mark_contract_applied" not in _names(store)
