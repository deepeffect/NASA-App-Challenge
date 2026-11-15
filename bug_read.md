# Hata notu: arka planda başlatılan geliştirme sunucuları durdurulunca kapanmıyor (Windows)

> **Durum: depo tarafında ÇÖZÜLDÜ, araç tarafında AÇIK.** İlk görülme: 2026-11-14.
>
> - Depo tarafı: `npm run stop` eklendi; `dev` ve `serve` başlamadan önce kontrol ediyor (aşağıda "Çözüm").
> - Araç tarafı: Claude Code arka plan görevini durdururken süreç ağacını kapatmıyor; bu hâlâ böyle.
>
> Bu bir **uygulama hatası değil**: astronot (`/me`) ve Dünya (`/monitor`) ekranlarının davranışını etkilemez.
> Geliştirme ortamı sorunudur ve Windows'ta çalışan herkesi etkileyebilir.

## Özet

Windows'ta `npm run dev:ship` veya `npm run dev:earth`, Claude Code'un **arka plan görevi** olarak başlatılıp sonra
durdurulduğunda araç "durduruldu" der, ama süreç zincirinin **tamamı** çalışmaya devam eder. API (8000 / 8001) ve Vite
(5173 / 5174) portları dolu kalır.

Artık yapılacak şey tek komut:

```bash
npm run stop            # iki rolün de sunucularını ve artakalan oturumlarını kapatır
npm run stop -- ship    # sadece gemi (8000 + 5173)
npm run stop -- earth   # sadece Dünya (8001 + 5174)
```

## Tam olarak ne oluyor

`npm run dev:ship` şu süreç zincirini kurar (`scripts/station.mjs`, `scripts/backend-dev.mjs`); Windows'ta 13 süreç:

```
bash … npm run dev:ship                      (kabuk sarmalayıcıları)
└─ node npm-cli.js run dev:ship
   └─ cmd /c node scripts/station.mjs dev ship
      └─ node scripts/station.mjs dev ship          (concurrently)
         ├─ cmd /c "node scripts/backend-dev.mjs --port 8000"
         │  └─ node scripts/backend-dev.mjs --port 8000        (izleyici: .py değişince uvicorn'u yeniden başlatır)
         │     └─ backend\.venv\Scripts\python.exe -m uvicorn app.main:app …   (venv başlatıcısı)
         │        └─ python.exe -m uvicorn app.main:app …                      (8000'i dinler)
         └─ cmd /c "npm --prefix frontend run dev -- --port 5173 --strictPort"
            └─ node npm-cli.js --prefix frontend run dev …
               └─ cmd /c vite --port 5173 --strictPort
                  └─ node …\vite\bin\vite.js --port 5173 --strictPort         (5173'ü dinler)
```

Görev durdurulunca bu zincir kapanmıyor. İki neden birleşiyor:

1. Windows'ta üst süreç sonlandırılınca alt süreçler kendiliğinden ölmez.
2. Zorla sonlandırmada Node'un sinyal işleyicileri çalışmaz. `scripts/backend-dev.mjs` kapanırken alt süreç ağacını
   temizleyecek şekilde yazılmış (`killTree` → `taskkill /T /F`), ama bu kod SIGINT / SIGTERM / SIGHUP gelince çalışır.

İkinci bir tuzak: sadece portu dinleyen süreçleri (uvicorn, vite) elle kapatmak **yetmez**. `backend-dev.mjs` izleyicisi
hayatta kalır ve `backend/app/` altında bir `.py` dosyası değişince (kaydetme, `git checkout`) uvicorn'u yeniden başlatacak
şekilde yazılmıştır; yani port sonradan "kendiliğinden" yeniden dolabilir.

## Gözlemler

Ortam: Windows 11 Home 10.0.26200, Git Bash, Node 24.19.0, Python 3.14.3.

| Ne yapıldı | Sonuç |
|---|---|
| `npm run dev:ship` + `npm run dev:earth` arka planda başlatıldı, sonra durduruldu | Araç "durduruldu" dedi; 8000, 8001, 5173, 5174 dinlenmeye devam etti |
| Sadece port dinleyen süreçler elle kapatıldı (üç ayrı sefer) | Portlar boşaldı, ama her oturumun geri kalanı (kabuk, npm, `station.mjs`, `backend-dev.mjs`: 7 süreç) açık kaldı |
| Birkaç saat sonra süreç listesine bakıldı | Üç eski gemi oturumu ve bir Dünya oturumundan toplam **34 süreç** hâlâ çalışıyordu |
| Yarıda kesilen bir test ajanının başlattığı geçici backend (port 8023) | Ajan öldü, backend dinlemeye devam etti |

## Nasıl yeniden üretilir

1. Windows'ta Claude Code'a `npm run dev:ship` komutunu arka planda çalıştırt.
2. Sunucular açılınca görevi durdurt.
3. `netstat -ano | findstr LISTENING | findstr ":8000 :5173"` → iki port da hâlâ dinleniyor.

## Çözüm (depo tarafı)

### `npm run stop [-- ship|earth] [--port N] [--force]`

`scripts/station.mjs stop`:

- Rolün portlarını (API + web) dinleyen süreçleri bulur ve dinleyen süreçten **zincirin en üst halkasına** kadar çıkıp
  bütün ağacı kapatır (Windows: `taskkill /PID <pid> /T /F`, diğerleri: SIGTERM).
- Port dinlemeyen artık oturumları da (sunucusu kapatılmış ama izleyicisi yaşayan) bulur ve kapatır.
- Portu bu depoya ait olmayan bir program tutuyorsa **dokunmaz**, ne olduğunu yazar ve 1 ile çıkar; `--force` ile onu da
  kapatır. "Bu depoya ait" = komut satırında deponun yolu geçiyor (uvicorn `backend/.venv`'den, Vite
  `frontend/node_modules`'ten çalışır).
- Kendini ve kendi üst süreçlerini asla kapatmaz.
- `--port N`: o portu da kapatır; rol verilmediyse sadece onu (`npm run serve -- --port N` için).

### Başlamadan önce kontrol

`npm run dev`, `dev:ship`, `dev:earth` ve `serve` başlamadan önce portlarına ve eski oturumlara bakar. Sorun varsa
başlamaz, kimin tuttuğunu yazar ve komutu önerir:

```
✖ Port 8000 dolu: pid 4048 python.exe
    …\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
✖ Eski bir geliştirme oturumu hâlâ açık (şu an port dinlemiyor): pid 25372 bash.exe
    … npm run dev:ship

Başlatılmadı. Önce kapatın:  npm run stop -- ship
```

Sadece bakmak için: `node scripts/station.mjs check ship` (temizse sessiz, çıkış kodu 0; değilse 1).

### Ortak modül

`scripts/ports.mjs`: `listeningPids`, `listeningPid`, `killPid`, `killTree`, `listProcesses`, `descendantsOf`.
`frontend/scripts/smoke-earth.ts` içindeki `listeningPid` ve `killPid` buraya taşındı; smoke testi artık oradan kullanıyor.

### Nasıl doğrulandı (Windows)

- Hata yeniden üretildi (arka planda başlat, durdur): `dev:ship`, `dev` ve `serve` başlamayı reddetti ve tutan süreçleri gösterdi.
- `npm run stop` yukarıdaki 34 artık süreci 4 süreç ağacı olarak kapattı; dört port boşaldı, zincirden süreç kalmadı.
- Çalışan (durdurulmamış) bir `dev:ship` oturumu `npm run stop -- ship` ile tamamen kapandı.
- Role ait bir portu depoyla ilgisiz bir program tutarken: `dev:earth` başlamadı, `stop` dokunmadı (çıkış kodu 1),
  `stop --force` kapattı.
- `serve --port 8055`: temizken başladı, ikinci kez başlamayı reddetti, `npm run stop -- --port 8055` kapattı.

**Denenmedi:** macOS / Linux. O yollar (`lsof`, `ps`, SIGTERM) yazıldı ama çalıştırılmadı.

## Hâlâ açık olan (araç tarafı)

Claude Code, arka plan görevini durdururken Windows'ta bütün süreç ağacını kapatmalı. Bunun için bir hata bildirimi
taslağı hazırlandı; henüz gönderilmedi (Claude Code'da `/feedback` ile gönderilir). O düzelene kadar: Claude Code ile
arka planda sunucu başlattıysanız, işiniz bitince `npm run stop` çalıştırın.

## Elle bakmak isterseniz

Portları kimin tuttuğunu görmek:

```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000,8001,5173,5174 -ErrorAction SilentlyContinue |
  Select-Object LocalPort, OwningProcess
```

```bash
netstat -ano | grep LISTENING | grep -E ':(8000|8001|5173|5174)\s'
```

`taskkill /IM node.exe` veya `taskkill /IM python.exe` **kullanmayın**: makinedeki bütün Node ve Python süreçlerini
(editör eklentileri dahil) kapatır.

## Bilinmeyenler

- Normal bir terminalde `Ctrl+C` ile durdurunca aynı şey oluyor mu: **denenmedi.** Betikler `Ctrl+C`'de temizlik yapacak
  şekilde yazılmış, bu yüzden büyük olasılıkla olmuyor.
- Sorun şimdiye kadar yalnızca Claude Code'un arka plan görevlerinde (ve onun başlattığı alt ajanlarda) görüldü.
