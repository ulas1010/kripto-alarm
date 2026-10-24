# Kripto Onay (Confirmation) Alarmı

Efloud'un **Confirmation (Onay) Mekanizmaları** videosundaki yapıları BTC ve ETH'de otomatik arar.
Bir yapı oluştuğunda Telegram'a **grafikli** bir mesaj gönderir.

- **Breaker**: Fiyat destekte eski dibin altındaki likiditeyi alır, sonra ara tepeyi kırar (short için tersi).
- **Mitigation**: Fiyat eski dibi bozmadan daha yüksek bir dip yapar ve ara tepeyi kırar.
- **SFP**: Fitil eski dibin altına sarkar ama mum üstünde kapatır, ardından onay mumu gelir.
- **Kırılım + Retest**: Bölge sert bir mumla kırılır, geri test edilir ve tekrar kaybedilir (ya da kazanılır).

Destek ve direnç bölgeleri günlük ve 4 saatlik grafikten otomatik bulunur. Onaylar 15 dakikalık ve 1 saatlik grafikte aranır.
Bot GitHub'ın ücretsiz sunucularında 15 dakikada bir çalışır, bilgisayarının açık olması gerekmez.

> ⚠️ Bu bot bir yatırım tavsiyesi değildir. Sadece "bu grafiğe bir bak" der. Her işlemde stop kullan.

---

## Kurulum (yaklaşık 10 dakika, tamamen ücretsiz)

### 1) Telegram botunu oluştur
1. Telegram'da **@BotFather**'ı aç ve `/newbot` yaz.
2. Bota bir isim ver (örn. `Kripto Alarmım`). Sonra sonu `bot` ile biten bir kullanıcı adı ver (örn. `ulas_kripto_alarm_bot`).
3. BotFather sana uzun bir **token** verir (`123456:ABC...` gibi görünür). Bunu bir kenara kopyala, **kimseyle paylaşma**.
4. BotFather'ın verdiği linkten kendi botunu aç ve **Başlat**'a (/start) bas.

### 2) GitHub hesabı ve depo
1. github.com'da ücretsiz bir hesap aç (varsa giriş yap).
2. Sağ üstten **+ → New repository**'yi seç.
   - İsim: `kripto-alarm`
   - **Public** seç. Public depolarda bot sınırsız ve ücretsiz çalışır. Token gizli kalır, sadece kod görünür.
3. **Create repository**'ye bas.
4. Dosyaları yükle. Bunu Claude yapabilir: depo adını Claude'a yazman yeterli.
   Kendin yükleyeceksen **uploading an existing file** linkine tıklayıp zip içindeki her şeyi sürükle.
   (`.github` klasörü Mac'te gizli olabilir. Görünmüyorsa Finder'da `Cmd + Shift + .` ile gizli dosyaları göster.)

### 3) Telegram token'ını gizli olarak ekle
Depoda **Settings → Secrets and variables → Actions → New repository secret** yolunu izle.
- Name: `TELEGRAM_BOT_TOKEN`
- Secret: BotFather'ın verdiği token

### 4) İlk çalıştırma ve Chat ID
1. Depoda **Actions** sekmesine gir. Uyarı çıkarsa **I understand my workflows, go ahead and enable them**'a bas.
2. Soldan **Kripto Onay Alarmi** → **Run workflow** → mod: `test` → **Run workflow**.
3. Telegram'a gelen mesajda **Chat ID**'n yazar.
4. 3. adımdaki gibi ikinci bir secret ekle: Name `TELEGRAM_CHAT_ID`, Secret o numara.
5. **Run workflow → test**'i tekrar çalıştır. Bu sefer bölge haritası ve birkaç örnek sinyal gelir. 🎉

Bundan sonrası otomatik çalışır:
- **15 dakikada bir** tarama yapılır, yeni yapı varsa alarm gelir.
- **Her sabah ~09:00**'da günlük özet gelir: güncel destek/direnç haritası ve trend.

---

## Alarm mesajı nasıl okunur?
- **Bölge**: Fiyatın tepki verdiği büyük zaman dilimi destek/direnci. Grafikte sarı alanla gösterilir.
- **Giriş**: Onay mumunun kapanışı. *Geri çekilme girişi* ise Efloud'un tercih ettiği, kırılan seviyeye geri test bekleyen giriştir.
- **Stop**: Yapının bozulduğu yer. Fiyat buraya gelirse fikir geçersizdir.
- **Hedef 1 / Hedef 2**: Parçalı kâr almak için düşük zaman dilimindeki likidite noktaları. **R** = risk/ödül oranıdır, R 2 riskin iki katı kazanç demektir.
- **Güç**: Yapı türüne, bölgenin gücüne ve R oranına göre verilen 1-5 yıldızlık puan.
- **Trend tersi** uyarısı: Efloud onay yapılarını en çok trend tersi ve yatay piyasada kullanıyor. Bu işlemlerde uzak hedef kovalama, kârı parça parça al.

## Ayarlar
`ayarlar.py` dosyasından coin ekleyip çıkarabilir, yapıları açıp kapatabilir ve minimum R oranını değiştirebilirsin.
GitHub'da dosyayı açıp kalem simgesine basman ve **Commit changes** demen yeterli.

## Bilmen gerekenler
- GitHub'ın kendi zamanlayıcısı güvenilir değil, saatlerce atlayabiliyor. Bu yüzden bot, yapı oluştuktan 20-30 dakikadan geç fark ettiği sinyalleri hiç göndermez (`ayarlar.py` → `MAKS_GECIKME_DAKIKA`). Her mesajda yapının kaç dakika önce oluştuğu yazar.
- Bot sinyalin bayatlayıp bayatlamadığını kontrol eder. Fiyat stopa veya ilk hedefe çoktan gittiyse alarm göndermez.
- Otomatik tespit bir insanın gözü kadar iyi değildir. Gelen her alarmı Efloud'un videodaki kurallarıyla grafikte doğrula.
