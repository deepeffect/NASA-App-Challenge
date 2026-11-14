"""Belge yükleme: data/docs/ altındaki MD/TXT/PDF dosyaları → bölümlere ayrılmış metin.

- Markdown/TXT: başlıklara (#, ##, ...) göre bölünür; bölüm adı kaynak referansında kullanılır.
- PDF: sayfa sayfa okunur (pypdf gerekir: `pip install -e ".[rag]"`); yoksa atlanır ve uyarı verilir.
- README.md ve '_' / '.' ile başlayan dosyalar indekslenmez.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)
SUPPORTED = {".md", ".markdown", ".txt", ".pdf"}
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass
class Section:
    heading: str | None
    text: str
    page: int | None = None


@dataclass
class Document:
    file: str  # docs klasörüne göre göreli yol (kaynak referansı)
    title: str
    sections: list[Section] = field(default_factory=list)


def iter_doc_files(docs_dir: Path) -> list[Path]:
    if not docs_dir.exists():
        return []
    return sorted(
        p for p in docs_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED and p.name.lower() != "readme.md"
        and not p.name.startswith(("_", "."))
    )


def _load_markdown(path: Path, rel: str) -> Document:
    text = path.read_text(encoding="utf-8", errors="replace")
    sections: list[Section] = []
    heading: str | None = None
    buf: list[str] = []
    title = path.stem
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            if buf and "".join(buf).strip():
                sections.append(Section(heading, "\n".join(buf).strip()))
            heading, buf = m.group(2).strip(), []
            if len(m.group(1)) == 1 and title == path.stem:
                title = heading
        else:
            buf.append(line)
    if buf and "".join(buf).strip():
        sections.append(Section(heading, "\n".join(buf).strip()))
    return Document(file=rel, title=title, sections=sections)


def _load_pdf(path: Path, rel: str) -> Document | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("pypdf kurulu değil, PDF atlandı: %s (pip install -e '.[rag]')", rel)
        return None
    reader = PdfReader(str(path))
    sections = [Section(heading=None, text=(page.extract_text() or "").strip(), page=i + 1)
                for i, page in enumerate(reader.pages)]
    return Document(file=rel, title=path.stem, sections=[s for s in sections if s.text])


def load_documents(docs_dir: Path) -> list[Document]:
    docs: list[Document] = []
    for path in iter_doc_files(docs_dir):
        rel = path.relative_to(docs_dir).as_posix()
        try:
            doc = _load_pdf(path, rel) if path.suffix.lower() == ".pdf" else _load_markdown(path, rel)
        except Exception as e:  # noqa: BLE001 — bozuk bir dosya indeksi düşürmesin
            log.warning("Belge okunamadı %s: %s", rel, e)
            continue
        if doc and doc.sections:
            docs.append(doc)
    return docs
