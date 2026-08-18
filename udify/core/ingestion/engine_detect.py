"""
引擎识别器（iter4 M1，T1-ENGINE-AUTO 研究落地）。

字段级指纹识别 RPG Maker MV/MZ、Godot、miu2d。不靠单一文件——每个引擎多条证据，
按证据强度（definitive/strong/weak）与置信度判定。未知返回 unknown + diagnostics。

设计原则（T1 研究结论）：
- 不臆造：无法确凿识别时返回 unknown，不猜。
- 真实指纹：RPGMV 的 package.json + www/data/；Godot 的 project.godot；miu2d 的 index.html + 特征。
- 证据可追溯：每条证据标注 source_path + field + strength。
"""

from __future__ import annotations

import json
import os

from udify.models.detection import (
    DetectionBudget,
    DetectionDiagnostic,
    DetectionEvidence,
    DetectionResult,
    EngineId,
    EvidenceStrength,
    unknown_result,
)


def detect(game_root: str, budget: DetectionBudget | None = None) -> DetectionResult:
    """识别游戏目录的引擎类型。

    按优先级依次尝试各引擎指纹。首个 definitive 证据确定引擎；否则按证据聚合置信度。
    无任何证据返回 unknown。
    """
    budget = budget or DetectionBudget()
    root = os.path.abspath(game_root)
    evidence: list[DetectionEvidence] = []

    # RPG Maker MV
    rpgmv_ev = _detect_rpg_maker_mv(root)
    if rpgmv_ev:
        evidence.extend(rpgmv_ev)
        if any(e.strength == EvidenceStrength.DEFINITIVE for e in rpgmv_ev):
            return _result(EngineId.RPG_MAKER_MV, root, rpgmv_ev)

    # RPG Maker MZ
    rpgmz_ev = _detect_rpg_maker_mz(root)
    if rpgmz_ev:
        evidence.extend(rpgmz_ev)
        if any(e.strength == EvidenceStrength.DEFINITIVE for e in rpgmz_ev):
            return _result(EngineId.RPG_MAKER_MZ, root, rpgmz_ev)

    # Godot
    godot_ev = _detect_godot(root)
    if godot_ev:
        evidence.extend(godot_ev)
        if any(e.strength == EvidenceStrength.DEFINITIVE for e in godot_ev):
            return _result(EngineId.GODOT, root, godot_ev)

    # miu2d（浏览器引擎：index.html + 特征）
    miu2d_ev = _detect_miu2d(root)
    if miu2d_ev:
        evidence.extend(miu2d_ev)
        if any(e.strength == EvidenceStrength.DEFINITIVE for e in miu2d_ev):
            return _result(EngineId.MIU2D, root, miu2d_ev)

    if not evidence:
        return unknown_result(
            root,
            (DetectionDiagnostic("NO_FINGERPRINT", "未发现任何已知引擎指纹"),),
        )
    # 有弱证据但无 definitive
    confidence = sum(_strength_weight(e.strength) for e in evidence) / 4.0
    return DetectionResult(
        engine_id=EngineId.UNKNOWN,
        confidence=round(min(confidence, 0.49), 2),
        evidence=tuple(evidence),
        diagnostics=(DetectionDiagnostic("AMBIGUOUS", "存在弱证据但无法确凿判定"),),
        root_path=root,
    )


def _result(engine: EngineId, root: str, ev: list[DetectionEvidence]) -> DetectionResult:
    has_def = any(e.strength == EvidenceStrength.DEFINITIVE for e in ev)
    conf = 0.95 if has_def else 0.7
    return DetectionResult(engine_id=engine, confidence=conf, evidence=tuple(ev), root_path=root)


def _strength_weight(s: EvidenceStrength) -> float:
    return {
        EvidenceStrength.DEFINITIVE: 2.0,
        EvidenceStrength.STRONG: 1.0,
        EvidenceStrength.WEAK: 0.3,
    }.get(s, 0.0)


def _ev(
    kind: str,
    path: str,
    strength: EvidenceStrength,
    field: str = "",
    expected: str = "",
    actual: str = "",
) -> DetectionEvidence:
    return DetectionEvidence(
        kind=kind,
        source_path=path,
        field=field,
        expected=expected,
        actual=actual,
        strength=strength,
    )


def _read_json(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _detect_rpg_maker_mv(root: str) -> list[DetectionEvidence]:
    """RPG Maker MV 指纹：package.json(chgamename) + www/data/ + nwjs。"""
    ev: list[DetectionEvidence] = []
    pkg_path = os.path.join(root, "package.json")
    pkg = _read_json(pkg_path)
    if pkg is not None and isinstance(pkg, dict):
        # RPGMV 的 package.json 有 chgamename 或 name + www/
        if "chgamename" in pkg or "gameName" in pkg:
            ev.append(
                _ev(
                    "package.json",
                    "package.json",
                    EvidenceStrength.DEFINITIVE,
                    "chgamename",
                    actual=str(pkg.get("chgamename") or pkg.get("gameName")),
                )
            )
        elif "name" in pkg and os.path.isdir(os.path.join(root, "www")):
            ev.append(
                _ev(
                    "package.json+www",
                    "package.json",
                    EvidenceStrength.STRONG,
                    "name",
                    actual=str(pkg.get("name")),
                )
            )
    www_data = os.path.join(root, "www", "data")
    if os.path.isdir(www_data):
        actors = os.path.join(www_data, "Actors.json")
        enemies = os.path.join(www_data, "Enemies.json")
        if os.path.exists(actors) or os.path.exists(enemies):
            ev.append(
                _ev(
                    "www/data/*.json",
                    "www/data/",
                    EvidenceStrength.DEFINITIVE,
                    "Actors.json/Enemies.json",
                )
            )
    # nwjs 指纹
    if os.path.exists(os.path.join(root, "nwjs")) or os.path.exists(os.path.join(root, "Game.exe")):
        ev.append(_ev("nwjs/Game.exe", "Game.exe", EvidenceStrength.STRONG))
    return ev


def _detect_rpg_maker_mz(root: str) -> list[DetectionEvidence]:
    """RPG Maker MZ 指纹：package.json(engines/optimization) + www/data + nwjs。"""
    ev: list[DetectionEvidence] = []
    pkg_path = os.path.join(root, "package.json")
    pkg = _read_json(pkg_path)
    if pkg is not None and isinstance(pkg, dict):
        # MZ 的 package.json 通常有 engines.web 或 optimization 字段，且无 chgamename（MZ 用 Game.rmmzproject）
        web_main = os.path.exists(os.path.join(root, "www", "js", "main.js"))
        rmmz = os.path.exists(os.path.join(root, "Game.rmmzproject"))
        if rmmz:
            ev.append(_ev("Game.rmmzproject", "Game.rmmzproject", EvidenceStrength.DEFINITIVE))
        if web_main and os.path.isdir(os.path.join(root, "www", "data")):
            ev.append(_ev("www/js/main.js+data", "www/js/main.js", EvidenceStrength.STRONG))
    return ev


def _detect_godot(root: str) -> list[DetectionEvidence]:
    """Godot 指纹：project.godot（application/config/name 等 section）。"""
    ev: list[DetectionEvidence] = []
    proj = os.path.join(root, "project.godot")
    if os.path.exists(proj):
        try:
            with open(proj, encoding="utf-8") as f:
                content = f.read(4096)
            if "config_version" in content and "[application]" in content:
                ev.append(
                    _ev(
                        "project.godot",
                        "project.godot",
                        EvidenceStrength.DEFINITIVE,
                        "config_version+[application]",
                    )
                )
            elif "config_version" in content:
                ev.append(
                    _ev("project.godot", "project.godot", EvidenceStrength.STRONG, "config_version")
                )
        except OSError:
            pass
    # .godot/ 目录（Godot 4）
    if os.path.isdir(os.path.join(root, ".godot")):
        ev.append(_ev(".godot/", ".godot/", EvidenceStrength.STRONG))
    return ev


def _detect_miu2d(root: str) -> list[DetectionEvidence]:
    """miu2d 指纹：index.html + 特征（管理平台/游戏引擎的 web root）。"""
    ev: list[DetectionEvidence] = []
    idx = os.path.join(root, "index.html")
    if os.path.exists(idx):
        ev.append(_ev("index.html", "index.html", EvidenceStrength.WEAK))
    # miu2d 特征：admin/dashboard 相关（保守，需 RuntimeProfile 二次确认）
    if os.path.exists(os.path.join(root, "admin")) or os.path.exists(
        os.path.join(root, "dashboard")
    ):
        ev.append(_ev("admin/dashboard dir", "admin/", EvidenceStrength.WEAK))
    return ev
