"""
Udify Preview Formatter

将 VFS Diff 转换为用户友好的预览格式。
"""

from __future__ import annotations

from typing import Any


class PreviewFormatter:
    """
    预览格式化器

    支持输出格式:
    - markdown: Markdown 表格
    - json: JSON
    - text: 纯文本
    - terminal: 带颜色的终端输出
    """

    def __init__(self, fmt: str = "terminal") -> None:
        self.fmt = fmt

    def format_diffs(self, diffs: list[dict[str, Any]]) -> str:
        """格式化 diff 列表"""
        if self.fmt == "markdown":
            return self._format_markdown(diffs)
        elif self.fmt == "json":
            import json

            return json.dumps(diffs, indent=2, ensure_ascii=False)
        elif self.fmt == "terminal":
            return self._format_terminal(diffs)
        else:
            return self._format_text(diffs)

    def _format_markdown(self, diffs: list[dict[str, Any]]) -> str:
        """Markdown 格式"""
        lines = ["# Mod 预览", ""]

        for diff in diffs:
            path = diff["path"]
            status = diff["status"]

            lines.append(f"## {path} ({status})")
            lines.append("")

            if status == "modified":
                lines.append("| 操作 | 内容 |")
                lines.append("|------|------|")
                for change in diff.get("diff", []):
                    op = "+" if change["type"] == "add" else "-"
                    content = change["line"].strip()
                    lines.append(f"| {op} | {content} |")
                lines.append("")
            elif status == "new":
                content = diff.get("current", "")
                lines.append("```")
                lines.append(content)
                lines.append("```")
                lines.append("")
            elif status == "deleted":
                original = diff.get("original", "")
                lines.append("```")
                lines.append(original)
                lines.append("```")
                lines.append("")

        return "\n".join(lines)

    def _format_terminal(self, diffs: list[dict[str, Any]]) -> str:
        """带颜色的终端格式"""
        lines = []

        # ANSI 颜色
        GREEN = chr(27) + "[92m"
        RED = chr(27) + "[91m"
        YELLOW = chr(27) + "[93m"
        chr(27) + "[96m"
        RESET = chr(27) + "[0m"
        BOLD = chr(27) + "[1m"

        lines.append(f"{BOLD}=== Mod 预览 ==={RESET}\n")

        stats = {"modified": 0, "new": 0, "deleted": 0}
        for diff in diffs:
            stats[diff["status"]] = stats.get(diff["status"], 0) + 1

        lines.append(
            f"修改: {YELLOW}{stats.get('modified', 0)}{RESET}  "
            f"新增: {GREEN}{stats.get('new', 0)}{RESET}  "
            f"删除: {RED}{stats.get('deleted', 0)}{RESET}\n"
        )

        for diff in diffs:
            path = diff["path"]
            status = diff["status"]

            if status == "modified":
                lines.append(f"{YELLOW}{BOLD}~ {path}{RESET}")
                for change in diff.get("diff", [])[:20]:
                    if change["type"] == "add":
                        lines.append(f"  {GREEN}+ {change['line'].rstrip()}{RESET}")
                    else:
                        lines.append(f"  {RED}- {change['line'].rstrip()}{RESET}")
                if len(diff.get("diff", [])) > 20:
                    lines.append(f"  ... 还有 {len(diff['diff']) - 20} 行变化 ...")

            elif status == "new":
                lines.append(f"{GREEN}{BOLD}+ {path}{RESET}")
                content = diff.get("current", "")
                for line in content.splitlines()[:10]:
                    lines.append(f"  {GREEN}{line}{RESET}")
                if len(content.splitlines()) > 10:
                    lines.append(f"  ... 还有 {len(content.splitlines()) - 10} 行 ...")

            elif status == "deleted":
                lines.append(f"{RED}{BOLD}- {path}{RESET}")
                original = diff.get("original", "")
                for line in original.splitlines()[:10]:
                    lines.append(f"  {RED}{line}{RESET}")
                if len(original.splitlines()) > 10:
                    lines.append(f"  ... 还有 {len(original.splitlines()) - 10} 行 ...")

            lines.append("")

        return "\n".join(lines)

    def _format_text(self, diffs: list[dict[str, Any]]) -> str:
        """纯文本格式"""
        lines = ["=== Mod 预览 ===", ""]

        for diff in diffs:
            path = diff["path"]
            status = diff["status"]

            if status == "modified":
                lines.append(f"[MODIFIED] {path}")
                for change in diff.get("diff", []):
                    prefix = "+ " if change["type"] == "add" else "- "
                    lines.append(f"  {prefix}{change['line'].strip()}")

            elif status == "new":
                lines.append(f"[NEW] {path}")
                content = diff.get("current", "")
                for line in content.splitlines()[:20]:
                    lines.append(f"  {line}")

            elif status == "deleted":
                lines.append(f"[DELETED] {path}")
                original = diff.get("original", "")
                for line in original.splitlines()[:20]:
                    lines.append(f"  {line}")

            lines.append("")

        return "\n".join(lines)

    def format_summary(self, stats: dict[str, Any]) -> str:
        """格式化统计摘要"""
        if self.fmt == "terminal":
            BOLD = chr(27) + "[1m"
            RESET = chr(27) + "[0m"
            CYAN = chr(27) + "[96m"

            lines = [
                f"{BOLD}=== 统计摘要 ==={RESET}",
                f"  节点数: {CYAN}{stats.get('node_count', 0)}{RESET}",
                f"  边数: {CYAN}{stats.get('edge_count', 0)}{RESET}",
                f"  操作数: {CYAN}{stats.get('operations', 0)}{RESET}",
                f"  修改文件: {CYAN}{stats.get('modified_files', 0)}{RESET}",
                f"  成本: ${CYAN}{stats.get('cost_spent', 0):.4f}{RESET}",
                f"  LLM 调用: {CYAN}{stats.get('llm_calls', 0)}{RESET}",
            ]
            return "\n".join(lines)
        else:
            lines = [
                "=== 统计摘要 ===",
                f"  节点数: {stats.get('node_count', 0)}",
                f"  边数: {stats.get('edge_count', 0)}",
                f"  操作数: {stats.get('operations', 0)}",
                f"  修改文件: {stats.get('modified_files', 0)}",
                f"  成本: ${stats.get('cost_spent', 0):.4f}",
                f"  LLM 调用: {stats.get('llm_calls', 0)}",
            ]
            return "\n".join(lines)
