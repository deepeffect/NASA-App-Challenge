# Egemen'in Claude'una güncelleme: main entegrasyonu (v3)

Egemen için: bu sefer **kod veya dosya kopyalamana gerek yok**. Claude Code'u asistan API projesinin ana
klasöründe aç ve aşağıdaki çizginin altındaki her şeyi yapıştır.

---

## Bağlam

Ben Egemen, NASA Space Apps 2026 "AI Gambit" takımındayım. Bu klasör benim **asistan API'm** (FastAPI + Ollama
`qwen2.5:7b`, `[D]`/`[K]` kaynak rozetleri, sayı doğrulayıcı). Ana projenin `llm` branch'i takımın `main`'iyle
birleştirildi ve bu API'yi kullanmaya devam ediyor. Ana projede **kod değişikliği gerekmiyor**; bu mesajın amacı:
(1) Mac'teki Ollama ayarını main'in yeni gereksinimlerine uydurmak, (2) API'nin sözleşmesini korumak,
(3) testte görülen birkaç küçük sorunu düzeltmek.

Bu Mac'e **iki ayrı istemci** bağlanıyor:

| İstemci | Nereye | Ne için |
|---|---|---|
| Ana projenin arayüzü (eski astronot sayfası, `/legacy`) | bu API, port **8000** | sohbet, uyarılar, günlük rapor |
| Ana projenin backend'i (gemi bilgisayarı) | **doğrudan Ollama**, port **11434** (`/v1`) | yeni `/me` ekranı: check-in sohbeti ve "Asistana sor" |

Yani Ollama hem bu API'ye hem de gemi bilgisayarına hizmet ediyor.

## 1. Mac ayarları (zorunlu)

Main'in yeni belgesine göre (README → "2b) LLM bilgisayarı"):

- **Bağlam uzunluğu en az 16k olmalı.** Ollama varsayılanı VRAM'e göre seçer (24 GB'tan az: 4k) ve 4k yetmez;
  check-in turu ~1,7 bin, sohbet 1–4 bin, 30 günlük ölçüm sorusu ~11 bin token tutar. Ollama uygulaması →
  Settings → context length (denemede 32768 ile çalıştı). `ollama serve` ile çalışıyorsa
  `OLLAMA_CONTEXT_LENGTH=16384`. Bu API Ollama'yı kendi `num_ctx` değeriyle çağırıyorsa onu da ≥16384 yap.
- Ollama ağa açık kalmalı: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"` (Mac yeniden başlarsa tekrar; sonra
  Ollama'yı tamamen kapatıp aç). İsteğe bağlı: `launchctl setenv OLLAMA_KEEP_ALIVE "-1"` (model bellekte kalır,
  ilk cevap gecikmesi olmaz).
- Bu API `--host 0.0.0.0 --port 8000` ile çalışmaya ve CORS'ta tüm kaynaklara izin vermeye devam etmeli
  (arayüz tarayıcıdan doğrudan çağırıyor).
- macOS güvenlik duvarı açıksa 8000 ve 11434'e gelen bağlantılara izin ver. Mac uykuya geçince iki port da
  cevap vermiyor (testte iki kez oldu): demo sırasında uykuyu kapat.

## 2. Sözleşme — bunları bozma (alan eklemek serbest, silme/yeniden adlandırma yok)

Arayüz şunları kullanıyor:

- `GET /health` → `ok`, `current`, `mission_day` (arayüzde "Asistan verisi: AST-02 · 180. gün" etiketi)
- `GET /records` → `{file, astronauts: {"AST-02": {first_day, last_day}}}`
- `POST /select {"astronaut_id": "AST-02", "day": 157}` → sayfadaki astronot + görev günü değişince çağrılır,
  ardından rapor ve uyarılar yeniden çekilir. **`day` = ana projedeki görev günü (1–180).**
- `GET /alerts` → `alerts[]`: `level` ("RED"/"YELLOW"), `indicator`, `fallback` (her zaman dolu), `explanation`, `sources`
- `GET /daily_report?force=` → `report` (markdown), `sources`
- `POST /chat {"message"}` → `answer` (markdown), `sources`
- `POST /reset`
- `sources`: `{"D1": {type:"data", label, value, unit, status}, "K1": {type:"knowledge", label, text}}` —
  metindeki `[D1]`/`[K1]` etiketleri arayüzde 📊/📄 rozetine çevriliyor; etiketin `sources`'ta karşılığı olmalı.
- Zaman aşımı arayüzde 180 sn; cevaplar bunun altında kalmalı.

## 3. Testte görülen sorunlar (düzelt)

1. **`[Advice]` yer tutucusu cevaba sızıyor.** "How is my sleep?" (AST-02, gün 180) cevabı arayüzde şöyle
   göründü: "Sleep duration is 4.7 hours [D…] and sleep quality is 3.0 points [D…]. **[Advice]** [K…]" — öneri
   cümlesi yerine şablondaki `[Advice]` kalmış. Doldurulmamış şablon parçası kalırsa ya doldur ya da çıkar.
2. **Türkçe mesajlar genel bir hata cevabına düşüyor.** Arayüz Türkçe de olabiliyor;
   "Göğsümde baskı var, nefes darlığı çekiyorum" mesajına cevap:
   "I couldn't produce a reliable answer from the available data…". Türkçe girdiyi anlayıp **İngilizce** cevap
   vermesi yeterli (niyet/anahtar kelime yönlendirmesi varsa Türkçe karşılıkları ekle).
3. **Acil belirtide yönlendirme.** Ana projede acil tespit kural tabanlı ve ayrı çalışıyor (arayüzde kırmızı
   ACİL bandı çıkıyor), ama bu API de göğüs ağrısı / nefes darlığı / bayılma / kendine zarar gibi ifadelerde
   genel hata yerine kısa bir cevap vermeli: "Start the onboard medical emergency protocol and contact the Crew
   Medical Officer now." Teşhis koyma, sayı uydurma.
4. **Gün numarası teyidi.** `/select`'teki `day` ile veri dosyasındaki (`payloads_tr_mission_iss180.jsonl`) gün
   aynı şeyi mi ifade ediyor (görev günü 1 = görevin ilk günü)? Değilse dönüşümü API'de yap ve bana söyle.

## Nasıl çalış

1. Önce kodu oku ve bana raporla (dosya:satır): Ollama çağrısı ve `num_ctx`; `[Advice]` nereden geliyor;
   niyet yönlendirmesi; acil ifadeler için bir kontrol var mı; `/select`'te gün nasıl kullanılıyor.
2. 5–8 maddelik plan yaz ve **onayımı bekle**.
3. Sonra düzelt; yukarıdaki sözleşmeyi bozma. Her düzeltmeden sonra şunlarla kontrol et:

```bash
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/select -H "Content-Type: application/json" -d '{"astronaut_id":"AST-02","day":157}'
curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"message":"How is my sleep?"}'
curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"message":"Göğsümde baskı var, nefes darlığı çekiyorum"}'
curl -s "http://localhost:8000/daily_report?force=true"
ollama ps    # CONTEXT sütunu ≥ 16384 olmalı
```

Beklenen: `[Advice]` yok; Türkçe acil mesajına İngilizce kısa acil yönlendirme; `ollama ps`'te bağlam ≥16384.
