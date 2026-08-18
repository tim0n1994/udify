"""JSON 字段级递归三路合并（structured merge，保留键序）。"""

from __future__ import annotations

from typing import Any

from udify.core.mod_manager.real_merge.types import ConflictKind


def merge_json_values(base: Any, ours: Any, theirs: Any, path: str = "") -> tuple[Any, list[dict]]:
    """递归三路合并 JSON 值。

    Returns:
        (merged_value, conflicts)。conflicts 为空表示全自动合并成功。
    """
    conflicts: list[dict] = []

    # 类型不一致 → 冲突
    if not _same_type(ours, theirs):
        if ours == theirs:
            return ours, []
        conflicts.append(
            {
                "path": path,
                "base": base,
                "ours": ours,
                "theirs": theirs,
                "kind": ConflictKind.TYPE_MISMATCH.value,
                "rationale": f"类型冲突: ours={_tn(ours)} theirs={_tn(theirs)}",
            }
        )
        return base, conflicts

    # 都是 dict → 递归字段合并
    if isinstance(base, dict) and isinstance(ours, dict) and isinstance(theirs, dict):
        merged: dict[str, Any] = {}
        all_keys = list(base.keys())
        for k in ours:
            if k not in all_keys:
                all_keys.append(k)
        for k in theirs:
            if k not in all_keys:
                all_keys.append(k)
        for k in all_keys:
            b = base.get(k)
            o = ours.get(k)
            t = theirs.get(k)
            sub_path = f"{path}.{k}" if path else k
            # 仅 ours 加键
            if k not in base and k in ours and k not in theirs:
                merged[k] = o
                continue
            if k not in base and k not in ours and k in theirs:
                merged[k] = t
                continue
            # 双方都加同键
            if k not in base and k in ours and k in theirs:
                if o == t:
                    merged[k] = o
                else:
                    m, c = merge_json_values(None, o, t, sub_path)
                    merged[k] = m
                    conflicts.extend(c)
                continue
            # 都存在
            m, c = merge_json_values(b, o, t, sub_path)
            if c:
                conflicts.extend(c)
                merged[k] = m  # 保留 base 作占位
            else:
                merged[k] = m
        return merged, conflicts

    # 都是 list → 元素级合并（按索引）
    if isinstance(base, list) and isinstance(ours, list) and isinstance(theirs, list):
        max_len = max(len(base), len(ours), len(theirs))
        merged_list: list[Any] = []
        for i in range(max_len):
            b = base[i] if i < len(base) else None
            o = ours[i] if i < len(ours) else None
            t = theirs[i] if i < len(theirs) else None
            m, c = merge_json_values(b, o, t, f"{path}[{i}]")
            merged_list.append(m)
            conflicts.extend(c)
        return merged_list, conflicts

    # 标量：三方比较
    if ours == theirs:
        return ours, []
    if ours == base:
        return theirs, []  # ours 未改，取 theirs
    if theirs == base:
        return ours, []  # theirs 未改，取 ours
    # 双方改成不同标量 → 冲突
    conflicts.append(
        {
            "path": path,
            "base": base,
            "ours": ours,
            "theirs": theirs,
            "kind": ConflictKind.SAME_FIELD_DIFFERENT_VALUE.value,
            "rationale": "标量双方改成不同值",
        }
    )
    return base, conflicts


def _same_type(a: Any, b: Any) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return True
    if isinstance(a, list) and isinstance(b, list):
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return True
    return type(a) is type(b)


def _tn(v: Any) -> str:
    return type(v).__name__
