# AGENTS.md — Proje kuralları ve mimari özeti

NASA Space Apps Challenge 2026 · "Create Health Monitoring Software for Astronauts on Space Mission"
Ekip: AI Gambit (1 veri/analiz, 2 LLM, 2 arayüz, 1 test/demo). Süre: 36 saat.

Uzun süreli görevde (Mars: 20+ dk iletişim gecikmesi) astronotun sağlık göstergelerini toplayan,
değerlendiren ve aksiyon önerisi sunan, **tamamen offline / gemide** çalışan bir sistem.

## Mimari

**İstasyonlar (yeni mimari).** Aynı kod iki rolde çalışır (`STATION_ROLE`), aynı yerel ağda 3 bilgisayar,
internet / Docker / bulut / tünel yok (kurulum: README → "3 bilgisayar kurulumu"):

```
Astronot terminali (tarayıcı) → GEMİ :8000 /me ──downlink (snapshot + SSE)──▶ DÜNYA ÜSSÜ :8000 /monitor
                                Ollama + backend + bütün veri (ship.db)         earth.db, salt okunur
                                gizlilik filtresi BURADA
```

- Veri: `data/raw/astronaut_health.json` (200 astronot × 30 gün; prototipten yeniden üretildi, orijinal
  bulunana kadar bağlayıcı şema) → `app/personal/` (adaptör, değerlendirme, check-in, gizlilik).
- Kurallar için TEK DOĞRU KAYNAK: `frontend/reference/personal-artifact.html` (prototip). Değerlendirme ve
  check-in prototipin JS'iyle golden testlidir (`tests/golden/`, Node gerekir).
- Durum, ana endişe, ground, self-care kodları ve skorlar VERİDEN okunur; Python sadece seviyeyi,
  tetikleyicileri, Dünya'nın göreceği ground'u ve alt başlığı hesaplar.

**Eski mimari (`DATA_SOURCE=synthetic`, sadece gemide, `/legacy` ekranları):**

```
Ham veri → ingest/ adaptörü → ortak long format (astronaut_id, timestamp, metric, value, unit, source)
        → SQLite (measurement tablosu)
        → analysis/ (Python: günlük agregasyon, baseline, z-score, eğim, dedektörler, skorlar)
        → HealthEvent + sistem skorları (yapılandırılmış JSON)
        → llm/ (yorum, açıklama, öneri, sohbet — tool calling ile veriye erişir)
        → api/ (FastAPI, REST + SSE) → frontend/ (React)
```

## DEĞİŞMEZ KURALLAR

1. **Sayıları LLM üretmez.** Tüm sayısal analiz (`analysis/`) Python'dadır. LLM sayıları sadece
   tool sonuçlarından / verilen bağlamdan alır. `safety/grounding.py` çıktıdaki kaynağı olmayan
   sayıları `ungrounded_numbers` alanında işaretler (birimli sayılar her zaman, birimsiz 0–10 tam sayılar hariç; ±%2 / yarım basamak tolerans). LLM'e skor, eşik veya istatistik hesaplatma.
2. **Uyarılar LLM'den bağımsızdır.** Eşik/sapma/trend uyarıları ve acil belirti tespiti
   (`safety/emergency.py`, check-in'de `personal/checkin_script.py`) kural tabanlıdır; LLM kapalıyken de
   çalışır. LLM katmanında bir hata asla uyarı üretimini / check-in'i engellememeli (`CHECKIN_MODE=auto`
   → scripted). Explain/briefing LLM'siz şablon cevaba düşer. Acil belirti → gemide CMO kaydı
   (`CmoNotification`); Dünya'ya gitmeyip gitmeyeceğine CMO karar verir.
3. **Eşik değerleri uydurulmaz.** `config/metrics.yaml` (eski) eşikleri placeholder'dır (`verified: false`,
   `# TODO: NASA-STD-3001 ile doğrula`). `config/catalog.yaml` (yeni) aralıkları simüle veri setinden
   gelir: `threshold_source: dataset`, `verified: false`; arayüzde tek dipnot (`threshold_note`).
   Yeni eşik eklerken aynı işaretlemeyi yap. Acil protokol metni de placeholder'dır.
4. **Belge içeriği uydurulmaz.** RAG için `data/docs/`'a sadece gerçek kaynak belgeler girer.
   Test belgeleri `backend/tests/fixtures/docs/` altındadır ve açıkça "ÖRNEK" yazar.
5. **Asistan teşhis koymaz**, karar desteği verir; belirsizliği açıkça söyler; ciddi belirtide acil
   protokole ve CMO / yer ekibine yönlendirir; kullanıcının dilinde (TR/EN) cevap verir.
6. **Offline.** Çalışma zamanında internet erişimi yok: harici API, CDN, telemetri ekleme.
7. **Önce sözleşme.** `backend/app/models/schemas.py` arayüzle sözleşmedir. Değiştirirsen:
   `python -m app.cli export-openapi` → `docs/API.md` güncelle → `frontend: npm run gen:api`.
   Alan silme/yeniden adlandırma yerine ekleme tercih et.
8. **Gizlilik filtresi gemide.** Dünya'ya giden her şey `app/personal/privacy.py` (`EarthDay`) üzerinden
   outbox'a yazılmadan ÖNCE filtrelenir: ruh hali / stres ve davranışsal alan skoru sadece o günün check-in'i
   en az `scores` paylaşıldıysa; maskeli to-do öğeleri sadece sayı; check-in mesajları, `urgent` ve CMO
   bilgisi asla. Paylaşım seviyesi sadece artar. Terminal varlığı (`terminal.online` / `terminal.offline`) sadece
   kimlik, durum ve son görülme taşır (`privacy.earth_presence`); terminalde yapılan hiçbir şey gitmez. Bu kuralları
   gevşeten değişiklik gizlilik testlerini (`tests/station/test_sharing_privacy.py`, `test_downlink.py`,
   `test_presence.py`) kırmalı.

## Klasörler

```
frontend/reference/personal-artifact.html   prototip — kurallar için tek doğru kaynak
data/raw/astronaut_health.json              veri seti (repoda; gemi git pull ile alır)
scripts/extract_dataset_from_artifact.py    veri setini prototipten yeniden üretir + doğrular
scripts/station.mjs                         dev:ship | dev:earth | reset | serve
backend/
  config/catalog.yaml      YENİ: 18 ölçüm + 14 self-care çözümü (TR/EN, aralıklar, trig, gizli)
  app/station.py, auth.py, i18n.py, errors.py, web.py   rol, giriş/token, dil, hata biçimi, arayüz servisi
  app/personal/            catalog, dataset (adaptörler), store, evaluate, view, earth_view, privacy,
                           checkin_script / checkin_context / checkin_llm
  app/downlink/            outbox (gemi), receiver + earth_store + broadcast (Dünya)
  app/api/                 station, auth, personal, checkin, assistant (/chat), downlink, monitor; routes.py = eski
  app/llm/personal_tools.py  "Asistana sor" tool'ları (sadece giriş yapan astronot)
  tests/station/, tests/golden/   yeni mimarinin testleri (golden: prototipin JS'i Node'da)
  config/metrics.yaml      ESKİ mod metrik kataloğu + placeholder eşikler
  config/rules.yaml        baseline/z/trend/skor parametreleri
  config/emergency.yaml    acil belirti terimleri (TR/EN) + placeholder protokol
  app/main.py              FastAPI app (CORS, OpenAPI'ye SSE modelleri eklenir)
  app/config.py            pydantic-settings (.env)
  app/db.py                SQLite (WAL) engine
  app/cli.py               reset | seed | reindex | export-openapi | analyze
  app/api/routes.py        ince route'lar
  app/models/schemas.py    API sözleşmesi (Pydantic)
  app/models/tables.py     SQLModel tabloları
  app/ingest/              adaptör registry (long_csv, wide_csv, json_records)
  app/analysis/            catalog, daily, features, episodes, detectors/, scoring, engine
  app/safety/              emergency (acil tespit), grounding (sayı denetimi)
  app/services/            analiz + DB + LLM orkestrasyonu
  app/llm/                 client (mock/openai), tools, agent, toolcall_parser, structured, templates
  app/llm/prompts/         system.md, explain_alert.md, briefing.md, tool_fallback.md
  app/llm/rag/             chunker, Embedder arayüzü, keyword (BM25) retriever
  app/data/synthetic.py    sentetik veri + demo senaryosu
  tests/
frontend/                  Vite + React + TS + Tailwind; src/apps/personal (/me), src/apps/monitor (/monitor),
                           src/shared/health (ortak), src/api/station.ts (yeni istemci), /legacy = eski ekranlar
data/raw | processed | docs
docs/API.md, docs/openapi.json
```

## Komutlar

Kök klasörden (önerilen, Windows/bash aynı): `npm run setup` · `npm run dev:ship` (API :8000 + /me :5173) ·
`npm run dev:earth` (API :8001 + /monitor :5174) · `npm run reset -- ship|earth` · `npm run serve` (gerçek kurulum) ·
`npm run stop [-- ship|earth]` (çalışan / artakalan geliştirme sunucularını kapatır; bkz. bug_read.md) ·
`npm run test` · eski ekranlar: `npm run dev` / `npm run seed` / `npm run smoke` (ayrıntı: README → "Kök npm komutları").
Backend Python'u `node scripts/py.mjs <args>` ile de çağrılabilir.

Backend (`backend/` içinde; venv: `.venv`):

```bash
uv venv .venv && uv pip install -e ".[dev]"        # veya: python -m venv .venv && pip install -e ".[dev]"
.venv/Scripts/python -m app.cli seed --seed 42      # sentetik veri (DB'yi sıfırlar); SPE: --spe-day 120
.venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
.venv/Scripts/python -m pytest                      # tüm testler (mock LLM, geçici DB)
.venv/Scripts/python -m app.cli export-openapi      # docs/openapi.json
.venv/Scripts/python -m app.cli analyze --as-of 2026-11-14   # konsolda ekip durumu
.venv/Scripts/python -m app.cli reindex             # RAG chunk'larını yeniden üret
```

(Linux/macOS'ta `.venv/Scripts/python` yerine `.venv/bin/python`.)

> **Durum:** `feat/foundation`: istasyon rolleri, astronaut_health verisi, değerlendirme (golden testli),
> giriş/yetki, check-in, paylaşım + gizlilik, downlink, TR/EN, frontend iskeleti (/me, /monitor yer tutucu).
> Eski mimari `DATA_SOURCE=synthetic` ile çalışmaya devam eder. Testler: `pytest` → ~330 test (testler global
> olarak `DATA_SOURCE=synthetic`; yeni mimari testleri kendi `Settings` ve geçici DB'lerini kurar).

## Açık işler (kim, nerede)

| Alan | İş | Nerede |
|---|---|---|
| LLM | Gerçek Ollama'ya karşı uçtan uca deneme (`LLM_PROVIDER=openai`); prompt ayarı | `app/llm/prompts/*.md` |
| LLM | Embedder (bge-m3: CPU'da veya Ollama) + FAISS indeksi | `app/llm/rag/embedder.py`, `vector.py`, `retriever._build` |
| Veri/ML | Isolation Forest / ruptures / tahmin dedektörleri (örnekleri değiştir) | `app/analysis/detectors/` (`examples.py` şablon) |
| Veri/ML | NASA verisi gelince adaptör + katalog girişleri | `app/ingest/adapters.py`, `config/metrics.yaml` |
| Herkes | Eşikleri NASA-STD-3001 ile doğrula (`verified: true` + `source`) | `config/metrics.yaml` |
| UI | Ekranları `feat/ui-*` branch'lerinde geliştir; changepoint/forecast için örnek dedektörleri aç | `frontend/src/features/*` |

## Değerlendirme (yeni mimari) — bilinmesi gerekenler

- Sağlık ölçümleri son 3 günün ortalaması (JS ile aynı toplama sırası: `avg3`), `exposure` o günün değeri.
- Seviye 0/1/2; gösterilen durum = max(health_status, ground ? 1 : 0). Sayı biçimi JS `toFixed` ile aynı
  (`to_fixed`, yarımda yukarı). Bilinçli prototip farkları golden testte D1–D4 olarak belgeli.
- "Bugün" = her astronotun son kaydı; check-in sadece bugün. `CHECKIN_MODE=scripted|llm|auto`.
- Kural değişince: `pytest tests/golden tests/station`.

## Analiz motoru (eski mod) — bilinmesi gerekenler

- Günlük değer: katalogdaki `aggregation` (saatlik metrikler günlüğe indirgenir). Eşik kuralı ortalama
  metriklerde günün **en kötü** ölçümüne bakar (tek bir düşük SpO2 saati yakalanır).
- Baseline: astronotun ilk 14 günü (`rules.yaml`). Sapma/trend kuralları baseline penceresinden SONRA çalışır.
- z7 = (7 günlük ortalama − baseline) / baseline_std. info ≥ 1,75 · warning ≥ 2 · critical ≥ 3,5 (kötü yönde).
- Trend: "hızlı kötüleşme" erken uyarısı; aynı metrikte warning+ sapma varken bastırılır.
- Demo zaman çizelgesi (seed 42): AST-02 gün 1–151 yeşil → 152 sarı → 157 kırmızı; diğerleri tüm görev yeşil.
  `rules.yaml` değişince `pytest tests/analysis` ile bunu doğrula.
- Analiz sonucu `(veri versiyonu, rules/metrics dosya zamanı, as_of)` ile önbellekli; YAML düzenlemesi
  sunucu yeniden başlatılmadan etkili olur.

Frontend (`frontend/` içinde):

```bash
npm install
npm run gen:api     # ../docs/openapi.json → src/api/types.ts
npm run dev         # http://localhost:5173  (VITE_API_BASE_URL=.env)
npm run build       # tip kontrolü + üretim derlemesi
```

## Nasıl genişletilir

- **Orijinal astronaut_health.json gelirse:** `app/personal/dataset.py` → `ADAPTERS` listesine yeni adaptör
  ekle ve `tests/station/test_dataset.py`'deki gibi yeniden üretilen dosyayla aynı sonucu verdiğini test et.
- **Yeni ölçüm / self-care çözümü (yeni mod):** `config/catalog.yaml` (TR/EN, `verified: false`).

- **Yeni veri formatı (NASA verisi geldiğinde):** `app/ingest/` altına `BaseAdapter`'dan türeyen
  bir sınıf yaz, `@register_adapter` ile kaydet. Sadece `can_handle()` ve `parse()` →
  ortak long DataFrame. Metrik adları katalogdaki ad veya `aliases` ile eşleşmeli.
- **Yeni metrik:** `config/metrics.yaml`'a ekle (placeholder eşik + TODO). Kod değişikliği gerekmez.
- **Yeni dedektör (ML):** `app/analysis/detectors/` altında `EventDetector` protokolünü uygula,
  `@register_detector("ad")` ile kaydet, `.env`'de `ANALYSIS_DETECTORS` listesine ekle
  (`system_pattern` en sonda kalsın). `HealthEvent` üret: `source` = `anomaly|changepoint|forecast`,
  `event_id` için `make_event_id()` kullan. Örnek: `detectors/examples.py`.
- **Prompt'lar:** `app/llm/prompts/*.md` — kod değiştirmeden düzenlenebilir. `{{degisken}}` yer tutucuları.
- **Yeni tool:** `app/llm/tools.py` içinde Pydantic argüman modeli + handler + `ToolRegistry` kaydı.

## Kod kuralları

- Python 3.11+, tip ipuçları, Pydantic v2. Kod tanımlayıcıları İngilizce; yorumlar, UI metinleri ve
  hata mesajları Türkçe. Prompt'lar İngilizce (model için), cevap kullanıcının dilinde.
- Route'lar ince; iş mantığı `services/`. Analiz fonksiyonları saf (DB'siz) ve test edilebilir.
- pandas 3.x kullanılıyor (copy-on-write varsayılan): zincirleme atama yapma, `.loc` kullan.
- Her davranış değişikliğine test: `backend/tests/`. Analiz değişikliğinde demo senaryosu testleri
  (`tests/analysis/test_scenario.py`) geçmeli: AST-02 kırmızıya döner, diğerleri yeşil kalır.
- Testler her zaman `LLM_PROVIDER=mock` ve geçici DB ile çalışır (`tests/conftest.py`).
- Arayüz değişikliğinden sonra `npm run smoke` çalıştır ve `frontend/screenshots/` görüntülerine bak (durum hiçbir yerde sadece renkle anlatılmamalı: ikon + metin).

## Git akışı

- `main`: iskelet + sözleşme (+ stub). Takım buradan branch alır.
- `feat/backend-core`: gerçek veri katmanı, analiz, LLM katmanı (adım başına bir commit).
- Özellik branch'leri: `feat/<alan>-<kısa-ad>` (örn. `feat/ui-chat`, `feat/llm-rag`, `feat/ml-iforest`).
