"""JSON 字节稳定序列化测试（iter3 N2 / S3-CROSSPATCH）。"""

import json
from pathlib import Path

from udify.core.execution.patch_executor import PatchExecutor
from udify.core.execution.vfs import VirtualFileSystem


def _exec_with_json(tmp_path, jtext):
    vfs = VirtualFileSystem(Path(str(tmp_path)))
    vfs.write_file("game/data.json", jtext)
    return PatchExecutor(vfs), "game/data.json"


def test_modify_nested_value_preserves_indent_and_key_order(tmp_path):
    original = (
        "{\n"
        '  "Enemies": [\n'
        '    {"name": "Boss", "hp": 5000, "atk": 320},\n'
        '    {"name": "Goblin", "hp": 120}\n'
        "  ]\n"
        "}\n"
    )
    executor, path = _exec_with_json(tmp_path, original)
    content = executor.vfs.read_file(path)
    new_content = executor._modify_json(content, "Enemies.0.hp", 9999)
    data = json.loads(new_content)
    assert data["Enemies"][0]["hp"] == 9999
    # 键序保留：name 在 hp 前
    assert list(data["Enemies"][0].keys())[0] == "name"
    # 缩进保留：仍是 2 空格
    assert '  "Enemies"' in new_content
    # 其他敌人未变
    assert data["Enemies"][1]["hp"] == 120


def test_float_precision_not_drifted(tmp_path):
    original = '{"crit": 0.25, "drop": 0.001}\n'
    executor, path = _exec_with_json(tmp_path, original)
    content = executor.vfs.read_file(path)
    new_content = executor._modify_json(content, "crit", 0.5)
    data = json.loads(new_content)
    assert data["crit"] == 0.5
    assert data["drop"] == 0.001


def test_only_target_key_changed_other_keys_byte_stable(tmp_path):
    original = '{\n  "MaxLife": 5000,\n  "Attack": 320,\n  "Defense": 10\n}\n'
    executor, path = _exec_with_json(tmp_path, original)
    content = executor.vfs.read_file(path)
    new_content = executor._modify_json(content, "MaxLife", 9999)
    # 其他键的值不变
    assert '"Attack": 320' in new_content
    assert '"Defense": 10' in new_content
    assert '"MaxLife": 9999' in new_content
