"""Değerlendirme fonksiyonlarının birim testleri (golden test bütünü prototiple karşılaştırır)."""

import pytest

from app.personal.evaluate import avg3, js_num, level_of, shown_status, to_fixed


@pytest.mark.parametrize(
    ("v", "d", "expected"),
    [
        (86.5, 0, "87"),  # JS yarımda yukarı; Python format'ı "86" verirdi
        (87.5, 0, "88"),
        (-2.5, 0, "-3"),
        (0.125, 2, "0.13"),
        (1.005, 2, "1.00"),  # ikili gösterim 1.00499… → JS de "1.00"
        (-0.001, 1, "-0.0"),
        (-0.0, 1, "0.0"),
        (53.04, 2, "53.04"),
    ],
)
def test_to_fixed_matches_js(v: float, d: int, expected: str) -> None:
    assert to_fixed(v, d) == expected


@pytest.mark.parametrize(("v", "expected"), [(1.0, "1"), (36.1, "36.1"), (-2, "-2"), (0.5, "0.5"), (2.5, "2.5")])
def test_js_num(v: float, expected: str) -> None:
    assert js_num(v) == expected


def test_avg3_window_narrows_at_start() -> None:
    arr = [3.0, 6.0, 9.0, 12.0]
    assert [avg3(arr, i) for i in range(4)] == [3.0, 4.5, 6.0, 9.0]


def test_level_of_boundaries_and_open_upper(catalog) -> None:
    sleep = catalog.indicator("beh_sleep_h")  # sağlıklı 7–9, uyarı 6–10
    assert [level_of(sleep, v) for v in (7, 9, 6.99, 6, 10, 10.01, 5.99)] == [0, 0, 1, 1, 1, 2, 2]
    hrv = catalog.indicator("cv_hrv_ms")  # sağlıklı ≥ 25, uyarı ≥ 15, üst sınır yok
    assert [level_of(hrv, v) for v in (1000, 25, 24.9, 15, 14.9)] == [0, 0, 1, 1, 2]


def test_shown_status() -> None:
    assert shown_status(0, False) == 0 and shown_status(0, True) == 1
    assert shown_status(2, False) == 2 and shown_status(1, True) == 1
