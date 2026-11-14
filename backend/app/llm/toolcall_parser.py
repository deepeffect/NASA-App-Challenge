"""Prompt tabanlı (native olmayan) tool çağrılarını model metninden ayrıştırma.

Native tool calling çalışmadığında (sunucu `tools`'u reddeder ya da model çağrıyı düz metin olarak
basar) devreye girer. Desteklenen biçimler:

    <tool_call>{"name": "get_metric", "arguments": {"astronaut_id": "AST-02", "metric": "sleep_duration"}}</tool_call>
    ```json
    {"name": "get_alerts", "arguments": {"astronaut_id": "AST-02"}}
    ```
    {"tool": "get_alerts", "args": {...}}          # yaygın varyant anahtarlar
    [{"name": ...}, {"name": ...}]                  # birden fazla çağrı
    "arguments" JSON string olarak da gelebilir; sondaki virgül gibi küçük hatalar onarılır.
"""

import json
import re
from typing import Any

from app.llm.types import ToolCall, new_call_id

TAG_OPEN = "<tool_call>"
_TAGGED = re.compile(r"<tool_call>\s*(.*?)\s*(?:</tool_call>|$)", re.DOTALL)
_FENCED = re.compile(r"```(?:json|tool_call)?\s*(.*?)```", re.DOTALL)
_NAME_KEYS = ("name", "tool", "tool_name", "function")
_ARG_KEYS = ("arguments", "args", "parameters", "input")


def _repair(s: str) -> str:
    s = s.strip()
    s = re.sub(r",\s*([}\]])", r"\1", s)  # sondaki virgül
    return s


def _loads(s: str) -> Any:
    for candidate in (s, _repair(s)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    # metin içinde ilk dengeli JSON nesnesini/listesini bul
    start = min((i for i in (s.find("{"), s.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i, ch in enumerate(s[start:], start):
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(_repair(s[start : i + 1]))
                except json.JSONDecodeError:
                    return None
    return None


def _to_call(obj: Any, known: set[str] | None) -> ToolCall | None:
    if not isinstance(obj, dict):
        return None
    if "function" in obj and isinstance(obj["function"], dict):  # OpenAI biçimi metin olarak basılmış
        obj = obj["function"]
    name = next((obj[k] for k in _NAME_KEYS if isinstance(obj.get(k), str)), None)
    if not name or (known is not None and name not in known):
        return None
    args = next((obj[k] for k in _ARG_KEYS if k in obj), {})
    if isinstance(args, str):
        parsed = _loads(args)
        args = parsed if isinstance(parsed, dict) else {}
    if not isinstance(args, dict):
        args = {}
    return ToolCall(id=new_call_id(), name=name, arguments=json.dumps(args, ensure_ascii=False))


def _calls_from(obj: Any, known: set[str] | None) -> list[ToolCall]:
    items = obj if isinstance(obj, list) else [obj]
    return [c for c in (_to_call(i, known) for i in items) if c]


def parse_tool_calls(text: str, known: set[str] | None = None) -> tuple[list[ToolCall], str]:
    """(çağrılar, çağrılar çıkarıldıktan sonra kalan metin). Çağrı yoksa ([], text)."""
    if not text:
        return [], ""
    calls: list[ToolCall] = []
    rest = text
    for m in _TAGGED.finditer(text):
        calls += _calls_from(_loads(m.group(1)), known)
    if calls:
        return calls, _TAGGED.sub("", text).strip()
    for m in _FENCED.finditer(text):
        found = _calls_from(_loads(m.group(1)), known)
        if found:
            calls += found
            rest = rest.replace(m.group(0), "")
    if calls:
        return calls, rest.strip()
    stripped = text.strip()
    if stripped[:1] in "{[":
        found = _calls_from(_loads(stripped), known)
        if found:
            return found, ""
    return [], text


class StreamGuard:
    """Akan metinde olası tool çağrısını kullanıcıya sızdırmamak için tutar.

    - Metin `{`, `[`, ``` veya `<tool_call` ile başlıyorsa adımın sonuna kadar tutar.
    - Akış ortasında `<tool_call` görülürse o noktadan sonrasını tutar.
    Adım bitince: tool çağrısı ayrıştırıldıysa tutulan metin atılır, yoksa `flush()` ile gönderilir.
    """

    def __init__(self) -> None:
        self._buf = ""
        self.holding = False
        self._decided = False

    def feed(self, text: str) -> str:
        self._buf += text
        if self.holding:
            return ""
        if not self._decided:
            s = self._buf.lstrip()
            if not s:
                return ""
            if s[0] in "{[`" or s.startswith(TAG_OPEN) or (len(s) < len(TAG_OPEN) and TAG_OPEN.startswith(s)):
                if s[0] in "{[`" or s.startswith(TAG_OPEN):
                    self.holding = True
                return ""
            self._decided = True
        idx = self._buf.find(TAG_OPEN)
        if idx >= 0:
            out, self._buf = self._buf[:idx], self._buf[idx:]
            self.holding = True
            return out
        keep = 0
        for n in range(min(len(TAG_OPEN) - 1, len(self._buf)), 0, -1):
            if TAG_OPEN.startswith(self._buf[-n:]):
                keep = n
                break
        out, self._buf = self._buf[: len(self._buf) - keep], self._buf[len(self._buf) - keep:]
        return out

    def flush(self) -> str:
        out, self._buf = self._buf, ""
        return out
