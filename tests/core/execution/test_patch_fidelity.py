"""补丁字节保真的行为锁（PATCH-SYN-10，iter7 M4）。

为什么这是 P0 而不是体验优化：M3-PR4 的 pass-to-pass 回归断言是「意图未涉及的实体
逐字节不变」。若序列化本身会归一化行尾、吞掉尾换行，那条最强回归断言根本无法成立——
保真是验证体系的**前置条件**，不是 diff 好看与否的问题。

对照 APR 领域的双向断言：
- fail-to-pass（改动生效）→ 目标行确实变了
- pass-to-pass（回归安全）→ 其余字节一个不差
"""

from __future__ import annotations

import pytest

from udify.core.execution.patch_executor import PatchExecutor, _split_keep_eol

CRLF = "\r\n"
LF = "\n"


@pytest.fixture
def ex() -> PatchExecutor:
    """只测纯序列化方法，不需要 VFS。"""
    return PatchExecutor.__new__(PatchExecutor)


@pytest.fixture(params=[LF, CRLF], ids=["lf", "crlf"])
def sep(request: pytest.FixtureRequest) -> str:
    return str(request.param)


class TestSplitKeepEol:
    def test_roundtrip_is_byte_exact(self, sep: str) -> None:
        src = f"a{sep}b{sep}c{sep}"
        lines, detected = _split_keep_eol(src)
        assert "".join(lines) == src
        assert detected == sep

    def test_no_trailing_newline_preserved(self) -> None:
        lines, _ = _split_keep_eol("a\nb")
        assert "".join(lines) == "a\nb"


class TestIniFidelity:
    def test_removing_absent_section_is_byte_identical(self, ex: PatchExecutor, sep: str) -> None:
        """零改动操作必须产生零字节差异——这是回归断言成立的地基。"""
        src = f"[Boss]{sep}HP=100{sep}Defense=10{sep}"
        assert ex._remove_ini_section(src, "DoesNotExist") == src

    def test_modify_existing_key_touches_only_target_line(
        self, ex: PatchExecutor, sep: str
    ) -> None:
        src = f"[Boss]{sep}HP=100{sep}Defense=10{sep}"
        assert ex._modify_ini_ci(src, "Boss", "HP", 200) == f"[Boss]{sep}HP=200{sep}Defense=10{sep}"

    def test_append_missing_key_preserves_eol_and_trailing_newline(
        self, ex: PatchExecutor, sep: str
    ) -> None:
        """key 不存在会回退到 _add_ini_section——该路径过去会把 CRLF 归一化成 LF。"""
        src = f"[Boss]{sep}HP=100{sep}"
        assert ex._modify_ini_ci(src, "Boss", "Speed", 5) == f"[Boss]{sep}HP=100{sep}Speed=5{sep}"

    def test_unrelated_sections_survive_byte_exact(self, ex: PatchExecutor, sep: str) -> None:
        """只改 Boss，Hero 段必须一个字节都不动（pass-to-pass）。"""
        src = f"[Hero]{sep}HP=50{sep}{sep}[Boss]{sep}HP=100{sep}"
        out = ex._modify_ini_ci(src, "Boss", "HP", 200)
        assert out.split("[Boss]")[0] == src.split("[Boss]")[0]

    def test_add_section_to_empty_content(self, ex: PatchExecutor) -> None:
        assert ex._add_ini_section("", "Boss", {"HP": 1}) == "[Boss]\nHP=1\n"


class TestObjFidelity:
    def test_removing_absent_entry_is_byte_identical(self, ex: PatchExecutor, sep: str) -> None:
        src = f"Sword{sep}    Atk=5{sep}"
        assert ex._remove_obj_entry(src, "DoesNotExist") == src

    def test_modify_property_preserves_eol(self, ex: PatchExecutor, sep: str) -> None:
        src = f"Sword{sep}    Atk=5{sep}"
        assert ex._modify_obj(src, "Sword", "Atk", 9) == f"Sword{sep}    Atk=9{sep}"


class TestJsonFidelity:
    def test_key_order_and_indent_preserved(self, ex: PatchExecutor) -> None:
        src = '{\n  "b": 1,\n  "a": 2\n}'
        out = ex._modify_json(src, "b", 99)
        assert out.index('"b"') < out.index('"a"'), "键序必须保持"
        assert '\n  "b": 99' in out, "缩进必须保持"

    def test_nested_list_index_addressing(self, ex: PatchExecutor) -> None:
        src = '{\n  "e": [\n    {\n      "hp": 50\n    }\n  ]\n}'
        assert '"hp": 100' in ex._modify_json(src, "e.0.hp", 100)
