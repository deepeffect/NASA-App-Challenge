# Frontend — Astronot Sağlık İzleme

Vite + React 19 + TypeScript 5 · Tailwind 4 · Recharts 3 · TanStack Query 5 · react-router 7 ·
`@microsoft/fetch-event-source` (POST + SSE).

## Kurulum

```powershell
cd frontend
npm install
Copy-Item .env.example .env     # bash: cp .env.example .env
npm run dev                     # http://localhost:5173 (ağdan da erişilebilir: host=true)
```

`.env`:

```ini
VITE_API_BASE_URL=http://127.0.0.1:8000     # backend başka makinedeyse onun IP'si
```

Backend başka makinedeyse, backend `.env`'deki `CORS_ORIGINS` listesine bu frontend'in adresini
(örn. `http://192.168.1.50:5173`) ekleyin.

## Mock backend ile çalışma

GPU/LLM gerekmez. Backend'i mock modda başlatın (varsayılan `LLM_PROVIDER=mock`):

```powershell
cd ..\backend
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

- `main` branch'inde backend tüm endpoint'lerde **stub** veri döner: 4 astronot, AST-02 kırmızı,
  tüm olay türleri (kural / model tespiti / changepoint / tahmin) ve tüm SSE olayları örneklenir.
- `feat/backend-core` branch'inde gerçek sentetik veri gelir (`python -m app.cli seed --seed 42`);
  sohbet mock modda **gerçek tool çağrıları** yapar (tool_call/tool_result olayları gerçek veriyle).
  Changepoint/forecast katmanlarını görmek için backend `.env`'de örnek dedektörleri açın:
  `ANALYSIS_DETECTORS=threshold,baseline_deviation,trend,example_changepoint,example_forecast,system_pattern`
- Sohbette acil durum bandını denemek için: "göğüs ağrısı var" yazın.

## API tipleri (`gen:api`)

```powershell
npm run gen:api     # ../docs/openapi.json → src/api/types.ts
```

`src/api/types.ts` **üretilen** dosyadır, elle düzenlemeyin. Backend sözleşmesi değişince:
backend'de `python -m app.cli export-openapi` → burada `npm run gen:api` → `npm run typecheck`.
SSE olay modelleri (`SSEToken`, `SSEToolCall`, `SSEDone`, …) de bu dosyaya üretilir.

> `openapi-typescript` 7.x, TypeScript 5.x gerektirir; bu yüzden `typescript` 5'e sabitlendi (TS 7 ile çalışmaz).

## Yapı

```
src/
  api/          client.ts (tipli fetch istemcisi) · sse.ts (sohbet akışı) · queries.ts (TanStack hook'ları) · types.ts (üretilen)
  app/          App (router), Layout, AsOfContext (global as_of), TimeSlider, HealthIndicator
  components/
    ui/         Badges (durum/ciddiyet: renk + ikon + metin), primitives (Card, Button, QueryState), EmergencyBanner, icons, labels, format
    charts/     MetricChart (normal bandı, eşik, olay penceresi, changepoint, tahmin)
  features/
    crew/       Mürettebat ekranı (durum kartları)
    astronaut/  Astronot detayı (sistem skorları, olaylar, grafik, brifing)
    alerts/     Olay kartı, katkı çubukları, "Neden?" açıklaması
    chat/       Sohbet paneli + useChatStream (SSE)
    checkin/    Günlük check-in formu
```

Kurallar:

- Her feature bağımsızdır; başka bir feature'ı **sadece `index.ts`** üzerinden kullanır
  (şu an: `astronaut` → `alerts`, `chat`). Ortak parçalar `components/` altında.
- Tüm veri sorguları global `as_of`'u (`useAsOf()`) alır; zaman kaydırıcısı hepsini birlikte değiştirir.
- Durum **asla sadece renkle** anlatılmaz: `StatusBadge`/`SeverityBadge` her zaman ikon + metin içerir.
- `info` seviyesindeki olaylar olay listesinde değil, sadece brifingde gösterilir.
- Eşik `threshold_verified=false` ise "doğrulanmamış" notu gösterilir.

## Komutlar

| Komut | Açıklama |
|---|---|
| `npm run dev` | geliştirme sunucusu |
| `npm run typecheck` | tip kontrolü |
| `npm run build` | tip kontrolü + üretim derlemesi (`dist/`) |
| `npm run preview` | derlemeyi önizle |
| `npm run gen:api` | API tiplerini yeniden üret |

## Görsel smoke testi (Playwright)

Backend ve Vite açıkken (kökte `npm run dev`):

```powershell
npx playwright install --only-shell chromium   # ilk sefer, sadece headless Chromium (~290 MB, kullanıcı dizinine)
npm run smoke                                  # kökte veya frontend/ içinde
```

`scripts/smoke.ts` şu ekranları açar ve `screenshots/` altına kaydeder (gitignore'da):
mürettebat · AST-02 150. gün (yeşil) · AST-02 157. gün (kırmızı, açıklama açık) · örnek dedektörlerle metrik
grafiği · sohbet (mock cevap + acil durum bandı) · check-in formu · mürettebat 390 px. Konsol hataları,
yakalanmamış JS hataları ve 4xx/5xx istekler raporlanır; sorun varsa çıkış kodu 1.
Örnek dedektörler ekranı için 8001 portunda geçici ikinci bir backend başlatılır (çalışan dev sunucusuna dokunmaz).

## URL'de zaman

Seçili gün URL'de tutulur: `/astronauts/AST-02?as_of=2026-10-22`. Link paylaşılabilir; geri/ileri çalışır;
sayfalar arası gezinmede gün korunur. "Canlıya dön" parametreyi kaldırır.
