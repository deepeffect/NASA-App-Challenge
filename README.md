# Astronot Sağlık İzleme Sistemi — AI Gambit

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
```

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

> `main` branch'inde endpoint'ler sözleşmeye uygun **stub** veri döner (arayüz geliştirmek için yeterli);
> `seed` komutu ve gerçek analiz `feat/backend-core` ile gelir.

```powershell
.venv\Scripts\python -m app.cli seed --seed 42            # 4 astronot × 180 gün (DB'yi sıfırlar)
.venv\Scripts\python -m app.cli seed --seed 42 --spe-day 120   # + güneş parçacık olayı senaryosu
.venv\Scripts\python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger UI: <http://localhost:8000/docs>
- Sağlık: <http://localhost:8000/api/health>

Demo senaryosu: **Astronot 2**'de 150. günden itibaren uyku süresi düşer → birkaç gün sonra stres
artar ve HRV düşer → istirahat nabzı yükselir. Diğer astronotlar normaldir. Zaman kaydırıcısıyla
(`?as_of=`) yeşil → sarı → kırmızı geçişi izlenebilir.

### Testler

```powershell
.venv\Scripts\python -m pytest            # mock LLM + geçici DB; .env'den bağımsız
```

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
curl http://localhost:8000/api/health            # llm.reachable ve llm.model_available = true
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
Copy-Item .env.example .env       # VITE_API_BASE_URL=http://localhost:8000
npm run dev                        # http://localhost:5173
```

Ayrıntılar: [`frontend/README.md`](frontend/README.md).

## 4. NASA verisi geldiğinde

1. Dosyayı `data/raw/` altına koyun.
2. Format long/wide CSV veya JSON kayıtlarıysa doğrudan yükleyin:
   `curl -F "file=@data/raw/nasa.csv" http://localhost:8000/api/ingest`
3. Değilse `backend/app/ingest/` altına yeni bir adaptör yazın (bkz. `CLAUDE.md` → "Nasıl genişletilir").
4. Yeni metrikler için `backend/config/metrics.yaml`'a giriş ekleyin (placeholder eşik + TODO).
