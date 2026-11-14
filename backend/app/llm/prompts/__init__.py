"""Prompt şablonları. Dosyalar her çağrıda okunur → sunucuyu yeniden başlatmadan düzenlenebilir.

Yer tutucular: {{degisken}} (JSON süslü parantezleriyle çakışmaması için çift parantez).
"""

import re
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render(template: str, **values: object) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        return str(values[key]) if key in values else m.group(0)

    return _VAR.sub(sub, template)


def prompt(name: str, **values: object) -> str:
    return render(load_prompt(name), **values)
