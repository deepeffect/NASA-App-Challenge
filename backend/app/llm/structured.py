"""Yapılandırılmış çıktı: Pydantic şemasına uyan JSON üret, doğrula, uymazsa bir kez yeniden dene.

Sıra: response_format=json_schema → (sunucu reddederse) json_object → (o da olmazsa) sadece prompt.
Her denemede çıktı `<think>` ve ``` bloklarından temizlenip Pydantic ile doğrulanır. Doğrulama hatası
modele geri verilip tekrar istenir. Hepsi başarısızsa None döner → çağıran kural tabanlı şablona düşer.
"""

import json
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.client import LLMClient
from app.llm.think import strip_think
from app.llm.types import Message, StructuredOutputUnsupported

M = TypeVar("M", bound=BaseModel)


@dataclass
class StructuredResult(Generic[M]):
    value: M | None
    raw: str
    attempts: int
    error: str | None = None
    model: str | None = None


def extract_json(text: str) -> str:
    t = strip_think(text).strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        t = t.rsplit("```", 1)[0]
    start, end = t.find("{"), t.rfind("}")
    return t[start : end + 1] if start >= 0 and end > start else t


def _short_errors(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or '(root)'}: {err['msg']}" for err in e.errors()[:6])


async def generate_structured(
    client: LLMClient, messages: list[Message], model_cls: type[M], *, retries: int = 1, temperature: float = 0.2,
) -> StructuredResult[M]:
    schema = model_cls.model_json_schema()
    formats: list[dict | None] = [
        {"type": "json_schema", "json_schema": {"name": model_cls.__name__, "schema": schema, "strict": True}},
        {"type": "json_object"},
        None,
    ]
    fmt_i = 0
    msgs = list(messages)
    raw, err, model = "", None, None
    attempt = 0
    while attempt <= retries:
        try:
            resp = await client.chat(msgs, response_format=formats[fmt_i], temperature=temperature)
        except StructuredOutputUnsupported:
            if fmt_i + 1 < len(formats):
                fmt_i += 1
                continue  # aynı denemeyi bir alt formatla tekrarla
            raise
        attempt += 1
        raw, model = resp.content, resp.model
        try:
            return StructuredResult(model_cls.model_validate_json(extract_json(raw)), raw, attempt, None, model)
        except ValidationError as e:
            err = _short_errors(e)
        except (ValueError, json.JSONDecodeError) as e:
            err = str(e)
        msgs = [*msgs, {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Your previous output was invalid: {err}. "
                                            "Return ONLY one JSON object that matches the schema exactly."}]
    return StructuredResult(None, raw, attempt, err, model)
