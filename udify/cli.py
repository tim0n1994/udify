"""
Udify CLI

命令行入口。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from udify.core.infrastructure.config_center import config
from udify.core.infrastructure.preview_formatter import PreviewFormatter
from udify.core.mod_manager.mod_exporter import ModExporter, ModManifest
from udify.core.pipeline import UdifyPipeline


def create_parser() -> argparse.ArgumentParser:
    """创建参数解析器"""
    parser = argparse.ArgumentParser(
        prog="udify",
        description="Udify - Intent-Driven Automated Content Transformation",
    )

    parser.add_argument(
        "--game-root",
        type=Path,
        default=Path("."),
        help="游戏根目录 (默认: 当前目录)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="配置文件路径 (JSON/YAML)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".udify/mods"),
        help="输出目录",
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # mod 命令
    mod_parser = subparsers.add_parser("mod", help="创建 Mod")
    mod_parser.add_argument("intent", help="修改意图（自然语言）")
    mod_parser.add_argument(
        "--user-id",
        default="cli_user",
        help="用户 ID",
    )
    mod_parser.add_argument(
        "--apply",
        action="store_true",
        help="直接应用（不预览）",
    )
    mod_parser.add_argument(
        "--name",
        help="Mod 名称",
    )
    mod_parser.add_argument(
        "--author",
        default="Udify CLI",
        help="作者",
    )
    mod_parser.add_argument(
        "--export",
        choices=["zip", "directory"],
        help="导出格式",
    )

    # preview 命令
    subparsers.add_parser("preview", help="预览当前修改")

    # apply 命令
    apply_parser = subparsers.add_parser("apply", help="应用待确认的 Mod")
    apply_parser.add_argument("session_id", help="会话 ID")

    # rollback 命令
    rollback_parser = subparsers.add_parser("rollback", help="回滚 Mod")
    rollback_parser.add_argument("session_id", help="会话 ID")

    # stats 命令
    subparsers.add_parser("stats", help="查看统计")

    # validate 命令
    subparsers.add_parser("validate", help="验证游戏目录")

    # serve 命令（SRV-01，2026-08 批次 4B）
    serve_parser = subparsers.add_parser("serve", help="启动本地 API 服务（产品化后端）")
    serve_parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    serve_parser.add_argument("--port", type=int, default=8765, help="端口（默认 8765）")
    serve_parser.add_argument(
        "--state-dir",
        type=Path,
        default=Path(".udify"),
        help="状态目录（jobs.db 与任务工件，默认 ./.udify）",
    )
    serve_parser.add_argument(
        "--json-logs",
        action="store_true",
        help="输出单行 JSON 结构化日志（OBS-02）",
    )

    return parser


async def cmd_mod(args: argparse.Namespace) -> int:
    """mod 命令——走单一编排入口。

    miu2d 游戏走 ``Miu2dClosedLoop``（批次 2 的黄金闭环：语义图→file_patch→VFS
    预览）；其它引擎回退到 ``UdifyPipeline``。
    """
    from udify.core.adapters.miu2d import Miu2dAdapter

    print(f"🎮 分析游戏目录: {args.game_root}")
    print(f"💭 意图: {args.intent}")

    # 检测是否为 miu2d → 走新编排入口
    adapter = Miu2dAdapter()
    detection = adapter.detect(args.game_root)
    use_miu2d_loop = detection.confidence.score > 0

    if use_miu2d_loop:
        from udify.core.miu2d_pipeline import Miu2dClosedLoop

        print(f"🛰️  引擎: miu2d (置信度 {detection.confidence.score:.2f}) → 黄金闭环")
        print()
        loop = Miu2dClosedLoop(args.game_root)
        loop_result = loop.run(args.intent)

        if not loop_result.success:
            print("❌ 失败!")
            for error in loop_result.errors:
                print(f"  - {error}")
            return 1

        # 认知层产物
        if loop_result.graph:
            tagged = [n for n in loop_result.graph.nodes if n.semantic_tags]
            print(f"🧠 语义图: {len(loop_result.graph.nodes)} 节点, {len(tagged)} 带标签")
        if loop_result.patch:
            modes = {op.execution_mode.value for op in loop_result.patch.operations}
            print(f"📦 计划: {len(loop_result.patch.operations)} 操作, 模式={modes}")
        print()

        formatter = PreviewFormatter(fmt="terminal")
        if loop_result.vfs_diffs:
            print(formatter.format_diffs(loop_result.vfs_diffs))
        else:
            print("⚠️  没有文件被修改（VFS 预览）")

        # 导出
        if args.export and loop_result.patch:
            exporter = ModExporter(args.output)
            manifest = ModManifest(
                mod_id="mod_miu2d",
                name=args.name or args.intent[:30],
                version="1.0.0",
                author=args.author,
                description=args.intent,
                modified_files=[d["path"] for d in loop_result.vfs_diffs],
            )
            output_path = exporter.export(loop_result.patch, manifest, format=args.export)
            print(f"\n📦 已导出: {output_path}")

        print("\n✅ VFS 预览完成（原文件未修改）")
        return 0

    # 非 miu2d：回退到 UdifyPipeline
    pipeline = UdifyPipeline(game_root=args.game_root)
    print()
    result = await pipeline.process_intent(
        user_id=args.user_id,
        intent=args.intent,
        preview_only=not args.apply,
    )

    # 认知层产物（让意图分类/参考/冲突第一次在 CLI 可见）
    if result.structured_intent:
        goal = result.structured_intent.primary_goal
        print(f"🧠 意图分类: {goal.get('type', 'unknown')} → {goal.get('target', '')}")
    if result.warnings:
        for w in result.warnings[:5]:
            print(f"  ⚠️  {w}")
    print()

    if not result.success:
        print("❌ 失败!")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    # 显示预览
    formatter = PreviewFormatter(fmt="terminal")

    if result.vfs_diffs:
        print(formatter.format_diffs(result.vfs_diffs))
    else:
        print("⚠️  没有文件被修改")

    print()
    print(formatter.format_summary(result.stats))

    # 导出
    if args.export and result.patch:
        exporter = ModExporter(args.output)
        manifest = ModManifest(
            mod_id=f"mod_{result.session_id[:8]}",
            name=args.name or args.intent[:30],
            version="1.0.0",
            author=args.author,
            description=args.intent,
            modified_files=[d["path"] for d in result.vfs_diffs],
        )
        output_path = exporter.export(result.patch, manifest, format=args.export)
        print(f"\n📦 已导出: {output_path}")

    if not args.apply:
        print(f"\n💡 使用 `udify apply {result.session_id}` 应用修改")

    return 0


async def cmd_preview(args: argparse.Namespace) -> int:
    """preview 命令"""
    pipeline = UdifyPipeline(game_root=args.game_root)
    diffs = pipeline.get_preview()

    if not diffs:
        print("没有待预览的修改")
        return 0

    formatter = PreviewFormatter(fmt="terminal")
    print(formatter.format_diffs(diffs))
    return 0


async def cmd_apply(args: argparse.Namespace) -> int:
    """apply 命令"""
    pipeline = UdifyPipeline(game_root=args.game_root)
    result = await pipeline.apply_pending_mod(args.session_id)

    if result.get("success"):
        print(f"✅ 已应用 {len(result.get('applied', []))} 个文件")
        return 0
    else:
        print("❌ 应用失败")
        for error in result.get("failed", []):
            print(f"  - {error}")
        return 1


async def cmd_rollback(args: argparse.Namespace) -> int:
    """rollback 命令"""
    pipeline = UdifyPipeline(game_root=args.game_root)
    success = pipeline.rollback_session(args.session_id)

    if success:
        print("✅ 已回滚")
        return 0
    else:
        print("❌ 回滚失败")
        return 1


async def cmd_stats(args: argparse.Namespace) -> int:
    """stats 命令"""
    pipeline = UdifyPipeline(game_root=args.game_root)
    stats = pipeline.get_stats()

    print("📊 统计")
    print(f"  会话数: {stats['sessions']['total_sessions']}")
    print(f"  活跃会话: {stats['sessions']['active_sessions']}")
    print(f"  总成本: ${stats['sessions']['total_cost']:.4f}")
    print(f"  总 LLM 调用: {stats['sessions']['total_llm_calls']}")
    return 0


async def cmd_validate(args: argparse.Namespace) -> int:
    """validate 命令"""
    from udify.core.perception.incremental_perception import IncrementalPerception

    perception = IncrementalPerception(args.game_root)
    graph = await perception.perceive()

    print("✅ 游戏目录验证通过")
    print(f"  节点数: {len(graph.nodes)}")
    print(f"  边数: {len(graph.edges)}")
    print(f"  资源数: {len(graph.assets)}")

    return 0


async def main() -> int:
    """主入口"""
    parser = create_parser()
    args = parser.parse_args()

    if args.config:
        from udify.core.infrastructure.config_loader import ConfigFileLoader

        loader = ConfigFileLoader(config)
        loader.load(args.config)

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "mod": cmd_mod,
        "preview": cmd_preview,
        "apply": cmd_apply,
        "rollback": cmd_rollback,
        "stats": cmd_stats,
        "validate": cmd_validate,
        "serve": cmd_serve,
    }

    handler = commands.get(args.command)
    if handler:
        return await handler(args)
    else:
        print(f"未知命令: {args.command}")
        return 1


async def cmd_serve(args: argparse.Namespace) -> int:
    """serve 命令——启动薄 API（ADR-v3-007：默认 127.0.0.1 单用户）。"""
    try:
        import uvicorn
    except ImportError:
        print("❌ 缺少 server 依赖，请先安装: pip install -e '.[server]'")
        return 1

    if args.json_logs:
        from udify.core.infrastructure.json_logging import configure_json_logging

        configure_json_logging()

    from udify.api.app import create_app

    app = create_app(state_dir=args.state_dir)
    print(f"🚀 Udify API: http://{args.host}:{args.port}/api/v0/healthz")
    print(f"📚 OpenAPI 文档: http://{args.host}:{args.port}/api/docs")
    print(f"💾 状态目录: {args.state_dir.resolve()}")
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="info"))
    await server.serve()
    return 0


def cli_entry() -> None:
    """CLI 入口点"""
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n已取消")
        sys.exit(130)


if __name__ == "__main__":
    cli_entry()
