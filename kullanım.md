# Arayüz Kullanımı

Kökte `npm run dev` çalıştırıp <http://localhost:5173> adresini açın. (İlk kurulum: `npm run setup`.)

> Asistan **karar desteği** verir, teşhis koymaz. Uyarılar kural tabanlıdır ve yapay zekâ kapalıyken de çalışır.

## Üst bar (her sayfada)

- **Mürettebat / Check-in:** sayfalar arası geçiş.
- **Asistan durumu** (sağ üst):
  - `● Asistan: mock mod`: model bağlı değil, şablon cevaplar geliyor.
  - `● Asistan: qwen3:14b`: gerçek model bağlı.
  - `● Asistan çevrim dışı`: model yok ama uyarılar çalışıyor.
- **Zaman kaydırıcısı:** görevin herhangi bir gününe gider. Bütün ekranlar o günün verisiyle yeniden hesaplanır.
  - **Canlıya dön** butonu son güne döner.
  - Seçili gün URL'de durur (`?as_of=2026-10-22`), link olarak paylaşılabilir.

## Durum ve renkler

Durum hiçbir yerde sadece renkle verilmez; her zaman ikon + metin vardır.

| Rozet | Anlamı |
|---|---|
| ✔ **Normal** (yeşil) | Kişisel normal aralıkta |
| ⚠ **Dikkat** (sarı) | En az bir uyarı var |
| ⛔ **Kritik** (kırmızı) | Kritik uyarı var ya da skor 50'nin altında |
| ? **Veri yok** | O sistem için ölçüm yok |

- **Skor (0–100):** 100'den aktif uyarıların cezaları düşülür. Sistem kartında hangi uyarının kaç puan düşürdüğü yazar.
- **Uyarı ciddiyeti:**
  - **Kritik** ve **Uyarı** olay kartlarında görünür.
  - **Bilgi** seviyesindekiler sadece günlük brifingde görünür.

## Mürettebat ekranı

Her astronot için bir kart gösterilir: genel durum, skor, kritik ve uyarı sayıları, dikkat gerektiren sistemler. Detaya gitmek için karta tıklayın.

## Astronot detayı

1. **Sistem kartları:** kardiyovasküler, kas-iskelet, bağışıklık, davranışsal sağlık, uyku ve radyasyon için skor ve durum.
2. **Aktif uyarılar:** en ciddi 3 olay gösterilir, kalanlar **Tüm uyarıları göster** ile açılır. Her olay kartında şunlar var:
   - **Etiketler:**
     - kaynak: *Kural*, *Model tespiti* veya *Tahmin*
     - **Güven** (düşük / orta / yüksek)
     - ilgili sistem
   - **Bu uyarıya katkı:** olayı oluşturan metrikler; her birinin şu anki değeri, kişisel normali ve katkı payı.
   - **Neden?** Olası etkenler, önerilen adımlar ve kaynaklarla bir açıklama açar. Model kullanılamadıysa açıklama "Kural tabanlı şablon" etiketiyle gelir.
   - **Yanlış alarm:** geri bildirim kaydeder.
   - **Yer ekibiyle paylaş:** olayı yer ekibi raporuna ekler (varsayılan kapalı).
   - **Grafikte göster:** ilgili metriği aşağıdaki grafikte açar.
3. **Metrik grafiği:** metrik ve gün aralığı seçilir (14 / 30 / 60 / 180 gün).
4. **Günlük brifing:** günün özeti, dikkat edilecekler, öneriler, iyi gidenler ve bilgi notları.
5. **Sağlık asistanı:** sohbet paneli (aşağıda).

### Grafiği okumak

| Görünüm | Anlamı |
|---|---|
| Beyaz çizgi | Günlük değer |
| Gri çizgi | 7 günlük ortalama |
| Mavi bant | Kişisel normal (ilk 14 günün ortalaması ± standart sapma) |
| Kesikli turuncu / kırmızı çizgi | Uyarı / kritik eşiği. *"doğrulanmamış"*: eşik henüz NASA-STD-3001 ile doğrulanmadı |
| Turuncu / kırmızı gölge | Uyarı / kritik olay dönemi |
| Mor dikey kesikli çizgi | Değişim noktası (model tespiti) |
| Mor kesikli çizgi + bant | 7 günlük tahmin ve belirsizlik aralığı |

Grafiğin üstündeki **"7 gün z"**, 7 günlük ortalamanın kişisel normalden kaç standart sapma uzakta olduğunu gösterir. ±2'nin ötesi belirgin bir sapmadır.

## Sağlık asistanı (sohbet)

- Hazır sorulara tıklayın ya da kendi sorunuzu yazın: "Son günlerde uykum nasıl?", "Radyasyon dozum ne durumda?"
- Asistan veriye bakarken **"Veri alınıyor: …"** göstergesi çıkar; bitince **✓** olur.
- Cevaptaki sayılar asistanın aldığı veriden gelir. Karşılığı bulunamayan bir sayı varsa altında **"Doğrulanamayan sayılar"** uyarısı çıkar.
- Cevap gelirken **■** ile durdurabilir, **Temizle** ile sohbeti sıfırlayabilirsiniz.

**Acil durum:** Mesajda göğüs ağrısı, nefes darlığı, bayılma gibi ciddi bir belirti geçerse, yapay zekâdan önce ve ondan bağımsız olarak kırmızı **ACİL** bandı çıkar. Bantta protokol adımları ve iletişim bilgileri yer alır. Bandı gizlemek protokolü durdurmaz.

## Günlük check-in

1. Astronotu seçin.
2. **Ruh hali**, **stres** ve **uyku kalitesi** için 1–5 arası bir değer seçin. Seçili değer çerçeve ve ✔ işaretiyle gösterilir.
3. İsterseniz not ekleyin. Not, acil belirtiler için otomatik taranır.
4. **Yer ekibiyle paylaş** (isteğe bağlı) → **Kaydet**. Üç ölçek seçilmeden Kaydet aktif olmaz.

## 2 dakikalık demo akışı

1. **Mürettebat:** Astronot 2 *Kritik*, diğerleri *Normal*.
2. **Kaydırıcıyı geriye çekin:**
   - 150. gün: herkes Normal.
   - 152. gün: Astronot 2 *Dikkat* (uyku eşiğin altında).
   - 157. gün: *Kritik*.
3. **Astronot 2 → bir olay kartında Neden?:** etkenler ve öneriler; uyku düşüşü, stres ve nabız artışıyla birlikte görünüyor.
4. **Grafikte göster:** uyku süresi kişisel normal bandının altına iniyor.
5. **Sohbet:**
   - "Son günlerde uykum nasıl?" sorusuna gerçek veriden bir cevap gelir.
   - "Göğsümde ağrı var" yazınca ACİL bandı çıkar.
6. **Check-in:** formu doldurup kaydedin.

> Değişim noktası ve tahmin katmanlarını görmek için backend `.env` dosyasında örnek dedektörleri açın:
> `ANALYSIS_DETECTORS=threshold,baseline_deviation,trend,example_changepoint,example_forecast,system_pattern`
