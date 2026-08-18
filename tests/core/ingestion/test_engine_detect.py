"""iter4 M1 — 引擎识别 + ingestion 安全测试。"""

from __future__ import annotations

import json
import os

from udify.core.ingestion.engine_detect import detect
from udify.core.ingestion.security import GuardIssue, IngestionGuard
from udify.models.detection import DetectionBudget, EngineId


def _write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def test_detect_rpg_maker_mv(tmp_path):
    _write(str(tmp_path / "package.json"), json.dumps({"chgamename": "TestGame"}))
    _write(str(tmp_path / "www" / "data" / "Actors.json"), "[]")
    r = detect(str(tmp_path))
    assert r.engine_id == EngineId.RPG_MAKER_MV
    assert r.has_definitive_evidence
    assert r.confidence >= 0.9


def test_detect_godot(tmp_path):
    _write(
        str(tmp_path / "project.godot"), 'config_version=5\n[application]\nconfig/name="MyGame"\n'
    )
    r = detect(str(tmp_path))
    assert r.engine_id == EngineId.GODOT
    assert r.has_definitive_evidence


def test_detect_unknown_empty_dir(tmp_path):
    r = detect(str(tmp_path))
    assert r.is_unknown
    assert r.confidence == 0.0
    assert any(d.code == "NO_FINGERPRINT" for d in r.diagnostics)


def test_detect_unknown_weak_evidence(tmp_path):
    _write(str(tmp_path / "index.html"), "<html></html>")
    r = detect(str(tmp_path))
    assert r.is_unknown
    assert r.confidence < 0.5
    assert any(d.code == "AMBIGUOUS" for d in r.diagnostics)


def test_detection_result_serializable(tmp_path):
    _write(str(tmp_path / "package.json"), json.dumps({"chgamename": "X"}))
    r = detect(str(tmp_path))
    d = r.to_dict()
    assert d["engine_id"] == "rpg_maker_mv"
    assert isinstance(d["evidence"], list)


def test_detection_budget_defaults():
    b = DetectionBudget()
    assert b.max_files > 0
    assert b.max_bytes > 0


def test_guard_rejects_nonexistent(tmp_path):
    g = IngestionGuard()
    r = g.validate(str(tmp_path / "nope"))
    assert not r.safe
    assert any(f.issue == GuardIssue.NOT_A_DIRECTORY for f in r.findings)


def test_guard_rejects_path_traversal():
    g = IngestionGuard()
    r = g.validate("../../etc")
    assert not r.safe
    assert any(f.issue == GuardIssue.PATH_TRAVERSAL for f in r.findings)


def test_guard_accepts_safe_dir(tmp_path):
    _write(str(tmp_path / "game.txt"), "ok")
    g = IngestionGuard()
    r = g.validate(str(tmp_path))
    assert r.safe
    assert len(r.findings) == 0


def test_guard_rejects_empty_dir(tmp_path):
    g = IngestionGuard()
    r = g.validate(str(tmp_path))
    assert not r.safe
    assert any(f.issue == GuardIssue.EMPTY_DIRECTORY for f in r.findings)


def test_guard_rejects_oversized_file(tmp_path):
    g = IngestionGuard(max_file_bytes=10)
    _write(str(tmp_path / "big.bin"), "x" * 100)
    r = g.validate(str(tmp_path))
    assert not r.safe
    assert any(f.issue == GuardIssue.OVERSIZED_FILE for f in r.findings)
