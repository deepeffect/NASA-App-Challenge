# Frontend — Astronot Sağlık İzleme

Vite + React 19 + TypeScript 5 · Tailwind 4 · Recharts 3 · TanStack Query 5 · react-router 7 ·
`@microsoft/fetch-event-source` (POST + SSE).

## İki istasyon, tek derleme

Aynı derleme iki istasyonda servis edilir; her istasyon kendi ekranını açar, diğerinde "bu ekran bu
istasyonda değil" gösterilir (`GET /api/station`):

| Rota | İstasyon | Klasör | Durum |
|---|---|---|---|
| `/me` | gemi (astronot terminali) | `src/apps/personal/` | astronot ekranı: giriş, durum + şerit, yapılacaklar ("Yaptım"), günlük check-in + paylaşım, ayrıntılar, "Asistana sor" |
| `/monitor` | Dünya üssü | `src/apps/monitor/` | Dünya ekranı; astronot detayı `/monitor/astronaut/:id` (ortak bileşenler, `audience="earth"`) |
| `/legacy/*` | gemi + `DATA_SOURCE=synthetic` | `src/app/LegacyApp.tsx` + `src/features/` | eski ekranlar |

- Kurallar ve görünüm için tek doğru kaynak: `reference/personal-artifact.html` (prototip).
- İki ekranın ortak bileşenleri: `src/shared/health/` (aynı `DayView` / `StripDay` sözleşmesi; Dünya'da gizli alanlar `hidden: true`).
  `StatusCard`, `TodoCard`, `ReadingsTable`, `ScoreChart`, `WhoRow`, `SelfCareDialog`; hepsi `audience: "astronaut" | "earth"` alır
  ve bir `HealthRoot` içinde kullanılır (prototipin teması, açık/koyu, tek dar kolon, offline yazı tipleri). Kullanım örneği ve
  ekranların kendi kartları için hazır sınıflar: `src/shared/health/index.ts`.
- Yeni uçların istemcisi: `src/api/station.ts` (`stationApi.*`, `openMonitorStream`, `chat`). Dil her istekte
  `lang` ile açıkça gider (`src/shared/i18n.tsx`, TR/EN), token sekme oturumunda saklanır.
- Geliştirme: kökte `npm run dev:ship` (→ <http://localhost:5173/me>) ve `npm run dev:earth` (→ <http://localhost:5174/monitor>).
- Üretim: kökte `npm run serve` arayüzü `VITE_API_BASE_URL` boş (aynı adres) derler; backend `dist/`'i kendisi servis eder.

## Kurulum

```powershell
cd frontend
npm install
Copy-Item .env.example .env     # bash: cp .env.example .env
npm run dev                     # http://localhost:5173 (ağdan da erişilebilir: host=true)
```

`.env` (sadece geliştirme; `npm run serve` bunu boş derler, `dev:ship` / `dev:earth` kendileri ayarlar):

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
reference/      personal-artifact.html — prototip (kurallar ve görünüm için tek doğru kaynak)
src/
  apps/
    personal/   /me — astronot ekranı (gemi)
    monitor/    /monitor — Dünya üssü ekranı
  shared/       i18n (TR/EN), station (istasyon bilgisi, rol koruması), Placeholder, health/ (ortak bileşenler)
  api/          station.ts (yeni uçlar) · client.ts (eski uçlar) · sse.ts (eski sohbet akışı) · queries.ts · types.ts (üretilen)
  app/          App (kök router), LegacyApp (/legacy), Layout, AsOfContext (global as_of), TimeSlider, HealthIndicator
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

Eski ekranları (`/legacy`) dener. Backend ve Vite açıkken (kökte `npm run dev`):

```powershell
npx playwright install --only-shell chromium   # ilk sefer, sadece headless Chromium (~290 MB, kullanıcı dizinine)
npm run smoke                                  # kökte veya frontend/ içinde
```

`scripts/smoke.ts` şu ekranları açar ve `screenshots/` altına kaydeder (gitignore'da):
mürettebat · AST-02 150. gün (yeşil) · AST-02 157. gün (kırmızı, açıklama açık) · örnek dedektörlerle metrik
grafiği · sohbet (mock cevap + acil durum bandı) · check-in formu · mürettebat 390 px. Konsol hataları,
yakalanmamış JS hataları ve 4xx/5xx istekler raporlanır; sorun varsa çıkış kodu 1.
Örnek dedektörler ekranı için 8001 portunda geçici ikinci bir backend başlatılır (çalışan dev sunucusuna dokunmaz).

Vite'a hazırlık kontrolü takılırsa ("Backend veya Vite açık değil" ama ikisi de açıksa) smoke'u backend'in
servis ettiği derlemeye karşı çalıştırın: kökte `DATA_SOURCE=synthetic` ile `npm run serve -- ship`, sonra
`SMOKE_WEB=http://127.0.0.1:8000 SMOKE_API=http://127.0.0.1:8000 DATA_SOURCE=synthetic npm run smoke`.

### Dünya ekranı smoke testi

Gemi (:8000) ve Dünya (:8001, web :5174) lokal açıkken (`npm run dev:ship` + `npm run dev:earth`):

```powershell
npm run smoke -- earth      # kökte veya frontend/ içinde; görüntüler: screenshots/earth/
```

`scripts/smoke-earth.ts`: giriş ve genel görünüm (1440 / 1920, TR koyu, EN açık) · gemide mürettebatın ilk
astronotu (DEMO_CREW[0]) check-in + "Sadece skorlar" → Dünya'da gecikme + 2 sn içinde, cevap metni yok · paylaşılmamış
günde ruh hali / stres "Paylaşılmadı" (kartta ve detayın ölçümler tablosunda, "Uyku, ruh hali ve stres" alan skoru dahil)
· gemi kapatılır (uyarı, son durum korunur) ve açılır (akış kaldığı seq'ten, boşluksuz) · astronot detayı: paylaşıma
göre check-in paneli, iki çizgili grafik, önceki/sonraki · mürettebat kartında "Aktif" rozeti · akışta "Sadece mürettebat".
Ayrıca: detaydaki ortak bileşenlerin bütün hesaplanmış stili `.mon` dışındakiyle (yani /me'dekiyle) aynı olmalı ve
`monitor.css`'teki her seçici `.mon` ile başlayıp ortak bileşenleri (`.ahc`) dışlamalı. Dünya ekranı gemiye hiç istek
atmamalı. Gemi testte smoke'un kendi sürecinde açılır, sonunda dev:ship'teki yerine döner (bu sırada dev:earth
backend'i de bir kez yeniden başlar; izleyici yoksa gemi kapalı kalır, smoke arka planda sunucu bırakmaz). Paylaşım geri
alınamadığı için süre ölçümünü tekrarlamak isterseniz önce `npm run reset -- ship` ve `npm run reset -- earth`.

### Astronot ekranı smoke testi

Gemi lokal açıkken (`npm run dev:ship`, web :5173):

```powershell
npm run smoke -- personal   # kökte veya frontend/ içinde; görüntüler: screenshots/personal/
```

`scripts/smoke-personal.ts`: giriş kartı (kimlik aralığı API'den, EARTH yok) · A000 ile giriş · şeritte gün seçimi
(geçmiş gün salt okunur) · "Yaptım" · bugünün check-in'i sonuna kadar · "Sadece skorlar" ile paylaşım → geminin
downlink akışındaki `checkin.shared` olayında ruh hali / stres skoru var, cevap metni yok · ayrıntılar ve öz bakım
penceresi · "Asistana sor" (mock) + acil belirti kutusu (sohbet downlink'e girmez) · check-in'de acil belirti →
"Gemideki sağlık sorumlusu bilgilendirildi" kutusu (Dünya'ya gitmez) · TR → EN, yenileme, çıkış. Ana durumlar 390 ve
1440 px'te, açık ve koyu temada kaydedilir.
Test kendi geçici gemi backend'ini başlatır (port 8010, atılabilir veritabanı) ve sayfanın API isteklerini oraya
yönlendirir: `ship.db`'ye dokunmaz, her çalıştırmada baştan tekrarlanabilir. Port doluysa `SMOKE_PERSONAL_PORT`.

## URL'de zaman

Seçili gün URL'de tutulur: `/legacy/astronauts/AST-02?as_of=2026-10-22`. Link paylaşılabilir; geri/ileri çalışır;
sayfalar arası gezinmede gün korunur. "Canlıya dön" parametreyi kaldırır.
