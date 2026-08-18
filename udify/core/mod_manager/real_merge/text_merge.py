"""ini/文本行级三路合并（diff3，基于 difflib.SequenceMatcher）。"""

from __future__ import annotations

import difflib

from udify.core.mod_manager.real_merge.types import ConflictKind, MergeHunk, ResolutionStrategy


def _lines(s: str) -> list[str]:
    """保留行尾的拆行（与 patch_executor 的字节稳定拆行一致）。"""
    if not s:
        return []
    parts = s.splitlines(keepends=True)
    return parts


def merge_ini_lines(base: str, ours: str, theirs: str) -> list[MergeHunk]:
    """base/ours/theirs 的行级三路合并。

    算法：对 base→ours 和 base→theirs 各做 SequenceMatcher，找出「稳定区」
    （两边都未改）、「ours 独改区」、「theirs 独改区」、「双改区」（冲突）。
    """
    base_l = _lines(base)
    ours_l = _lines(ours)
    theirs_l = _lines(theirs)

    sm_ours = difflib.SequenceMatcher(a=base_l, b=ours_l, autojunk=False)
    sm_theirs = difflib.SequenceMatcher(a=base_l, b=theirs_l, autojunk=False)

    ours_ops = sm_ours.get_opcodes()
    theirs_ops = sm_theirs.get_opcodes()

    # 构建每个 base 行的改动标记：None=未改，否则=新内容列表
    ours_changes: dict[int, list[str] | None] = {}  # base 行索引 -> 替换内容（None=删除占位）
    for tag, i1, i2, j1, j2 in ours_ops:
        if tag == "equal":
            continue
        new = ours_l[j1:j2]
        for bi in range(i1, i2):
            ours_changes[bi] = new if tag != "delete" else []
        if tag == "insert":
            ours_changes.setdefault(i1 - 1 if i1 > 0 else -1, [])
            # insert 在 i1 之前插入 new
            ours_changes[i1] = (
                ours_changes.get(i1, base_l[i1] if i1 < len(base_l) else "")
                if i1 < len(base_l)
                else new
            )
    theirs_changes: dict[int, list[str] | None] = {}
    for tag, i1, i2, j1, j2 in theirs_ops:
        if tag == "equal":
            continue
        new = theirs_l[j1:j2]
        for bi in range(i1, i2):
            theirs_changes[bi] = new if tag != "delete" else []

    hunks: list[MergeHunk] = []
    for i, bline in enumerate(base_l):
        oc = ours_changes.get(i)  # None = 未改；[] = 删除；[...] = 替换
        tc = theirs_changes.get(i)
        ours_changed = i in ours_changes
        theirs_changed = i in theirs_changes

        if not ours_changed and not theirs_changed:
            # 都未改 → 保留 base
            hunks.append(
                MergeHunk(
                    bline,
                    bline,
                    bline,
                    ConflictKind.NONE,
                    ResolutionStrategy.AUTO,
                    bline,
                    "双方均未修改",
                )
            )
            continue
        if ours_changed and not theirs_changed:
            # 仅 ours 改
            new = oc if oc is not None else []
            hunks.append(
                MergeHunk(
                    bline,
                    "".join(new),
                    bline,
                    ConflictKind.NONE,
                    ResolutionStrategy.AUTO,
                    "".join(new),
                    "仅 ours 修改",
                )
            )
            continue
        if theirs_changed and not ours_changed:
            new = tc if tc is not None else []
            hunks.append(
                MergeHunk(
                    bline,
                    bline,
                    "".join(new),
                    ConflictKind.NONE,
                    ResolutionStrategy.AUTO,
                    "".join(new),
                    "仅 theirs 修改",
                )
            )
            continue
        # 双方都改了
        o_val = oc if oc is not None else []
        t_val = tc if tc is not None else []
        if "".join(o_val) == "".join(t_val):
            # 改成了一样的 → 自动合并
            hunks.append(
                MergeHunk(
                    bline,
                    "".join(o_val),
                    "".join(t_val),
                    ConflictKind.NONE,
                    ResolutionStrategy.AUTO,
                    "".join(o_val),
                    "双方改成相同值",
                )
            )
        else:
            hunks.append(
                MergeHunk(
                    bline,
                    "".join(o_val),
                    "".join(t_val),
                    ConflictKind.SAME_FIELD_DIFFERENT_VALUE,
                    ResolutionStrategy.MANUAL,
                    None,
                    "双方改成不同值，需人工裁决",
                )
            )

    # 处理 base 之外的纯插入行（insert opcode where i1 >= len(base_l)）。
    # 这些行只在 theirs 中存在、base 没有，当前逐行循环会漏掉（M3 PR3 suffix_replay 暴露）。
    # 策略：ours 未插入的同位置 → theirs 的插入视为新增，自动取 theirs。
    for tag, i1, _i2, j1, j2 in theirs_ops:
        if tag != "insert" or i1 < len(base_l):
            continue
        inserted = "".join(theirs_l[j1:j2])
        if not inserted:
            continue
        # ours 是否也在末尾插入了同样内容
        ours_inserted = ""
        for otag, oi1, _oi2, oj1, oj2 in ours_ops:
            if otag == "insert" and oi1 >= len(base_l):
                ours_inserted = "".join(ours_l[oj1:oj2])
        if ours_inserted == inserted:
            hunks.append(
                MergeHunk(
                    "",
                    ours_inserted,
                    inserted,
                    ConflictKind.NONE,
                    ResolutionStrategy.AUTO,
                    inserted,
                    "双方都新增了相同行",
                )
            )
        elif not ours_inserted:
            hunks.append(
                MergeHunk(
                    "",
                    "",
                    inserted,
                    ConflictKind.NONE,
                    ResolutionStrategy.AUTO,
                    inserted,
                    "theirs 新增行",
                )
            )
        else:
            hunks.append(
                MergeHunk(
                    "",
                    ours_inserted,
                    inserted,
                    ConflictKind.SAME_FIELD_DIFFERENT_VALUE,
                    ResolutionStrategy.MANUAL,
                    None,
                    "双方在末尾新增了不同行，需人工裁决",
                )
            )
    return hunks
