"""
AYARLAR - Botun davranışını buradan değiştirebilirsin.
Bir şeyi değiştirmek istersen sadece bu dosyayı düzenlemen yeterli.
"""

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
