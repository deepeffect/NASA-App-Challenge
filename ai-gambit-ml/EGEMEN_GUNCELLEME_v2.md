# Egemen'in Claude'una güncelleme: tahmin modeli v2

Egemen için: yeni zip'i aç, projedeki eski `ai-gambit-ml` klasörünü bununla değiştir (eskisini silip yenisini
kopyala). Sonra çizginin altını Claude Code'a yapıştır. Arayüz sorularına verilen cevaplar ayrı mesajda geldi; bu
güncelleme onları değiştirmiyor.

---

## Tahmin modeli güncellendi (forecast_v2)

`ai-gambit-ml` klasörünü yeni sürümle değiştirdim. Neler değişti:

- **Varsayılan model artık `models/forecast_v2.joblib`.** Takımın yeni hastalıklı veri setiyle (320 seed, olaylı +
  kontrol ikizi) eğitildi. v1 hâlâ klasörde; `AI_GAMBIT_FORECAST_MODEL=forecast_v1` ortam değişkeniyle seçilir.
- **API değişmedi:** `forecast_from_records(records, astronaut_id, day, audience)` aynı, JSON alanları aynı.
  Sadece `model_version` "forecast_v2" oldu ve sayılar değişti.
- **Model sunucu açılışında bir kez yüklendiği için sunucuyu yeniden başlat.**
- `examples/` v2 ile yeniden üretildi. Testlerinde beklenen değerleri buna göre güncelle:
  - AST-02 gün 156: `watch_list` = stress (self-report) **`likely`**, resting heart rate `possible`,
    sleep duration `possible` (v1'de üçü de `possible` idi). Stres `likely` olduğu için kural 5'e göre cevap
    ekip doktoruna (crew medical officer) yönlendirmeli. Deterministik şablonun da bunu yapmalı.
  - AST-02 gün 156 kontrol ikizi: `watch_list` hâlâ boş. AST-01 gün 10: hâlâ `insufficient_data`.
  - Testlerin sabit sayılar içeriyorsa (ör. nabız kötü ucu 48.67) `examples/AST-02_day156.json`'dan yeniden al
    (v2'de 48.4). Mümkünse testler sayıları dosyadan okusun, elle yazmasın.
- `LLM_REHBERI.md` içindeki örnek cevap v2 sayılarıyla güncellendi (yine elle yazılmış, Qwen ile denenmedi).
- **Yeni kural (LLM_REHBERI kural 3'ün sonuna eklendi, FORECAST_TASK'a da ekle):** `status_now` YELLOW veya RED olan
  bir gösterge bugün ZATEN uyarı seviyesinde. Bunlar da `risk_next_week: likely` geliyor (ör. AST-02 gün 164 ve
  178'de nabız ve stres). Cevap "could reach the warning level" DEMEMELİ; "is already at the warning level" demeli ve
  `status_forecast`'a göre "may stay there" (YELLOW/RED) ya da "may ease back toward normal" (GREEN) eklemeli.
  **Deterministik şablonda da aynı dal olmalı:** `status_now != "GREEN"` ise
  "Your {indicator} is already at the warning level: it averaged {last_7_day_mean} {unit} over the last 7 days
  (your usual: {personal_baseline})." Bu durumda ekip doktoru önerisi her zaman eklenmeli (kural 5).
  Senin demo günün 178 olduğu için bu dal sahnede kesin çalışacak; test et.

### Yapman gerekenler

1. Sunucuyu yeniden başlat; açılış log'unda yüklenen modelin `forecast_v2` olduğunu doğrula.
2. `cd ai-gambit-ml && python check_forecast.py --data <payload klasörü>`: 7 kontrolün hepsi GEÇTİ olmalı.
   Yüklemede hata alırsan yeniden eğitmeye çalışma, bana hata mesajını göster.
3. Kendi testlerindeki beklenen değerleri yukarıdaki gibi güncelle ve testleri çalıştır.
4. Uçtan uca dene, gerçek cevapları bana göster: AST-02 gün 156, "What will next week look like for me?".
   Cevapta stres uyarısı ve ekip doktoru önerisi olmalı; sayı doğrulayıcı geçmeli. LLM cevabı mı şablon mu
   kullanıldı, kaç saniye sürdü?
5. AST-02 gün 178 için de dene ("What will next week look like for me?"): nabız ve stres zaten RED; cevap
   "already at the warning level" demeli, "could reach" dememeli.
6. **Demo günü önerisi: 156 yerine 157.** Gün 157'de stres, nabız ve uyku süresi üçü de `likely`; nabız tahmini
   7 gün sonra (164. gün, motorun ilk sarı günü) doğru çıkıyor, yani "bir hafta önceden uyardı" demek doğru.
   Gün 156'daki nabız uyarısı (`possible`) kendi ufkunda (163. gün, motor hâlâ yeşil) tutmuyor; sahnede 156
   kullanılırsa "yaklaşık bir hafta önce" denmeli. Akış: 157 (tahmin uyarıyor) → 164 (nabız sarı, gerçekleşti)
   → 178 (nabız ve stres kırmızı).

### Bilmen gerekenler (sunumda yanlış söylenmesin)

- v2'nin test seed'lerinde stres-uyku olaylarının yaklaşık %44'ünde, olay başlamadan önceki 7 gün içinde bir uyarısı
  var (olaysız kontrol ikizinde aynı günlerde %3). Bu 7 günün 4'ü olayın öncül uyku düşüşü; yani model çoğunlukla
  uyku zaten düşmeye başlamışken uyarıyor, hiç belirti yokken değil. Sahnede "stresi bir hafta önceden tahmin
  ediyor" denmesin; "uyku düşüşünü görüp önümüzdeki haftanın stres ve nabız riskini gösteriyor" denebilir.
- Ateşli enfeksiyon ve egzersiz aksamasını önceden tahmin edemiyor (bunları kural motoru başladıktan sonra yakalıyor).
- Veri tamamen sentetik; hekim incelemesi yok. Cevaplardaki "projection, not a diagnosis" ifadesi kalmalı.
- Ayrıntılar ve tüm sayılar: `ai-gambit-ml/README.md`, "Sürüm 2" bölümü.

Commit/push yapma; değişen dosyaların listesini yaz.
