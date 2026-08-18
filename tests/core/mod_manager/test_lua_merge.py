"""iter4 M3 PR2 — 受限 Lua 三路合并测试。

覆盖 T3-MODSTACK-REAL 研究落地的结构化合并边界：
全局赋值对齐、函数定义对齐、一方改/两方改、新增单元、raw 行兜底。
"""

from __future__ import annotations

from udify.core.mod_manager.real_merge.lua_merge import LuaUnit, merge_lua
from udify.core.mod_manager.real_merge.types import ResolutionStrategy

# --------------------------------------------------------------- structural alignment


class TestAssignmentAlignment:
    """全局赋值按变量名对齐。"""

    def test_both_change_different_fields_auto(self):
        """两个 Mod 改不同配置字段 → 全 auto，无冲突。"""
        base = "hp=100\natk=10\n"
        ours = "hp=200\natk=10\n"
        theirs = "hp=100\natk=20\n"
        hunks = merge_lua(base, ours, theirs)
        assert all(h.strategy == ResolutionStrategy.AUTO for h in hunks)
        merged = "".join(h.merged for h in hunks if h.merged)
        assert "hp=200" in merged
        assert "atk=20" in merged

    def test_both_change_same_field_different_manual(self):
        """两个 Mod 改同一字段不同值 → manual。"""
        base = "hp=100\n"
        ours = "hp=200\n"
        theirs = "hp=300\n"
        hunks = merge_lua(base, ours, theirs)
        manuals = [h for h in hunks if h.strategy == ResolutionStrategy.MANUAL]
        assert len(manuals) == 1
        assert "hp" in manuals[0].rationale

    def test_one_side_unchanged_auto(self):
        """仅 ours 改 → auto 取改方。"""
        base = "hp=100\n"
        ours = "hp=200\n"
        theirs = "hp=100\n"
        hunks = merge_lua(base, ours, theirs)
        hp_hunk = [h for h in hunks if h.ours == "hp=200\n"][0]
        assert hp_hunk.strategy == ResolutionStrategy.AUTO
        assert hp_hunk.merged == "hp=200\n"


class TestFunctionAlignment:
    """函数定义按函数名对齐。"""

    def test_both_add_different_functions_auto(self):
        """两个 Mod 各加一个不同函数 → auto。"""
        base = ""
        ours = "function on_win()\n  return 1\nend\n"
        theirs = "function on_lose()\n  return 2\nend\n"
        hunks = merge_lua(base, ours, theirs)
        assert all(h.strategy == ResolutionStrategy.AUTO for h in hunks)
        merged = "".join(h.merged for h in hunks if h.merged)
        assert "on_win" in merged
        assert "on_lose" in merged

    def test_both_change_same_function_manual(self):
        base = "function greet()\n  return 1\nend\n"
        ours = "function greet()\n  return 2\nend\n"
        theirs = "function greet()\n  return 3\nend\n"
        hunks = merge_lua(base, ours, theirs)
        manuals = [h for h in hunks if h.strategy == ResolutionStrategy.MANUAL]
        assert len(manuals) >= 1
        assert "greet" in manuals[0].rationale

    def test_one_side_change_function_auto(self):
        base = "function greet()\n  return 1\nend\n"
        ours = "function greet()\n  return 99\nend\n"
        theirs = "function greet()\n  return 1\nend\n"
        hunks = merge_lua(base, ours, theirs)
        assert all(h.strategy == ResolutionStrategy.AUTO for h in hunks)


class TestNewUnitAddition:
    """新增单元（base 中不存在）。"""

    def test_ours_adds_assignment_auto(self):
        base = "hp=100\n"
        ours = "hp=100\nmp=50\n"
        theirs = "hp=100\n"
        hunks = merge_lua(base, ours, theirs)
        mp_hunk = [h for h in hunks if "mp" in h.rationale or h.ours == "mp=50\n"]
        assert mp_hunk
        assert mp_hunk[0].strategy == ResolutionStrategy.AUTO

    def test_theirs_adds_function_auto(self):
        base = "hp=100\n"
        ours = "hp=100\n"
        theirs = "hp=100\nfunction extra()\nend\n"
        hunks = merge_lua(base, ours, theirs)
        auto_merged = "".join(h.merged for h in hunks if h.merged)
        assert "extra" in auto_merged


class TestRawLines:
    """无法识别结构的行。"""

    def test_identical_raw_lines_auto(self):
        """三者完全相同的 raw 行 → auto（三方一致）。"""
        base = "print('hello')\n"
        ours = "print('hello')\n"
        theirs = "print('hello')\n"
        hunks = merge_lua(base, ours, theirs)
        # 三方一致 → auto
        assert any(h.strategy == ResolutionStrategy.AUTO and h.merged for h in hunks)

    def test_differing_raw_lines_manual(self):
        """两方改同一 raw 行且不同 → manual。"""
        base = "if x then return end\n"
        ours = "if x then return 1 end\n"
        theirs = "if x then return 2 end\n"
        hunks = merge_lua(base, ours, theirs)
        assert any(h.strategy == ResolutionStrategy.MANUAL for h in hunks)


class TestMixedScenario:
    """混合场景：赋值 + 函数 + 冲突。"""

    def test_mixed_auto_and_manual(self):
        base = "hp=100\natk=10\nfunction init()\n  return 0\nend\n"
        ours = "hp=200\natk=10\nfunction init()\n  return 0\nend\n"
        theirs = "hp=300\natk=10\nfunction init()\n  return 0\nend\n"
        hunks = merge_lua(base, ours, theirs)
        strategies = {h.strategy for h in hunks}
        # hp 冲突 → manual；atk + init 一致 → auto
        assert ResolutionStrategy.MANUAL in strategies
        assert ResolutionStrategy.AUTO in strategies

    def test_table_field_assignment_aligned(self):
        """点号字段 table.field = v 也按 key 对齐。"""
        base = "config.hp=100\n"
        ours = "config.hp=200\n"
        theirs = "config.hp=100\n"
        hunks = merge_lua(base, ours, theirs)
        assert all(h.strategy == ResolutionStrategy.AUTO for h in hunks)


class TestUnitSplitting:
    """_split_units 内部结构（直接验证结构识别）。"""

    def test_assignment_unit(self):
        from udify.core.mod_manager.real_merge.lua_merge import _split_units

        units = _split_units("hp=100\n")
        assigns = [u for u in units if u.kind == "assign"]
        assert len(assigns) == 1
        assert assigns[0].key == "hp"

    def test_function_unit_absorbs_body(self):
        from udify.core.mod_manager.real_merge.lua_merge import _split_units

        src = "function f()\n  x=1\n  y=2\nend\n"
        units = _split_units(src)
        funcs = [u for u in units if u.kind == "func"]
        assert len(funcs) == 1
        assert "end" in funcs[0].body
        assert "x=1" in funcs[0].body

    def test_lua_unit_is_frozen(self):
        import pytest

        u = LuaUnit("assign", "hp", "hp=100")
        with pytest.raises((AttributeError, TypeError)):
            u.key = "mp"  # type: ignore[misc]
