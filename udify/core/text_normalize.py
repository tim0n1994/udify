"""
共享的文本归一化与解析小工具。

抽取自 review 发现的多处重复逻辑（dangerous-API 归一化、INI 行校验、
约束表达式解析），避免三处 copy-paste。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def normalize_identifier(s: str) -> str:
    """归一化标识符/调用名：小写 + 去掉空白与点。

    使 ``os.execute`` / ``os . execute`` / ``OS.EXECUTE`` 都映射到 ``osexecute``，
    供危险 API 匹配与属性键比对复用。
    """
    return "".join(ch for ch in s.lower() if not ch.isspace() and ch != ".")


def is_valid_ini_line(stripped: str) -> bool:
    """判断一行（已 strip）是否是合法的 INI 行。

    合法：空行、注释（``;``/``#``）、``[section]``、或含 ``=`` 的键值行。
    """
    if not stripped or stripped.startswith((";", "#", "[")):
        return True
    return "=" in stripped


@dataclass(frozen=True)
class ConstraintExpr:
    """解析后的约束表达式（``factor <= 1.35`` → ConstraintExpr("factor","<=",1.35)）。"""

    attr: str
    op: str
    threshold: float

    def evaluate(self, actual: float) -> bool:
        return {
            "<=": actual <= self.threshold,
            ">=": actual >= self.threshold,
            "==": actual == self.threshold,
            "<": actual < self.threshold,
            ">": actual > self.threshold,
        }.get(self.op, False)


_CONSTRAINT_RE = re.compile(r"(\w+)\s*(<=|>=|==|<|>)\s*([\d.]+)")


def parse_constraint(expr: str) -> ConstraintExpr | None:
    """解析 ``attr OP number`` 形式的约束；无法解析返回 None。"""
    m = _CONSTRAINT_RE.match(expr.strip())
    if not m:
        return None
    try:
        return ConstraintExpr(m.group(1), m.group(2), float(m.group(3)))
    except ValueError:
        return None


def iter_constraints(expr: str) -> list[ConstraintExpr]:
    """提取约束字符串中所有 ``attr OP number`` 段（支持复合约束如
    ``"0.1 <= factor <= 5.0"`` → [ConstraintExpr("0.1"...), ConstraintExpr("factor"...)])。"""
    results: list[ConstraintExpr] = []
    for m in _CONSTRAINT_RE.finditer(expr):
        try:
            results.append(ConstraintExpr(m.group(1), m.group(2), float(m.group(3))))
        except ValueError:
            continue
    return results


def extract_attr_from_patch(patch_ops: Any, attr: str) -> float | None:
    """从一组 patch 操作的 payload 中提取某属性值（如 factor）。"""
    for op in patch_ops:
        payload = getattr(op, "payload", None)
        if isinstance(payload, dict) and attr in payload:
            try:
                return float(payload[attr])
            except (TypeError, ValueError):
                continue
    return None


__all__ = [
    "ConstraintExpr",
    "extract_attr_from_patch",
    "is_valid_ini_line",
    "iter_constraints",
    "normalize_identifier",
    "parse_constraint",
]
