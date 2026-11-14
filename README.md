# Astronot Sağlık İzleme Sistemi — AI Gambit

> **Hızlı başlangıç** (kök klasörde; gereken: Node 20.19+, [uv](https://docs.astral.sh/uv/)):
> 1. `npm run setup` — Python ortamı, npm paketleri, `.env` dosyaları, API tipleri, demo verisi
> 2. `npm run dev:ship` — gemi: API <http://127.0.0.1:8000/docs> + astronot ekranı <http://localhost:5173/me>
> 3. `npm run dev:earth` — Dünya üssü: API :8001 + <http://localhost:5174/monitor> (gemiden downlink alır)
>
> Gerçek kurulum (3 bilgisayar, `npm run serve`): aşağıda **"3 bilgisayar kurulumu"**.
> Eski ekranlar (sentetik veri): `npm run dev` → <http://localhost:5173/legacy>

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
| `npm run dev:ship` | gemi rolü: backend `127.0.0.1:8000` (`ship.db`, veri seti ilk açılışta yüklenir) + arayüz `:5173` (`/me`). `-- --lan` → `0.0.0.0` |
| `npm run dev:earth` | Dünya rolü: backend `127.0.0.1:8001` (`earth.db`, `SHIP_URL=http://127.0.0.1:8000`) + arayüz `:5174` (`/monitor`) |
| `npm run reset` | seçili rolün DB'sini sıfırlar: `npm run reset -- ship` / `-- earth` (rol verilmezse `backend/.env`'deki `STATION_ROLE`) |
| `npm run serve` | arayüzü derler, backend'i `0.0.0.0:8000`'de başlatır ve derlenmiş arayüzü kendisi servis eder (gemi `/me`, Dünya `/monitor`). Rol `backend/.env`'den; `npm run serve -- earth --port 8001 --no-build` |
| `npm run setup` | uv kontrolü → `backend/.venv` + `uv pip install -e ".[dev]"` → `.env.example`→`.env` (yoksa) → npm paketleri → `gen:api` → DB boşsa `seed --seed 42`. Tekrar çalıştırmak güvenli. |
| `npm run dev` | **eski ekranlar** (`DATA_SOURCE=synthetic`, `health.db`, `/legacy`): backend (`127.0.0.1:8000`) + frontend (Vite `:5173`) birlikte, `api`/`web` renkli önekleriyle; biri kapanırsa diğeri de kapanır. Backend `app/` altındaki `.py` değişince kendiliğinden yeniden başlar (`scripts/backend-dev.mjs`; uvicorn `--reload` Windows'ta tüm konsola Ctrl+C gönderip `npm run dev`'i düşürdüğü için kullanılmıyor) |
| `npm run dev:backend` / `npm run dev:frontend` | tek tek |
| `npm run dev:backend:lan` | backend'i ağa aç (`0.0.0.0:8000`) — takım arkadaşları bağlanacaksa |
| `npm run seed` | eski ekranların sentetik demo verisini yeniden yükle (`health.db`'yi sıfırlar). Ek argüman: `npm run seed -- --spe-day 120` |
| `npm run test` | backend `pytest` + frontend tip kontrolü |
| `npm run smoke` | Playwright ile 7 ekranın tam sayfa görüntüsü (`frontend/screenshots/`) + konsol hatası / başarısız istek raporu. `npm run dev` açıkken çalıştırın; ilk sefer: `npx --prefix frontend playwright install --only-shell chromium` |

Aşağıdaki bölümler aynı adımların elle yapılışını anlatır.

## 3 bilgisayar kurulumu (gemi · astronot terminali · Dünya üssü)

Aynı yerel ağda üç bilgisayar; **internet yok**, Docker/bulut/tünel yok. Aynı repo iki rolde çalışır
(`STATION_ROLE`). Kurallar için tek doğru kaynak: [`frontend/reference/personal-artifact.html`](frontend/reference/personal-artifact.html).

```
 Astronot terminali ──(tarayıcı)──▶  GEMİ  :8000  ──(downlink: snapshot + SSE)──▶  DÜNYA ÜSSÜ :8000
   http://<gemi>:8000/me            Ollama + backend + bütün veri                  earth.db, /monitor (salt okunur)
                                    ship.db, gizlilik filtresi BURADA
```

| Rol | Ne çalışır | Açtığı ekran | Veri |
|---|---|---|---|
| **Gemi** (`STATION_ROLE=ship`) | Ollama + backend (`npm run serve`) | `/me` (astronot) | `data/processed/ship.db` (veri seti ilk açılışta `data/raw/astronaut_health.json`'dan yüklenir) |
| **Astronot terminali** | sadece tarayıcı | `http://<gemi>:8000/me` | yok |
| **Dünya üssü** (`STATION_ROLE=earth`) | backend (`npm run serve`) | `/monitor` (EARTH / EARTH) | `data/processed/earth.db` — sadece gemiden gelen, **gemide filtrelenmiş** veri |

- Paylaşılmamış veri (ruh hali, stres, check-in cevapları, CMO bildirimleri) gemi bilgisayarından hiç çıkmaz.
- Gemi, Dünya bağlantısı olmadan tam çalışır; bağlantı gelince Dünya kaldığı yerden devam eder.
- Diğer rolün ekranı açılırsa arayüz "bu ekran bu istasyonda değil" gösterir.

### 1) Her bilgisayarda (bir kez)

```powershell
git clone <repo> ; cd NASA-App-Challenge
npm run setup            # Python ortamı, npm paketleri, .env dosyaları
ipconfig                 # IPv4 adresini not edin (Wi-Fi/Ethernet), örn. gemi 192.168.1.10
```

Windows ağ profili **Özel** olmalı (Ayarlar → Ağ ve İnternet → bağlantı → Ağ profili türü: Özel);
"Ortak" profilde gelen bağlantılar engellenir.

Ortak bir downlink anahtarı üretin (iki istasyonda **aynı** olacak):

```powershell
backend\.venv\Scripts\python -c "import secrets; print(secrets.token_urlsafe(24))"
```

### 2) Gemi bilgisayarı

`backend/.env`:

```ini
STATION_ROLE=ship
DATA_SOURCE=astronaut_health
EARTH_LINK_TOKEN=<ortak-anahtar>
# Ollama aynı makinede
LLM_PROVIDER=openai
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen3:14b
# scripted (varsayılan) | auto: LLM'e ulaşılamazsa scripted | llm
CHECKIN_MODE=scripted
# Gecikme deneyi: olaylar Dünya'ya bu kadar saniye sonra gider (0 = hemen)
DOWNLINK_DELAY_SECONDS=0
# Gerçek ışık gecikmesi etiketi (dakika; sadece gösterilir)
DOWNLINK_SIMULATED_LIGHT_DELAY_MINUTES=20
```

Ollama (bkz. "2. LLM servisi"; backend aynı makinede olduğu için `OLLAMA_HOST` değiştirmek gerekmez):

```powershell
ollama pull qwen3:14b                    # 8 GB VRAM: qwen3:8b
setx OLLAMA_KEEP_ALIVE "-1"
setx OLLAMA_CONTEXT_LENGTH "16384"
```

Firewall (Yönetici PowerShell) — astronot terminali ve Dünya üssü gemiye 8000'den bağlanır:

```powershell
New-NetFirewallRule -DisplayName "Astro Health 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

Çalıştır:

```powershell
npm run serve            # arayüzü derler, 0.0.0.0:8000'de başlar; ağ adreslerini yazar
```

### 3) Astronot terminali

Sadece tarayıcı: `http://<gemi-ip>:8000/me`. Kiosk modu (tam ekran, adres çubuğu yok; çıkış Alt+F4):

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk http://192.168.1.10:8000/me
# Edge: msedge --kiosk http://192.168.1.10:8000/me --edge-kiosk-type=fullscreen
```

Giriş: astronot kimliği (A000 … A199), şifre kimlikle aynı (büyük/küçük harf duyarsız).

### 4) Dünya üssü

`backend/.env`:

```ini
STATION_ROLE=earth
SHIP_URL=http://192.168.1.10:8000
EARTH_LINK_TOKEN=<ortak-anahtar>
# EARTH_PASSWORD=EARTH
```

```powershell
npm run serve            # tarayıcıda http://127.0.0.1:8000/monitor  (EARTH / EARTH)
```

Dünya ekranını başka cihazlar da açacaksa Dünya bilgisayarında da 8000 için aynı firewall kuralını ekleyin.

### 5) Kontrol

```powershell
curl http://192.168.1.10:8000/api/station          # gemi: {"role":"ship", ...}
curl http://127.0.0.1:8000/api/station             # Dünya'da: {"role":"earth", ...}
```

Dünya ekranındaki bağlantı durumu (`GET /api/link/status`, giriş gerekir): bağlı mı, son temas, gemide
bekleyen olay sayısı. Gemi kapatılıp açılırsa Dünya kendiliğinden yeniden bağlanır ve eksik olayları alır.
Gemi DB'si sıfırlanırsa (`npm run reset`) Dünya baştan senkronize olur.

Güncelleme: her bilgisayarda `git pull` → `npm run serve` (veri seti değiştiyse gemi açılışta yeniden yükler).

### Tek makinede geliştirme

```powershell
npm run dev:ship         # API :8000 (ship.db) + arayüz :5173  → http://localhost:5173/me
npm run dev:earth        # API :8001 (earth.db, SHIP_URL=http://127.0.0.1:8000) + arayüz :5174 → /monitor
npm run reset -- ship    # rolün DB'sini sıfırla (earth için: npm run reset -- earth)
```

İki rol aynı geliştirme anahtarını kullanır (`EARTH_LINK_TOKEN` ortamda yoksa `dev-link-token`).

> **Otomatik yeniden başlatma (sadece `dev:*`):** `scripts/backend-dev.mjs`, `backend/app/` altındaki `.py`
> değişikliklerinde backend'i yeniden başlatır (500 ms debounce; `__pycache__`, `.venv`, `data/`, `node_modules`
> yok sayılır). İki rol aynı klasörü izlediği için bir değişiklik `dev:ship` ve `dev:earth`'ü birlikte yeniden
> başlatır. Windows'ta zaman zaman içeriği değişmemiş dosyalar için de yeniden başlatma görüldü; kökü bulunamadı
> (dosya okuma, Python import'u, git ve pytest tetiklemiyor). Ekran kısa kesintiden kendiliğinden toparlanır.
> `npm run serve` bu izleyiciyi **kullanmaz** (uvicorn `--reload` olmadan çalışır): demo sırasında otomatik
> yeniden başlatma olmaz.


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

## 4. NASA verisi geldiğinde

1. Dosyayı `data/raw/` altına koyun.
2. Format long/wide CSV veya JSON kayıtlarıysa doğrudan yükleyin:
   `curl -F "file=@data/raw/nasa.csv" http://127.0.0.1:8000/api/ingest`
3. Değilse `backend/app/ingest/` altına yeni bir adaptör yazın (bkz. `CLAUDE.md` → "Nasıl genişletilir").
4. Yeni metrikler için `backend/config/metrics.yaml`'a giriş ekleyin (placeholder eşik + TODO).
