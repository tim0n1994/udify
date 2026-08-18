"""
游戏目录候选根发现（iter4 M1 PR2，T1-ENGINE-AUTO 研究落地）。

用户给的路径可能不是真正的游戏根（例如解压后多了一层包装目录）。
discover_project_root 向下搜索，找到最像游戏根的目录——不靠单一文件，
而是按「证据强度」聚合：多个引擎指纹同时命中 → 高置信根。

设计原则（T1 研究结论）：
- 不靠单一文件：package.json 单独存在不一定是 RPGMV 根（也可能是 npm 项目）。
- 证据聚合：RPGMV 的 www/data/*.json + package.json（project name 含 rpg）才算强证据。
- 有限深度：最多向下搜 3 层，防 OOM 与超时。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class RootConfidence(StrEnum):
    """候选根的置信度。"""

    HIGH = "high"  # 多条引擎指纹同时命中
    MEDIUM = "medium"  # 单条强指纹或多条弱指纹
    LOW = "low"  # 仅弱迹象
    NONE = "none"  # 无任何游戏迹象


@dataclass(frozen=True, slots=True)
class CandidateRoot:
    """一个候选游戏根。"""

    path: Path
    confidence: RootConfidence
    signals: tuple[str, ...] = ()
    engine_hint: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "confidence": self.confidence.value,
            "signals": list(self.signals),
            "engine_hint": self.engine_hint,
        }


# 引擎指纹：文件相对路径 -> (signal_name, engine, strength)
# strength: 2 = definitive（单条即可），1 = strong（需配对），0.5 = weak
_ENGINE_FINGERPRINTS: list[tuple[str, str, str, float]] = [
    # RPG Maker MV
    ("package.json", "rpgmv_package_json", "rpg_maker_mv", 1.0),
    ("www/data/System.json", "rpgmv_system_json", "rpg_maker_mv", 2.0),
    ("www/data/Actors.json", "rpgmv_actors_json", "rpg_maker_mv", 1.0),
    ("www/js/main.js", "rpgmv_main_js", "rpg_maker_mv", 1.0),
    ("www/index.html", "rpgmv_index_html", "rpg_maker_mv", 1.0),
    # RPG Maker MZ
    ("package.json", "rpgmz_package_json", "rpg_maker_mz", 1.0),
    ("www/data/System.json", "rpgmz_system_json", "rpg_maker_mz", 2.0),
    ("www/js/rmmz_core.js", "rpgmz_core_js", "rpg_maker_mz", 2.0),
    # Godot
    ("project.godot", "godot_project_file", "godot", 2.0),
    ("export_presets.cfg", "godot_export_presets", "godot", 1.0),
    # Unity
    ("ProjectSettings/ProjectSettings.asset", "unity_project_settings", "unity", 2.0),
    ("Library/Bee/artifacts", "unity_bee_artifacts", "unity", 0.5),
    # miu2d
    ("index.html", "miu2d_index_html", "miu2d", 0.5),
    ("js/libs/pixi.js", "miu2d_pixi", "miu2d", 1.0),
]


def _score_dir(d: Path) -> tuple[float, tuple[str, ...], str]:
    """给一个目录打引擎指纹分。返回 (total_score, signals, top_engine)。"""
    total = 0.0
    signals: list[str] = []
    engine_scores: dict[str, float] = {}
    for rel, signal, engine, strength in _ENGINE_FINGERPRINTS:
        candidate = d / rel
        if candidate.exists():
            # RPGMV/MZ 的 package.json 太通用，只在 www/ 存在时才算分
            if signal in ("rpgmv_package_json", "rpgmz_package_json"):
                if not (d / "www").is_dir():
                    continue
            total += strength
            signals.append(signal)
            engine_scores[engine] = engine_scores.get(engine, 0.0) + strength
    top_engine = max(engine_scores, key=engine_scores.get) if engine_scores else "unknown"
    return total, tuple(signals), top_engine


def discover_project_root(
    start_path: str | Path,
    max_depth: int = 3,
    max_candidates: int = 50,
) -> CandidateRoot:
    """从 start_path 向下搜索最像游戏根的目录。

    策略：
    - 先给 start_path 本身打分。
    - 向下逐层（max_depth 层）搜索子目录，给每个打分。
    - 选总分最高的候选；并列时优先更浅的。
    - 全 0 分返回 start_path 本身 + NONE 置信度。

    Args:
        start_path: 用户给的初始路径。
        max_depth: 最大向下搜索深度。
        max_candidates: 最大候选目录数（防爆栈）。

    Returns:
        CandidateRoot。
    """
    start = Path(start_path).resolve()
    if not start.is_dir():
        return CandidateRoot(path=start, confidence=RootConfidence.NONE)

    candidates: list[tuple[int, Path, float, tuple[str, ...], str]] = []
    visited = 0

    # start 本身
    score, signals, engine = _score_dir(start)
    candidates.append((0, start, score, signals, engine))
    visited += 1

    # BFS 向下搜索
    queue: list[tuple[int, Path]] = [(0, start)]
    while queue and visited < max_candidates:
        depth, current = queue.pop(0)
        if depth >= max_depth:
            continue
        try:
            children = sorted(current.iterdir())
        except (PermissionError, OSError):
            continue
        for child in children:
            if not child.is_dir():
                continue
            # 跳过明显的非游戏目录
            name = child.name.lower()
            if name in {".git", "node_modules", "__pycache__", ".venv", "venv", "build", "dist"}:
                continue
            visited += 1
            if visited > max_candidates:
                break
            c_score, c_signals, c_engine = _score_dir(child)
            candidates.append((depth + 1, child, c_score, c_signals, c_engine))
            queue.append((depth + 1, child))

    # 选最高分；并列选更浅
    candidates.sort(key=lambda c: (-c[2], c[0]))
    best_depth, best_path, best_score, best_signals, best_engine = candidates[0]

    if best_score >= 3.0:
        confidence = RootConfidence.HIGH
    elif best_score >= 1.5:
        confidence = RootConfidence.MEDIUM
    elif best_score > 0:
        confidence = RootConfidence.LOW
    else:
        confidence = RootConfidence.NONE

    return CandidateRoot(
        path=best_path,
        confidence=confidence,
        signals=best_signals,
        engine_hint=best_engine,
    )
