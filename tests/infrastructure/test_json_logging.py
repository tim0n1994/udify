"""OBS-02：JSON 日志格式化器测试。"""

from __future__ import annotations

import json
import logging

from udify.core.infrastructure.json_logging import JsonFormatter


class TestJsonFormatter:
    def _format(self, record: logging.LogRecord) -> dict:
        return json.loads(JsonFormatter().format(record))

    def test_basic_record_is_single_line_json(self) -> None:
        record = logging.LogRecord(
            name="udify.api",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="job %s created",
            args=("abc",),
            exc_info=None,
        )
        payload = self._format(record)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "udify.api"
        assert payload["message"] == "job abc created"
        assert "\n" not in JsonFormatter().format(record)

    def test_extra_fields_pass_through(self) -> None:
        record = logging.LogRecord(
            name="udify",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="m",
            args=(),
            exc_info=None,
        )
        record.job_id = "j123"  # logging 的 extra 机制
        payload = self._format(record)
        assert payload["job_id"] == "j123"

    def test_exception_captured(self) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="udify",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="failed",
                args=(),
                exc_info=sys.exc_info(),
            )
        payload = self._format(record)
        assert "boom" in payload["exc"]
