"""OBS-02：结构化 JSON 日志（stdlib logging，零新依赖）。

`udify serve` 默认启用——每行一个 JSON 对象，可被任何日志采集器消费。
不上 OTel/Loki（红线：OBS-05/06 维持 P2）。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any


class JsonFormatter(logging.Formatter):
    """每条记录输出单行 JSON：ts/level/logger/message + extra 字段。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": round(record.created, 3),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = self.formatException(record.exc_info)
        # LogRecord 的 extra 字段（如 job_id）原样带出
        for key, value in record.__dict__.items():
            if key in _STDLIB_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


_STDLIB_FIELDS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
    }
)


def configure_json_logging(level: int = logging.INFO) -> None:
    """把根 logger 切换为单行 JSON 输出（幂等）。"""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


__all__ = ["JsonFormatter", "configure_json_logging"]
