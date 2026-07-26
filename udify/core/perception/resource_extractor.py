"""
Udify Core - Resource Extractor

资源提取器，从游戏中提取纹理、模型、音频、脚本、配置文件等资源，
并生成统一的 ContentAsset 列表。

支持引擎：Unity、Unreal、Godot、RPG Maker、GameMaker
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import struct
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from udify.models.content_graph import ContentAsset, GameEngine

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """提取结果"""

    assets: list[ContentAsset]
    success: bool = True
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class ResourceExtractor(ABC):
    """资源提取器基类"""

    @abstractmethod
    def extract(self, path: Path) -> ExtractionResult:
        """
        从给定路径提取资源

        Args:
            path: 游戏文件或目录路径

        Returns:
            提取结果
        """
        pass

    @property
    @abstractmethod
    def supported_engine(self) -> GameEngine:
        """返回支持的引擎类型"""
        pass

    def _calculate_hash(self, file_path: Path) -> str:
        """计算文件的 SHA-256 哈希"""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _get_file_type(self, suffix: str) -> str:
        """根据文件扩展名判断资源类型"""
        type_map = {
            # 纹理
            ".png": "texture",
            ".jpg": "texture",
            ".jpeg": "texture",
            ".bmp": "texture",
            ".tga": "texture",
            ".dds": "texture",
            ".psd": "texture",
            ".ktx": "texture",
            ".pvr": "texture",
            # 模型
            ".fbx": "model",
            ".obj": "model",
            ".dae": "model",
            ".blend": "model",
            ".3ds": "model",
            ".gltf": "model",
            ".glb": "model",
            ".skp": "model",
            # 音频
            ".wav": "audio",
            ".mp3": "audio",
            ".ogg": "audio",
            ".flac": "audio",
            ".aac": "audio",
            ".wma": "audio",
            # 视频
            ".mp4": "video",
            ".avi": "video",
            ".mov": "video",
            ".mkv": "video",
            ".webm": "video",
            # 脚本/代码
            ".cs": "script",
            ".js": "script",
            ".lua": "script",
            ".py": "script",
            ".gd": "script",
            ".cpp": "script",
            ".h": "script",
            ".c": "script",
            ".java": "script",
            # 配置文件
            ".json": "config",
            ".xml": "config",
            ".yaml": "config",
            ".yml": "config",
            ".ini": "config",
            ".cfg": "config",
            ".txt": "config",
            ".csv": "config",
            # 着色器
            ".shader": "shader",
            ".cginc": "shader",
            ".hlsl": "shader",
            ".glsl": "shader",
            ".vert": "shader",
            ".frag": "shader",
            # 字体
            ".ttf": "font",
            ".otf": "font",
            ".fnt": "font",
            # 动画
            ".anim": "animation",
            ".controller": "animation",
            # 其他
            ".asset": "unity_asset",
            ".prefab": "prefab",
            ".mat": "material",
            ".scene": "scene",
        }
        return type_map.get(suffix.lower(), "unknown")

    def _scan_directory(self, path: Path, recursive: bool = True) -> Iterator[Path]:
        """扫描目录中的所有文件"""
        if recursive:
            for file_path in path.rglob("*"):
                if file_path.is_file():
                    yield file_path
        else:
            for file_path in path.iterdir():
                if file_path.is_file():
                    yield file_path


class UnityResourceExtractor(ResourceExtractor):
    """Unity 资源提取器"""

    @property
    def supported_engine(self) -> GameEngine:
        return GameEngine.UNITY

    def extract(self, path: Path) -> ExtractionResult:
        assets = []
        errors = []

        if path.is_file():
            # 处理单个文件（如 .apk）
            if zipfile.is_zipfile(path):
                result = self._extract_from_apk(path)
                return result
            else:
                errors.append(f"Unsupported file type: {path.suffix}")
                return ExtractionResult(assets=[], success=False, errors=errors)

        elif path.is_dir():
            # 查找 Data 目录
            data_dirs = self._find_data_directories(path)

            if not data_dirs:
                errors.append("No Unity data directory found")
                return ExtractionResult(assets=[], success=False, errors=errors)

            for data_dir in data_dirs:
                # 提取资源文件
                try:
                    dir_assets = self._extract_from_data_directory(data_dir)
                    assets.extend(dir_assets)
                except Exception as e:
                    errors.append(f"Failed to extract from {data_dir}: {e}")
                    logger.warning(f"Extraction failed for {data_dir}: {e}")

        return ExtractionResult(assets=assets, success=len(errors) == 0, errors=errors)

    def _find_data_directories(self, root: Path) -> list[Path]:
        """查找所有 Unity Data 目录"""
        data_dirs = []

        # Windows: *_Data
        data_dirs.extend(root.glob("*_Data"))

        # macOS: *.app/Contents/Resources/Data
        for app_bundle in root.glob("*.app"):
            macos_data = app_bundle / "Contents" / "Resources" / "Data"
            if macos_data.is_dir():
                data_dirs.append(macos_data)

        # Linux: *_data
        data_dirs.extend(root.glob("*_data"))

        return data_dirs

    def _extract_from_data_directory(self, data_dir: Path) -> list[ContentAsset]:
        """从 Unity Data 目录提取资源"""
        assets = []

        # 扫描所有文件
        for file_path in self._scan_directory(data_dir):
            try:
                asset = self._create_asset_from_file(file_path, base_dir=data_dir)
                if asset:
                    assets.append(asset)
            except Exception as e:
                logger.debug(f"Failed to process {file_path}: {e}")

        return assets

    def _extract_from_apk(self, apk_path: Path) -> ExtractionResult:
        """从 Android APK 中提取资源"""
        assets = []
        errors = []

        try:
            with zipfile.ZipFile(apk_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue

                    # 只提取可识别的资源文件
                    suffix = Path(info.filename).suffix
                    file_type = self._get_file_type(suffix)

                    if file_type != "unknown":
                        # 计算大小，但不实际解压（节省内存）
                        asset = ContentAsset(
                            path=info.filename,
                            type=file_type,
                            format=suffix.lstrip(".") if suffix else "",
                            size=info.file_size,
                        )
                        assets.append(asset)
        except Exception as e:
            errors.append(f"Failed to extract APK: {e}")

        return ExtractionResult(assets=assets, success=len(errors) == 0, errors=errors)

    def _create_asset_from_file(self, file_path: Path, base_dir: Path) -> ContentAsset | None:
        """从文件路径创建 ContentAsset"""
        suffix = file_path.suffix
        file_type = self._get_file_type(suffix)

        if file_type == "unknown":
            return None

        # 计算相对路径
        try:
            rel_path = file_path.relative_to(base_dir.parent)
        except ValueError:
            rel_path = file_path.name

        asset = ContentAsset(
            path=str(rel_path),
            type=file_type,
            format=suffix.lstrip(".") if suffix else "",
            size=file_path.stat().st_size,
        )

        # 对于小文件计算哈希
        if asset.size < 10 * 1024 * 1024:  # < 10MB
            with contextlib.suppress(Exception):
                asset.hash = self._calculate_hash(file_path)

        # 图像文件尝试获取尺寸
        if file_type == "texture" and suffix.lower() in [".png", ".jpg", ".jpeg", ".bmp"]:
            try:
                width, height = self._get_image_size(file_path)
                asset.width = width
                asset.height = height
            except Exception:
                pass

        return asset

    def _get_image_size(self, file_path: Path) -> tuple[int, int]:
        """获取图像文件尺寸"""
        with open(file_path, "rb") as f:
            header = f.read(32)

            if header.startswith(b"\x89PNG"):
                # PNG
                w, h = struct.unpack(">II", header[16:24])
                return w, h
            elif header.startswith(b"\xff\xd8"):
                # JPEG (简化处理)
                return self._get_jpeg_size(file_path)
            elif header.startswith(b"BM"):
                # BMP
                w, h = struct.unpack("<II", header[18:26])
                return w, h

        return 0, 0

    def _get_jpeg_size(self, file_path: Path) -> tuple[int, int]:
        """获取 JPEG 尺寸"""
        with open(file_path, "rb") as f:
            f.read(2)  # Skip SOI
            while True:
                marker = f.read(2)
                if len(marker) < 2:
                    break

                # Skip padding
                while marker[0] == 0xFF:
                    if marker[1] != 0xFF:
                        break
                    marker = bytes([marker[1]]) + f.read(1)

                # SOF markers
                if marker[1] in (
                    0xC0,
                    0xC1,
                    0xC2,
                    0xC3,
                    0xC5,
                    0xC6,
                    0xC7,
                    0xC9,
                    0xCA,
                    0xCB,
                    0xCD,
                    0xCE,
                    0xCF,
                ):
                    f.read(3)  # Length and precision
                    h, w = struct.unpack(">HH", f.read(4))
                    return w, h

                # Skip other segments
                length_bytes = f.read(2)
                if len(length_bytes) < 2:
                    break
                length = struct.unpack(">H", length_bytes)[0]
                f.read(length - 2)

        return 0, 0


class UnrealResourceExtractor(ResourceExtractor):
    """Unreal Engine 资源提取器"""

    @property
    def supported_engine(self) -> GameEngine:
        return GameEngine.UNREAL

    def extract(self, path: Path) -> ExtractionResult:
        assets = []
        errors = []

        if path.is_dir():
            # 扫描 .uasset 和 .umap 文件
            for file_path in path.rglob("*.uasset"):
                try:
                    asset = self._create_asset_from_uasset(file_path, path)
                    if asset:
                        assets.append(asset)
                except Exception as e:
                    logger.debug(f"Failed to process uasset {file_path}: {e}")

            for file_path in path.rglob("*.umap"):
                try:
                    asset = self._create_asset_from_file(file_path, path, "scene")
                    if asset:
                        assets.append(asset)
                except Exception as e:
                    logger.debug(f"Failed to process umap {file_path}: {e}")

            # 扫描 Content 目录中的原始资源
            content_dirs = list(path.rglob("Content"))
            for content_dir in content_dirs:
                for file_path in self._scan_directory(content_dir):
                    if file_path.suffix in [".png", ".jpg", ".wav", ".mp3", ".fbx", ".obj"]:
                        try:
                            asset = self._create_raw_asset(file_path, path)
                            if asset:
                                assets.append(asset)
                        except Exception as e:
                            logger.debug(f"Failed to process raw asset {file_path}: {e}")

            # 扫描 .pak 文件（列出内容但不解压）
            for pak_file in path.rglob("*.pak"):
                try:
                    pak_assets = self._list_pak_contents(pak_file)
                    assets.extend(pak_assets)
                except Exception as e:
                    errors.append(f"Failed to list pak contents {pak_file}: {e}")

        return ExtractionResult(assets=assets, success=len(errors) == 0, errors=errors)

    def _create_asset_from_uasset(self, file_path: Path, base_dir: Path) -> ContentAsset | None:
        """从 .uasset 文件创建资产记录"""
        try:
            rel_path = file_path.relative_to(base_dir)
        except ValueError:
            rel_path = file_path.name

        # 尝试从文件头读取类型信息
        asset_type = self._read_uasset_type(file_path)

        return ContentAsset(
            path=str(rel_path),
            type=asset_type,
            format="uasset",
            size=file_path.stat().st_size,
        )

    def _read_uasset_type(self, file_path: Path) -> str:
        """读取 .uasset 文件头获取资源类型"""
        try:
            with open(file_path, "rb") as f:
                # Unreal .uasset 文件头结构：
                # int32 Signature (0x9E2A83C1)
                # int32 LegacyFileVersion
                # ...
                # FString PackageName
                # 然后是导出表等

                # 简化：读取前 1KB 查找类名
                data = f.read(1024)

                # 常见的 Unreal 资源类名
                type_markers = {
                    b"Texture2D": "texture",
                    b"StaticMesh": "model",
                    b"SkeletalMesh": "model",
                    b"SoundWave": "audio",
                    b"Blueprint": "script",
                    b"Material": "material",
                    b"Font": "font",
                    b"ParticleSystem": "effect",
                }

                for marker, asset_type in type_markers.items():
                    if marker in data:
                        return asset_type
        except Exception:
            pass

        return "unreal_asset"

    def _create_asset_from_file(
        self, file_path: Path, base_dir: Path, file_type: str
    ) -> ContentAsset | None:
        """从文件创建资产记录"""
        try:
            rel_path = file_path.relative_to(base_dir)
        except ValueError:
            rel_path = file_path.name

        return ContentAsset(
            path=str(rel_path),
            type=file_type,
            format=file_path.suffix.lstrip("."),
            size=file_path.stat().st_size,
        )

    def _create_raw_asset(self, file_path: Path, base_dir: Path) -> ContentAsset | None:
        """从原始资源文件创建记录"""
        suffix = file_path.suffix
        file_type = self._get_file_type(suffix)

        if file_type == "unknown":
            return None

        try:
            rel_path = file_path.relative_to(base_dir)
        except ValueError:
            rel_path = file_path.name

        asset = ContentAsset(
            path=str(rel_path),
            type=file_type,
            format=suffix.lstrip("."),
            size=file_path.stat().st_size,
        )

        return asset

    def _list_pak_contents(self, pak_file: Path) -> list[ContentAsset]:
        """列出 pak 文件中的内容（不实际解压）"""
        # 实际的 pak 解析需要更复杂的逻辑
        # 这里仅做占位，返回 pak 文件本身作为记录
        return [
            ContentAsset(
                path=str(pak_file.name),
                type="archive",
                format="pak",
                size=pak_file.stat().st_size,
            )
        ]


class GodotResourceExtractor(ResourceExtractor):
    """Godot 资源提取器"""

    @property
    def supported_engine(self) -> GameEngine:
        return GameEngine.GODOT

    def extract(self, path: Path) -> ExtractionResult:
        assets = []
        errors = []

        if path.is_dir():
            # 扫描所有可识别资源
            for file_path in self._scan_directory(path):
                try:
                    asset = self._create_asset(file_path, path)
                    if asset:
                        assets.append(asset)
                except Exception as e:
                    logger.debug(f"Failed to process {file_path}: {e}")

        return ExtractionResult(assets=assets, success=len(errors) == 0, errors=errors)

    def _create_asset(self, file_path: Path, base_dir: Path) -> ContentAsset | None:
        """创建 Godot 资源记录"""
        suffix = file_path.suffix.lower()

        # Godot 特有文件类型
        godot_type_map = {
            ".tscn": "scene",
            ".scn": "scene",
            ".gd": "script",
            ".cs": "script",
            ".tres": "resource",
            ".res": "resource",
            ".import": "import_config",
            ".gdns": "script",  # GDNativeScript
            ".gdnlib": "config",
        }

        file_type = godot_type_map.get(suffix)
        if not file_type:
            file_type = self._get_file_type(suffix)

        if file_type == "unknown":
            return None

        try:
            rel_path = file_path.relative_to(base_dir)
        except ValueError:
            rel_path = file_path.name

        return ContentAsset(
            path=str(rel_path),
            type=file_type,
            format=suffix.lstrip("."),
            size=file_path.stat().st_size,
        )


class RPGMakerResourceExtractor(ResourceExtractor):
    """RPG Maker 资源提取器"""

    @property
    def supported_engine(self) -> GameEngine:
        return GameEngine.RPG_MAKER

    def extract(self, path: Path) -> ExtractionResult:
        assets = []
        errors = []

        if path.is_dir():
            # MV/MZ: www 目录结构
            www_dir = path / "www"
            if www_dir.is_dir():
                # 提取 img 目录
                img_dir = www_dir / "img"
                if img_dir.is_dir():
                    for file_path in self._scan_directory(img_dir):
                        try:
                            asset = self._create_asset(file_path, path)
                            if asset:
                                assets.append(asset)
                        except Exception as e:
                            logger.debug(f"Failed to process {file_path}: {e}")

                # 提取 audio 目录
                audio_dir = www_dir / "audio"
                if audio_dir.is_dir():
                    for file_path in self._scan_directory(audio_dir):
                        try:
                            asset = self._create_asset(file_path, path)
                            if asset:
                                assets.append(asset)
                        except Exception as e:
                            logger.debug(f"Failed to process {file_path}: {e}")

                # 提取 js 目录
                js_dir = www_dir / "js"
                if js_dir.is_dir():
                    for file_path in self._scan_directory(js_dir):
                        if file_path.suffix == ".js":
                            try:
                                asset = self._create_asset(file_path, path)
                                if asset:
                                    assets.append(asset)
                            except Exception as e:
                                logger.debug(f"Failed to process {file_path}: {e}")

                # 提取 data 目录（JSON 配置）
                data_dir = www_dir / "data"
                if data_dir.is_dir():
                    for file_path in self._scan_directory(data_dir):
                        if file_path.suffix == ".json":
                            try:
                                asset = self._create_asset(file_path, path)
                                if asset:
                                    assets.append(asset)
                            except Exception as e:
                                logger.debug(f"Failed to process {file_path}: {e}")

            # VX Ace / XP: 传统结构
            else:
                # 扫描 Graphics 和 Audio 目录
                for subdir in ["Graphics", "Audio", "Data"]:
                    subpath = path / subdir
                    if subpath.is_dir():
                        for file_path in self._scan_directory(subpath):
                            try:
                                asset = self._create_asset(file_path, path)
                                if asset:
                                    assets.append(asset)
                            except Exception as e:
                                logger.debug(f"Failed to process {file_path}: {e}")

        return ExtractionResult(assets=assets, success=len(errors) == 0, errors=errors)

    def _create_asset(self, file_path: Path, base_dir: Path) -> ContentAsset | None:
        """创建 RPG Maker 资源记录"""
        suffix = file_path.suffix.lower()
        file_type = self._get_file_type(suffix)

        if file_type == "unknown":
            # RPG Maker 特有的扩展名
            if suffix in [".rvdata", ".rvdata2", ".rxdata", ".lmu"]:
                file_type = "rpgmaker_data"

        if file_type == "unknown":
            return None

        try:
            rel_path = file_path.relative_to(base_dir)
        except ValueError:
            rel_path = file_path.name

        return ContentAsset(
            path=str(rel_path),
            type=file_type,
            format=suffix.lstrip("."),
            size=file_path.stat().st_size,
        )


class CompositeResourceExtractor:
    """组合资源提取器"""

    def __init__(self):
        self.extractors: dict[GameEngine, ResourceExtractor] = {
            GameEngine.UNITY: UnityResourceExtractor(),
            GameEngine.UNREAL: UnrealResourceExtractor(),
            GameEngine.GODOT: GodotResourceExtractor(),
            GameEngine.RPG_MAKER: RPGMakerResourceExtractor(),
        }

    def extract(self, path: Path, engine: GameEngine) -> ExtractionResult:
        """
        根据引擎类型提取资源

        Args:
            path: 游戏路径
            engine: 检测到的引擎类型

        Returns:
            提取结果
        """
        extractor = self.extractors.get(engine)

        if not extractor:
            logger.warning(f"No extractor available for engine: {engine.value}")
            return ExtractionResult(
                assets=[],
                success=False,
                errors=[f"Unsupported engine: {engine.value}"],
            )

        logger.info(f"Extracting resources using {extractor.__class__.__name__}")
        return extractor.extract(path)

    def extract_all(self, path: Path) -> dict[GameEngine, ExtractionResult]:
        """
        尝试用所有提取器提取资源（用于调试和未知引擎）

        Args:
            path: 游戏路径

        Returns:
            各引擎的提取结果
        """
        results = {}

        for engine, extractor in self.extractors.items():
            try:
                result = extractor.extract(path)
                if result.assets:
                    results[engine] = result
            except Exception as e:
                logger.warning(f"Extractor {engine.value} failed: {e}")

        return results


# 便捷函数
def extract_resources(path: str | Path, engine: GameEngine | str) -> ExtractionResult:
    """
    便捷函数：提取资源

    Example:
        >>> result = extract_resources("/path/to/game", GameEngine.UNITY)
        >>> print(f"Extracted {len(result.assets)} assets")
    """
    if isinstance(engine, str):
        engine = GameEngine(engine)

    extractor = CompositeResourceExtractor()
    return extractor.extract(Path(path), engine)
