# Geliştirme turu 1 — sonuç (25.10.2026)

Dört dönem (her biri 6 ay, BTC+ETH, komisyon dahil, işlem başına ortalama R):

| Dönem | Kullanım | Temel bot | Aday A (1s, güç≥4, stop≥%1, yapı-trend yönünde) | Aday B (15dk+1s, aynı filtreler) |
|---|---|---|---|---|
| Eki 2025–Nis 2026 | geliştirme | -0,155R (1462) | +0,086R (101) | +0,047R (254) |
| Nis–Eki 2026 | doğrulama (seçimde görüldü) | -0,264R (1666) | +0,289R (102) | +0,183R (193) |
| Nis–Eki 2025 | bağımsız test 1 | -0,202R (1526) | +0,006R (88) | -0,013R (198) |
| Eki 2024–Nis 2025 | bağımsız test 2 | -0,195R (1364) | -0,063R (76) | -0,051R (190) |

Ön kayıttaki ölçüt (iki bağımsız dönemde de ort. R > 0 ve ≥ 40 işlem): **A ve B geçemedi.**

Çıkarımlar:
* Filtreler kaybı belirgin azaltıyor (≈ -0,2R → ≈ 0R): trend yönünde, güçlü bölge, geniş stop, 1 saatlik.
* Ama bağımsız verilerde kalıcı pozitif bir avantaj görülmedi → otomatik sinyal modu kapalı kalıyor.
* 360 kombinasyon denendi; en iyi görünenlerin çoğu başka dönemde tutmadı (aşırı uydurma riski).
* İzleme modu: trend artık günlük tepe/dip yapısından okunuyor, trend yönündeki bölge temasları ⭐ ile işaretleniyor.
