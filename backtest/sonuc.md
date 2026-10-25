# Backtest sonucu (25.09.2026 – 25.10.2026)

R = risk birimi. +1R = stop mesafesi kadar kâr, -1R = stopla tam kayıp. Komisyon (%0.1) düşülmüştür.
isabet_% = Hedef 1'in stoptan önce geldiği sinyallerin oranı.

### Genel

| hepsi | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| TÜMÜ | 127 | 34.6 | 63.0 | -0.27 | -34.0 | -0.12 | -15.2 |

### Yapıya göre

| yapi | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| sfp | 44 | 25.0 | 75.0 | -0.65 | -28.6 | -0.67 | -29.3 |
| retest | 34 | 32.4 | 64.7 | -0.3 | -10.3 | -0.04 | -1.3 |
| breaker | 25 | 36.0 | 60.0 | -0.12 | -2.9 | 0.08 | 2.0 |
| mitigation | 24 | 54.2 | 41.7 | 0.32 | 7.8 | 0.56 | 13.4 |

### Trende göre

| trend_iliskisi | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| yatay piyasa | 107 | 30.8 | 66.4 | -0.36 | -38.0 | -0.22 | -23.7 |
| trend tersi | 12 | 66.7 | 33.3 | 0.52 | 6.3 | 0.62 | 7.4 |
| trend yönünde | 8 | 37.5 | 62.5 | -0.29 | -2.3 | 0.14 | 1.1 |

### Yapı × trend

| yapi | trend_iliskisi | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|---|
| sfp | yatay piyasa | 38 | 21.1 | 78.9 | -0.76 | -29.0 | -0.81 | -30.8 |
| retest | yatay piyasa | 29 | 34.5 | 62.1 | -0.22 | -6.3 | 0.12 | 3.4 |
| breaker | yatay piyasa | 21 | 33.3 | 61.9 | -0.13 | -2.8 | 0.1 | 2.1 |
| mitigation | yatay piyasa | 19 | 42.1 | 52.6 | 0.01 | 0.2 | 0.09 | 1.7 |
| sfp | trend tersi | 3 | 66.7 | 33.3 | 0.7 | 2.1 | 0.92 | 2.8 |
| mitigation | trend tersi | 3 | 100.0 | 0.0 | 1.5 | 4.5 | 1.89 | 5.7 |
| breaker | trend tersi | 3 | 66.7 | 33.3 | 0.32 | 0.9 | 0.31 | 0.9 |
| retest | trend tersi | 3 | 33.3 | 66.7 | -0.42 | -1.3 | -0.64 | -1.9 |
| sfp | trend yönünde | 3 | 33.3 | 66.7 | -0.55 | -1.7 | -0.4 | -1.2 |
| retest | trend yönünde | 2 | 0.0 | 100.0 | -1.37 | -2.7 | -1.37 | -2.7 |
| mitigation | trend yönünde | 2 | 100.0 | 0.0 | 1.55 | 3.1 | 3.06 | 6.1 |
| breaker | trend yönünde | 1 | 0.0 | 100.0 | -1.04 | -1.0 | -1.04 | -1.0 |

### Zaman dilimine göre

| tf | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| 15m | 88 | 35.2 | 63.6 | -0.31 | -27.0 | -0.21 | -18.7 |
| 1h | 39 | 33.3 | 61.5 | -0.18 | -7.0 | 0.09 | 3.6 |

### Coine göre

| sembol | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 106 | 31.1 | 67.0 | -0.37 | -39.0 | -0.25 | -26.7 |
| ETHUSDT | 21 | 52.4 | 42.9 | 0.24 | 5.0 | 0.55 | 11.5 |

### Yöne göre

| yon | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| short | 73 | 38.4 | 58.9 | -0.17 | -12.2 | -0.06 | -4.3 |
| long | 54 | 29.6 | 68.5 | -0.4 | -21.9 | -0.2 | -10.9 |

### Güç puanına göre (yıldız)

| puan | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| 3.0 | 78.0 | 30.8 | 69.2 | -0.41 | -32.4 | -0.35 | -27.1 |
| 2.0 | 26.0 | 42.3 | 50.0 | -0.12 | -3.1 | 0.1 | 2.6 |
| 4.0 | 21.0 | 38.1 | 57.1 | 0.0 | 0.0 | 0.32 | 6.8 |
| 5.0 | 2.0 | 50.0 | 50.0 | 0.7 | 1.4 | 1.27 | 2.5 |

### Aylara göre

| ay | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| 2026-09 | 16 | 37.5 | 62.5 | -0.16 | -2.6 | 0.67 | 10.8 |
| 2026-10 | 111 | 34.2 | 63.1 | -0.28 | -31.4 | -0.23 | -26.0 |


Geçersiz/atlanan sinyal: 1
