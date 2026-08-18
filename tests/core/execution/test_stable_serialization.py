"""PATCH-SYN-10 修复测试：字节级稳定 ini 序列化。"""

from pathlib import Path

from udify.core.execution.patch_executor import PatchExecutor, _split_keep_eol
from udify.core.execution.vfs import VirtualFileSystem


def test_split_keep_eol_preserves_newlines():
    src = "[A]\nX=1\n; comment\nY=2\n"
    lines, sep = _split_keep_eol(src)
    assert sep == "\n"
    assert "".join(lines) == src


def test_split_keep_eol_crlf():
    src = "[A]\r\nX=1\r\n"
    lines, sep = _split_keep_eol(src)
    assert sep == "\r\n"
    assert "".join(lines) == src


def _exec_with_ini(tmp_path, ini):
    vfs = VirtualFileSystem(Path(str(tmp_path)))
    vfs.write_file("game/enemies.ini", ini)
    return PatchExecutor(vfs), "game/enemies.ini"


def test_only_target_value_changes_other_lines_byte_identical(tmp_path):
    original = "; boss config\n[DarkLord]\nMaxLife=5000\nAttack=320\nDefense=10\n"
    executor, path = _exec_with_ini(tmp_path, original)
    content = executor.vfs.read_file(path)
    new_content = executor._modify_ini(content, "DarkLord", "MaxLife", 9999)
    assert "MaxLife=9999" in new_content
    assert "Attack=320\n" in new_content
    assert "Defense=10\n" in new_content
    assert "; boss config\n" in new_content
    old_lines = original.split("\n")
    new_lines = new_content.split("\n")
    diffs = [(a, b) for a, b in zip(old_lines, new_lines, strict=False) if a != b]
    assert all("MaxLife" in a or "MaxLife" in b for a, b in diffs), str(diffs)


def test_no_same_value_noise(tmp_path):
    original = "[S]\nA=1\nB=2\nC=3\n"
    executor, path = _exec_with_ini(tmp_path, original)
    content = executor.vfs.read_file(path)
    new_content = executor._modify_ini(content, "S", "B", 99)
    diffs = [
        (a, b)
        for a, b in zip(original.split("\n"), new_content.split("\n"), strict=False)
        if a != b
    ]
    assert len(diffs) == 1, str(diffs)
    assert "B=99" in diffs[0][1]


def test_trailing_newline_preserved(tmp_path):
    original = "[S]\nX=1\n"
    executor, path = _exec_with_ini(tmp_path, original)
    content = executor.vfs.read_file(path)
    new_content = executor._modify_ini(content, "S", "X", 2)
    assert new_content.endswith("\n")


def test_crlf_preserved(tmp_path):
    original = "[S]\r\nX=1\r\n"
    executor, path = _exec_with_ini(tmp_path, original)
    content = executor.vfs.read_file(path)
    new_content = executor._modify_ini(content, "S", "X", 2)
    assert "\r\n" in new_content
