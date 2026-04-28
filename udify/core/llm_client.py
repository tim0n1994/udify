"""
Udify LLM Integration

统一的 LLM 调用接口，支持多种后端：
- OpenAI API
- Anthropic Claude API
- 本地模型 (llama.cpp / vLLM)
- 远程 API (通用 HTTP 接口)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str = "stop"


class LLMClient:
    """
    LLM 客户端

    统一的 LLM 调用接口。
    """

    def __init__(self, provider: str = "openai", model: str = "gpt-4o-mini") -> None:
        self.provider = provider
        self.model = model
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        """获取或创建底层客户端"""
        if self._client is not None:
            return self._client

        if self.provider == "openai":
            try:
                import openai
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise RuntimeError("OPENAI_API_KEY not set")
                self._client = openai.OpenAI(api_key=api_key)
            except ImportError:
                raise ImportError("openai package not installed")

        elif self.provider == "anthropic":
            try:
                import anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise RuntimeError("ANTHROPIC_API_KEY not set")
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError("anthropic package not installed")

        else:
            raise ValueError(f"Unknown provider: {self.provider}")

        return self._client

    def complete(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1000) -> LLMResponse:
        """
        单次补全调用
        """
        client = self._get_client()

        if self.provider == "openai":
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=self.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                },
            )

        elif self.provider == "anthropic":
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            content = ""
            if response.content and len(response.content) > 0:
                content = response.content[0].text
            return LLMResponse(
                content=content,
                model=self.model,
                usage={
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                },
            )

        raise RuntimeError("Unknown provider")

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 1000) -> LLMResponse:
        """
        多轮对话
        """
        client = self._get_client()

        if self.provider == "openai":
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=self.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                },
            )

        elif self.provider == "anthropic":
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=messages,  # type: ignore
            )
            content = ""
            if response.content and len(response.content) > 0:
                content = response.content[0].text
            return LLMResponse(
                content=content,
                model=self.model,
                usage={
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                },
            )

        raise RuntimeError("Unknown provider")

    def is_available(self) -> bool:
        """检查 LLM 是否可用"""
        try:
            self._get_client()
            return True
        except Exception:
            return False
