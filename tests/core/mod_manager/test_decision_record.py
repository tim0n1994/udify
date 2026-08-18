"""Tests for decision record persistence (U5-MODSTACK-DEPENDENCY PR1)."""

from __future__ import annotations

import pytest

from udify.core.mod_manager.decision_record import (
    DecisionRecord,
    DecisionStore,
    compute_fingerprint,
)


def test_fingerprint_stable():
    a = compute_fingerprint("data/Enemies.json", "attack", "numeric")
    b = compute_fingerprint("data/Enemies.json", "attack", "numeric")
    assert a == b


def test_fingerprint_distinguishes_fields():
    a = compute_fingerprint("data/Enemies.json", "attack", "numeric")
    b = compute_fingerprint("data/Enemies.json", "hp", "numeric")
    assert a != b


def test_exact_lookup_only():
    fp = compute_fingerprint("f", "x", "t")
    store = DecisionStore({fp: DecisionRecord(fp, "keep_ours", "2026-01-01", ("A", "B"))})
    assert store.lookup(fp) is not None
    assert store.lookup("different") is None


def test_immutable_with_decision():
    store = DecisionStore({})
    fp = compute_fingerprint("f", "x", "t")
    updated = store.with_decision(DecisionRecord(fp, "d", "2026-01-01"))
    assert updated.lookup(fp) is not None
    assert store.lookup(fp) is None  # original unchanged


def test_record_frozen():
    r = DecisionRecord("fp", "d", "2026-01-01")
    with pytest.raises(AttributeError):
        r.decision = "other"  # type: ignore[misc]


def test_to_dict_structure():
    fp = compute_fingerprint("f", "x", "t")
    r = DecisionRecord(fp, "keep", "2026-01-01", ("A",))
    assert r.to_dict()["mod_ids"] == ["A"]
