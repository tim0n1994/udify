"""
Secure Tool Gateway —— 审计链（TOOL-GW-05）。

对应 ITERATION-PLAN-2026-07.md §4.3 与 §7.3。每次工具调用追加一条链式哈希
记录，保证可回放、可审计。复用基础设施层 AuditLog 的链式哈希思路。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ToolCallRecord:
    """一次工具调用的审计记录。"""

    timestamp: str
    tool_id: str
    capability: str
    args: dict[str, Any]
    requested_paths: list[str]
    risk: str  # RiskLevel 名
    decision: str  # allowed/blocked
    success: bool
    return_code: int | None = None
    duration_seconds: float = 0.0
    output_artifact: str | None = None  # 截断输出的落盘路径
    prev_hash: str = ""
    record_hash: str = ""


class ToolAuditChain:
    """工具调用审计链（链式哈希）。

    每条记录的 ``record_hash = sha256(prev_hash + canonical(record_fields))``，
    篡改任意一条都会使后续全部哈希断裂。
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._records: list[ToolCallRecord] = []
        self._store_path = store_path
        self._load()

    def append(self, record: ToolCallRecord) -> str:
        """追加一条记录，返回其哈希。"""
        prev = self._records[-1].record_hash if self._records else ""
        record.prev_hash = prev
        record.record_hash = self._hash(record)
        self._records.append(record)
        self._save()
        return record.record_hash

    def verify(self) -> bool:
        """校验整条链是否完整（未被篡改）。"""
        prev = ""
        for rec in self._records:
            if rec.prev_hash != prev:
                return False
            if self._hash(rec) != rec.record_hash:
                return False
            prev = rec.record_hash
        return True

    def records(self) -> list[ToolCallRecord]:
        return list(self._records)

    @staticmethod
    def _hash(record: ToolCallRecord) -> str:
        # 排除 record_hash 自身，对其余字段做规范化哈希
        d = asdict(record)
        d.pop("record_hash", None)
        d.pop("prev_hash", None)
        canonical = json.dumps(d, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _save(self) -> None:
        if self._store_path is None:
            return
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(r) for r in self._records]
        self._store_path.write_text(json.dumps(payload, indent=2, default=str))

    def _load(self) -> None:
        if not self._store_path or not self._store_path.exists():
            return
        data = json.loads(self._store_path.read_text())
        self._records = [ToolCallRecord(**d) for d in data]


def now_iso() -> str:
    return datetime.now().replace(tzinfo=None).isoformat()


__all__ = ["ToolAuditChain", "ToolCallRecord", "now_iso"]
