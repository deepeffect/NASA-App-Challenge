"""Adaptör altyapısı.

Yeni bir veri formatı geldiğinde SADECE yeni bir adaptör yazmak yeterlidir:

    @register_adapter
    class NasaXmlAdapter(BaseAdapter):
        name = "nasa_xml"
        def can_handle(self, filename, head, ctx): return filename.endswith(".xml")
        def parse(self, content, ctx): ...  # → LONG_COLUMNS + "row" kolonlu DataFrame

Adaptör sadece ŞEKİL dönüşümü yapar (ham → long). Metrik adı çözme, birim dönüştürme,
zaman damgası/değer doğrulama ve DB'ye yazma `pipeline.py`'de ortaktır.
"""

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd

from app.analysis.catalog import Catalog, normalize_key

LONG_COLUMNS = ["astronaut_id", "timestamp", "metric", "value", "unit", "source"]

# Standart kolon → kabul edilen başlık adları (normalize_key sonrası)
COLUMN_ALIASES: dict[str, list[str]] = {
    "astronaut_id": ["astronaut_id", "astronaut", "crew_id", "crew_member", "crewmember", "subject", "subject_id",
                     "participant", "participant_id"],
    "timestamp": ["timestamp", "time", "datetime", "date_time", "ts", "date", "recorded_at", "measured_at"],
    "metric": ["metric", "measure", "parameter", "variable", "metric_name"],
    "value": ["value", "val", "reading", "result", "measurement_value"],
    "unit": ["unit", "units", "uom"],
    "source": ["source", "device", "sensor", "origin"],
}


@dataclass
class ParseContext:
    filename: str
    catalog: Catalog
    default_astronaut: str | None = None
    default_source: str = "ingest"


class BaseAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def can_handle(self, filename: str, head: str, ctx: ParseContext) -> bool:
        """Dosya adı ve ilk ~4 KB metne bakarak bu adaptör işleyebilir mi?"""

    @abstractmethod
    def parse(self, content: bytes, ctx: ParseContext) -> pd.DataFrame:
        """Ham içerik → LONG_COLUMNS + 'row' (hata raporu için kaynak satır no) kolonlu DataFrame.

        Eksik kolonlar (unit, source, astronaut_id) None olabilir; pipeline tamamlar.
        """


ADAPTERS: dict[str, BaseAdapter] = {}


def register_adapter(cls: type[BaseAdapter]) -> type[BaseAdapter]:
    inst = cls()
    ADAPTERS[inst.name] = inst
    return cls


def detect_adapter(filename: str, head: str, ctx: ParseContext) -> BaseAdapter | None:
    for adapter in ADAPTERS.values():
        if adapter.can_handle(filename, head, ctx):
            return adapter
    return None


# ----------------------------------------------------------------------------- yardımcılar
def map_columns(columns: list[str]) -> dict[str, str]:
    """Başlıkları standart adlara eşle: {'astronaut_id': 'Subject', 'timestamp': 'Time', ...}."""
    norm = {normalize_key(c): c for c in columns}
    out: dict[str, str] = {}
    for std, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in norm:
                out[std] = norm[a]
                break
    return out


def decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def sniff_sep(header_line: str) -> str:
    counts = {sep: header_line.count(sep) for sep in (",", ";", "\t", "|")}
    return max(counts, key=counts.get) if max(counts.values()) > 0 else ","


def read_csv(content: bytes) -> pd.DataFrame:
    text = decode(content)
    first = text.splitlines()[0] if text else ""
    return pd.read_csv(io.StringIO(text), sep=sniff_sep(first), dtype=str, keep_default_na=False,
                       skipinitialspace=True)
