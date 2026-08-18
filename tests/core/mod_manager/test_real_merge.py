"""iter4 M3 — 多 Mod 三路合并测试（text/json）。"""

from __future__ import annotations

import json

from udify.core.mod_manager.real_merge import (
    ConflictKind,
    MergeFormat,
    ResolutionStrategy,
    merge,
)
from udify.core.mod_manager.real_merge.json_merge import merge_json_values


def test_ini_both_unchanged():
    base = "hp=100\natk=10\n"
    r = merge(base, base, base, MergeFormat.INI)
    assert r.fully_auto_merged
    assert r.merged_text == base


def test_ini_only_ours_changes():
    base = "hp=100\natk=10\n"
    ours = "hp=200\natk=10\n"
    theirs = "hp=100\natk=10\n"
    r = merge(base, ours, theirs, MergeFormat.INI)
    assert r.fully_auto_merged
    assert "hp=200" in r.merged_text


def test_ini_only_theirs_changes():
    base = "hp=100\natk=10\n"
    ours = "hp=100\natk=10\n"
    theirs = "hp=100\natk=99\n"
    r = merge(base, ours, theirs, MergeFormat.INI)
    assert r.fully_auto_merged
    assert "atk=99" in r.merged_text


def test_ini_non_overlapping_both_change():
    base = "hp=100\natk=10\n"
    ours = "hp=200\natk=10\n"
    theirs = "hp=100\natk=99\n"
    r = merge(base, ours, theirs, MergeFormat.INI)
    assert r.fully_auto_merged
    assert "hp=200" in r.merged_text
    assert "atk=99" in r.merged_text


def test_ini_same_field_different_value_conflict():
    base = "hp=100\n"
    ours = "hp=200\n"
    theirs = "hp=300\n"
    r = merge(base, ours, theirs, MergeFormat.INI)
    assert r.has_conflicts
    assert r.conflict_count >= 1
    assert r.merged_text is None
    manual = [h for h in r.hunks if h.strategy == ResolutionStrategy.MANUAL]
    assert len(manual) >= 1


def test_ini_both_change_same_value_auto():
    base = "hp=100\n"
    ours = "hp=200\n"
    theirs = "hp=200\n"
    r = merge(base, ours, theirs, MergeFormat.INI)
    assert r.fully_auto_merged
    assert "hp=200" in r.merged_text


def test_json_non_overlapping_keys():
    base = {"boss": {"hp": 100}, "hero": {"hp": 50}}
    ours = {"boss": {"hp": 200}, "hero": {"hp": 50}}
    theirs = {"boss": {"hp": 100}, "hero": {"hp": 99}}
    merged, conflicts = merge_json_values(base, ours, theirs)
    assert not conflicts
    assert merged["boss"]["hp"] == 200
    assert merged["hero"]["hp"] == 99


def test_json_same_field_different_value_conflict():
    base = {"boss": {"hp": 100}}
    ours = {"boss": {"hp": 200}}
    theirs = {"boss": {"hp": 300}}
    merged, conflicts = merge_json_values(base, ours, theirs)
    assert len(conflicts) == 1
    assert conflicts[0]["kind"] == ConflictKind.SAME_FIELD_DIFFERENT_VALUE.value


def test_json_type_mismatch_conflict():
    base = {"x": 100}
    ours = {"x": 200}
    theirs = {"x": "high"}
    merged, conflicts = merge_json_values(base, ours, theirs)
    assert len(conflicts) == 1
    assert conflicts[0]["kind"] == ConflictKind.TYPE_MISMATCH.value


def test_json_only_one_side_adds_key():
    base = {"a": 1}
    ours = {"a": 1, "b": 2}
    theirs = {"a": 1}
    merged, conflicts = merge_json_values(base, ours, theirs)
    assert not conflicts
    assert merged["b"] == 2


def test_json_both_add_same_key_same_value():
    base = {"a": 1}
    ours = {"a": 1, "b": 2}
    theirs = {"a": 1, "b": 2}
    merged, conflicts = merge_json_values(base, ours, theirs)
    assert not conflicts
    assert merged["b"] == 2


def test_json_merge_wrapper_roundtrip():
    base = json.dumps({"hp": 100, "name": "boss"})
    ours = json.dumps({"hp": 200, "name": "boss"})
    theirs = json.dumps({"hp": 100, "name": "boss", "def": 10})
    r = merge(base, ours, theirs, MergeFormat.JSON)
    assert r.fully_auto_merged
    out = json.loads(r.merged_text)
    assert out["hp"] == 200
    assert out["def"] == 10


def test_json_wrapper_invalid_json_manual():
    r = merge("{bad", '{"a":1}', '{"a":1}', MergeFormat.JSON)
    assert r.has_conflicts
    assert r.merged_text is None
