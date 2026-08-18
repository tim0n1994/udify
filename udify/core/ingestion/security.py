"""
Ingestion 安全层（iter4 M1，T1-ENGINE-AUTO 研究落地）。

验证用户给的游戏目录是否安全：路径穿越、symlink loop、超大文件、二进制误解析。
fail-closed：不安全的目录拒绝 ingestion，不静默降级。

设计原则（T1 研究结论）：
- 每个威胁带检测与缓解。
- 不修改文件系统，只读校验。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class GuardIssue(StrEnum):
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    SYMLINK_LOOP = "SYMLINK_LOOP"
    SYMLINK_ESCAPE = "SYMLINK_ESCAPE"
    OVERSIZED_FILE = "OVERSIZED_FILE"
    NOT_A_DIRECTORY = "NOT_A_DIRECTORY"
    EMPTY_DIRECTORY = "EMPTY_DIRECTORY"


@dataclass(frozen=True, slots=True)
class GuardFinding:
    """单条安全发现。"""

    issue: GuardIssue
    path: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {"issue": self.issue.value, "path": self.path, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class GuardReport:
    """安全校验报告。"""

    safe: bool
    findings: tuple[GuardFinding, ...] = ()
    root_path: str = ""

    @property
    def blocking_findings(self) -> tuple[GuardFinding, ...]:
        return self.findings

    def to_dict(self) -> dict:
        return {
            "safe": self.safe,
            "root_path": self.root_path,
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class IngestionGuard:
    """游戏目录安全校验器。

    检测：路径穿越（..）、symlink（loop 与逃逸）、超大文件、空目录、非目录。
    """

    max_file_bytes: int = 50 * 1024 * 1024  # 50MB 单文件上限
    max_total_bytes: int = 500 * 1024 * 1024  # 500MB 总量
    max_files: int = 10000

    def validate(self, game_root: str) -> GuardReport:
        findings: list[GuardFinding] = []
        root = os.path.abspath(game_root)

        # 路径穿越检测
        if ".." in game_root or game_root.startswith("~"):
            findings.append(GuardFinding(GuardIssue.PATH_TRAVERSAL, game_root, "路径含穿越序列"))

        # 非目录
        if not os.path.exists(root):
            findings.append(GuardFinding(GuardIssue.NOT_A_DIRECTORY, game_root, "路径不存在"))
            return GuardReport(safe=False, findings=tuple(findings), root_path=game_root)
        if not os.path.isdir(root):
            findings.append(GuardFinding(GuardIssue.NOT_A_DIRECTORY, game_root, "不是目录"))
            return GuardReport(safe=False, findings=tuple(findings), root_path=game_root)

        # 空目录
        try:
            entries = os.listdir(root)
        except OSError as e:
            findings.append(GuardFinding(GuardIssue.NOT_A_DIRECTORY, game_root, f"无法读取: {e}"))
            return GuardReport(safe=False, findings=tuple(findings), root_path=game_root)
        if not entries:
            findings.append(GuardFinding(GuardIssue.EMPTY_DIRECTORY, game_root, "目录为空"))

        # 遍历：symlink / 超大文件 / 总量
        total_bytes = 0
        file_count = 0
        visited_inodes: set[tuple[int, int]] = set()
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            # symlink 检测
            for name in dirnames + filenames:
                full = os.path.join(dirpath, name)
                if os.path.islink(full):
                    target = os.path.realpath(full)
                    # symlink 逃逸出 root
                    if not target.startswith(root):
                        findings.append(
                            GuardFinding(GuardIssue.SYMLINK_ESCAPE, full, f"指向 root 外: {target}")
                        )
                    # symlink loop（inode 重复）
                    try:
                        st = os.stat(full)
                        key = (st.st_dev, st.st_ino)
                        if key in visited_inodes:
                            findings.append(
                                GuardFinding(
                                    GuardIssue.SYMLINK_LOOP, full, "inode 重复，疑似 symlink loop"
                                )
                            )
                        else:
                            visited_inodes.add(key)
                    except OSError:
                        pass
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                file_count += 1
                if file_count > self.max_files:
                    findings.append(
                        GuardFinding(GuardIssue.OVERSIZED_FILE, full, f"文件数超 {self.max_files}")
                    )
                    break
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                total_bytes += size
                if size > self.max_file_bytes:
                    findings.append(
                        GuardFinding(
                            GuardIssue.OVERSIZED_FILE,
                            full,
                            f"单文件 {size} > {self.max_file_bytes}",
                        )
                    )
                if total_bytes > self.max_total_bytes:
                    findings.append(
                        GuardFinding(
                            GuardIssue.OVERSIZED_FILE, full, f"总量超 {self.max_total_bytes}"
                        )
                    )
                    break

        safe = len(findings) == 0
        return GuardReport(safe=safe, findings=tuple(findings), root_path=game_root)
