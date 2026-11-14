# Hata notu: arka planda başlatılan geliştirme sunucuları durdurulunca kapanmıyor (Windows)

> **Durum: AÇIK.** Düzeltilmedi; her seferinde elle temizleniyor. İlk görülme: 2026-11-14.
>
> Bu bir **uygulama hatası değil**: astronot (`/me`) ve Dünya (`/monitor`) ekranlarının davranışını etkilemez.
> Geliştirme ortamı sorunudur ve Windows'ta çalışan herkesi etkileyebilir.

## Özet

Windows'ta `npm run dev:ship` veya `npm run dev:earth`, Claude Code'un **arka plan görevi** olarak başlatılıp sonra
durdurulduğunda araç "durduruldu" der, ama sunucular çalışmaya devam eder. API (8000 / 8001) ve Vite (5173 / 5174)
portları dolu kalır.

## Tam olarak ne oluyor

`npm run dev:ship` şu süreç zincirini kurar (`scripts/station.mjs`, `scripts/backend-dev.mjs`):

```
npm run dev:ship
└─ node scripts/station.mjs dev ship
   └─ concurrently
      ├─ node scripts/backend-dev.mjs --port 8000
      │  └─ backend\.venv\Scripts\python.exe -m uvicorn app.main:app …   (venv başlatıcısı)
      │     └─ python.exe -m uvicorn app.main:app …                      (asıl süreç; 8000'i dinler)
      └─ npm --prefix frontend run dev -- --port 5173 --strictPort
         └─ node …\vite\bin\vite.js --port 5173 --strictPort            (5173'ü dinler)
```

Görev durdurulunca zincirin **tepesi zorla sonlandırılıyor**. İki şey birleşince alttaki süreçler sahipsiz kalıyor:

1. Windows'ta üst süreç ölünce alt süreçler kendiliğinden ölmez.
2. Zorla sonlandırmada Node'un sinyal işleyicileri çalışmaz. `scripts/backend-dev.mjs` kapanırken alt süreç ağacını
   temizleyecek şekilde yazılmış (`killTree` → `taskkill /T /F`), ama bu kod SIGINT / SIGTERM / SIGHUP gelince çalışır;
   zorla sonlandırmada hiç çalışmaz.

Sonuç: aradaki `node` süreçleri (station.mjs, concurrently, backend-dev.mjs) kapanır; en alttaki `python.exe` (uvicorn)
ve `node.exe` (vite) süreçleri portları dinlemeye devam eder.

## Gözlemler

Ortam: Windows 11 Home 10.0.26200, Git Bash, Node 24.19.0, Python 3.14.3.

| Ne başlatıldı | Durdurduktan sonra hâlâ dinleyen |
|---|---|
| `npm run dev:ship` + `npm run dev:earth` (iki arka plan görevi) | 8000 ve 8001: ikişer `python.exe … uvicorn` (başlatıcı + asıl süreç) · 5173 ve 5174: birer `node.exe … vite.js` |
| `npm run dev:ship` (tek arka plan görevi) | 8000: iki `python.exe … uvicorn` · 5173: bir `node.exe … vite.js` |
| Yarıda kesilen bir test ajanının kendi başlattığı geçici backend (port 8023) | 8023: iki `python.exe … uvicorn` |

Üç durumda da araç görevi "başarıyla durduruldu" olarak bildirdi; `netstat` portların dolu olduğunu gösterdi.
Aradaki `node` süreçleri listede yoktu, yani zincirin üstü kapanmış, altı kalmıştı.

## Nasıl yeniden üretilir

1. Windows'ta Claude Code'a `npm run dev:ship` komutunu arka planda çalıştırt.
2. Sunucular açılınca görevi durdurt.
3. `netstat -ano | findstr LISTENING | findstr ":8000 :5173"` çalıştır → iki port da hâlâ dinleniyor.

## Etkisi

Gözlenen:

- Portlar dolu kalıyor; sunucular elle (süreç numarasıyla) kapatılana kadar çalışıyor.

Beklenen (bu oturumda denenmedi, betiklerin koduna dayanıyor):

- Yeniden `npm run dev:ship` çalıştırınca Vite açılmaz: `--strictPort` ile başlatıldığı için port doluysa çıkar.
  uvicorn da 8000'e bağlanamaz.
- Eski sunucu çalışmaya devam ettiği için tarayıcı ve testler **eski kodu / eski veritabanı durumunu** görebilir;
  "değişikliğim neden görünmüyor" türü yanıltıcı sonuçlar çıkar.
- `npm run smoke -- personal` kendi geçici portu (8010) doluysa başlamaz (çıkış kodu 2).

## Nasıl anlaşılır

PowerShell:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,8001,5173,5174,8010 -ErrorAction SilentlyContinue |
  Select-Object LocalPort, OwningProcess
```

Git Bash:

```bash
netstat -ano | grep LISTENING | grep -E ':(8000|8001|5173|5174|8010)\s'
```

Çıktı boşsa sorun yok.

## Geçici çözüm

Sadece bu depoya ait uvicorn ve vite süreçlerini kapatır (PowerShell). Bu oturumda kullanılan yöntem budur:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'NASA-App-Challenge' -and $_.CommandLine -match 'uvicorn app\.main:app|vite\.js' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

- Depoyu başka adla bir klasöre klonladıysanız `NASA-App-Challenge` yerine o klasör adını yazın.
- `taskkill /IM node.exe` veya `taskkill /IM python.exe` **kullanmayın**: makinedeki bütün Node ve Python süreçlerini
  (editör eklentileri dahil) kapatır.

## Kalıcı çözüm önerileri

1. **Depo tarafında (ekipten biri yapabilir): `npm run stop`.**
   `node scripts/station.mjs stop [ship|earth]` rolün portlarını dinleyen süreci bulup süreç ağacını kapatsın
   (Windows: `taskkill /PID <pid> /T /F`, diğerleri: SIGTERM). Gereken iki yardımcı zaten yazılı:
   `frontend/scripts/smoke-earth.ts` içindeki `listeningPid` ve `killPid`.
   İstenirse `dev` komutu da başlamadan önce portlara bakıp "port X'i şu süreç tutuyor, `npm run stop` çalıştırın"
   diyebilir.
2. **Araç tarafında (Claude Code):** arka plan görevini durdururken Windows'ta bütün süreç ağacını kapatmalı.
   Bunun için bir hata bildirimi taslağı hazırlandı; henüz gönderilmedi (Claude Code'da `/feedback` ile gönderilir).
3. **Tek başına yetmez:** betiklere daha fazla sinyal işleyicisi eklemek. Zorla sonlandırmada Windows sürece sinyal
   iletmediği için o kod hiç çalışmaz.

## Bilinmeyenler

- Normal bir terminalde `Ctrl+C` ile durdurunca aynı şey oluyor mu: **denenmedi.** Betikler `Ctrl+C`'de temizlik yapacak
  şekilde yazılmış, bu yüzden büyük olasılıkla olmuyor.
- macOS / Linux'ta oluyor mu: **denenmedi.**
- Sorun şimdiye kadar yalnızca Claude Code'un arka plan görevlerinde (ve onun başlattığı alt ajanlarda) görüldü.
