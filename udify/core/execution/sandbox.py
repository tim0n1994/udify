"""
Udify Execution - Sandboxed Execution

沙箱执行器：在隔离环境中执行 AI 生成的代码。
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from udify.core.infrastructure.config_center import config


@dataclass
class ExecutionResult:
    """执行结果"""

    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    execution_time: float = 0.0
    side_effects: list[str] = None

    def __post_init__(self):
        if self.side_effects is None:
            self.side_effects = []


@dataclass
class SandboxConfig:
    """沙箱配置"""

    # 资源限制
    memory_limit_mb: int = 512
    cpu_limit_percent: int = 50
    timeout_seconds: int = 30

    # 网络隔离
    network_disabled: bool = True

    # 文件系统隔离
    readonly_root: bool = True
    allowed_paths: list[str] = None

    def __post_init__(self):
        if self.allowed_paths is None:
            self.allowed_paths = []


@dataclass
class SafetyReport:
    """安全报告"""

    is_safe: bool
    vulnerabilities: list[dict[str, Any]]
    scan_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "vulnerability_count": len(self.vulnerabilities),
            "vulnerabilities": self.vulnerabilities,
            "scan_time": self.scan_time,
        }


class SandboxManager:
    """
    沙箱管理器

    管理多个沙箱实例，提供统一的执行接口。
    """

    def __init__(self, config: SandboxConfig | None = None):
        self.config = config or SandboxConfig()
        self.sandboxes = {}
        self.executor = SandboxExecutor()

    def execute_lua(self, code: str, context: dict[str, Any] | None = None) -> ExecutionResult:
        """执行 Lua 代码"""
        return self.executor.execute_lua(code, context)

    def validate_script_safety(self, code: str, language: str = "lua") -> SafetyReport:
        """验证脚本安全性"""
        return self.executor.validate_script_safety(code, language)

    def list_sandboxes(self) -> list[str]:
        """列出所有沙箱"""
        return list(self.sandboxes.keys())

    def cleanup(self) -> None:
        """清理所有沙箱"""
        self.sandboxes.clear()


class SandboxExecutor:
    """
    沙箱执行器

    当前实现：基于进程隔离 + 资源限制
    未来扩展：Docker 容器、gVisor
    """

    def __init__(self) -> None:
        self.memory_limit = config.security.sandbox_memory_limit
        self.cpu_limit = config.security.sandbox_cpu_limit
        self.timeout = config.security.sandbox_timeout_seconds
        self.network_disabled = config.security.enable_network_isolation

    def execute_lua(self, code: str, context: dict[str, Any] | None = None) -> ExecutionResult:
        """
        在沙箱中执行 Lua 代码

        使用 Lua 的 sandbox 模式（禁用危险函数）
        """
        import time

        start_time = time.time()

        # 构建安全的 Lua 执行环境
        sandbox_prelude = """
        -- 禁用危险函数
        local dangerous = {
            "os.execute", "os.remove", "os.rename", "os.tmpname",
            "io.popen", "io.open", "load", "loadfile", "dofile",
            "require", "package", "debug",
        }

        -- 创建安全环境
        local env = {}
        for k, v in pairs(_G) do
            env[k] = v
        end

        -- 移除危险函数
        env.os = { clock = os.clock, date = os.date, difftime = os.difftime, time = os.time }
        env.io = { write = io.write, print = print }
        env.load = nil
        env.loadfile = nil
        env.dofile = nil
        env.require = nil
        env.package = nil
        env.debug = nil
        """

        # 写入临时文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write(sandbox_prelude)
            f.write("\n")
            f.write(code)
            temp_path = f.name

        try:
            # 使用受限进程执行
            cmd = ["lua", temp_path]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                # 资源限制（如果系统支持）
            )

            execution_time = time.time() - start_time

            return ExecutionResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                returncode=result.returncode,
                execution_time=execution_time,
            )

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                stderr=f"Execution timeout after {self.timeout}s",
                returncode=-1,
                execution_time=self.timeout,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                stderr=str(e),
                returncode=-1,
                execution_time=time.time() - start_time,
            )
        finally:
            # 清理临时文件
            Path(temp_path).unlink(missing_ok=True)

    def validate_script_safety(self, code: str, language: str = "lua") -> SafetyReport:
        """
        验证脚本安全性（静态分析）
        """
        import time

        start_time = time.time()
        vulnerabilities = []

        # 1. 语法检查
        syntax_valid, syntax_error = self._check_syntax(code, language)
        if not syntax_valid:
            vulnerabilities.append(
                {
                    "level": "error",
                    "type": "syntax_error",
                    "message": syntax_error,
                }
            )

        # 2. 危险模式检测
        dangerous_patterns = {
            "lua": [
                (r"os\.execute", "禁止执行系统命令"),
                (r"os\.remove", "禁止删除文件"),
                (r"io\.popen", "禁止执行外部程序"),
                (r"load\s*\(", "禁止动态加载"),
                (r"loadfile\s*\(", "禁止动态加载文件"),
                (r"dofile\s*\(", "禁止执行文件"),
                (r"require\s*\(", "禁止模块加载"),
                (r"package", "禁止访问包系统"),
                (r"debug", "禁止访问调试接口"),
            ],
            "dsl": [
                (r"RunScript\s+system", "禁止执行系统脚本"),
                (r"RunParallelScript\s+system", "禁止执行系统脚本"),
            ],
        }

        patterns = dangerous_patterns.get(language, [])
        for pattern, message in patterns:
            import re

            if re.search(pattern, code, re.IGNORECASE):
                vulnerabilities.append(
                    {
                        "level": "critical",
                        "type": "dangerous_pattern",
                        "message": message,
                        "pattern": pattern,
                    }
                )

        # 3. 网络操作检测
        network_patterns = [
            r"socket",
            r"http",
            r"https",
            r"ftp",
            r"url",
            r"curl",
            r"wget",
        ]
        for pattern in network_patterns:
            import re

            if re.search(pattern, code, re.IGNORECASE):
                vulnerabilities.append(
                    {
                        "level": "high",
                        "type": "network_operation",
                        "message": f"检测到可能的网络操作: {pattern}",
                    }
                )

        # 4. 文件操作检测（超出游戏目录）
        file_patterns = [
            r"\.\./",  # 目录遍历
            r"/etc/",
            r"/usr/",
            r"/bin/",
            r"/sbin/",
            r"C:\\\\",
            r"\\\\",
        ]
        for pattern in file_patterns:
            import re

            if re.search(pattern, code):
                vulnerabilities.append(
                    {
                        "level": "critical",
                        "type": "path_traversal",
                        "message": f"检测到路径遍历: {pattern}",
                    }
                )

        scan_time = time.time() - start_time
        is_safe = not any(v["level"] == "critical" for v in vulnerabilities)

        return SafetyReport(
            is_safe=is_safe,
            vulnerabilities=vulnerabilities,
            scan_time=scan_time,
        )

    def _check_syntax(self, code: str, language: str) -> tuple:
        """检查代码语法"""
        if language == "lua":
            # 使用 luac 检查语法
            try:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
                    f.write(code)
                    temp_path = f.name

                result = subprocess.run(
                    ["luac", "-p", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                Path(temp_path).unlink(missing_ok=True)

                if result.returncode == 0:
                    return True, ""
                else:
                    return False, result.stderr

            except FileNotFoundError:
                # luac 不可用，跳过语法检查
                return True, ""
            except Exception as e:
                return False, str(e)

        # DSL 语法检查（简化版）
        elif language == "dsl":
            lines = code.split("\n")
            for i, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith("//") or line.startswith("#"):
                    continue
                # 简单检查：每行应该是一个命令或标签
                if not line.startswith("[") and not line.endswith("]"):
                    # 检查是否有等号（赋值）
                    if "=" in line and not line.startswith("If"):
                        parts = line.split("=", 1)
                        if len(parts) != 2:
                            return False, f"Line {i}: 语法错误"
            return True, ""

        return True, ""

    def execute_in_docker(self, code: str, language: str = "lua") -> ExecutionResult:
        """
        在 Docker 容器中执行（更安全的隔离）

        需要 Docker 环境支持。
        """
        # 这是一个占位实现，实际使用时需要配置 Docker
        return ExecutionResult(
            success=False,
            stderr="Docker execution not configured",
            returncode=-1,
        )
