# Tahmin JSON'unu LLM'e verme rehberi

Model, astronotun son 7 gününe bakıp her gösterge için **gelecek haftanın ortalamasını** tahmin eder ve
`health_forecast` JSON'u üretir. LLM bu JSON'u astronotun anlayacağı sade İngilizceye çevirir.
**Sayıları model üretir; LLM hiçbir sayıyı hesaplamaz veya değiştirmez.**

## Asistan API'sine bağlama

```python
from predict import forecast_from_records
forecast = forecast_from_records(records, astronaut_id="AST-02", day=156)            # astronotun kendisi için
forecast_g = forecast_from_records(records, astronaut_id="AST-02", day=156, audience="ground")  # yer ekibi için
```

- `records`: o astronotun görev başından o güne kadarki payload kayıtları (jsonl satırlarıyla aynı yapı).
- Yer ekibine giden her şeyde `audience="ground"` kullanın: stres, ruh hali ve uyku kalitesi tahminleri çıkarılır.
  Not: çıkarılan bu göstergeler, kalan göstergelerin tahmininde yine girdi olarak kullanılır (ör. stres, nabız
  tahminini etkiler). Yer ekibi stres değerini görmez ama nabız tahmini onu dolaylı olarak içerir.
- `status` alanı `insufficient_data` ise (görevin ilk ~3 haftası, baseline yok) LLM tahmin cümlesi kurmamalı.

## Alanlar

| Alan | Anlamı |
|---|---|
| `last_7_day_mean` | Son 7 günün ortalaması (gerçek veri) |
| `personal_baseline` | Astronotun kendi normali (görevin ilk günleri) |
| `forecast_next_7_day_mean` | Gelecek haftanın ortalaması için ortanca tahmin |
| `forecast_range_80pct` | %80 tahmin aralığı (küçük sayı, büyük sayı) |
| `worse_when` | Bu göstergede kötü olan yön: `higher` (nabız, stres...) ya da `lower` (uyku, HRV, egzersiz...) |
| `worst_case_value` | Aralığın KÖTÜ ucu (uyku için küçük sayı, nabız için büyük sayı) |
| `status_now` | Kural motorunun bugünkü durumu (payload'daki `durum`): GREEN / YELLOW / RED |
| `status_forecast` | Ortanca tahminin eşiğe göre durumu |
| `worst_case_status` | Kötü ucun eşiğe göre durumu |
| `risk_next_week` | `likely`: ortanca tahmin sarı/kırmızı eşiğini geçiyor. `possible`: kötü uç geçiyor. `low`: normal |
| `watch_list` | Dikkat edilmesi gereken göstergeler (risk `likely`/`possible` ya da şu an yeşil değil) |
| `self_report` | Öz bildirim mi (stres, ruh hali, uyku kalitesi) |

## Sistem prompt'una eklenecek kısım (İngilizce, model için)

```text
You may receive a JSON object of type "health_forecast". It is produced by a forecasting model, not by you.

Rules:
1. Use only numbers that appear in the JSON. Do not compute new numbers, averages or percentages.
   You may round to one decimal place.
2. Talk only about indicators in "watch_list". If it is empty, say the outlook for next week is stable.
3. "likely" means the model's central forecast reaches the warning level next week.
   "possible" means only the worst-case end of the forecast ("worst_case_value") reaches it.
   Say "may" or "could", never "will". "worse_when" tells you whether higher or lower is worse for that indicator.
   If "status_now" is YELLOW or RED, the indicator is ALREADY at the warning level today: say that, and do not
   say it "could reach" the warning level. Use "status_forecast" to say whether it may stay there (YELLOW/RED)
   or may ease back to normal (GREEN).
4. Always say it is a projection based on the last 7 days, not a diagnosis.
5. Suggest only low-risk actions (protect sleep, keep the exercise routine, check in with the crew medical
   officer). Recommend talking to the crew medical officer when any item is "likely" or currently YELLOW/RED.
6. Keep it short: 3 to 5 sentences, plain English, second person ("your sleep...").
7. If "status" is "insufficient_data", say there is not enough data yet for a forecast.
```

## Örnek

Girdi: `examples/AST-02_day156.json` (model `forecast_v2`; AST-02, 156. gün; `watch_list`: stress (`likely`),
resting heart rate ve sleep duration (`possible`)).

Beklenen türde cevap. **Bu metni ben elle yazdım; gerçek modelden gelmedi ve Qwen ile denenmedi:**

> Over the past week you slept 5.4 hours on average, below your usual 6.35 hours, and your stress score has
> risen to 1.9 from your usual 1.3. If this pattern continues, your stress may reach the warning level next week,
> and your sleep and resting heart rate could follow; in the worst case your resting heart rate could rise to
> about 48.4 bpm, compared with your usual 45 bpm. This is a projection based on the last 7 days, not a diagnosis.
> Try to protect your sleep window, and please check in with the crew medical officer.

Bu cevaptaki her sayı JSON'da var: uyku `last_7_day_mean` 5.37 ve `personal_baseline` 6.35, stres
`last_7_day_mean` 1.86 ve `personal_baseline` 1.26, nabız `worst_case_value` 48.4 ve `personal_baseline` 45.05.
Stres `likely` olduğu için cevap ekip doktoruna (crew medical officer) yönlendiriyor (kural 5).
Asistan API'sinin sayı doğrulayıcısı bu yuvarlamaları kabul etmeli. Sahnede kullanmadan önce bu adımı gerçek
modelle deneyin. (v1 ile aynı gün: üç gösterge de `possible`, nabız kötü ucu 48.67.)
