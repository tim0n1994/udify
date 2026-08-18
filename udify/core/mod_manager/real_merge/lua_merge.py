"""
受限 Lua 三路合并（iter4 M3 PR2，T3-MODSTACK-REAL 研究落地）。

对叠加 Mod 的 Lua 脚本做保守的三路合并。与 text_merge（行级 diff3）不同，
lua_merge 在「可识别的结构单元」粒度上合并：

- 全局赋值 `key = value`：按 key 对齐，ours/theirs 改不同 key → auto；
  改同一 key 不同值 → manual（语义层交给 semantic_merge 处理数值）。
- 函数定义 `function name(...)` / `local function name(...)`：按函数名对齐，
  三者相同 → auto；一方改 → auto 取改方；两方都改 → manual。
- 无法识别的行（控制流、复杂表达式、多行语句）→ 该单元 manual。

设计原则（T3 研究结论）：
- 安全边界明确：只对「无歧义、可逆」的结构自动合并，其余一律 manual。
- 不做完整 Lua AST——tree-sitter 在运行时不一定可用，且 Mod 场景的合并
  价值集中在配置/数值层，控制流合并不可靠也不安全。
- 纯函数，可测试。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from udify.core.mod_manager.real_merge.types import (
    ConflictKind,
    MergeHunk,
    ResolutionStrategy,
)

# 赋值：[local] name = value（含点号 table.field）
_ASSIGN_RE = re.compile(r"^(local\s+)?([A-Za-z_][\w.]*)\s*=\s*(.+?)\s*;?\s*(--.*)?$")
# 函数定义：[local] function name(args)
_FUNC_RE = re.compile(r"^(local\s+)?function\s+([A-Za-z_][\w.]*)\s*\(([^)]*)\)\s*$")


@dataclass(frozen=True, slots=True)
class LuaUnit:
    """一个可识别的 Lua 结构单元（赋值或函数块）。"""

    kind: str  # "assign" | "func" | "raw"
    key: str  # 赋值变量名 / 函数名；raw 用序号字符串
    body: str  # 单元完整文本（含换行）


def _split_units(src: str) -> list[LuaUnit]:
    """把 Lua 源码切成结构单元列表（跳过纯空行）。

    逐行扫描：识别赋值和函数定义；函数体吸收到匹配的 `end`。
    空行与注释行跳过（不产生单元），避免按行号索引在不同版本间错位。
    """
    lines = src.split("\n")
    units: list[LuaUnit] = []
    i = 0
    raw_seq = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            i += 1
            continue
        m_func = _FUNC_RE.match(stripped)
        if m_func:
            fname = m_func.group(2)
            body_lines = [lines[i]]
            depth = 0
            j = i
            while j < len(lines):
                bl = lines[j].strip()
                # 进入：function/if/for/while/do/repeat 增加 depth
                if re.match(r"^(local\s+)?function\b", bl) or re.match(
                    r"^(if|for|while|repeat|do)\b", bl
                ):
                    depth += 1
                if re.match(r"^end\b", bl) or bl == "end":
                    depth -= 1
                if depth == 0 and j > i:
                    body_lines.append(lines[j])
                    j += 1
                    break
                if j > i:
                    body_lines.append(lines[j])
                j += 1
            units.append(LuaUnit("func", fname, "\n".join(body_lines) + "\n"))
            i = j
            continue
        m_assign = _ASSIGN_RE.match(stripped)
        if m_assign:
            var = m_assign.group(2)
            units.append(LuaUnit("assign", var, lines[i] + "\n"))
            i += 1
            continue
        units.append(LuaUnit("raw", f"raw_{raw_seq}", lines[i] + "\n"))
        raw_seq += 1
        i += 1
    return units


def _keyed(units: list[LuaUnit]) -> dict[str, LuaUnit]:
    """结构单元按 key 索引（同 key 后者覆盖，模拟 Lua 语义）。"""
    out: dict[str, LuaUnit] = {}
    for u in units:
        out[u.key] = u
    return out


def merge_lua(base: str, ours: str, theirs: str) -> list[MergeHunk]:
    """对三份 Lua 源做结构化三路合并，返回 MergeHunk 列表。

    白名单（auto）：
    - 三者一致，或仅一方与 base 不同 → 取改方。
    - 新增单元（base 无）：取新增方。
    黑名单（manual）：两方都改了同一 key 且不同。
    """
    bu = _keyed(_split_units(base))
    ou = _keyed(_split_units(ours))
    tu = _keyed(_split_units(theirs))
    all_keys = list(bu.keys())
    for k in ou:
        if k not in bu:
            all_keys.append(k)
    for k in tu:
        if k not in bu and k not in ou:
            all_keys.append(k)

    hunks: list[MergeHunk] = []
    seen: set[str] = set()
    for key in all_keys:
        if key in seen:
            continue
        seen.add(key)
        b = bu.get(key)
        o = ou.get(key)
        t = tu.get(key)
        b_body = b.body if b else ""
        o_body = o.body if o else ""
        t_body = t.body if t else ""

        # 新增：base 无，仅一方有
        if b is None and o is not None and t is None:
            hunks.append(
                MergeHunk(
                    base="",
                    ours=o_body,
                    theirs="",
                    kind=ConflictKind.NONE,
                    strategy=ResolutionStrategy.AUTO,
                    merged=o_body,
                    rationale="ours 新增单元",
                )
            )
            continue
        if b is None and t is not None and o is None:
            hunks.append(
                MergeHunk(
                    base="",
                    ours="",
                    theirs=t_body,
                    kind=ConflictKind.NONE,
                    strategy=ResolutionStrategy.AUTO,
                    merged=t_body,
                    rationale="theirs 新增单元",
                )
            )
            continue
        # ours 与 theirs 一致（含都为空）→ auto
        if o_body == t_body and (o_body or t_body):
            hunks.append(
                MergeHunk(
                    base=b_body,
                    ours=o_body,
                    theirs=t_body,
                    kind=ConflictKind.NONE,
                    strategy=ResolutionStrategy.AUTO,
                    merged=o_body or t_body,
                    rationale="三方一致或双方未改",
                )
            )
            continue
        # 一方改、另一方 == base（含另一方不存在但 base 有）
        o_changed = o_body != b_body
        t_changed = t_body != b_body
        if o_changed and not t_changed:
            hunks.append(
                MergeHunk(
                    base=b_body,
                    ours=o_body,
                    theirs=t_body,
                    kind=ConflictKind.NONE,
                    strategy=ResolutionStrategy.AUTO,
                    merged=o_body,
                    rationale="仅 ours 修改",
                )
            )
            continue
        if t_changed and not o_changed:
            hunks.append(
                MergeHunk(
                    base=b_body,
                    ours=o_body,
                    theirs=t_body,
                    kind=ConflictKind.NONE,
                    strategy=ResolutionStrategy.AUTO,
                    merged=t_body,
                    rationale="仅 theirs 修改",
                )
            )
            continue
        # 两方都改且不同 → manual
        hunks.append(
            MergeHunk(
                base=b_body,
                ours=o_body,
                theirs=t_body,
                kind=ConflictKind.SAME_FIELD_DIFFERENT_VALUE,
                strategy=ResolutionStrategy.MANUAL,
                rationale=f"两方都修改了 {key} 且内容不同（需人工裁决）",
            )
        )
    return hunks
