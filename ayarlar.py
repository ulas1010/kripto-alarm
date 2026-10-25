"""
AYARLAR - Botun davranışını buradan değiştirebilirsin.
Bir şeyi değiştirmek istersen sadece bu dosyayı düzenlemen yeterli.
"""

# ÇALIŞMA MODU
#   "izleme" : Fiyat güçlü bir bölgeye gelince "grafiğe bak" uyarısı (işlem sinyali YOK)
#   "sinyal" : Otomatik giriş/stop/hedef sinyalleri (backtest'te kârsız çıktı, önerilmez)
CALISMA_MODU = "izleme"

# İzleme modu: bölgenin en az bu güçte olması gerekir (Günlük dönüş noktası 2, 4 saatlik 1 puan)
IZLEME_MIN_PUAN = 3
# İzleme modu: aynı bölge için en erken kaç saat sonra tekrar uyarı gönderilsin
IZLEME_TEKRAR_SAAT = 24

# Takip edilecek coinler
SEMBOLLER = ["BTCUSDT", "ETHUSDT"]

# Onay (confirmation) aranacak düşük zaman dilimleri.
# Efloud: 4s / 1s / 15dk gibi zaman dilimlerine inip onay arıyor.
ONAY_ZAMAN_DILIMLERI = ["15m", "1h"]

# Destek/direnç bölgelerinin bulunacağı yüksek zaman dilimleri
BOLGE_ZAMAN_DILIMLERI = ["1d", "4h"]

# Hangi yapılar aransın? (İstemediğini False yap)
YAPILAR = {
    "breaker": True,      # Likidite alıp yapı kırma (Efloud'un en güvendiği)
    "mitigation": True,   # Eski dibi/tepeyi bozmadan yapı kırma
    "sfp": True,          # Swing Failure Pattern + onay mumu
    "retest": True,       # Destek/direnç kaybı (kazanımı) + retest
}

# Bir bölgenin dikkate alınması için gereken minimum güç puanı
# (Günlük grafikteki her dönüş noktası 2, 4 saatlikteki 1 puan)
MIN_BOLGE_PUANI = 2

# Fiyattan en fazla yüzde kaç uzaktaki bölgeler takip edilsin
BOLGE_MESAFE_YUZDE = 12

# Bu risk/ödül oranının altındaki sinyaller gönderilmez
MIN_RISK_ODUL = 1.0

# Günlük özet mesajı gönderilsin mi (her sabah ~09:00)
GUNLUK_OZET = True

# Yapı oluştuktan en fazla kaç dakika sonra alarm gönderilsin.
# Bundan daha geç fark edilen yapılar (fiyat çoktan kaçmış olabilir) GÖNDERİLMEZ.
MAKS_GECIKME_DAKIKA = {"15m": 20, "30m": 25, "1h": 30}

# Onay adayı: stop mesafesi bundan darsa aday gönderilmez (backtest: %1'den dar stoplar zarar ettirdi)
ADAY_MIN_STOP_YUZDE = 1.0
