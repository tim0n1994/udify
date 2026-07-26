"""
Udify Core - Engine Detector

游戏引擎检测器，通过分析文件结构、特征文件、元数据来识别游戏使用的引擎。
支持 Unity、Unreal、Godot、RPG Maker、GameMaker 等主流引擎。
"""

from __future__ import annotations

import logging
import struct
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from udify.models.content_graph import GameEngine

logger = logging.getLogger(__name__)


@dataclass
class EngineDetectionResult:
    """引擎检测结果"""

    engine: GameEngine
    version: str | None = None
    confidence: float = 0.0  # 0.0 - 1.0
    evidence: list[str] = None  # 检测依据

    def __post_init__(self):
        if self.evidence is None:
            self.evidence = []


class EngineDetector(ABC):
    """引擎检测器基类"""

    @abstractmethod
    def detect(self, path: Path) -> EngineDetectionResult | None:
        """
        检测给定路径是否使用本引擎

        Args:
            path: 游戏文件或目录路径

        Returns:
            如果匹配则返回检测结果，否则返回 None
        """
        pass

    @property
    @abstractmethod
    def engine_type(self) -> GameEngine:
        """返回本检测器对应的引擎类型"""
        pass


class UnityDetector(EngineDetector):
    """Unity 引擎检测器"""

    # Unity 特征文件和目录
    UNITY_SIGNATURES: dict[str, list[str]] = {
        "directories": [
            "_Data",  # Windows 构建
            "_data",  # Linux 构建
            ".app/Contents/Resources/Data",  # macOS 构建
        ],
        "files": [
            "globalgamemanagers",
            "globalgamemanagers.assets",
            "level0",
            "sharedassets0.assets",
            "resources.assets",
            "unity default resources",
            "Managed/UnityEngine.dll",
            "UnityPlayer.dll",
        ],
        "extensions": [".assets", "", ".resS"],  # 空字符串表示无扩展名
    }

    # Unity 文件头魔数
    UNITY_FS_SIGNATURE = b"UnityFS"  # UnityFS 格式 (Unity 5+)
    UNITY_RAW_SIGNATURE = b"UnityRaw"  # 旧格式

    @property
    def engine_type(self) -> GameEngine:
        return GameEngine.UNITY

    def detect(self, path: Path) -> EngineDetectionResult | None:
        evidence = []
        confidence = 0.0
        version = None

        if path.is_file():
            # 单个文件（可能是 .apk、.ipa、.zip 等）
            result = self._detect_from_archive(path)
            if result:
                return result
            # 检查是否是 UnityFS 格式的文件
            if self._check_unity_fs_header(path):
                evidence.append(f"UnityFS header found in {path.name}")
                confidence += 0.4

        elif path.is_dir():
            # 目录结构检测
            # 检查 _Data 目录
            data_dirs = list(path.glob("*_Data")) + list(path.glob("*.app"))

            # 如果传入的路径本身就是 .app bundle，也加入检测
            if path.suffix == ".app":
                data_dirs.insert(0, path)

            if data_dirs:
                evidence.append(f"Data directory found: {data_dirs[0].name}")
                confidence += 0.3

                # 检查内部结构
                data_dir = data_dirs[0]
                if data_dir.is_dir():
                    if data_dir.suffix == ".app":
                        # macOS .app bundle
                        resources_data = data_dir / "Contents" / "Resources" / "Data"
                        if resources_data.is_dir():
                            evidence.append("macOS app bundle structure found")
                            confidence += 0.3
                            if any(
                                (resources_data / f).exists()
                                for f in ["globalgamemanagers", "globalgamemanagers.assets"]
                            ):
                                evidence.append("globalgamemanagers found in macOS bundle")
                                confidence += 0.3
                            version = self._extract_unity_version(resources_data)
                            if version:
                                evidence.append(f"Unity version detected: {version}")
                                confidence += 0.1
                    else:
                        # Windows/Linux
                        if any(
                            (data_dir / f).exists()
                            for f in ["globalgamemanagers", "globalgamemanagers.assets"]
                        ):
                            evidence.append("globalgamemanagers file found")
                            confidence += 0.3

                        if (data_dir / "Managed").is_dir():
                            evidence.append("Managed assemblies directory found")
                            confidence += 0.2

                        # 尝试提取版本信息
                        version = self._extract_unity_version(data_dir)
                        if version:
                            evidence.append(f"Unity version detected: {version}")
                            confidence += 0.1

            # 检查根目录下的 UnityPlayer.dll
            if (path / "UnityPlayer.dll").exists() or (path / "UnityPlayer.so").exists():
                evidence.append("UnityPlayer runtime found")
                confidence += 0.3

            # 检查 .assets 文件
            assets_files = list(path.rglob("*.assets"))
            if assets_files:
                evidence.append(f"Found {len(assets_files)} .assets files")
                confidence += 0.2

        if confidence > 0.5:
            return EngineDetectionResult(
                engine=GameEngine.UNITY,
                version=version,
                confidence=min(confidence, 1.0),
                evidence=evidence,
            )

        return None

    def _detect_from_archive(self, path: Path) -> EngineDetectionResult | None:
        """从压缩包中检测 Unity"""
        try:
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path, "r") as zf:
                    file_list = zf.namelist()

                    evidence = []
                    confidence = 0.0

                    # Android APK 结构
                    if "assets/bin/Data/Managed/" in list(file_list) or any(
                        "assets/bin/Data/" in f for f in file_list
                    ):
                        evidence.append("Android APK Unity data path found")
                        confidence += 0.5

                    # iOS 结构
                    if any("Data/Managed/" in f for f in file_list):
                        evidence.append("iOS Unity data path found")
                        confidence += 0.5

                    # 通用检查
                    if any("globalgamemanagers" in f for f in file_list):
                        evidence.append("globalgamemanagers found in archive")
                        confidence += 0.3

                    if any("UnityEngine" in f for f in file_list):
                        evidence.append("UnityEngine assembly found")
                        confidence += 0.2

                    if confidence > 0.5:
                        return EngineDetectionResult(
                            engine=GameEngine.UNITY,
                            confidence=min(confidence, 1.0),
                            evidence=evidence,
                        )
        except Exception as e:
            logger.debug(f"Failed to analyze archive {path}: {e}")

        return None

    def _check_unity_fs_header(self, path: Path) -> bool:
        """检查文件头是否为 UnityFS 格式"""
        try:
            with open(path, "rb") as f:
                header = f.read(16)
                return header.startswith(self.UNITY_FS_SIGNATURE) or header.startswith(
                    self.UNITY_RAW_SIGNATURE
                )
        except Exception:
            return False

    def _extract_unity_version(self, data_dir: Path) -> str | None:
        """尝试从 globalgamemanagers 或 level0 中提取 Unity 版本"""
        try:
            # Unity 5+ 的版本信息存储在 globalgamemanagers 的前几个字节
            for filename in [
                "globalgamemanagers",
                "globalgamemanagers.assets",
                "level0",
                "data.unity3d",
            ]:
                file_path = data_dir / filename
                if file_path.exists():
                    with open(file_path, "rb") as f:
                        # 读取前 64 字节查找版本字符串
                        data = f.read(256)
                        # 查找形如 "20XX.X" 或 "X.X.X" 的版本号
                        import re

                        # Unity 版本通常在文件开头附近
                        version_match = re.search(rb"(\d{4}\.\d+\.?\d*\w?)", data)
                        if version_match:
                            return version_match.group(1).decode("ascii", errors="ignore")
        except Exception as e:
            logger.debug(f"Failed to extract Unity version: {e}")

        return None


class UnrealDetector(EngineDetector):
    """Unreal Engine 检测器"""

    UNREAL_SIGNATURES = [
        ".pak",  # 打包资源文件
        ".uproject",  # 项目文件（源码版）
        ".uasset",  # 资源文件
        ".umap",  # 地图文件
    ]

    @property
    def engine_type(self) -> GameEngine:
        return GameEngine.UNREAL

    def detect(self, path: Path) -> EngineDetectionResult | None:
        evidence = []
        confidence = 0.0
        version = None

        if path.is_dir():
            # 检查 .pak 文件（打包后的游戏）
            pak_files = list(path.rglob("*.pak"))
            if pak_files:
                evidence.append(f"Found {len(pak_files)} .pak files")
                confidence += 0.5

                # 尝试读取 pak 文件头验证
                if self._verify_pak_file(pak_files[0]):
                    evidence.append("Valid pak file format confirmed")
                    confidence += 0.2

            # 检查 .uproject（未打包的源码项目）
            uproject_files = list(path.rglob("*.uproject"))
            if uproject_files:
                evidence.append(f"Found {len(uproject_files)} .uproject files")
                confidence += 0.8  # uproject 是强信号
                version = self._extract_unreal_version(uproject_files[0])

            # 检查 .uasset 和 .umap
            uasset_files = list(path.rglob("*.uasset"))
            umap_files = list(path.rglob("*.umap"))
            if uasset_files or umap_files:
                evidence.append(f"Found {len(uasset_files)} .uasset, {len(umap_files)} .umap")
                confidence += 0.3

            # 检查 Unreal 特有的可执行文件命名
            exe_files = list(path.glob("*.exe"))
            for exe in exe_files:
                if "UE4" in exe.name or "UE5" in exe.name or "Shipping" in exe.name:
                    evidence.append(f"Unreal-style executable: {exe.name}")
                    confidence += 0.2

            # 检查 Content 目录结构
            content_dirs = list(path.rglob("Content"))
            if content_dirs:
                evidence.append("Unreal Content directory found")
                confidence += 0.2

        elif path.is_file():
            # 检查是否是 .pak 文件
            if path.suffix.lower() == ".pak" and self._verify_pak_file(path):
                evidence.append("Standalone pak file confirmed")
                confidence += 0.6

        if confidence > 0.5:
            return EngineDetectionResult(
                engine=GameEngine.UNREAL,
                version=version,
                confidence=min(confidence, 1.0),
                evidence=evidence,
            )

        return None

    def _verify_pak_file(self, path: Path) -> bool:
        """验证 pak 文件格式"""
        try:
            with open(path, "rb") as f:
                # Unreal pak 文件头: uint32 magic = 0x5A6F12E1
                magic = struct.unpack("<I", f.read(4))[0]
                return magic == 0x5A6F12E1
        except Exception:
            return False

    def _extract_unreal_version(self, uproject_path: Path) -> str | None:
        """从 .uproject 文件中提取引擎版本"""
        try:
            import json

            with open(uproject_path, encoding="utf-8") as f:
                data = json.load(f)

                # 新格式
                if "EngineAssociation" in data:
                    assoc = data["EngineAssociation"]
                    if assoc.startswith("{"):
                        return "Installed"  # 通过 Launcher 安装的
                    return assoc

                # 旧格式
                if "EngineVersion" in data:
                    return data["EngineVersion"]
        except Exception as e:
            logger.debug(f"Failed to extract Unreal version: {e}")

        return None


class GodotDetector(EngineDetector):
    """Godot 引擎检测器"""

    @property
    def engine_type(self) -> GameEngine:
        return GameEngine.GODOT

    def detect(self, path: Path) -> EngineDetectionResult | None:
        evidence = []
        confidence = 0.0
        version = None

        if path.is_dir():
            # 检查 project.godot（源码项目）
            project_files = list(path.rglob("project.godot"))
            if project_files:
                evidence.append(f"Found {len(project_files)} project.godot files")
                confidence += 0.9  # 强信号
                version = self._extract_godot_version(project_files[0])

            # 检查 .pck 文件（打包后的游戏）
            pck_files = list(path.rglob("*.pck"))
            if pck_files:
                evidence.append(f"Found {len(pck_files)} .pck files")
                confidence += 0.5
                if self._verify_pck_file(pck_files[0]):
                    evidence.append("Valid pck file format confirmed")
                    confidence += 0.2

            # 检查 .tscn 或 .scn 文件（场景文件）
            scene_files = list(path.rglob("*.tscn")) + list(path.rglob("*.scn"))
            if scene_files:
                evidence.append(f"Found {len(scene_files)} scene files")
                confidence += 0.3

            # 检查 .gd 脚本文件
            gd_files = list(path.rglob("*.gd"))
            if gd_files:
                evidence.append(f"Found {len(gd_files)} GDScript files")
                confidence += 0.3

        elif path.is_file():
            # 检查是否是 .pck 文件
            if path.suffix.lower() == ".pck" and self._verify_pck_file(path):
                evidence.append("Standalone pck file confirmed")
                confidence += 0.7

            # 检查可执行文件是否包含 Godot 特征
            if self._check_executable_for_godot(path):
                evidence.append("Godot runtime signature in executable")
                confidence += 0.5

        if confidence > 0.5:
            return EngineDetectionResult(
                engine=GameEngine.GODOT,
                version=version,
                confidence=min(confidence, 1.0),
                evidence=evidence,
            )

        return None

    def _verify_pck_file(self, path: Path) -> bool:
        """验证 Godot pck 文件格式"""
        try:
            with open(path, "rb") as f:
                # Godot 3.x+: magic = "GDPC"
                # Godot 4.x: magic = "GDPC" with different version
                magic = f.read(4)
                return magic == b"GDPC"
        except Exception:
            return False

    def _extract_godot_version(self, project_path: Path) -> str | None:
        """从 project.godot 中提取版本信息"""
        try:
            with open(project_path, encoding="utf-8") as f:
                content = f.read()
                import re

                # 查找 config/features
                match = re.search(r"config/features=PoolStringArray\((.*?)\)", content)
                if match:
                    features = match.group(1)
                    version_match = re.search(r'"(\d+\.\d+)"', features)
                    if version_match:
                        return version_match.group(1)
        except Exception as e:
            logger.debug(f"Failed to extract Godot version: {e}")

        return None

    def _check_executable_for_godot(self, path: Path) -> bool:
        """检查可执行文件中是否包含 Godot 特征字符串"""
        try:
            with open(path, "rb") as f:
                # 读取文件查找 Godot 特征字符串
                chunk = f.read(65536)  # 读取前 64KB
                return b"Godot Engine" in chunk or b"GDScript" in chunk
        except Exception:
            return False


class RPGMakerDetector(EngineDetector):
    """RPG Maker 检测器"""

    @property
    def engine_type(self) -> GameEngine:
        return GameEngine.RPG_MAKER

    def detect(self, path: Path) -> EngineDetectionResult | None:
        evidence = []
        confidence = 0.0
        version = None

        if path.is_dir():
            # RPG Maker MV/MZ: www/index.html, js/plugins.js, etc.
            if (path / "www" / "index.html").exists():
                evidence.append("RPG Maker MV/MZ web structure found")
                confidence += 0.6

                # 检查 js/plugins.js
                if (path / "www" / "js" / "plugins.js").exists():
                    evidence.append("plugins.js found")
                    confidence += 0.2

                # 检查 data/System.json
                system_json = path / "www" / "data" / "System.json"
                if system_json.exists():
                    evidence.append("System.json found")
                    confidence += 0.2
                    version = self._extract_rpgmv_version(system_json)

            # RPG Maker VX Ace / XP / 2003
            if (path / "Game.exe").exists() or (path / "Game.ini").exists():
                evidence.append("RPG Maker Windows structure found")
                confidence += 0.5

                if (path / "Game.ini").exists():
                    version = self._extract_rpgmaker_ini_version(path / "Game.ini")
                    if version:
                        evidence.append(f"RPG Maker {version} detected from Game.ini")
                        confidence += 0.3

            # 检查 RGSS 脚本
            if list(path.rglob("*.rvdata")) or list(path.rglob("*.rvdata2")):
                evidence.append("RGSS script files found")
                confidence += 0.3

            # 通用数据目录
            if (path / "Data").is_dir():
                data_files = list((path / "Data").glob("*.rvdata*"))
                if data_files:
                    evidence.append(f"Found {len(data_files)} RPG Maker data files")
                    confidence += 0.3

        if confidence > 0.5:
            return EngineDetectionResult(
                engine=GameEngine.RPG_MAKER,
                version=version,
                confidence=min(confidence, 1.0),
                evidence=evidence,
            )

        return None

    def _extract_rpgmv_version(self, system_json: Path) -> str | None:
        """从 System.json 中提取 RPG Maker MV/MZ 版本"""
        try:
            import json

            with open(system_json, encoding="utf-8") as f:
                data = json.load(f)
                # MV 和 MZ 的 System.json 结构不同
                if "versionId" in data:
                    return "MV"
                elif "advanced" in data:
                    return "MZ"
        except Exception:
            pass
        return None

    def _extract_rpgmaker_ini_version(self, ini_path: Path) -> str | None:
        """从 Game.ini 中提取 RPG Maker 版本"""
        try:
            with open(ini_path, encoding="utf-8") as f:
                content = f.read()
                if "RPGVX" in content:
                    return "VX"
                elif "RPGVXAce" in content:
                    return "VX Ace"
                elif "RPGXP" in content:
                    return "XP"
                elif "RPG_RT" in content:
                    return "2000/2003"
        except Exception:
            pass
        return None


class GameMakerDetector(EngineDetector):
    """GameMaker 检测器"""

    @property
    def engine_type(self) -> GameEngine:
        return GameEngine.GAME_MAKER

    def detect(self, path: Path) -> EngineDetectionResult | None:
        evidence = []
        confidence = 0.0
        version = None

        if path.is_dir():
            # GameMaker Studio 2: .yyp 项目文件
            yyp_files = list(path.rglob("*.yyp"))
            if yyp_files:
                evidence.append(f"Found {len(yyp_files)} .yyp project files")
                confidence += 0.9

            # GameMaker 8.1 及更早: .gmk, .gm81
            gm_files = (
                list(path.rglob("*.gmk")) + list(path.rglob("*.gm81")) + list(path.rglob("*.gmx"))
            )
            if gm_files:
                evidence.append(f"Found {len(gm_files)} GameMaker project files")
                confidence += 0.8

            # 检查 .win 文件（Windows 可执行数据）
            win_files = list(path.rglob("*.win"))
            if win_files:
                evidence.append(f"Found {len(win_files)} .win data files")
                confidence += 0.5

            # 检查 options.ini（GameMaker 运行时常用）
            if (path / "options.ini").exists():
                evidence.append("options.ini found")
                confidence += 0.2

        if confidence > 0.5:
            return EngineDetectionResult(
                engine=GameEngine.GAME_MAKER,
                version=version,
                confidence=min(confidence, 1.0),
                evidence=evidence,
            )

        return None


class CompositeEngineDetector:
    """
    组合引擎检测器

    按优先级依次调用各个检测器，返回置信度最高的结果。
    如果多个检测器都有较高置信度，会返回所有候选结果供进一步分析。
    """

    def __init__(self):
        self.detectors: list[EngineDetector] = [
            UnityDetector(),
            UnrealDetector(),
            GodotDetector(),
            RPGMakerDetector(),
            GameMakerDetector(),
        ]

    def detect(self, path: Path) -> EngineDetectionResult:
        """
        检测游戏使用的引擎

        Args:
            path: 游戏文件或目录路径

        Returns:
            检测结果，如果没有明确匹配则返回 UNKNOWN
        """
        logger.info(f"Detecting engine for: {path}")

        results: list[EngineDetectionResult] = []

        for detector in self.detectors:
            try:
                result = detector.detect(path)
                if result:
                    results.append(result)
                    logger.info(
                        f"  {detector.engine_type.value}: "
                        f"confidence={result.confidence:.2f}, "
                        f"version={result.version}"
                    )
            except Exception as e:
                logger.warning(f"Detector {detector.engine_type.value} failed: {e}")

        if not results:
            return EngineDetectionResult(
                engine=GameEngine.UNKNOWN,
                confidence=0.0,
                evidence=["No engine signatures found"],
            )

        # 按置信度排序
        results.sort(key=lambda r: r.confidence, reverse=True)
        best = results[0]

        # 如果有多个高置信度结果，添加警告
        if len(results) > 1 and results[1].confidence > 0.5:
            best.evidence.append(
                f"WARNING: Alternative detected: {results[1].engine.value} "
                f"(confidence={results[1].confidence:.2f})"
            )

        logger.info(f"Best match: {best.engine.value} (confidence={best.confidence:.2f})")
        return best

    def detect_multiple(self, path: Path) -> list[EngineDetectionResult]:
        """返回所有候选检测结果（用于调试和分析）"""
        results = []
        for detector in self.detectors:
            try:
                result = detector.detect(path)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Detector {detector.engine_type.value} failed: {e}")

        return sorted(results, key=lambda r: r.confidence, reverse=True)


# 便捷函数
def detect_engine(path: str | Path) -> EngineDetectionResult:
    """
    便捷函数：检测给定路径的引擎

    Example:
        >>> result = detect_engine("/path/to/game")
        >>> print(f"Engine: {result.engine.value}, Version: {result.version}")
    """
    detector = CompositeEngineDetector()
    return detector.detect(Path(path))
