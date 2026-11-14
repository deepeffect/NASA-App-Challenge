"""Tool-call ayrıştırıcı, StreamGuard, <think> filtresi ve sayı denetimi."""

import json

import pytest

from app.llm.think import ThinkFilter, split_think, strip_think
from app.llm.toolcall_parser import StreamGuard, parse_tool_calls
from app.safety.grounding import extract_numbers, find_ungrounded_numbers

KNOWN = {"get_metric", "get_alerts", "get_health_summary"}


# --------------------------------------------------------------------------- parser
@pytest.mark.parametrize("text", [
    '<tool_call>{"name": "get_metric", "arguments": {"metric": "sleep_duration", "days": 7}}</tool_call>',
    'Bakıyorum.\n<tool_call>\n{"name": "get_metric", "arguments": {"metric": "sleep_duration", "days": 7},}\n</tool_call>',
    '```json\n{"name": "get_metric", "arguments": {"metric": "sleep_duration", "days": 7}}\n```',
    '{"tool": "get_metric", "args": {"metric": "sleep_duration", "days": 7}}',
    '{"name": "get_metric", "arguments": "{\\"metric\\": \\"sleep_duration\\", \\"days\\": 7}"}',
    '{"type": "function", "function": {"name": "get_metric", "arguments": {"metric": "sleep_duration", "days": 7}}}',
    '<tool_call>{"name": "get_metric", "arguments": {"metric": "sleep_duration", "days": 7}}',  # kapanış etiketi yok
])
def test_parse_variants(text):
    calls, _ = parse_tool_calls(text, KNOWN)
    assert len(calls) == 1
    assert calls[0].name == "get_metric"
    assert calls[0].parsed_arguments() == {"metric": "sleep_duration", "days": 7}
    assert calls[0].id.startswith("call_")


def test_parse_multiple_and_rest():
    text = ('<tool_call>{"name": "get_alerts", "arguments": {}}</tool_call>\n'
            '<tool_call>{"name": "get_health_summary", "arguments": {"astronaut_id": "AST-02"}}</tool_call>')
    calls, rest = parse_tool_calls(text, KNOWN)
    assert [c.name for c in calls] == ["get_alerts", "get_health_summary"]
    assert rest == ""
    calls, _ = parse_tool_calls('[{"name": "get_alerts", "arguments": {}}, {"name": "get_metric", "arguments": {}}]', KNOWN)
    assert len(calls) == 2


def test_parse_ignores_plain_text_and_unknown_tools():
    assert parse_tool_calls("Uykun son 7 günde azaldı.", KNOWN) == ([], "Uykun son 7 günde azaldı.")
    calls, _ = parse_tool_calls('<tool_call>{"name": "rm_rf", "arguments": {}}</tool_call>', KNOWN)
    assert calls == []
    calls, _ = parse_tool_calls('{"summary": "json ama tool değil"}', KNOWN)
    assert calls == []


# --------------------------------------------------------------------------- StreamGuard
def _feed(chunks):
    g = StreamGuard()
    out = "".join(g.feed(c) for c in chunks)
    return g, out


def test_guard_passes_normal_text():
    g, out = _feed(["Mer", "haba, uykun ", "iyi görünüyor."])
    assert out + g.flush() == "Merhaba, uykun iyi görünüyor."
    assert not g.holding


def test_guard_holds_leading_tool_call_split_across_chunks():
    g, out = _feed(["<to", "ol_call>{\"name\": ", "\"get_alerts\"}</tool_call>"])
    assert out == "" and g.holding


def test_guard_holds_from_midstream_tag():
    g, out = _feed(["Bir saniye, kontrol ediyorum. <tool", "_call>{...}</tool_call>"])
    assert out == "Bir saniye, kontrol ediyorum. "
    assert g.holding


def test_guard_holds_json_start():
    g, out = _feed(['  {"name": "get_alerts"', "}"])
    assert out == "" and g.holding


# --------------------------------------------------------------------------- think
def test_split_think():
    assert split_think("<think>\n\n</think>\n\nMerhaba") == ("", "Merhaba")
    assert split_think("<think>plan yap</think>Cevap") == ("plan yap", "Cevap")
    assert split_think("Düz metin") == ("", "Düz metin")
    assert strip_think("<think>kapanmamış") == ""


def test_think_filter_across_boundaries():
    f = ThinkFilter()
    parts = []
    for chunk in ["<th", "ink>düşü", "nce</thi", "nk>\n\nCe", "vap"]:
        parts += f.feed(chunk)
    parts += f.flush()
    tokens = "".join(t for k, t in parts if k == "token")
    thinking = "".join(t for k, t in parts if k == "thinking")
    assert (tokens, thinking) == ("Cevap", "düşünce")


# --------------------------------------------------------------------------- grounding
def test_extract_numbers_turkish_and_ignores():
    nums = extract_numbers("Uyku 5,1 sa (baseline 7.25), 2026-11-14 tarihinde AST-02 için 14:30'da.")
    assert [n.value for n in nums] == [5.1, 7.25]
    assert [n.has_unit for n in nums] == [True, False]


@pytest.mark.parametrize("text,unit", [
    ("5 saat uyudun", True), ("5 saatten az", True), ("5 sa", True), ("8 h", True), ("9 bpm", True),
    ("40 ms", True), ("%5 düşüş", True), ("5% drop", True), ("2 mSv", True), ("9 mmHg", True),
    ("1 °C", True), ("2 kg", True), ("5 dk", True), ("5 dakika", True), ("5 min", True),
    ("3 gün", False), ("2 uyarı", False), ("7 günlük", False), ("Saat 5 gibi", False),
])
def test_unit_detection(text, unit):
    (n,) = extract_numbers(text)
    assert n.has_unit is unit, text


def test_small_int_with_unit_is_checked():
    # Yanında birim olan küçük sayı her zaman aranır
    assert find_ungrounded_numbers("Dün gece 5 saat uyudun.", [{"value": 7.2}]) == ["5"]
    assert find_ungrounded_numbers("Dün gece 5 saat uyudun.", [{"value": 4.97}]) == []
    assert find_ungrounded_numbers("Nabzın 9 bpm arttı.", [{"latest": 70, "baseline": 61}]) == ["9"]
    assert find_ungrounded_numbers("Stres %5 arttı.", [{"value": 30}]) == ["5"]  # Türkçe önek yüzde
    # birimsiz küçük sayılar (sayım/süre) yok sayılır
    assert find_ungrounded_numbers("3 gün daha izle; 2 uyarı var.", [{"value": 99}]) == []


def test_rounding_tolerance_both_ways():
    assert find_ungrounded_numbers("Uyku 5,1 sa.", [{"value": 5}]) == []      # 5,1 ↔ 5
    assert find_ungrounded_numbers("Uyku 5 sa.", [{"value": 5.1}]) == []      # 5 ↔ 5,1
    assert find_ungrounded_numbers("Uyku 7,2 sa.", [{"value": 7.18}]) == []
    assert find_ungrounded_numbers("Uyku 6,5 sa.", [{"value": 5.1}]) == ["6,5"]
    assert find_ungrounded_numbers("Nabız 72 bpm.", [{"value": 70}]) == ["72"], "%2'yi aşan fark eşleşmez"


def test_denominators_are_scale_bounds():
    assert find_ungrounded_numbers("Genel skor 35/100; ruh hali 2/5.", [{"score": 35}]) == []


def test_standard_codes_are_not_numbers():
    assert extract_numbers("Eşikler NASA-STD-3001 ve ISO-8601 ile doğrulanmalı; SpO2 ve qwen3:14b") == []


def test_ungrounded_numbers():
    data = [{"value": 5.12, "baseline": 7.248, "z7": -2.61}, json.dumps({"dose": 1.84})]
    text = "Son değer 5,1 sa, normal 7,2 sa; z = -2,6. Doz 1,84 mSv. Ama 9,9 saat uyuman lazım. 3 gün izle."
    assert find_ungrounded_numbers(text, data) == ["9,9"]
