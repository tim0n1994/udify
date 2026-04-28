"""
Udify Infrastructure - Audit Log

不可变审计日志，链式哈希保证完整性。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AuditEntry:
    """审计记录"""
    timestamp: str
    user_id: str
    session_id: str
    action: str
    details: Dict[str, Any]
    previous_hash: str
    entry_hash: str
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "action": self.action,
            "details": self.details,
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }


class AuditLog:
    """
    审计日志

    特性:
    - 不可变追加
    - 链式哈希（类似区块链）
    - 完整性验证
    - 按会话查询
    """

    def __init__(self) -> None:
        self._entries: List[AuditEntry] = []
        self._chain_hash: str = "0" * 64
        self._session_index: Dict[str, List[int]] = {}

    def append(
        self,
        user_id: str,
        session_id: str,
        action: str,
        details: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditEntry:
        """追加审计记录"""
        timestamp = datetime.now().replace(tzinfo=None).isoformat()

        # 计算当前记录哈希（不包含 previous_hash）
        data = {
            "timestamp": timestamp,
            "user_id": user_id,
            "session_id": session_id,
            "action": action,
            "details": details,
        }
        entry_hash = self._hash_data(data)

        # 计算链式哈希
        combined = f"{self._chain_hash}{entry_hash}"
        self._chain_hash = hashlib.sha256(combined.encode()).hexdigest()

        entry = AuditEntry(
            timestamp=timestamp,
            user_id=user_id,
            session_id=session_id,
            action=action,
            details=details,
            previous_hash=self._chain_hash,
            entry_hash=entry_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        index = len(self._entries)
        self._entries.append(entry)

        # 更新会话索引
        self._session_index.setdefault(session_id, []).append(index)

        return entry

    def _hash_data(self, data: Dict[str, Any]) -> str:
        """计算数据哈希"""
        canonical = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def verify_integrity(self) -> bool:
        """验证审计日志完整性"""
        current_hash = "0" * 64

        for entry in self._entries:
            # 验证 entry_hash
            data = {
                "timestamp": entry.timestamp,
                "user_id": entry.user_id,
                "session_id": entry.session_id,
                "action": entry.action,
                "details": entry.details,
            }
            expected_hash = self._hash_data(data)
            if expected_hash != entry.entry_hash:
                return False

            # 验证链式哈希
            combined = f"{current_hash}{entry.entry_hash}"
            expected_chain = hashlib.sha256(combined.encode()).hexdigest()
            if expected_chain != entry.previous_hash:
                return False

            current_hash = expected_chain

        return True

    def get_session_logs(self, session_id: str) -> List[AuditEntry]:
        """获取会话的审计日志"""
        indices = self._session_index.get(session_id, [])
        return [self._entries[i] for i in indices]

    def get_user_logs(self, user_id: str, limit: int = 100) -> List[AuditEntry]:
        """获取用户的审计日志"""
        results = [e for e in self._entries if e.user_id == user_id]
        return results[-limit:]

    def get_all_logs(self, limit: int = 1000) -> List[AuditEntry]:
        """获取所有日志"""
        return self._entries[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        action_counts: Dict[str, int] = {}
        for entry in self._entries:
            action_counts[entry.action] = action_counts.get(entry.action, 0) + 1

        return {
            "total_entries": len(self._entries),
            "unique_sessions": len(self._session_index),
            "action_breakdown": action_counts,
            "integrity_verified": self.verify_integrity(),
        }
