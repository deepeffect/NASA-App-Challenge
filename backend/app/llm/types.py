"""LLM katmanının ortak tipleri (sağlayıcıdan bağımsız)."""

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

Message = dict[str, Any]  # OpenAI chat formatı: {"role": ..., "content": ..., "tool_calls"?: ..., "tool_call_id"?: ...}


def new_call_id() -> str:
    return "call_" + uuid.uuid4().hex[:10]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # ham JSON metni (model ne ürettiyse)

    def parsed_arguments(self) -> dict[str, Any]:
        if not self.arguments or not self.arguments.strip():
            return {}
        try:
            val = json.loads(self.arguments)
        except json.JSONDecodeError:
            return {}
        return val if isinstance(val, dict) else {}

    def as_openai(self) -> dict[str, Any]:
        return {"id": self.id, "type": "function", "function": {"name": self.name, "arguments": self.arguments or "{}"}}


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str = ""
    finish_reason: str | None = None
    model: str | None = None


@dataclass
class StreamDelta:
    kind: Literal["token", "thinking", "done"]
    text: str = ""
    response: LLMResponse | None = None  # sadece kind="done"


class LLMError(Exception):
    """LLM katmanı hatalarının tabanı."""


class LLMUnavailable(LLMError):
    """Sunucuya ulaşılamıyor / zaman aşımı / model yüklü değil."""


class ToolsUnsupported(LLMError):
    """Sunucu `tools` parametresini reddetti (→ prompt tabanlı tool calling'e geç)."""


class StructuredOutputUnsupported(LLMError):
    """Sunucu `response_format=json_schema`'yı reddetti (→ json_object / sadece prompt)."""
