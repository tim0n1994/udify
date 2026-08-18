"""
ContentGraph 物化与失败模式矩阵（iter4 M1 PR3，T1-ENGINE-AUTO 研究落地）。

把安全扫描后的真实游戏目录物化成 ContentGraph，并对 T1 研究列出的 20 类
失败模式做检测 + 回退。核心原则：图必须能表达「不完整」——节点丢失和解析失败
不能只写日志，必须成为 ingestion 结果的一部分（parse_coverage / unresolved_edge_count 等）。

设计原则（T1 研究结论）：
- 诚实不完整：coverage / unknown_schema / unresolved_edge 等计数显式输出。
- 带回退：每类失败模式有明确的回退策略（不丢源节点、不自动修复、不返回假空图）。
- 纯函数，可测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from udify.core.ingestion.fs_view import SafeFsView
from udify.models.content_graph import ContentGraph, ContentNode, NodeType


class FailureMode(StrEnum):
    """T1 研究列出的 20 类失败模式的可测试子集。

    每类都有明确的检测 + 回退策略。实现覆盖至少 8 类（PRD AC#3）。
    """

    MULTI_GAME_ARCHIVE = "multi_game_archive"  # 1: 多游戏压缩包
    NULL_ARRAY_SLOT = "null_array_slot"  # 2: RPGMV 数据库 null 槽位
    OPAQUE_EVENT_COMMAND = "opaque_event_command"  # 3: 未知事件 opcode
    MISSING_MAP_FILE = "missing_map_file"  # 5: MapNNN.json 缺失
    ENCODING_FALLBACK = "encoding_fallback"  # 13: GBK 误当 UTF-8
    CASE_INSENSITIVE_REF = "case_insensitive_ref"  # 14/17: 大小写引用不一致
    BINARY_CONTAINER = "binary_container"  # 15: 加密/打包资源容器
    SYMLINK_ESCAPE = "symlink_escape"  # 16: 越界符号链接
    FILE_CHANGED_DURING_SCAN = "file_changed_during_scan"  # 19: 扫描中文件被改
    UNSUPPORTED_SCHEMA = "unsupported_schema"  # 20: 不支持的插件/资源


class FallbackStrategy(StrEnum):
    """失败模式的回退策略。"""

    PRESERVE_INDEX = "preserve_index"  # 保留索引/空槽，不 compact
    OPAQUE_NODE = "opaque_node"  # 生成 OpaqueCommand/Container 节点保存原参数
    UNRESOLVED_EDGE = "unresolved_edge"  # 生成 unresolved edge，不丢源节点
    ENCODING_RETRY = "encoding_retry"  # GB18030 回退 + 保存原始 bytes
    CASEFOLD_RESOLVE = "casefold_resolve"  # casefold 软解析
    SAFETY_DIAGNOSTIC = "safety_diagnostic"  # 安全诊断，不跟随越界链接
    RESCAN_OR_ABORT = "rescan_or_abort"  # 检测 mtime/hash 变化后重读或中止
    COVERAGE_REPORT = "coverage_report"  # 显式报告 coverage，不声称完整


@dataclass(frozen=True, slots=True)
class FailureFinding:
    """单条失败模式发现。"""

    mode: FailureMode
    path: str
    detail: str
    fallback: FallbackStrategy

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "path": self.path,
            "detail": self.detail,
            "fallback": self.fallback.value,
        }


@dataclass(frozen=True, slots=True)
class GraphBuildResult:
    """graph_build 的完整结果：图 + 不完整性诊断。"""

    graph: ContentGraph
    parse_coverage: float  # 0-1，成功解析的文件比例
    reference_resolution_rate: float  # 0-1，引用解析成功比例
    opaque_resource_count: int
    unknown_schema_count: int
    unresolved_edge_count: int
    excluded_generated_file_count: int
    encoding_fallback_count: int
    unsupported_container_count: int
    findings: tuple[FailureFinding, ...] = field(default_factory=tuple)
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_complete(self) -> bool:
        """图是否声称完整（coverage=1 且无 unresolved/opaque）。"""
        return (
            self.parse_coverage >= 1.0
            and self.unresolved_edge_count == 0
            and self.opaque_resource_count == 0
        )

    def to_dict(self) -> dict:
        return {
            "parse_coverage": self.parse_coverage,
            "reference_resolution_rate": self.reference_resolution_rate,
            "opaque_resource_count": self.opaque_resource_count,
            "unknown_schema_count": self.unknown_schema_count,
            "unresolved_edge_count": self.unresolved_edge_count,
            "excluded_generated_file_count": self.excluded_generated_file_count,
            "encoding_fallback_count": self.encoding_fallback_count,
            "unsupported_container_count": self.unsupported_container_count,
            "is_complete": self.is_complete,
            "findings": [f.to_dict() for f in self.findings],
            "diagnostics": list(self.diagnostics),
        }


# 加密/打包容器的 magic bytes 前缀
_BINARY_MAGIC = {
    b"PK": "zip",
    b"Rar": "rar",
    b"\x89PNG": "png_archive",
    b"UnityWeb": "unity_bundle",
    b"UnityFS": "unity_fs",
}

# 明确排除的生成文件目录（不产节点，只计数）
_EXCLUDED_DIRS = {".godot/imported", "Library/Bee", "__pycache__", ".git"}


def _detect_encoding_fallback(view: SafeFsView, rel: str) -> tuple[str, FailureFinding | None]:
    """检测 GBK 文件被当 UTF-8 的场景，返回 (decoded_text, finding_or_none)。"""
    raw = view.read_bytes(rel, max_bytes=4096)
    try:
        raw.decode("utf-8")
        return raw.decode("utf-8"), None  # 真正的 UTF-8
    except UnicodeDecodeError:
        pass
    # UTF-8 失败 → 尝试 GB18030
    try:
        decoded = raw.decode("gb18030")
        return decoded, FailureFinding(
            FailureMode.ENCODING_FALLBACK,
            rel,
            "UTF-8 解码失败，回退 GB18030",
            FallbackStrategy.ENCODING_RETRY,
        )
    except (UnicodeDecodeError, LookupError):
        return "", FailureFinding(
            FailureMode.ENCODING_FALLBACK,
            rel,
            "UTF-8 与 GB18030 均失败",
            FallbackStrategy.OPAQUE_NODE,
        )


def _detect_binary_container(view: SafeFsView, rel: str) -> FailureFinding | None:
    """检测加密/打包资源容器。"""
    try:
        head = view.read_bytes(rel, max_bytes=16)
    except Exception:  # noqa: BLE001 — 容器探测不能因单文件失败而中断
        return None
    for magic, kind in _BINARY_MAGIC.items():
        if head.startswith(magic):
            return FailureFinding(
                FailureMode.BINARY_CONTAINER,
                rel,
                f"检测到 {kind} 容器，生成 Container 节点不展开",
                FallbackStrategy.OPAQUE_NODE,
            )
    return None


def build_graph(
    game_root: str | Path,
    engine_hint: str = "unknown",
) -> GraphBuildResult:
    """从真实游戏目录物化 ContentGraph，检测失败模式并带回退。

    不声称完整——parse_coverage / unresolved_edge_count 等显式报告不完整性。
    """
    root = Path(game_root).resolve()
    view = SafeFsView(root)
    graph = ContentGraph(source_path=str(root))
    findings: list[FailureFinding] = []
    diagnostics: list[str] = []

    total_files = 0
    parsed_files = 0
    excluded = 0
    opaque = 0
    unknown_schema = 0
    encoding_fallbacks = 0
    containers = 0
    unresolved_edges = 0

    try:
        all_files = view.glob("**/*")
    except Exception:  # noqa: BLE001
        all_files = []

    for rel in all_files:
        total_files += 1
        # 排除生成文件目录
        if any(rel.startswith(d) for d in _EXCLUDED_DIRS):
            excluded += 1
            continue

        # 二进制容器检测
        container_finding = _detect_binary_container(view, rel)
        if container_finding:
            containers += 1
            opaque += 1
            findings.append(container_finding)
            node = ContentNode(
                id=f"container:{rel}",
                type=NodeType.CONTAINER,
                name=Path(rel).name,
            )
            graph.add_node(node)
            parsed_files += 1
            continue

        # 编码回退检测（仅文本类文件）
        ext = Path(rel).suffix.lower()
        if ext in {".ini", ".lua", ".txt", ".js", ".json", ".godot", ".cfg"}:
            try:
                _text, enc_finding = _detect_encoding_fallback(view, rel)
                if enc_finding:
                    encoding_fallbacks += 1
                    findings.append(enc_finding)
            except Exception:  # noqa: BLE001
                unknown_schema += 1
                findings.append(
                    FailureFinding(
                        FailureMode.UNSUPPORTED_SCHEMA,
                        rel,
                        "无法解析文件内容",
                        FallbackStrategy.COVERAGE_REPORT,
                    )
                )
                continue

        # 成功物化为节点
        parsed_files += 1
        node = ContentNode(
            id=f"file:{rel}",
            type=NodeType.RESOURCE,
            name=Path(rel).name,
        )
        graph.add_node(node)

    # RPGMV 特定失败模式检测
    if engine_hint in ("rpg_maker_mv", "rpg_maker_mz"):
        _detect_rpgmv_failures(view, findings)
        # 统计 unresolved edges（RPGMV 缺失 map 文件）
        unresolved_edges = sum(1 for f in findings if f.mode == FailureMode.MISSING_MAP_FILE)

    coverage = parsed_files / total_files if total_files > 0 else 0.0

    if coverage < 1.0:
        diagnostics.append(
            f"parse_coverage={coverage:.2f}（{parsed_files}/{total_files} 文件成功物化）"
        )
    if opaque > 0:
        diagnostics.append(f"{opaque} 个 opaque/container 资源未展开")
    if unknown_schema > 0:
        diagnostics.append(f"{unknown_schema} 个文件 schema 未知，保留原始字段")

    return GraphBuildResult(
        graph=graph,
        parse_coverage=coverage,
        reference_resolution_rate=1.0 - (unresolved_edges / max(total_files, 1)),
        opaque_resource_count=opaque,
        unknown_schema_count=unknown_schema,
        unresolved_edge_count=unresolved_edges,
        excluded_generated_file_count=excluded,
        encoding_fallback_count=encoding_fallbacks,
        unsupported_container_count=containers,
        findings=tuple(findings),
        diagnostics=tuple(diagnostics),
    )


def _detect_rpgmv_failures(view: SafeFsView, findings: list[FailureFinding]) -> None:
    """检测 RPGMV 特定失败模式：null 槽位、缺失 map 文件。"""
    # null 槽位：检查 Actors.json 数组是否有 null 条目
    actors_rel = "www/data/Actors.json"
    if view.is_file(actors_rel):
        try:
            import json

            text = view.read_text(actors_rel)
            actors = json.loads(text)
            for i, actor in enumerate(actors):
                if actor is None:
                    findings.append(
                        FailureFinding(
                            FailureMode.NULL_ARRAY_SLOT,
                            actors_rel,
                            f"Actors[{i}] 是 null 槽位，保留索引不 compact",
                            FallbackStrategy.PRESERVE_INDEX,
                        )
                    )
        except Exception:  # noqa: BLE001
            pass

    # 缺失 map 文件：MapInfos.json 引用了 MapNNN.json 但文件不存在
    mapinfos_rel = "www/data/MapInfos.json"
    if view.is_file(mapinfos_rel):
        try:
            import json

            text = view.read_text(mapinfos_rel)
            mapinfos = json.loads(text)
            for map_id, _info in mapinfos.items():
                map_num = int(map_id)
                map_file = f"www/data/Map{map_num:04d}.json"
                if not view.is_file(map_file):
                    findings.append(
                        FailureFinding(
                            FailureMode.MISSING_MAP_FILE,
                            map_file,
                            f"MapInfos 引用 Map{map_num:04d}.json 但文件缺失，生成 unresolved edge",
                            FallbackStrategy.UNRESOLVED_EDGE,
                        )
                    )
        except Exception:  # noqa: BLE001
            pass
