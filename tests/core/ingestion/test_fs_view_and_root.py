"""iter4 M1 PR2 — SafeFsView + root_discovery 测试（T1-ENGINE-AUTO）。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from udify.core.ingestion.fs_view import FsViewError, SafeFsView
from udify.core.ingestion.root_discovery import (
    CandidateRoot,
    RootConfidence,
    discover_project_root,
)

# --------------------------------------------------------------- SafeFsView


class TestSafeFsViewEscape:
    """路径逃逸必须 fail-closed。"""

    def test_rejects_parent_traversal(self, tmp_path):
        (tmp_path / "inside.txt").write_text("ok")
        view = SafeFsView(tmp_path)
        with pytest.raises(FsViewError, match="escapes"):
            view.read_text("../outside.txt")

    def test_rejects_absolute_path_outside(self, tmp_path):
        view = SafeFsView(tmp_path)
        with pytest.raises(FsViewError, match="escapes"):
            view.read_text("/etc/passwd")

    def test_empty_path_rejected(self, tmp_path):
        view = SafeFsView(tmp_path)
        with pytest.raises(FsViewError, match="empty"):
            view.read_text("")

    def test_exists_returns_false_for_escaped(self, tmp_path):
        view = SafeFsView(tmp_path)
        assert view.exists("../outside") is False


class TestSafeFsViewRead:
    """正常路径的读取。"""

    def test_read_text_inside_root(self, tmp_path):
        (tmp_path / "config.ini").write_text("[Game]\nversion=1.0\n")
        view = SafeFsView(tmp_path)
        assert "[Game]" in view.read_text("config.ini")

    def test_read_text_missing_file_raises(self, tmp_path):
        view = SafeFsView(tmp_path)
        with pytest.raises(FsViewError, match="not a file"):
            view.read_text("nonexistent.txt")

    def test_truncates_oversized_file(self, tmp_path):
        big = tmp_path / "big.txt"
        big.write_text("x" * 5000)
        view = SafeFsView(tmp_path)
        # max_bytes=100 截断
        text = view.read_text("big.txt", max_bytes=100)
        assert len(text) == 100

    def test_read_bytes(self, tmp_path):
        (tmp_path / "data.bin").write_bytes(b"\x00\x01\x02")
        view = SafeFsView(tmp_path)
        assert view.read_bytes("data.bin") == b"\x00\x01\x02"

    def test_list_dir(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        view = SafeFsView(tmp_path)
        entries = view.list_dir(".")
        assert "a.txt" in entries
        assert "b.txt" in entries

    def test_glob(self, tmp_path):
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "x.json").write_text("{}")
        (tmp_path / "data" / "y.json").write_text("{}")
        view = SafeFsView(tmp_path)
        results = view.glob("data/*.json")
        assert "data/x.json" in results
        assert "data/y.json" in results


class TestSafeFsViewFrozen:
    def test_safe_fs_view_is_frozen(self, tmp_path):
        view = SafeFsView(tmp_path)
        # frozen dataclass: direct attribute assignment must fail
        with pytest.raises((AttributeError, FrozenInstanceError)):
            view.root = tmp_path / "other"  # type: ignore[misc]


# --------------------------------------------------------------- root_discovery


class TestRootDiscovery:
    """游戏根候选发现。"""

    def test_finds_rpgmv_root_in_nested_dir(self, tmp_path):
        """真实场景：用户给的路径多包了一层，真正的游戏根在子目录。"""
        wrapper = tmp_path / "downloaded_game"
        game_root = wrapper / "MyGame"
        (game_root / "www" / "data").mkdir(parents=True)
        (game_root / "www" / "data" / "System.json").write_text("{}")
        (game_root / "www" / "data" / "Actors.json").write_text("{}")
        (game_root / "www" / "index.html").write_text("<html></html>")
        (game_root / "package.json").write_text('{"name":"MyGame","main":"main.js"}')

        candidate = discover_project_root(str(wrapper))
        assert candidate.path == game_root.resolve()
        assert candidate.confidence in (RootConfidence.HIGH, RootConfidence.MEDIUM)
        assert candidate.engine_hint == "rpg_maker_mv"

    def test_returns_start_when_already_root(self, tmp_path):
        """start_path 本身就是游戏根。"""
        (tmp_path / "www" / "data").mkdir(parents=True)
        (tmp_path / "www" / "data" / "System.json").write_text("{}")
        (tmp_path / "package.json").write_text('{"name":"game"}')
        candidate = discover_project_root(str(tmp_path))
        assert candidate.path == tmp_path.resolve()

    def test_returns_none_confidence_for_no_game_files(self, tmp_path):
        """无任何引擎指纹 → NONE。"""
        (tmp_path / "readme.txt").write_text("not a game")
        candidate = discover_project_root(str(tmp_path))
        assert candidate.confidence == RootConfidence.NONE

    def test_finds_godot_root(self, tmp_path):
        (tmp_path / "game").mkdir()
        (tmp_path / "game" / "project.godot").write_text(
            '[application]\nname="Test"\nconfig_version=5\n'
        )
        candidate = discover_project_root(str(tmp_path))
        assert candidate.path.name == "game"
        assert candidate.engine_hint == "godot"

    def test_skips_node_modules_and_git(self, tmp_path):
        """搜索时跳过 .git / node_modules 等噪声目录。"""
        (tmp_path / "node_modules" / "lib").mkdir(parents=True)
        (tmp_path / "node_modules" / "lib" / "package.json").write_text("{}")
        (tmp_path / ".git").mkdir()
        candidate = discover_project_root(str(tmp_path))
        # node_modules 的 package.json 不应被当成游戏根
        # candidate 应是 tmp_path 本身（无游戏指纹），而非 node_modules/lib
        assert candidate.path == tmp_path.resolve()
        assert candidate.confidence == RootConfidence.NONE

    def test_nonexistent_path_returns_none(self, tmp_path):
        candidate = discover_project_root(str(tmp_path / "does_not_exist"))
        assert candidate.confidence == RootConfidence.NONE

    def test_candidate_root_serializable(self, tmp_path):
        (tmp_path / "project.godot").write_text("[application]\n")
        candidate = discover_project_root(str(tmp_path))
        d = candidate.to_dict()
        assert "path" in d
        assert "confidence" in d
        assert "signals" in d

    def test_candidate_root_is_frozen(self, tmp_path):
        candidate = CandidateRoot(path=tmp_path, confidence=RootConfidence.NONE)
        with pytest.raises((AttributeError, TypeError)):
            candidate.confidence = RootConfidence.HIGH  # type: ignore[misc]
