# AST-01..04 görev verisi (kaynak)

Veri ekibinin birleşik veri seti paketinden (`ai_gambit_final_dataset_v3_1`, `llm_ready/`) değiştirilmeden kopyalandı:

| Dosya | sha256 |
|---|---|
| `payloads_tr_mission_iss180.jsonl` | `d6fca301bf55408e89b088825555bba5d1f3f37b558ee07c86982d89d3f1a4c8` |
| `payloads_mission_iss180.jsonl` | `67c6225172bad003f107e2c278e57627f6d320066bc25e98ef3f9cf94844e9b0` |

İkisi aynı kayıtlardır (720 satır = AST-01..04 × görev günü 1–180, satır başına 22 gösterge); biri Türkçe, biri
İngilizce ad ve `normal` metni taşır. Özetler paketin kendi `SHA256SUMS.txt` dosyasıyla aynıdır.

- Gerçek NASA verisi: ISS radyasyonu (RadLab DOSTEL-2). Doz eşdeğeri tahmindir.
- Geri kalan ölçümler sentetiktir, yayımlanmış uzay çalışmalarına kalibre edilmiştir. Klinik karar için değildir.
- `durum` (YEŞİL / SARI / KIRMIZI) paketteki kural motorunun o gün verdiği işarettir; `normal` kişisel tabanı ya da
  NASA / klinik referansını gösteren metindir.

Panel bu dosyaları doğrudan okumaz: `python -m app.cli convert-ast` (backend/) bunlardan
`data/raw/astronaut_health_ast.json` dosyasını üretir (görev günü 149–178). Hiçbir değer üretilmez; kurallar
`backend/app/personal/ast_convert.py` ve `backend/app/personal/derive.py` içinde yazılıdır.
