# Gelecek hafta tahmin modeli (AI Gambit)

Astronotun **son 7 gününe** bakıp her sağlık göstergesi için **önümüzdeki 7 günün ortalamasını** tahmin eden
bir ML modeli. Çıktısı LLM'e verilen bir JSON'dur; LLM bunu astronota sade İngilizceyle anlatır
("böyle giderse önümüzdeki hafta nabzın uyarı seviyesine çıkabilir").

İki sürüm var, JSON biçimi ikisinde de aynı:

| Sürüm | Eğitim verisi | Durum |
|---|---|---|
| `forecast_v2` | Takımın hastalıklı veri seti `hastalikli_v1` (320 seed, her biri olaylı + kontrol ikizi) | **Varsayılan** |
| `forecast_v1` | Egemen'in 4 payload dosyası + bizim veri artırmamız | Yedek |

Seçim: `AI_GAMBIT_FORECAST_MODEL=forecast_v1` ortam değişkeni v1'i seçer; boşsa v2 kullanılır.

## Sürüm 2: takımın hastalıklı veri setiyle

v1'de sorun şuydu: veride kötüleşme örneği çok azdı (13 tane), model neredeyse hep "iyi" diyordu, biz de rastgele
olay ekleyerek veri artırdık. Veri ekibi bunun için `ml_hastalikli_v1` veri setini hazırladı: her seed'de astronot
başına 3-6 olay (ateşli enfeksiyon, stres-uyku sorunu, egzersiz aksaması, sadece not olan olaylar...) ve aynı seed'in
olaysız kontrol ikizi. v2 bu veriyle eğitildi ([train_v2.py](train_v2.py)). Veri artırma yok.

- **Bölme:** veri setinin sabit seed ayrımı (`splits.json`): ISS 210/45/45, Mars 14/3/3 seed (train/val/test).
  Bir seed'in olaylı ve kontrol koşusu hep aynı kümede. Hiperparametreler sadece val ile seçildi.
- **Eğitim:** olaylı ve kontrol koşuları birlikte (veri setinde olaylar bilerek ~1,5-2 kat sık; kontrol koşuları
  bunu kısmen dengeler). Satırlar gün atlayarak seyreltildi (bellek için), etikete göre seçilmedi. 681.360 satır,
  bunların 3.841'i "şu an yeşil, gelecek hafta sarı/kırmızı" örneği (v1'de 13 gerçek + 1.049 yapay).
- `labels/` ve `ground_truth/` sadece ölçümde kullanıldı, model girdisi değil.
- Eğitim ~9 dk ([features_fast.py](features_fast.py) ile; özelliklerin eski kodla birebir aynı olduğu kontrol edildi:
  `python features_fast.py --check <jsonl>`).

### v2 sonuçları (test seed'leri, bir kez ölçüldü: 45 ISS + 3 Mars seed)

Not: kod denemesi için iki küçük çalıştırma (`--limit 2/3`, 2-3 seed ile eğitilmiş model) ilk 2-3 test seed'ini de
işledi; sonuçlarına bakılmadı ve silindi. Sayılar `reports_v2/metrics_v2.json`'da (`show_metrics.py` sadece v1'i yazdırır).

Hata (z ölçeğinde, küçük daha iyi):

| | v2 | v1 | Kişisel normal (0) | Son hafta ortalaması |
|---|---|---|---|---|
| Olaylı koşular | **0,329** | 0,356 | 0,433 | 0,408 |
| Kontrol ikizleri | **0,293** | 0,300 | 0,317 | 0,367 |

%80 tahmin aralığı gerçek değerin %79'unu kapsıyor (val %80).

**Gösterge düzeyi erken uyarı** (şu an yeşil, 7 gün sonra motor sarı/kırmızı; olaylı koşularda 3.561 durum):

| | Yakalanan | Yanlış alarm | Kesinlik | Duyarlılık |
|---|---|---|---|---|
| v2 `likely` | 624 | 214 | 0,75 | 0,18 |
| v2 `possible` | **1.734** | **2.763** | 0,39 | 0,49 |
| v1 `likely` | 162 | 78 | 0,68 | 0,05 |
| v1 `possible` | 1.375 | 3.795 | 0,27 | 0,39 |

**Olay düzeyi:** alarm beklenen her olayın başlangıcından önceki 7 günde, herhangi bir gösterge için "yeşilken gelecek
hafta sarı/kırmızı" uyarısı var mı? Şans karşılaştırması: aynı seed'in **kontrol ikizinde**, aynı astronot ve aynı
günlerde uyarı var mı? (Olay yokken uyarı = şans.)

| Olay tipi (test) | v2 `possible` | Kontrol ikizinde aynı pencere | v2 `likely` | Kontrol | v1 `possible` | Kontrol | Motor (zaten sarı/kırmızı) |
|---|---|---|---|---|---|---|---|
| Stres-uyku (154) | **67** | 4 | 25 | 0 | 74 | 13 | 11 |
| Ateşli enfeksiyon (50) | 2 | 1 | 0 | 0 | 6 | 5 | 2 |
| Egzersiz aksaması (72) | 7 | 3 | 0 | 0 | 10 | 11 | 6 |

- **Stres-uyku olaylarının %44'ünü başlamadan önce uyarıyor** (kontrol ikizinde aynı pencere %3). Bu olayın
  önünde 4 günlük uyku düşüşü var; model bunu yakalıyor. v1 biraz daha fazlasını uyarıyor (74) ama kontrol ikizinde
  3 kat fazla yanlış uyarıyla (13'e karşı 4).
- **Ateşli enfeksiyon ve egzersiz aksaması önceden tahmin edilemiyor** (şans düzeyi). Bunlar rastgele başlıyor;
  egzersiz aksamasının öncülü yok, enfeksiyonun öncülü 1-2 gün ve hafif (muhtemelen 7 günlük ortalamada
  kayboluyor; bunu ayrıca ölçmedim). Bunları kural motoru başladıktan sonra yakalıyor.
- **Kontrol ikizlerinde (olaysız) yanlış alarm:** v2 `possible` 100 astronot-günde 0,7 alarm günü (v1: 2,24);
  192 astronot-görevden 73'ü en az bir kez uyarı alıyor (v1: 135). v2 `likely`: 100 günde 0,01.

**Egemen'in demosu (v3.1 ISS, AST-02 zinciri, gün 140-173).** Bu görev v2 eğitiminde yok (320 seed'in hiçbiri
bu görevle aynı değil; kontrol edildi).

| | v1 | v2 |
|---|---|---|
| Hata (z) | 0,322 | **0,301** |
| `possible`: yakalanan / yanlış alarm (21 durum) | 10 / 7 | **13 / 6** |
| `likely`: yakalanan / yanlış alarm | 2 / 0 | **9 / 0** |
| Kontrol ikizinde uyarı | 0 | 0 |
| Nabız ne kadar önce (motor 164. gün sarı) | 7 gün | 7 gün |
| Stres ne kadar önce (motor 158. gün sarı) | 2 gün | 3 gün |

v2'nin demodaki 6 yanlış alarmı: nabız gün 154, 155, 156 (sarıya geçiş 164'te; bu uyarılar 1-3 gün erken, kendi
7 günlük ufkunda tutmuyor) ve uyku kalitesi gün 157, 168, 172 (motor uyku kalitesini hiç sarıya çevirmiyor).
**Demo için gün 157 önerilir:** o gün stres, nabız ve uyku süresi `likely` ve nabız tahmini 164. günde doğru çıkıyor.
Gün 156'da nabız uyarısı henüz doğru değil; o gün kullanılırsa "yaklaşık bir hafta önce" denmeli.
Gün 164 ve 178'de nabız/stres zaten sarı/kırmızı; JSON'da `likely` görünür ama `status_now` sarı/kırmızıdır
(LLM kuralı 3 bunu "zaten uyarı seviyesinde" diye anlatır).

**Varsayılan olma kuralı** (sonuçlara bakmadan önce yazıldı): demoda v1 kadar ya da daha fazla yakalama ve kontrol
ikizinde sıfır uyarı. v2 geçti, varsayılan oldu.

### v2 için bilinmesi gerekenler

- **Hâlâ tamamen sentetik veri.** Olayların büyüklükleri çoğunlukla veri ekibinin varsayımı; hekim incelemesi yok
  (veri setinin README'si). Model bu üretecin imzalarını öğrendi; gerçek astronot için bir şey söylemez.
- **Olaylar bilerek ~1,5-2 kat sık.** Gerçek kullanımda uyarı oranları buradan düşük olur.
- **Demo testi tekrar görüldü:** aynı AST-02 aralığı v1'de üç kez ölçülmüştü; v2 için dördüncü kez ölçüldü
  (karar kuralı önceden yazıldı, v2 bu sonuca göre ayarlanmadı).
- **Sayılar takım arkadaşının taban çizgisiyle (`ml_hastalikli_v1_baseline`) doğrudan karşılaştırılamaz:** o model
  "3/7/14 gün içinde olay başlar mı" sınıflandırması yapıyor, bizimki göstergelerin gelecek haftasını tahmin ediyor.
- Örnek JSON'lar (`examples/`) v2 ile yeniden üretildi. AST-02 gün 156'da `watch_list` aynı 3 gösterge
  (stres, nabız, uyku süresi) ama stres artık `likely`.

---

Aşağıdaki bölümler **v1** içindir (yöntem v2'de de aynı; sadece eğitim verisi farklı).

Veri (v1): Egemen'in payload dosyaları (`egemen_payloads_tr_v3_1.zip`, `payloads_tr_*.jsonl`). `payloads_ground_*`
dosyaları kullanılmadı: aynı seriler, sadece öz bildirimler çıkarılmış.

## Nasıl çalışır

1. **Girdi:** son 7 günün değerleri ve kural motorunun z-skorları (12 gösterge: nabız, uyku, HRV, stres,
   egzersiz, tepki süresi, ruh hali, uyku kalitesi, SpO2, vücut ısısı, tansiyon, vücut kütlesi). Diğer
   göstergelerin son durumu da girdi olarak kullanılır (ör. uyku kötüyken nabız tahmini).
2. **Model:** gradient boosting (scikit-learn `HistGradientBoostingRegressor`). Üç kantil eğitilir:
   ortanca tahmin ve %80 aralık (alt ve üst).
3. **Durum:** tahmin, motorun kendi kuralıyla etikete çevrilir (kötü yönde z ≥ 2 sarı, ≥ 3 kırmızı).
   - `likely`: ortanca tahmin eşiği geçiyor.
   - `possible`: aralığın kötü ucu geçiyor.
4. **Çıktı:** `health_forecast` JSON'u ([LLM_REHBERI.md](LLM_REHBERI.md), örnekler `examples/` altında).

## Train / validation / test

Zamana göre, aralarında boşluk bırakılarak bölündü. Bölme astronota göre yapılamadı: aynı 4 kişi her senaryoda var.

| Bölüm | İçerik |
|---|---|
| Train | Mars 860 (gün ≤ 600), üç ortam 84, ISS görevi (gün ≤ 125) ve bunların veri artırılmış kopyaları |
| Validation | Mars 860 (gün 615-860) ve ISS görevi (gün 126-133), ayrıca Mars'ın son bölümünün ayrı tohumla artırılmış kopyaları |
| Test | ISS görevi gün 140-173 (AST-02 uyku zinciri) ve kontrol ikizi aynı günler (olay yok, yanlış alarm sayımı) |

Hiperparametreler sadece validation ile seçildi.

### Veri artırma neden gerekti

Payload verisinde "şu an yeşil, gelecek hafta sarı/kırmızı" örneği 29.633 eğitim satırında sadece **13** taneydi.
AST-02 zinciri dışında "kötü uyku → birkaç gün sonra nabız/stres artışı" ilişkisi de yoktu (korelasyon yaklaşık 0).
İlk model bu yüzden hiçbir yeni sorunu öngöremedi.

[augment.py](augment.py) sakin serilerin kopyalarına rastgele kötüleşme olayları ekliyor: rastgele gösterge,
büyüklük (0,8–4,5 kişisel std), hız, süre, bazen zincirleme etki, %15 iyileşme olayı ve bazı kopyalarda hiç olay yok.
Sonuçta 169 olay ve 1.049 geçiş örneği elde edildi. Her olay `reports/augmentation_log.csv` dosyasında.
Test serisine dokunulmadı.

## Sonuçlar (`reports/metrics.json`)

Hata, z-skor ölçeğinde (kişisel std cinsinden) ortalama mutlak hata. Küçük olan daha iyi.

| | Model | Kişisel normal (0) | Son hafta ortalaması | Doğrusal trend |
|---|---|---|---|---|
| Validation | **0,312** | 0,387 | 0,378 | 1,195 |
| Test (ISS, AST-02 zinciri) | **0,322** | 0,417 | 0,370 | 1,117 |
| Kontrol ikizi | **0,265** | 0,280 | 0,337 | 1,120 |

**Erken uyarı.** Test aralığında, motorun `durum` alanına göre "şu an yeşil, 7 gün sonra sarı/kırmızı" olan
21 durum var (hepsi AST-02'de).

| Yöntem | Yakalanan | Yanlış alarm | Kesinlik | Duyarlılık |
|---|---|---|---|---|
| Model, `possible` seviyesi | **10** | **7** | 0,59 | 0,48 |
| Model, `likely` seviyesi | 2 | 0 | 1,00 | 0,10 |
| Son hafta ortalaması | 2 | 1 | 0,67 | 0,10 |
| Doğrusal trend | 10 | 86 | 0,10 | 0,48 |

- **Kontrol ikizinde (olay yok) yanlış alarm: 0**, iki seviyede de.
- Model, doğrusal trendle aynı sayıda sorunu yakalıyor ama 86 yerine 7 yanlış alarm veriyor.
- 7 yanlış alarmın 6'sı AST-02'nin uyku kalitesinde: model düşüş bekliyor, motor onu hiç sarıya çevirmiyor.
  Kalan 1'i nabızda, gerçek geçişten bir gün önce.

**AST-02 için ne kadar önce uyardı** (`possible` seviyesi). Gün t'deki uyarı gün t+7 hakkında bir iddia
olduğu için, sadece kendi ufkunda doğru çıkan uyarılar sayıldı. Bu yüzden en fazla 7 gün olabilir.

| Gösterge | Motorun ilk sarı günü | Modelin ilk doğru uyarısı | Kaç gün önce |
|---|---|---|---|
| İstirahat nabzı | 164 | 157 | **7** |
| Uyku süresi | 158 | 155 | 3 |
| Stres | 158 | 156 | 2 |

%80 tahmin aralığı testte gerçek değerin %78'ini kapsıyor (hedef %80).

## Bilinmesi gerekenler

- **Tamamen sentetik veri.** Model simülatörün mantığını ve veri artırmadaki varsayımlarımızı öğrendi.
  Zincirleme etkiler (uyku → stres → nabız) bizim varsayımımız; AST-02 testinde işe yaradı ama gerçek
  astronot verisiyle doğrulanmadı.
- **Test üç kez görüldü.**
  1. İlk model (veri artırmasız) testte ölçüldü ve hiçbir yeni sorunu yakalayamadı. Veri artırma kararı bu
     sonuçla birlikte, eğitim verisindeki 13 örnekten dolayı alındı. `possible` seviyesi de bu ilk bakıştan
     sonra eklendi.
  2. Veri artırmalı model ölçüldü.
  3. Etiketler z eşiği yerine motorun `durum` alanından okunacak şekilde düzeltildi. Model değişmedi; sadece
     ölçüm düzeldi.

  Hiperparametreler her zaman sadece validation ile seçildi. Yine de test sonuçlarını bu geçmişle okuyun.
- **Az olay.** Test 21 geçiş durumu içeriyor, hepsi tek bir astronotta (AST-02). Sayılar küçük.
- **z-skor formülü birebir çözülemedi.** Motorun z'si, 7 günlük ortalamanın görevin ilk 20 gününe göre
  sapmasına çok yakın (ISS'te fark ~0,06), ama Mars'ta fark büyük (muhtemelen evreye göre baseline).
  - Gerçek veride motorun kendi z'si ve `durum` alanı kullanılıyor.
  - Birim tahmini, son 7 günün ortalamasına z değişimi kadar eklenerek bulunuyor; yön her zaman z ile aynı.
  - `personal_baseline` alanı yaklaşık bir referans.
- **Yer ekibi görünümü:** öz bildirimler çıktıdan çıkarılıyor ama diğer göstergelerin tahmininde girdi olarak
  kullanılmaya devam ediyor.
- **Model dosyası sürüme bağlı:** `forecast_v1.joblib` ve `forecast_v2.joblib` Python 3.14.3, scikit-learn 1.9.1,
  pandas 3.0.1, numpy 2.4.2 ve joblib 1.5.3 ile üretildi (Egemen'in makinesinde Python 3.13 + scikit-learn 1.9.1
  ile v1 sorunsuz yüklendi). Yüklenmezse: v1 için `python train.py --data <payload klasörü>` (~5 dk),
  v2 için `python train_v2.py --data <hastalikli_v1> --old <payload klasörü>` (~9 dk, 2,2 GB veri seti gerekir).
- **Sunumda:** model uygulamaya bağlı değil, sadece çevrim dışı değerlendirildi. Sunum script'indeki
  "ML modeli tespit etti" demeyin uyarısı, model asistan API'sine bağlanıp sahnede denenene kadar geçerli.
- **İlk ~3 hafta tahmin yok** (baseline oluşmadan): `status: insufficient_data`.
- **LLM adımı denenmedi.** Egemen'in asistan API'sine bu bilgisayardan erişemedim. JSON'u cümleye çeviren
  adım ve sayı doğrulayıcısı gerçek modelle denenmeli. Rehberdeki örnek cevabı ben yazdım.
- Laboratuvar değerleri (ayda bir), kabin CO2 ve radyasyon modele dahil değil.

## Çalıştırma

Gerekenler: Python 3.11+, `numpy`, `pandas`, `scikit-learn`, `joblib`.

```bash
python train_v2.py --data <hastalikli_v1 klasörü> --old <payload klasörü>   # v2 eğitim + ölçüm (~9 dk) -> models/, reports_v2/
python train.py --data <payload klasörü>          # v1 eğitim + ölçüm (~4-5 dk) -> models/, reports/
python show_metrics.py                             # sonuç tablosu
python check_forecast.py --data <payload klasörü>  # 7 kural kontrolü (gelecek sızıntısı, gizlilik, birim yönü...)
python predict.py --payloads <payloads_tr_mission_iss180.jsonl> --astronaut AST-02 --day 156
python predict.py --payloads <...> --astronaut AST-02 --day 156 --audience ground   # yer ekibi görünümü
```

## Dosyalar

| Dosya | Ne yapar |
|---|---|
| `forecast_core.py` | Veri okuma, özellikler, tahmin ve LLM JSON'u |
| `augment.py` | Veri artırma (rastgele kötüleşme olayları) |
| `train.py` | v1: bölme, eğitim, ölçüm |
| `train_v2.py` | v2: hastalikli_v1 ile eğitim, seed bazlı ölçüm, demo karşılaştırması |
| `features_fast.py` | Eğitim için hızlı (vektörel) özellik hesabı; `--check` ile eski kodla eşitlik kontrolü |
| `models/forecast_v2.joblib` | v2 modeli (varsayılan) |
| `reports_v2/` | `metrics_v2.json`, `test_predictions_v2.csv.gz`, `train_log_v2.txt` |
| `predict.py` | Komut satırı ve `forecast_from_records()` (asistan API'si için) |
| `check_forecast.py` | Kural kontrolleri |
| `models/forecast_v1.joblib` | Eğitilmiş model (ortanca, alt ve üst kantil) |
| `reports/` | `metrics.json`, `augmentation_log.csv`, `val_test_predictions.csv`, `train_log.txt` |
| `examples/` | Örnek JSON'lar (AST-02 gün 156 ve 166, yer ekibi görünümü, kontrol ikizi, yetersiz veri) |
| `EGEMEN_CLAUDE_PROMPT.md` | Asistan API'sine bağlamak için Claude Code'a yapıştırılacak hazır prompt |
| `EGEMEN_GUNCELLEME_v2.md` | Entegrasyonu başlamış olan Egemen'in Claude'u için v2 güncelleme notu |

Kod ve metinler yapay zekâ yardımıyla (Claude) yazıldı; proje sayfasında belirtilmeli.
