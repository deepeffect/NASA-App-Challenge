# API Sözleşmesi (v1)

Arayüz ekibiyle backend arasındaki sözleşme budur. Makine tarafından okunur hali `docs/openapi.json`
(çalışan sunucuda: `http://127.0.0.1:8000/docs` ve `/openapi.json`).

> **İki bölüm:** (A) yeni mimari — gemi (`/me`) ve Dünya üssü (`/monitor`) istasyonları, veri seti
> `data/raw/astronaut_health.json`; (B) eski ekranlar — sentetik veri ve eski analiz motoru (`/legacy`).
> `docs/openapi.json` ikisini birlikte içerir (`python -m app.cli export-openapi`).

- **Base URL:** `http://<backend-host>:8000/api`
- **Format:** JSON, UTF-8. Tarihler `YYYY-MM-DD`, zaman damgaları ISO-8601 UTC (`2026-11-14T08:00:00Z`).
- **Kimlik doğrulama:** yeni mimaride token (A → "Giriş"); eski ekranlarda yok.
- **Hatalar:** yeni uçlar `{"detail", "code"}` (A); eski uçlar `{"detail": "..."}` — `404` bilinmeyen
  astronot/metrik/olay, `422` doğrulama hatası (FastAPI formatı: `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`).
- **TS tipleri:** `frontend/` içinde `npm run gen:api` → `src/api/types.ts`.

> **Sözleşme değişikliği kuralı:** `backend/app/models/schemas.py` değişirse
> `python -m app.cli export-openapi` → bu dosyayı güncelle → frontend'de `npm run gen:api`.

# A. Yeni mimari: gemi ve Dünya istasyonları

Kurallar için tek doğru kaynak: `frontend/reference/personal-artifact.html`. Aynı backend iki rolde çalışır;
her istasyon sadece kendi rolünün uçlarını açar (diğerleri `404`).

| Uç | Gemi (`ship`) | Dünya (`earth`) | Yetki |
|---|:-:|:-:|---|
| `GET /api/station`, `GET /api/catalog` | ✓ | ✓ | yok |
| `POST /api/auth/login`, `GET /api/auth/hint`, `GET /api/auth/me` | ✓ | ✓ | login/hint yok; me: token |
| `GET /api/me`, `GET /api/me/days/{gün}`, `GET /api/personal/{id}[/days/{gün}]` | ✓ | | astronot (başka astronot → `403`) |
| `GET /api/checkin`, `GET /api/checkin/days/{gün}`, `POST /api/checkin/turn`, `/share`, `/reset` | ✓ | | astronot |
| `POST /api/actions/done`, `POST /api/chat` (SSE) | ✓ | | astronot |
| `GET /api/downlink/snapshot`, `GET /api/downlink/stream` (SSE) | ✓ | | `EARTH_LINK_TOKEN` |
| `GET /api/monitor/crew`, `/api/monitor/astronauts/{id}[/days/{gün}]` | | ✓ | Dünya |
| `GET /api/link/status`, `GET /api/stream/monitor` (SSE) | | ✓ | Dünya |

- **Dil:** bütün metinler TR/EN. Öncelik `?lang=` (veya gövdedeki `lang`) > `Accept-Language` > `tr`.
  Frontend dili her istekte `lang` ile açıkça gönderir (`frontend/src/api/station.ts`).
- **Hatalar:** `{"detail": "<kullanıcının dilinde>", "code": "<makine kodu>"}`. `422` ek olarak `errors` listesi taşır.
- **Dünya salt okunur:** `/api` altında GET dışı her istek `403 {"code": "read_only"}` (giriş hariç).
- **Gün numarası:** 1'den başlar; son gün = **bugün** (her astronotun son kaydı). Görev günü ayrıca
  `mission_day` olarak gelir; arayüz "30 günün X. günü · görev günü Y" gösterir (`day_label`).
- **Aralıklar:** simüle veri setinden, tıbbi doğrulama yok (`threshold_source: dataset`, `verified: false`).
  Arayüzde tek dipnot: `threshold_note`.

## Giriş

`GET /api/auth/hint` (giriş kartı):

```json
{"station": "ship", "astronauts": {"first_id": "A000", "last_id": "A199", "count": 200}, "earth_id": null,
 "text": "Astronotlar: A000 – A199 (200 hesap); şifre kimlikle aynıdır."}
```

`POST /api/auth/login` `{"id": "a003", "password": "A003"}` — kimlik = şifre, büyük/küçük harf duyarsız.
Dünya istasyonunda `EARTH` / `EARTH_PASSWORD` (varsayılan `EARTH`).

```json
{"token": "eyJr…", "kind": "astronaut", "subject": "A003", "astronaut_id": "A003", "station": "ship",
 "home_path": "/me", "expires_at": "2026-11-15T13:49:24Z"}
```

Sonraki isteklerde `Authorization: Bearer <token>` (SSE'de `?access_token=`). Hata kodları:

| `code` | HTTP | Ne zaman |
|---|---|---|
| `empty_id` | 400 | kimlik boş |
| `unknown_id` | 401 | bilinmeyen kimlik — mesaj geçerli aralığı söyler |
| `wrong_password` | 401 | şifre yanlış |
| `wrong_station` | 403 | gemide `EARTH` / Dünya'da astronot kimliği |
| `auth_required` / `auth_invalid` | 401 | token yok / geçersiz, süresi dolmuş veya başka istasyonun |
| `forbidden_other_astronaut` | 403 | başka astronotun verisi |
| `forbidden_kind` | 403 | hesap türü bu işlemi yapamaz |

## Astronotun ekranı (gemi)

### `GET /api/me` → `PersonalOverview`

Astronot bilgisi (`mission_label`, `profile_label` dilde), `today` (= `n_days`), 30 günlük şerit
(`strip[]`: `day`, `mission_day`, `status` 0/1/2, `status_label`, `score` = kümülatif skor, `label`).

### `GET /api/me/days/{gün}` → `DayView`

Prototipteki `render()`'ın verisi. Kısaltılmış örnek (A003, gün 30, `lang=tr`):

```json
{"day": 30, "n_days": 30, "mission_day": 30, "is_today": true, "day_label": "30 günün 30. günü · görev günü 30",
 "status": 2, "status_label": "Rahatsız", "health_status": 2, "ground": false,
 "subtitle": "Ana endişe: uyku, ruh hali ve stres", "score": 60.3, "score_text": "60",
 "main_concern": "behavioral", "main_concern_label": "Uyku, ruh hali ve stres",
 "areas": [{"area": "behavioral", "label": "Uyku, ruh hali ve stres", "score": 66.3, "score_text": "66", "hidden": false, "main_concern": true}],
 "readings": [{"col": "beh_sleep_h", "label": "Uyku", "unit": "saat", "value": 6.9, "today": 7.1, "value_text": "6,9",
               "healthy_text": "7–9", "level": 1, "flag_text": "Aralık dışında", "averaged": true, "private": false, "hidden": false}],
 "todo_title": "Yapılacaklar",
 "todo": [{"code": "SYMPTOM_CARE", "title": "Belirtileri tedavi edin ve izleyin", "why": "Belirti puanı 4,3, sağlıklı aralık 0–2",
           "source": "readings", "triggers": ["imm_symptom_score"], "steps": ["…"], "contact_ground_if": "…", "done": false}],
 "todo_masked_count": 0, "calm_text": null, "ground_title": null, "ground_text": null,
 "readings_note": "Sağlık ölçümleri son 3 günün ortalamasını gösterir. …",
 "threshold_note": "Aralıklar simüle veri setinden alınmıştır, tıbbi doğrulama yapılmamıştır.", "share": null}
```

Kurallar (`app/personal/evaluate.py`, prototiple golden testli):
- Sağlık ölçümleri son 3 günün ortalaması (başta pencere daralır); `exposure` (radyasyon, kabin CO2) o günün değeri.
- `level`: 0 sağlıklı aralıkta · 1 uyarı aralığında · 2 uyarı aralığının dışında; üst sınırı `null` olanın üst sınırı yok.
- `status` = max(`health_status`, ground ? 1 : 0). Etiketler Normal / Dikkat / Rahatsız (Normal / Needs attention / Unwell).
- `todo`: o günün self-care kodları (veri setindeki sırayla); tetikleyiciler: `action == kod` ve `level >= trig`.
  Tetikleyicisi olmayan kod: `source: "dataset"`, `why`: "Veri setinin önerisi".
- `subtitle`: durum varsa ana endişe (yoksa "Bir ölçüm aralığın çok dışında"), yoksa "Bakılacak N küçük şey" / "Bugün yapılacak bir şey yok".

### `POST /api/actions/done` `{"code": "PROTECT_SLEEP", "done": true}` → `{code, done, day: DayView}`

Bugünün to-do öğesini işaretler/kaldırır; Dünya'ya `action.done` gider (öğe Dünya'da maskeliyse kodsuz).

## Check-in (gemi) — prototipin `assistantTurn` sözleşmesi

Sadece **bugün** yapılır; geçmiş günler `GET /api/checkin/days/{gün}` ile salt okunur. Mod: `CHECKIN_MODE`
(`scripted` prototip kuralları · `llm` JSON şemalı LLM · `auto` LLM'e ulaşılamazsa scripted).

`GET /api/checkin` → `CheckinState` (ilk soru, hızlı cevaplar `options`, `messages`, `notes`, `done`, `share`,
`can_reset`, `cmo_notified` / `cmo_notice`, bitince `share_options` / `share_note` / `share_cmo_note`).

`POST /api/checkin/turn` `{"answer": "Kötü"}` → prototip çıktısı aynen + güncel durum:

```json
{"reply": "Not edildi. Ölçümleriniz de bunu gösteriyor: uyku ortalaması 6,9 saat. \"Uykunuzu koruyun\" yapılacaklar listenizde.",
 "note": {"topic": "Uyku", "topic_key": "sleep", "text": "Kötü", "flag": true, "urgent": false},
 "next": {"text": "Bugün ruh haliniz nasıl?", "options": ["İyi", "Şöyle böyle", "Düşük"]},
 "done": false, "checkin": {"…": "CheckinState"}}
```

- Konular: uyku, ruh hali, stres, belirtiler, diğer. Bitince özet mesajı: "Check-in tamamlandı. Bugün işaretlenenler: …".
- **Acil belirti** (belirti sorusunda; göğüs ağrısı, bayılma, baş dönmesi, çarpıntı, nefes, kan): gemide CMO
  kaydı, `note.urgent: true`, ekranda `cmo_notice` "Gemideki sağlık sorumlusu bilgilendirildi". Dünya'ya **gönderilmez**.
- Hata kodları: `empty_answer` (400), `checkin_done` (409).

`POST /api/checkin/share` `{"level": "private" | "scores" | "full"}` — sadece **artar**, geri alınamaz
(`409 share_downgrade`); tamamlanmamışsa `409 checkin_not_done`.
`POST /api/checkin/reset` — "Baştan başla", sadece paylaşım `private` iken (`409 reset_locked`). CMO kayıtları silinmez.

## "Asistana sor" (gemi) — `POST /api/chat` → `text/event-stream`

Gövde `{"messages": [{"role": "user", "content": "…"}], "lang": "tr"}`; astronot token'dan gelir (`astronaut_id`
verilirse aynı olmalı, yoksa `403`). Olaylar eski sohbetle aynı (`meta`, `token`, `tool_call`, `tool_result`,
`emergency`, `done`, `error`). Tool'lar sadece giriş yapan astronotun verisine erişir: `get_today_summary`,
`get_recent_readings`, `get_todo`, `get_selfcare_solutions`, `search_docs`. Acil belirti taraması LLM'den önce,
basit olumsuzlamayı ayırt eder ("göğüs ağrım yok" tetiklemez); eşleşirse gemide CMO kaydı
(`emergency.cmo_notified: true`), Dünya'ya gitmez.

## Downlink (gemi → Dünya)

`Authorization: Bearer <EARTH_LINK_TOKEN>` (gemide ayarlı değilse `503 downlink_disabled`).

- `GET /api/downlink/snapshot` → `DownlinkSnapshot` `{epoch, seq, astronauts[], days[]: EarthDay}` (gzip).
  Sadece **yayınlanmış** durumu içerir; stream `since=seq` ile devam eder.
- `GET /api/downlink/stream?since=<seq>[&follow=false]` → SSE. Her olay `id: <seq>`, `event: <tür>`,
  `data: DownlinkEvent`; ayrıca `event: link.heartbeat` (`DownlinkHeartbeat`: `last_seq`, `pending`).

Olay türleri: `checkin.completed`, `checkin.shared`, `action.done`, `day.snapshot`, `link.heartbeat`.
Her olay ilgili günün **gizlilik filtresinden geçmiş** güncel halini (`payload.day: EarthDay`) taşır:

```json
{"seq": 2, "type": "checkin.shared", "epoch": "5d55f41562ce6482", "astronaut_id": "A003", "day_index": 29,
 "ship_time": "2026-11-14T13:49:24.957Z", "publish_time": "2026-11-14T13:49:24.957Z", "earth_received_time": null,
 "simulated_light_delay_minutes": 20.0,
 "payload": {"share": "scores", "day": {"day_index": 29, "status": 2, "ground": false, "cumulative_score": 60.3,
   "behavioral_hidden": false, "area_scores": {"behavioral": 66.3, "…": 0},
   "readings": {"exp_radiation_mSv_day": {"today": 0.798, "used": 0.798, "level": 1}},
   "todo": [{"code": "SYMPTOM_CARE", "triggers": ["imm_symptom_score"], "done": false}], "todo_masked_count": 0,
   "checkin": {"share": "scores", "notes": [{"topic_key": "sleep", "flag": true, "text": null}]}}}}
```

**Gizlilik (gemide, outbox'a yazmadan önce):** ruh hali / stres ve "uyku, ruh hali ve stres" alan skoru sadece o
günün check-in'i en az `scores` paylaşıldıysa; tetikleyicisi sadece gizli ölçümler olan to-do öğeleri maskeli
(sadece `todo_masked_count`); ground sadece görünür ölçümlerden; check-in: yok / `private` / `scores` (konu + flag)
/ `full` (+ metin). Mesajlar, `urgent` ve CMO bilgisi hiçbir zaman gitmez.

`DOWNLINK_DELAY_SECONDS`: olaylar `ship_time + gecikme` anında yayınlanır (sıra atlanmaz).
`DOWNLINK_SIMULATED_LIGHT_DELAY_MINUTES`: gerçek ışık gecikmesi etiketi (bekletmez).

## Dünya üssü

- `GET /api/monitor/crew` → `{link: LinkStatus, astronauts: [{astronaut, today, status, status_label, subtitle, score, ground, share, checkin_text}]}`
- `GET /api/monitor/astronauts/{id}` → `PersonalOverview` (Dünya şeridi)
- `GET /api/monitor/astronauts/{id}/days/{gün}` → `{view: DayView (viewer=earth, gizliler hidden), checkin: EarthCheckinView, updated_seq, received_at}`
- `GET /api/link/status` → `LinkStatus` (`connected`, `last_contact`, `last_seq`, `ship_last_seq`, `pending_on_ship`, `behind`, `events_received`)
- `GET /api/stream/monitor?access_token=…` → SSE: `event: event` (`MonitorStreamEvent`: yeni olay) ve `event: link` (bağlantı durumu)

---

# B. Eski ekranlar (`DATA_SOURCE=synthetic`, `/legacy`)

Aşağıdaki uçlar sadece **gemi + `DATA_SOURCE=synthetic`** iken açıktır (eski analiz motoru, sentetik veri,
`data/processed/health.db`). `astronaut_health` modunda kapalıdır (`404`).

## Zaman kaydırıcısı (`as_of`)

`crew`, `summary`, `metrics`, `checkins`, `briefing`, `alerts`, `ground-report` endpoint'leri opsiyonel
`as_of=YYYY-MM-DD` alır: hesap **o güne kadarki veriyle** yapılır (gelecek veri sızmaz).
Boşsa verideki son gün kullanılır. Aralık dışı değerler görev başı/sonuna sıkıştırılır.
Cevaplardaki `mission.as_of` her zaman **etkin** günü döner.

## Ortak kavramlar

| Kavram | Değerler |
|---|---|
| `system` | `cardiovascular` `musculoskeletal` `immune` `behavioral` `sleep` `radiation` |
| `status` (renk) | `green` `yellow` `red` `unknown` (veri yok) — UI renk + ikon + metin göstermeli |
| `severity` | `info` `warning` `critical` — info sadece brifingde gösterilir |
| `source` | `rule` (kural) · `anomaly` / `changepoint` (model tespiti) · `forecast` (tahmin) |
| `score` (olay) | 0–1 güven/şiddet. UI: `<0.5` düşük, `0.5–0.75` orta, `>0.75` yüksek |
| `threshold_verified` | `false` → eşik placeholder, NASA-STD-3001 ile doğrulanmadı ("doğrulanmamış" notu) |

### `HealthEvent` (tüm olaylar — kural ve ML aynı şema)

```json
{
  "event_id": "evt_459a1592a142",
  "astronaut_id": "AST-02",
  "detected_at": "2026-10-19T00:00:00Z",
  "source": "rule",
  "system": "sleep",
  "severity": "critical",
  "score": 0.99,
  "title": "Uyku süresi kişisel normalin altında",
  "window": { "start": "2026-10-19", "end": "2026-11-14" },
  "contributors": [
    { "metric": "sleep_duration", "value": 4.97, "baseline": 7.18, "z": -5.12, "weight": 1.0, "threshold_verified": false }
  ],
  "changepoint_date": null,
  "forecast": null,
  "share_with_ground": false,
  "status": "active",
  "detector": "rule.baseline_deviation",
  "description": "7 günlük ortalama 5,0 sa; kişisel normal 7,2 sa ± 0,4 sa (z = -5,1).",
  "feedback": null
}
```

Çok metrikli olay örneği (`rule.system_pattern` — ML dedektörleri de böyle katkı listesi döner):

```json
"title": "Uyku: 2 göstergede eşzamanlı olumsuz değişim",
"contributors": [
  { "metric": "sleep_duration", "value": 4.97, "baseline": 7.18, "z": -5.12, "weight": 0.62, "threshold_verified": false },
  { "metric": "sleep_quality",  "value": 2.57, "baseline": 4.14, "z": -3.14, "weight": 0.38, "threshold_verified": false }
]
```

Kullanıcının verdiği şemaya **eklenen** alanlar: `status` (`active`/`resolved`), `detector`
(olayı üreten modül), `description` (kuralın ürettiği sayısal açıklama, Türkçe), `feedback` (son geri bildirim).

- `event_id` deterministiktir (astronot + kaynak + dedektör + metrik/sistem + başlangıç günü). Zaman kaydırıcısında aynı olay aynı ID'yi korur.
- `contributors[].weight` toplamı 1'dir. Tek metrikli kural olaylarında tek katkı vardır (`1.0`).
- `status`: olay bittikten sonra 2 gün daha `active` kalır (histerezis, `rules.yaml → episodes.merge_gap_days`).
- `detector` değerleri: `rule.threshold` (eşik), `rule.baseline_deviation` (kişisel normalden sapma, z7),
  `rule.trend` (hızlı kötüleşme), `rule.system_pattern` (aynı sistemde ≥2 metrik),
  `ml.example_changepoint` / `ml.example_forecast` (örnek, varsayılan kapalı), ML ekibinin `ml.*` dedektörleri.
- `score` kural olaylarında: eşik → doğrulanmamışsa 0,7 / doğrulanmışsa 0,95; sapma → z büyüklüğüyle artar.
- `changepoint_date` → grafikte dikey kesikli çizgi. `forecast` → kesikli tahmin çizgisi:

```json
"forecast": {
  "metric": "resting_hr", "method": "linear", "horizon_days": 7,
  "points": [ { "date": "2026-11-15", "value": 72.4, "lower": 70.6, "upper": 74.2 } ]
}
```

---

## Sistem

### `GET /api/health`

LLM erişilemese bile `status: "degraded"` döner; kural tabanlı uyarılar çalışmaya devam eder.

```json
{
  "status": "ok",
  "version": "0.1.0",
  "time": "2026-11-14T09:00:00Z",
  "db": { "ok": true, "astronauts": 4, "measurements": 44860, "latest_date": "2026-11-14", "error": null },
  "llm": {
    "provider": "openai", "base_url": "http://192.168.1.42:11434/v1", "model": "qwen3:14b",
    "reachable": true, "model_available": true, "available_models": ["qwen3:14b", "qwen3:8b"],
    "tool_mode": "auto", "thinking": false, "latency_ms": 12.3, "error": null,
    "checked_at": "2026-11-14T09:00:00Z"
  },
  "rag": { "backend": "keyword", "ok": true, "documents": 0, "chunks": 0, "error": null }
}
```

`status`: `ok` | `degraded` (LLM/RAG yok veya model yüklü değil) | `error` (DB yok).

### `GET /api/metrics/catalog`

Metrik adları, birimleri, sistemleri, normal aralıkları ve eşikler. Grafik eksen etiketleri ve metrik seçici için.

```json
{
  "systems": [ { "id": "sleep", "display_name": "Uyku", "display_name_en": "Sleep", "metrics": ["sleep_duration", "sleep_quality"] } ],
  "metrics": [
    {
      "name": "sleep_duration", "display_name": "Uyku süresi", "display_name_en": "Sleep duration",
      "unit": "h", "system": "sleep", "frequency": "daily", "bad_direction": "down", "aggregation": "sum",
      "normal_range": { "low": 7.0, "high": 9.0 },
      "thresholds": { "verified": false, "source": "placeholder", "warning": { "low": 6.0, "high": null }, "critical": { "low": 4.0, "high": null } },
      "threshold_verified": false, "rules": ["threshold", "baseline_deviation", "trend"], "decimals": 1
    }
  ]
}
```

---

## Mürettebat ve astronot

### `GET /api/crew?as_of=`

```json
{
  "mission": { "start_date": "2026-05-19", "latest_date": "2026-11-14", "as_of": "2026-11-14", "mission_day": 180, "total_days": 180 },
  "astronauts": [
    {
      "id": "AST-02", "name": "Astronot 2", "role": "Uçuş mühendisi",
      "status": "red", "score": 10.0,
      "active_events": { "critical": 8, "warning": 3, "info": 0 },
      "attention_systems": ["cardiovascular", "sleep", "behavioral"],
      "last_measurement_at": "2026-11-14T23:55:00Z"
    }
  ]
}
```

`mission` zaman kaydırıcısının aralığıdır (`start_date` … `latest_date`).
`score` = en zayıf sistemin skoru (0–100).

### `GET /api/astronauts/{id}/summary?as_of=`

```json
{
  "astronaut": { "id": "AST-02", "name": "Astronot 2", "role": "Uçuş mühendisi" },
  "mission": { "...": "crew ile aynı" },
  "overall": { "status": "red", "score": 35.0, "worst_system": "sleep" },
  "systems": [
    {
      "system": "sleep", "display_name": "Uyku", "score": 35.0, "status": "red",
      "metrics": ["sleep_duration", "sleep_quality"],
      "penalties": [ { "event_id": "evt_…", "title": "Uyku süresi kişisel normalin altında", "metric": "sleep_duration", "severity": "critical", "penalty": 45 } ]
    }
  ],
  "latest": [
    {
      "metric": "sleep_duration", "display_name": "Uyku süresi", "unit": "h", "system": "sleep",
      "date": "2026-11-14", "value": 5.0, "baseline_mean": 7.25, "baseline_std": 0.33,
      "z": -6.8, "z7": -6.5, "slope7": -0.02, "threshold_verified": false, "state": "alert"
    }
  ],
  "active_events": [ "HealthEvent…" ],
  "last_measurement_at": "2026-11-14T23:00:00Z"
}
```

- `systems[].penalties` skoru düşüren olaylardır (açıklanabilirlik).
- `latest[].state`: `normal` | `watch` (aktif info olay) | `alert` (aktif warning/critical) | `no_data`.
- Sistem skoru = `100 − Σ(metrik başına en yüksek ceza)`; ceza: critical 45, warning 20, info 3
  (`backend/config/rules.yaml`). Aktif critical olay → `red`, aktif warning → en iyi `yellow`.

### `GET /api/astronauts/{id}/metrics?metric=&days=30&resolution=daily&as_of=`

Grafik için tek çağrı: seri + kişisel normal bandı + eşikler + o metriği içeren olaylar.

| Parametre | Açıklama |
|---|---|
| `metric` (zorunlu) | katalogdaki ad, örn. `sleep_duration` |
| `days` | `as_of`'tan geriye gün sayısı (1–400, varsayılan 30) |
| `resolution` | `daily` (varsayılan) veya `raw` (saatlik ham noktalar da gelir) |

```json
{
  "astronaut_id": "AST-02",
  "metric": { "name": "sleep_duration", "unit": "h", "thresholds": { "verified": false, "warning": { "low": 6.0 } }, "threshold_verified": false, "...": "MetricInfo" },
  "as_of": "2026-11-14",
  "resolution": "daily",
  "baseline": { "mean": 7.25, "std": 0.33, "n_days": 14, "start": "2026-05-19", "end": "2026-06-01" },
  "daily": [ { "date": "2026-11-14", "value": 5.0, "min": 5.0, "max": 5.0, "n": 1, "roll7": 5.1, "z7": -6.5 } ],
  "raw": [],
  "events": [ "HealthEvent… (window gölgesi, changepoint_date, forecast)" ]
}
```

Çizim kuralları: bant = `baseline.mean ± baseline.std`; eşik çizgisi `metric.thresholds.warning/critical`
(`threshold_verified=false` ise "doğrulanmamış" notu); her `events[].window` gölgeli bölge;
`changepoint_date` dikey kesikli çizgi; `forecast.points` kesikli çizgi. Veri yoksa katman çizilmez.

---

## Olaylar / uyarılar

### `GET /api/alerts`

| Parametre | Açıklama |
|---|---|
| `astronaut_id` | filtre |
| `severity` | tam eşleşme, tekrarlanabilir: `severity=warning&severity=critical` |
| `min_severity` | bu seviye ve üstü (`warning` → warning + critical) |
| `system`, `source`, `metric` | filtre |
| `status` | `active` (varsayılan) · `resolved` · `all` |
| `as_of` | zaman kaydırıcısı |

```json
{ "as_of": "2026-11-14", "count": 1, "events": [ "HealthEvent…" ] }
```

Sıralama: önce severity (critical → info), sonra başlangıç tarihi.

### `GET /api/alerts/{event_id}?as_of=` → `HealthEvent`

### `POST /api/alerts/{event_id}/explain`

LLM açıklaması. Bağlam (olay, seri, skorlar, belgeler) deterministik toplanır, LLM tek bir
`json_schema` çağrısıyla `AlertExplanation` üretir; şemaya uymazsa bir kez yeniden denenir; yine
olmazsa veya LLM kapalıysa **kural tabanlı şablon** döner (`generated_by: "template_fallback"`). Endpoint
LLM yüzünden hata vermez. Sonuç cache'lenir (`refresh: true` ile yeniden üret).

İstek (gövde opsiyonel):

```json
{ "lang": "tr", "as_of": null, "refresh": false }
```

Cevap:

```json
{
  "event_id": "evt_3f9a1c2b7d10",
  "event": "HealthEvent…",
  "explanation": {
    "summary": "Son 7 günde uyku süreniz kişisel normalinizin belirgin altında (ort. 5,1 sa, baseline 7,2 sa).",
    "likely_factors": ["Aynı dönemde stres öz bildiriminde artış", "Çalışma/uyku programında değişiklik olasılığı"],
    "recommended_actions": ["Uyku programını mürettebat sağlık sorumlusu (CMO) ile gözden geçirin", "Önümüzdeki 3 gün uyku süresini izleyin"],
    "escalate_to_ground": true,
    "sources": ["metric:sleep_duration", "event:evt_3f9a1c2b7d10"],
    "uncertainty": "Eşik değerleri placeholder; NASA-STD-3001 ile doğrulanmadı."
  },
  "generated_by": "llm",
  "model": "qwen3:14b",
  "cached": false,
  "ungrounded_numbers": [],
  "doc_refs": [ { "file": "nasa-std-3001-vol1.pdf", "section": "Sleep", "page": 42, "snippet": "…", "score": 3.1 } ],
  "created_at": "2026-11-14T09:00:00Z"
}
```

- `generated_by`: `llm` | `mock` | `template_fallback` — UI şablon cevabını belirtmeli.
- `ungrounded_numbers`: çıktıda olup bağlam verisinde bulunmayan sayılar ("sayıları LLM üretmez" denetimi). Tolerans: max(metindeki hassasiyetin yarısı, değerin %2'si) — "5,1 sa" ↔ 5 eşleşir. Yok sayılanlar: tarih/saat/kimlik/standart kodu, paydalar (`35/100`), birimsiz 0–10 tam sayılar (`3 gün`). Birimli her sayı (`5 saat`, `9 bpm`, `%5`, `2 mSv`) değeri ne olursa olsun aranır.
- `escalate_to_ground`: critical olaylarda kural gereği her zaman `true`.

### `POST /api/alerts/{event_id}/feedback` — "Yanlış alarm" butonu

```json
{ "verdict": "false_alarm", "comment": "Sensör kayması" }
```

```json
{ "feedback_id": 7, "event_id": "evt_3f9a1c2b7d10", "verdict": "false_alarm", "comment": "Sensör kayması", "created_at": "2026-11-14T09:01:00Z" }
```

`verdict`: `false_alarm` | `useful`. Olayın `feedback` alanı son geri bildirimi gösterir.

### `PUT /api/alerts/{event_id}/share` — "Yer ekibiyle paylaş" (varsayılan kapalı)

```json
{ "share_with_ground": true }
```

```json
{ "event_id": "evt_3f9a1c2b7d10", "share_with_ground": true, "updated_at": "2026-11-14T09:02:00Z" }
```

---

## Brifing

### `GET /api/astronauts/{id}/briefing?as_of=&lang=tr&refresh=false`

Explain ile aynı boru hattı (deterministik bağlam → `json_schema` → retry → şablon).

```json
{
  "astronaut_id": "AST-02", "as_of": "2026-11-14", "lang": "tr",
  "briefing": {
    "summary": "Görev günü 180: genel durum kırmızı; uyku ve davranışsal göstergelerde kötüleşme var.",
    "highlights": ["Radyasyon dozu ve vücut ısısı kişisel normal aralıkta."],
    "concerns": ["Uyku süresi kişisel normalin altında (kritik)"],
    "recommended_actions": ["Uyku programını CMO ile gözden geçirin."],
    "info_notes": ["Egzersiz süresi: sürekli düşüş eğilimi"],
    "escalate_to_ground": true,
    "sources": ["event:evt_…"],
    "uncertainty": null
  },
  "generated_by": "llm", "model": "qwen3:14b", "cached": true, "ungrounded_numbers": [],
  "info_events": [ "HealthEvent… (severity=info)" ],
  "created_at": "2026-11-14T09:00:00Z"
}
```

---

## Check-in

### `POST /api/checkin` → `201`

```json
{
  "astronaut_id": "AST-02", "mood": 2, "stress": 4, "sleep_quality": 2,
  "note": "Uyuyamıyorum, kafam çok dolu.", "share_with_ground": false, "lang": "tr"
}
```

`mood`, `stress`, `sleep_quality`: 1–5 (`stress` 5 = çok yüksek). `timestamp` opsiyonel (boşsa sunucu zamanı).
Not, **kural tabanlı** acil belirti taramasından geçer:

```json
{
  "checkin": { "id": 812, "astronaut_id": "AST-02", "timestamp": "2026-11-14T21:00:00Z", "mood": 2, "stress": 4, "sleep_quality": 2, "note": "…", "share_with_ground": false, "emergency": false },
  "emergency": null
}
```

Acil belirti varsa `emergency` dolu gelir (`EmergencyNotice`, sohbetteki `emergency` olayıyla aynı):

```json
{
  "triggered": true,
  "matched_symptoms": ["chest_pain"], "matched_labels": ["Göğüs ağrısı"], "matched_terms": ["göğüs ağrısı"],
  "protocol": {
    "id": "EMERGENCY-PLACEHOLDER-01", "title": "Olası acil durum — tıbbi acil protokolü başlatın",
    "steps": ["Mürettebat sağlık sorumlusunu (CMO) hemen çağırın; kişiyi yalnız bırakmayın.", "…"],
    "contacts": ["Mürettebat sağlık sorumlusu (CMO)", "Yer ekibi: uçuş cerrahı"],
    "verified": false
  },
  "message": "Olası acil belirti tespit edildi (Göğüs ağrısı). Acil protokolü başlatın …"
}
```

### `GET /api/astronauts/{id}/checkins?days=14&as_of=`

```json
{ "astronaut_id": "AST-02", "checkins": [ "CheckinRecord… (yeniden eskiye)" ] }
```

---

## Sohbet (SSE)

### `POST /api/chat` → `text/event-stream`

```json
{
  "astronaut_id": "AST-02",
  "messages": [ { "role": "user", "content": "Son günlerde uykum nasıl?" } ],
  "as_of": null,
  "lang": null
}
```

Son mesaj `user` olmalı (yoksa 422). `lang` boşsa mesaj dilinden tahmin edilir.

> Tarayıcının `EventSource`'u POST desteklemez → `@microsoft/fetch-event-source` kullanın.

Akış (`event:` adı + `data:` JSON):

```
event: meta
data: {"request_id":"a1b2c3d4e5f6","provider":"openai","model":"qwen3:14b","tool_mode":"native","astronaut_id":"AST-02","as_of":"2026-11-14"}

event: tool_call
data: {"id":"call_1","name":"get_metric","arguments":{"astronaut_id":"AST-02","metric":"sleep_duration","days":14}}

event: tool_result
data: {"id":"call_1","name":"get_metric","ok":true,"duration_ms":18.2,"preview":"{\"metric\":\"sleep_duration\",…}","error":null}

event: token
data: {"text":"Son 7 günde "}

event: token
data: {"text":"uyku süreniz ortalama 5,1 saat…"}

event: done
data: {"message":"Son 7 günde uyku süreniz …","finish_reason":"stop","steps":2,"tool_calls":1,"ungrounded_numbers":[],"doc_refs":[],"degraded":false}
```

| Olay | Payload şeması | UI davranışı |
|---|---|---|
| `meta` | `SSEMeta` | ilk olay; model/sağlayıcı bilgisi |
| `token` | `SSEToken {text}` | cevaba ekle |
| `thinking` | `SSEThinking {text}` | sadece `LLM_THINKING=true` iken; gizli/katlanır göster |
| `tool_call` | `SSEToolCall {id,name,arguments}` | "veri alınıyor…" göstergesi |
| `tool_result` | `SSEToolResult {id,name,ok,duration_ms,preview,error}` | göstergeyi kapat |
| `emergency` | `EmergencyNotice` | **belirgin uyarı bandı** (LLM'den önce, kural tabanlı) |
| `done` | `SSEDone` | son olay; `degraded=true` → LLM yok, yedek cevap |
| `error` | `SSEError {code,message}` | hata mesajı (`llm_unavailable`, `timeout`, …) |

LLM kapalıysa: `error {code:"llm_unavailable"}` → kural tabanlı kısa yedek cevap `token`'ları →
`done {degraded:true, finish_reason:"llm_unavailable"}`. Acil belirti tespiti her durumda çalışır.

---

## Veri yükleme

### `POST /api/ingest` (multipart/form-data)

| Alan | Açıklama |
|---|---|
| `file` | CSV veya JSON |
| `?adapter=` | zorla: `long_csv` · `wide_csv` · `json_records` (boşsa otomatik algılanır) |
| `?astronaut_id=` | dosyada astronot kolonu yoksa kullanılır |

Desteklenen formatlar:

```csv
# long_csv (ortak format)
astronaut_id,timestamp,metric,value,unit,source
AST-01,2026-11-14T08:00:00Z,resting_hr,61,bpm,wearable

# wide_csv (her metrik bir kolon; kolon adları katalog adı veya alias)
astronaut_id,timestamp,resting_hr,hrv,sleep_hours
AST-01,2026-11-14T08:00:00Z,61,54,7.2
```

```json
[ { "astronaut_id": "AST-01", "timestamp": "2026-11-14T08:00:00Z", "metric": "resting_hr", "value": 61 } ]
```

Cevap:

```json
{
  "batch_id": 3, "filename": "nasa_day1.csv", "adapter": "long_csv",
  "rows_total": 1200, "rows_accepted": 1180, "rows_duplicate": 12, "rows_rejected": 8,
  "unknown_metrics": ["cortisol"], "astronauts": ["AST-01", "AST-02"],
  "date_range": { "start": "2026-11-01", "end": "2026-11-14" },
  "warnings": ["Bilinmeyen metrik atlandı: cortisol (8 satır)"],
  "errors_sample": [ { "row": 17, "reason": "unknown_metric", "value": "cortisol" } ]
}
```

Aynı (astronot, metrik, zaman, kaynak) satırı tekrar yüklenirse `rows_duplicate` sayılır (idempotent).

---

## Yer ekibi raporu

### `GET /api/ground-report?as_of=&days=7`

Sadece `share_with_ground: true` olan check-in'ler ve olaylar.

```json
{
  "generated_at": "2026-11-14T09:00:00Z", "as_of": "2026-11-14",
  "period": { "start": "2026-11-08", "end": "2026-11-14" },
  "crew": [
    { "astronaut": { "id": "AST-02", "name": "Astronot 2", "role": "Uçuş mühendisi" },
      "status": "red", "score": 35.0, "shared_checkins": [], "shared_events": [ "HealthEvent…" ] }
  ],
  "note": "Sadece share_with_ground=true olan check-in'ler ve olaylar dahildir."
}
```
