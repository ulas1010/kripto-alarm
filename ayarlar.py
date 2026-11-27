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
# XAUUSDT = altın, XAGUSDT = gümüş (OKX vadeli kontrat fiyatı, 7/24).
# Not: Efloud bölgeleri sadece BTC/ETH için var; altın/gümüşte şimdilik sadece otomatik bölge uyarıları gelir.
SEMBOLLER = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT", "XAUUSDT", "XAGUSDT"]

# Onay (confirmation) aranacak düşük zaman dilimleri.
# Efloud: 4s / 1s / 15dk gibi zaman dilimlerine inip onay arıyor.
# Efloud (13.11.2026): "mavi kutuda 1H-4H gibi zaman dilimlerindeki onay yapılarıyla alım düşünülmeli"
ONAY_ZAMAN_DILIMLERI = ["15m", "1h", "4h"]

# Destek/direnç bölgelerinin bulunacağı yüksek zaman dilimleri
BOLGE_ZAMAN_DILIMLERI = ["1d", "4h"]

# Eski yapılar: sadece "sinyal" modunda ve backtest.py'de kullanılır (izleme modunda mesaj atmaz)
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
MAKS_GECIKME_DAKIKA = {"15m": 20, "30m": 25, "1h": 30, "4h": 45}

# ----------------------------------------------------------------------------
# SWEEP → BOS → OTE (Efloud'un kurgusu, 27.11.2026)
# Sıra: fitille likidite alımı → son kısa vadeli tepenin kırılması (BOS) → Fibonacci 0.62–0.79'a geri çekilme.
# Bot iki mesaj atar: KURULUM (1/2) kırılım olunca, OTE'YE GELDİ (2/2) fiyat aralığa gelince.
# Not: Bu kuralın ham hali 3 yıllık backtest'te tek başına kâr etmedi; mesajlar "grafiğe bak" uyarısıdır.
# ----------------------------------------------------------------------------
OTE_SEMBOLLER = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "HYPEUSDT"]
OTE_ZAMAN_DILIMLERI = ["15m", "1h"]
OTE_FIB = (0.62, 0.79)       # OTE aralığı
OTE_GIRIS_FIB = 0.705        # aralığın ortası: mesajdaki giriş ve kâğıt takip bu seviyeden
# Kırılımdan sonra fiyatın OTE'ye gelmesi için en fazla kaç mum beklensin (15dk: 24 saat, 1s: 2 gün)
OTE_DOLUM_MUM = {"15m": 96, "1h": 48}
# True: sweep sadece Efloud'un bölgelerinde (bolgeler_manuel.json) aranır. SOL/HYPE'ta Efloud bölgesi yok.
OTE_SADECE_EFLOUD_BOLGESI = False
# Stop mesafesi bundan darsa (yüzde) mesaj gönderilmez: çok dar stopu komisyon ve gürültü yer
OTE_MIN_STOP_YUZDE = 0.5
