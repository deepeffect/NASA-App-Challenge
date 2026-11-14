# Egemen'in Claude'una verilecek prompt

Egemen için 2 adım:
1. Zip'i aç, içinden çıkan `ai-gambit-ml` klasörünü **asistan API projesinin ana klasörüne** (içinde `.env`
   dosyasının olduğu klasör) kopyala.
2. Claude Code'u o ana klasörde aç ve aşağıdaki çizginin altındaki her şeyi yapıştır. Yol yazmana gerek yok.

---

## Görev: tahmin ML'ini asistan API'sine bağla

Ben Egemen, NASA Space Apps 2026'da "AI Gambit" takımındayım (challenge: astronotlar için sağlık izleme yazılımı).
Bu klasör benim **asistan API'm**: FastAPI + Ollama (`qwen2.5:7b`, `.env` içinde `LLM_MODEL`), astronotun
telefonundaki sohbet buraya geliyor. Cevaplarda `[D]` (veri) ve `[K]` (kaynak/doküman) rozetleri var.
Takım arkadaşım bir **gelecek hafta tahmin modeli** yazdı; bu projenin ana klasöründeki `ai-gambit-ml/`
klasöründe. Orada değilse bilgisayarda ara ve bulduğun yolu bana söyle. Senden bu modeli
asistan API'sine bağlamanı istiyorum: astronot gelecek haftayla ilgili bir şey sorduğunda model tahmin JSON'u
üretsin, LLM bunu astronotun anlayacağı sade İngilizceye çevirsin.

### Önce oku, sonra plan sun (kod yazmadan önce)

1. `ai-gambit-ml/README.md`, `ai-gambit-ml/LLM_REHBERI.md`, `ai-gambit-ml/predict.py`,
   `ai-gambit-ml/examples/AST-02_day156.json` dosyalarını oku.
2. Bu projede şunları bul ve bana kısaca raporla (dosya:satır ile):
   - Sohbet endpoint'i nerede, LLM'e mesaj nasıl gidiyor (Ollama çağrısı, tool calling var mı, yoksa
     niyet/anahtar kelime ile mi yönlendiriliyor)?
   - `[D]`/`[K]` rozetleri ve sistem prompt'u nerede üretiliyor?
   - Sayı doğrulayıcı (cevaptaki sayıların veride olup olmadığını kontrol eden kod) var mı, nerede?
   - Payload kayıtları (`{astronot_id, gorev_gunu, gostergeler:[{ad, deger, birim, normal, z_skor, durum, trend}]}`)
     nerede üretiliyor / okunuyor? Bir astronotun **görev başından bugüne kadarki** tüm kayıtlarını hangi
     fonksiyonla alabilirim? "Bugün" (demo günü) nasıl belirleniyor?
   - Python sürümü ve kurulu `scikit-learn`, `pandas`, `numpy`, `joblib` sürümleri.
3. Bulduklarına göre 5-10 maddelik bir entegrasyon planı yaz ve **onayımı bekle**.

### Modelin sözleşmesi (değiştirme)

```python
import sys; sys.path.insert(0, "<ai-gambit-ml klasörünün tam yolu>")  # sabit yazma, proje köküne göre hesapla
from predict import forecast_from_records
js = forecast_from_records(records, astronaut_id="AST-02", day=156)                       # astronot görünümü
js_g = forecast_from_records(records, astronaut_id="AST-02", day=156, audience="ground")  # yer ekibi görünümü
```

- `records`: o astronotun **görevin 1. gününden** `day`'e kadarki payload kayıtları (dict listesi, jsonl satırıyla
  aynı yapı, Türkçe gösterge adlarıyla). Sadece son 7 günü verme: kişisel baseline ilk ~20 günden hesaplanıyor.
- Fonksiyon `day`'den sonraki kayıtları zaten atıyor (gelecek sızıntısı yok).
- Dönüş: `type: "health_forecast"` JSON'u. `status` şunlardan biri: `ok`, `insufficient_data` (görevin ilk ~3
  haftası), `no_data`. Alanların anlamı `LLM_REHBERI.md` içindeki tabloda.
- `audience="ground"`: stres, ruh hali, uyku kalitesi (öz bildirimler) çıktıdan çıkarılır. Yer ekibine giden her
  şeyde bunu kullan.
- Varsayılan model `models/forecast_v2.joblib` (takımın hastalıklı veri setiyle eğitildi). Yedek
  `models/forecast_v1.joblib`; `AI_GAMBIT_FORECAST_MODEL=forecast_v1` ortam değişkeni v1'i seçer. JSON biçimi ikisinde
  aynı. İkisi de Python 3.14.3 / scikit-learn 1.9.1 / pandas 3.0.1 / numpy 2.4.2 / joblib 1.5.3 ile üretildi.
  Yüklemeden sonra `python check_forecast.py --data <payload klasörü>` çalıştır: 7 kontrolün hepsi GEÇTİ olmalı.
  Yüklenmezse yeniden eğitme, bana söyle (v2'yi yeniden eğitmek 2,2 GB veri seti istiyor).
  `ai-gambit-ml` içindeki model koduna (forecast_core.py, augment.py, train*.py, features_fast.py) dokunma.

### Yapılacaklar

1. **Tahmin servisi.** Projede ayrı bir modül (ör. `forecast_service.py`):
   - `get_forecast(astronaut_id, day, audience)`: kayıtları projenin kendi veri katmanından alır,
     `forecast_from_records` çağırır, sonucu döner. Aynı (astronot, gün, audience) için önbellekle.
   - Model sunucu açılışında bir kez yüklensin (`predict.load_model()` zaten `lru_cache`'li; açılışta bir kez
     çağırıp ısıt). Model dosyası yoksa veya yükleme hata verirse sunucu çökmesin: tahmin özelliği kapalı
     sayılsın ve log'a yazılsın.
2. **LLM'e verilecek kısa JSON.** Tam JSON 12 gösterge içeriyor, 7B model için uzun. LLM'e sadece şunu ver:
   `status`, `as_of_mission_day`, `horizon_days`, `disclaimer` ve `watch_list`'teki göstergelerin
   `indicator, unit, personal_baseline, last_7_day_mean, forecast_next_7_day_mean, worst_case_value,
   worse_when, status_now, risk_next_week` alanları. `watch_list` boşsa sadece "stable" bilgisini ver.
3. **Yönlendirme.** Astronot gelecekle ilgili bir şey sorduğunda tahmini kullan. Örnek sorular:
   "What will next week look like?", "Am I heading toward any problems?", "How is my sleep trending?",
   "Should I be worried about my heart rate next week?". Projede tool calling varsa `get_health_forecast` adında
   bir tool ekle (parametre yok ya da sadece `indicator`; astronot kimliği ve gün oturumdan gelsin, LLM'den değil).
   Tool calling yoksa mevcut niyet/anahtar kelime yönlendirmesine ekle.
4. **Sistem prompt'u.** `LLM_REHBERI.md` içindeki İngilizce kural bloğunu mevcut sistem prompt'una ekle
   (tahmin JSON'u varken). Özellikle: sayıları sadece JSON'dan al, "will" değil "may/could" de, teşhis değil
   projeksiyon olduğunu söyle, 3-5 cümle, `insufficient_data` ise tahmin cümlesi kurma.
5. **Rozet.** Tahminden gelen cevaplara ayrı bir rozet ekle (ör. `[F]` = forecast) ya da mevcut `[D]`'yi kullan;
   hangisi UI'ı bozmuyorsa. UI tarafını değiştirmen gerekirse önce bana sor.
6. **Sayı doğrulayıcı + yedek cevap (önemli).** 7B model kuralları kaçırabilir. LLM cevabındaki her sayı kısa
   JSON'daki bir sayıya eşit olmalı (1 ondalığa yuvarlama kabul: 5.37 → 5.4, 48.67 → 48.7; tam sayıya yuvarlama
   kabul: 45.05 → 45). Ayrıca cevapta "will" geçmemeli ve teşhis koyuyormuş gibi bir ifade olmamalı. Doğrulama
   geçmezse LLM'e bir kez tekrar sor; yine geçmezse **Python şablonuyla üretilmiş deterministik cevabı** dön
   (ör. her `watch_list` maddesi için: "Your {indicator} averaged {last_7_day_mean} {unit} over the last 7 days
   (your usual: {personal_baseline}). If this continues, it could reach the warning level next week." ve sonunda
   disclaimer cümlesi; `status_now` YELLOW/RED olan göstergede "could reach" yerine "is already at the warning
   level" ve ekip doktoru önerisi). Sahnede bu yedek her zaman çalışmalı.
7. **Acil durum ayrı kalır.** Tahmin hiçbir zaman acil durum banner'ını tetiklemez, acil durum mantığını
   değiştirmez. "I have chest pain" gibi mesajlar mevcut acil durum yolundan gitmeye devam etmeli.
8. **Yer ekibi.** Projede yer ekibine/panele giden bir endpoint varsa tahmini orada `audience="ground"` ile ver.
   Yoksa ekleme, sadece bana söyle.

### Test et (bitti demeden önce)

- Birim testleri (pytest varsa pytest, yoksa basit script):
  - AST-02, gün 156 (`payloads_tr_mission_iss180.jsonl`): `status == "ok"`, `model_version == "forecast_v2"`,
    `watch_list` stress (`likely`), resting heart rate ve sleep duration (`possible`) içeriyor
    (`examples/AST-02_day156.json` ile aynı sonuç). Stres `likely` olduğu için cevap ekip doktoruna yönlendirmeli.
  - AST-01, gün 10: `insufficient_data` → cevapta tahmin sayısı yok, "not enough data yet" benzeri bir cümle var.
  - Kontrol ikizi (`payloads_tr_control_iss180.jsonl`), AST-02 gün 156: `watch_list` boş → "stable" cevabı.
  - `audience="ground"` çıktısında `self_report: true` olan gösterge yok.
  - Sayı doğrulayıcı: JSON'da olmayan bir sayı içeren sahte LLM cevabı reddediliyor, yuvarlanmış doğru sayılar
    kabul ediliyor.
  - Model dosyası eksikken sunucu açılıyor ve tahmin sorusuna kibar bir "forecast unavailable" cevabı veriyor.
- Gerçek uçtan uca deneme: Ollama açıkken sunucuyu çalıştır, AST-02 gün 156 için şu üç soruyu sor ve
  **gerçek cevapları** bana göster (her biri için: LLM cevabı mı yedek şablon mu kullanıldı, kaç saniye sürdü):
  1. "What will next week look like for me?"
  2. "How is my sleep trending?"
  3. "Should I be worried about my heart rate?"
  Ayrıca "I have chest pain" mesajının hâlâ acil durum yolundan gittiğini göster.

### Kurallar

- Sayıları LLM üretmez: tahmin sayıları sadece modelden, durumlar (GREEN/YELLOW/RED) kural motorundan gelir.
- Eşik uydurma; mevcut eşik/kural dosyalarına dokunma.
- Model tamamen sentetik veriyle eğitildi: cevaplarda ve UI'da "projection, not a diagnosis" ifadesi kalmalı.
- Commit/push yapma. Bitince değişen dosyaların listesini ve nasıl çalıştırılacağını yaz; ben bakıp commit'leyeceğim.
- Bir şey belirsizse (veri katmanı, demo günü, UI değişikliği) tahmin etme, bana sor.
