# Astronot Sağlık İzleme Sistemi — AI Gambit

> **Hızlı başlangıç** (kök klasörde; gereken: Node 20.19+, [uv](https://docs.astral.sh/uv/)):
> 1. `npm run setup` — Python ortamı, npm paketleri, `.env` dosyaları, API tipleri, demo verisi
> 2. `npm run dev` — backend + frontend birlikte → arayüz <http://localhost:5173>, API <http://127.0.0.1:8000/docs>

NASA Space Apps Challenge 2026 · *Create Health Monitoring Software for Astronauts on Space Mission*

Uzun süreli görevlerde astronotların sağlık göstergelerini toplayan, kişisel baseline'a göre
değerlendiren, kural tabanlı uyarılar üreten ve yerel bir LLM ile açıklama/öneri/sohbet sunan,
**tamamen offline** çalışan sistem.

- **Sayısal analizi LLM yapmaz.** Python analiz motoru baseline, z-score, trend, skor ve uyarıları üretir;
  LLM (Qwen3, Ollama) sadece yorumlar ve tool calling ile veriye erişir.
- **Uyarılar LLM'den bağımsızdır.** LLM kapalıyken de eşik/sapma/trend uyarıları ve acil belirti tespiti çalışır.
- Proje kuralları ve mimari: [`CLAUDE.md`](CLAUDE.md) · API sözleşmesi: [`docs/API.md`](docs/API.md)

```
backend/   FastAPI + SQLite + pandas + LLM katmanı
frontend/  Vite + React + TypeScript (bkz. frontend/README.md)
data/      raw/ (NASA verisi) · processed/ (DB, indeks) · docs/ (RAG belgeleri)
docs/      API.md, openapi.json
scripts/   kök npm script'lerinin yardımcıları (setup, venv python)
```

## 0. Kök npm komutları

Hepsi kök klasörde, Windows PowerShell ve bash'te aynı şekilde çalışır.

| Komut | Ne yapar |
|---|---|
| `npm run setup` | uv kontrolü → `backend/.venv` + `uv pip install -e ".[dev]"` → `.env.example`→`.env` (yoksa) → npm paketleri → `gen:api` → DB boşsa `seed --seed 42`. Tekrar çalıştırmak güvenli. |
| `npm run dev` | backend (`127.0.0.1:8000`) + frontend (Vite `:5173`) birlikte, `api`/`web` renkli önekleriyle; biri kapanırsa diğeri de kapanır. Backend `app/` altındaki `.py` değişince kendiliğinden yeniden başlar (`scripts/backend-dev.mjs`; uvicorn `--reload` Windows'ta tüm konsola Ctrl+C gönderip `npm run dev`'i düşürdüğü için kullanılmıyor) |
| `npm run dev:backend` / `npm run dev:frontend` | tek tek |
| `npm run dev:backend:lan` | backend'i ağa aç (`0.0.0.0:8000`) — takım arkadaşları bağlanacaksa |
| `npm run seed` | demo verisini yeniden yükle (DB'yi sıfırlar). Ek argüman: `npm run seed -- --spe-day 120` |
| `npm run test` | backend `pytest` + frontend tip kontrolü |
| `npm run smoke` | Playwright ile 7 ekranın tam sayfa görüntüsü (`frontend/screenshots/`) + konsol hatası / başarısız istek raporu. `npm run dev` açıkken çalıştırın; ilk sefer: `npx --prefix frontend playwright install --only-shell chromium` |

Aşağıdaki bölümler aynı adımların elle yapılışını anlatır.

## 1. Backend kurulumu

Gereksinim: Python 3.11+ (3.13 test edildi). [uv](https://docs.astral.sh/uv/) önerilir, pip de olur.

```powershell
cd backend
uv venv .venv
uv pip install -e ".[dev]"
# pip ile:  python -m venv .venv ; .venv\Scripts\activate ; pip install -e ".[dev]"
Copy-Item .env.example .env        # bash: cp .env.example .env
```

RAG embedding bağımlılıkları (torch, sentence-transformers, faiss — büyük) ayrıdır; sadece LLM ekibi kurar:

```powershell
uv pip install -e ".[rag]"
```

### Sentetik veriyi yükle ve çalıştır

> `main` branch'inde endpoint'ler sözleşmeye uygun **stub** veri döner; aşağıdakiler `feat/backend-core` içindir.

```powershell
.venv\Scripts\python -m app.cli seed --seed 42                 # 4 astronot × 180 gün (DB'yi sıfırlar, ~3 sn)
.venv\Scripts\python -m app.cli seed --seed 42 --spe-day 120   # + güneş parçacık olayı (SPE) senaryosu
.venv\Scripts\python -m app.cli analyze --as-of 2026-10-22     # ekip durumu ve aktif uyarılar konsolda
.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: <http://127.0.0.1:8000/docs>
- Sağlık: <http://127.0.0.1:8000/api/health>
- Backend adresi olarak `localhost` yerine `127.0.0.1` kullanın: Windows'ta `localhost` önce IPv6 denediği için her istek ~200 ms gecikir.

**Demo senaryosu** (görev 2026-05-19'da başlar, gün 180 = 2026-11-14): **Astronot 2**'de 150. günden
itibaren uyku süresi düşer → birkaç gün sonra stres artar, ruh hali ve HRV düşer, reaksiyon süresi uzar
→ istirahat nabzı yükselir. Diğer astronotlar normaldir. Zaman kaydırıcısıyla (`?as_of=`):

| Görev günü | AST-02 | Ne oluyor |
|---|---|---|
| 1–151 | 🟢 yeşil | kişisel baseline (ilk 14 gün), normal gürültü |
| 152 | 🟡 sarı | uyku süresi alt uyarı eşiğinin altında |
| 157 | 🔴 kırmızı | uyku sapması kritik; ardından davranışsal ve kardiyovasküler sistemler |
| 180 | 🔴 kırmızı | 3 sistemde çok metrikli örüntü olayları |

Arayüzde changepoint/forecast katmanlarını görmek için örnek dedektörleri açın (gerçek ML değildir):
`ANALYSIS_DETECTORS=threshold,baseline_deviation,trend,example_changepoint,example_forecast,system_pattern`

### RAG belgeleri

Gerçek belgeleri `data/docs/` altına koyun (PDF için `uv pip install -e ".[rag]"`), sonra
`.venv\Scripts\python -m app.cli reindex`. Varsayılan arama bağımlılıksız BM25'tir; embedding arka ucu
(`RAG_BACKEND=embedding`) LLM ekibi tarafından tamamlanacak.

### Testler

```powershell
.venv\Scripts\python -m pytest            # mock LLM + geçici DB; .env'den bağımsız (~140 test, ~10 sn)
.venv\Scripts\python -m pytest tests/analysis   # sadece analiz motoru + demo senaryosu
```

Gerçek LLM sunucusu testlerde kullanılmaz: agent loop kurgulanmış cevaplarla, `OpenAICompatClient`
Ollama tarzı cevaplar veren sahte HTTP transport ile test edilir. Gerçek modelle ilk denemede
`/api/health` → `llm.reachable`, `llm.model_available` kontrol edin, sonra sohbette "Bugün nasılım?" sorun.

## 2. LLM servisi (Ollama + Qwen3)

Backend OpenAI uyumlu herhangi bir sunucuya bağlanır. Geliştirmede `LLM_PROVIDER=mock` yeterlidir
(GPU gerekmez, şablon cevaplar döner, tool çağrıları gerçek veriyle çalışır).

### Senaryo A — İki makine (önerilen)

LLM, aynı ağdaki GPU'lu makinede çalışır; backend ona ağ üzerinden bağlanır.

**LLM makinesinde (Windows):**

```powershell
ollama pull qwen3:14b           # yavaş kalırsa: ollama pull qwen3:8b

# Kullanıcı ortam değişkenleri (sonra Ollama'yı tepsi simgesinden tamamen kapatıp yeniden açın)
setx OLLAMA_HOST "0.0.0.0:11434"         # ağdan erişim
setx OLLAMA_KEEP_ALIVE "-1"              # model bellekte kalsın (ilk istekte yükleme beklemesi olmasın)
setx OLLAMA_CONTEXT_LENGTH "16384"       # VRAM yetmezse 8192
setx OLLAMA_FLASH_ATTENTION "1"          # opsiyonel: KV cache belleğini azaltır
setx OLLAMA_KV_CACHE_TYPE "q8_0"         # opsiyonel: KV cache'i yarıya indirir

# Windows Firewall gelen kuralı (Yönetici PowerShell). Ağ profili "Özel" olmalı.
New-NetFirewallRule -DisplayName "Ollama 11434" -Direction Inbound -Protocol TCP -LocalPort 11434 -Action Allow -Profile Private

ipconfig        # IPv4 adresini not edin, örn. 192.168.1.42
ollama ps       # model yüklendikten sonra GPU/CPU payını gösterir (100% GPU olmalı)
```

> **Context uzunluğu neden önemli:** Ollama'nın OpenAI uyumlu `/v1` endpoint'i istek başına `num_ctx`
> kabul etmez. Context kısa kalırsa tool şemaları + veri + sohbet sessizce kesilir ve tool calling bozulur.
> VRAM tahmini: `qwen3:14b` Q4_K_M ≈ 9.3 GB + KV cache (≈160 KB/token fp16 → 16k ≈ 2.6 GB, q8_0 ile ≈ 1.3 GB).

**Backend makinesinde** `backend/.env`:

```ini
LLM_PROVIDER=openai
LLM_BASE_URL=http://192.168.1.42:11434/v1
LLM_MODEL=qwen3:14b
LLM_TIMEOUT=120
```

Kontrol:

```powershell
curl http://192.168.1.42:11434/v1/models         # model listesi gelmeli
curl http://127.0.0.1:8000/api/health            # llm.reachable ve llm.model_available = true
```

### Senaryo B — Tek makine (yedek; demo günü ağ sorunu olursa)

Her şey aynı bilgisayarda. 8 GB VRAM'de `qwen3:14b` sığmaz (CPU'ya taşar, yavaşlar) → `qwen3:8b` kullanın.

```powershell
ollama pull qwen3:8b
setx OLLAMA_KEEP_ALIVE "-1"
setx OLLAMA_CONTEXT_LENGTH "8192"
```

```ini
LLM_PROVIDER=openai
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:8b
```

Son çare: `LLM_PROVIDER=mock` — demo LLM'siz de çalışır (uyarılar, skorlar, grafikler, şablon açıklamalar).

### Tool calling ve thinking notları

- Ollama'da Qwen3 için native tool calling **ek ayar gerektirmez** (model template'i Hermes
  `<tool_call>` formatını ayrıştırır). vLLM kullanılırsa: `--enable-auto-tool-choice --tool-call-parser hermes`.
- `LLM_TOOL_MODE=auto`: önce native dener; sunucu tools'u reddederse veya model tool çağrısını düz metin
  olarak basarsa prompt tabanlı JSON ayrıştırıcıya (`llm/toolcall_parser.py`) düşer.
- Thinking varsayılan kapalı (`LLM_THINKING=false`): sistem prompt'una Qwen3'ün `/no_think` soft
  switch'i eklenir ve `<think>` blokları temizlenir. vLLM'de ek olarak
  `LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}`.

## 3. Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env       # VITE_API_BASE_URL=http://127.0.0.1:8000
npm run dev                        # http://localhost:5173
```

Ayrıntılar: [`frontend/README.md`](frontend/README.md).

### Asistan API (sohbet, uyarı açıklamaları, günlük rapor)

Arayüzdeki **sohbet**, **Assistant alerts** ve **Daily report** kartları LLM ekibinin ayrı API'sine
doğrudan bağlanır (kural motoru, `[D]`/`[K]` kaynak etiketleri ve sayı doğrulayıcı o API'nin içinde).
Mürettebat, metrik, check-in ekranları ve "Active alerts" listesi bizim backend'de kalır.

```bash
# frontend/.env
VITE_ASSISTANT_API_URL=http://192.168.1.12:8000
# VITE_ASSISTANT_ASTRONAUT_ID=      # boş: asistan API'sinde yüklü astronot (GET /health -> current)
```

- Bağlantı testi: `curl http://<IP>:8000/health` → `{"ok": true, "current": "A1", ...}`; şema: `http://<IP>:8000/docs`.
- Uçlar: `POST /chat {"message"}` → `answer` + `sources` · `GET /alerts` → `fallback` (her zaman dolu) + `explanation`
  · `GET /daily_report` → `report` (`force=true` yeniden üretir) · `GET /records` · `POST /select`
  · `POST /reset` (sohbet geçmişi).
- Yerel model 10–30 sn sürebilir; istek zaman aşımı 180 sn.
- **Astronot/gün senkronu:** astronot sayfası açılınca veya zaman kaydırıcısı değişince arayüz
  `GET /records` listesine bakar ve `POST /select {"astronaut_id", "day"}` gönderir (görev günü = sayfadaki
  mission day); ardından rapor ve uyarılar yeniden çekilir. Kartlardaki "Assistant data: AST-02 · day 157"
  etiketi asistanın o an hangi veriyle çalıştığını gösterir. Seçim sunucu tarafında **tektir** (aynı API'yi
  kullanan iki tarayıcı birbirinin seçimini değiştirir). `/records` yoksa (eski API) seçim yapılmaz.
- Cevaplar markdown'dır (kalın, liste, emoji); `[D1]`/`[K1]` etiketleri 📊/📄 kaynak rozetine çevrilir.
- **Acil tespit LLM'den bağımsız kalır:** her sohbet mesajı ayrıca bizim backend'in kural tabanlı
  `POST /api/emergency/check` ucuna gönderilir; banner asistan cevabını beklemez.

## 4. NASA verisi geldiğinde

1. Dosyayı `data/raw/` altına koyun.
2. Format long/wide CSV veya JSON kayıtlarıysa doğrudan yükleyin:
   `curl -F "file=@data/raw/nasa.csv" http://127.0.0.1:8000/api/ingest`
3. Değilse `backend/app/ingest/` altına yeni bir adaptör yazın (bkz. `CLAUDE.md` → "Nasıl genişletilir").
4. Yeni metrikler için `backend/config/metrics.yaml`'a giriş ekleyin (placeholder eşik + TODO).
