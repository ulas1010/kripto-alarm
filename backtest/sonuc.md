# Backtest sonucu (25.04.2026 – 25.10.2026)

R = risk birimi. +1R = stop mesafesi kadar kâr, -1R = stopla tam kayıp. Komisyon (%0.1) düşülmüştür.
isabet_% = Hedef 1'in stoptan önce geldiği sinyallerin oranı.

### Genel

| hepsi | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| TÜMÜ | 1671 | 38.4 | 56.8 | -0.26 | -439.8 | -0.26 | -430.6 |

### Yapıya göre

| yapi | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| sfp | 517 | 37.9 | 61.7 | -0.46 | -237.2 | -0.44 | -225.3 |
| mitigation | 463 | 40.6 | 51.2 | -0.07 | -33.6 | -0.1 | -47.8 |
| retest | 383 | 39.7 | 59.5 | -0.3 | -114.3 | -0.29 | -109.9 |
| breaker | 308 | 34.4 | 53.6 | -0.18 | -54.7 | -0.15 | -47.7 |

### Trende göre

| trend_iliskisi | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| yatay piyasa | 657 | 39.0 | 56.5 | -0.28 | -180.7 | -0.28 | -182.4 |
| trend yönünde | 518 | 41.7 | 54.8 | -0.18 | -93.7 | -0.14 | -73.0 |
| trend tersi | 496 | 34.3 | 59.3 | -0.33 | -165.4 | -0.35 | -175.2 |

### Yapı × trend

| yapi | trend_iliskisi | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|---|
| sfp | yatay piyasa | 210 | 35.2 | 63.8 | -0.52 | -108.6 | -0.51 | -107.3 |
| mitigation | yatay piyasa | 171 | 42.7 | 49.1 | -0.03 | -4.8 | -0.09 | -15.5 |
| retest | yatay piyasa | 166 | 42.2 | 56.6 | -0.3 | -49.0 | -0.29 | -48.8 |
| sfp | trend yönünde | 158 | 41.8 | 58.2 | -0.35 | -55.3 | -0.27 | -43.2 |
| mitigation | trend yönünde | 150 | 44.0 | 52.0 | -0.05 | -7.3 | -0.05 | -7.1 |
| sfp | trend tersi | 149 | 37.6 | 62.4 | -0.49 | -73.3 | -0.5 | -74.8 |
| mitigation | trend tersi | 142 | 34.5 | 52.8 | -0.15 | -21.4 | -0.18 | -25.2 |
| retest | trend yönünde | 114 | 46.5 | 52.6 | -0.05 | -6.1 | 0.0 | 0.4 |
| breaker | yatay piyasa | 110 | 35.5 | 53.6 | -0.17 | -18.3 | -0.1 | -10.8 |
| retest | trend tersi | 103 | 28.2 | 71.8 | -0.58 | -59.2 | -0.6 | -61.4 |
| breaker | trend tersi | 102 | 35.3 | 51.0 | -0.11 | -11.5 | -0.13 | -13.7 |
| breaker | trend yönünde | 96 | 32.3 | 56.2 | -0.26 | -24.9 | -0.24 | -23.1 |

### Zaman dilimine göre

| tf | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| 15m | 1149 | 37.2 | 58.4 | -0.32 | -372.6 | -0.31 | -359.1 |
| 1h | 522 | 41.0 | 53.3 | -0.13 | -67.2 | -0.14 | -71.5 |

### Coine göre

| sembol | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 901 | 37.4 | 57.9 | -0.32 | -287.6 | -0.32 | -284.7 |
| ETHUSDT | 770 | 39.6 | 55.5 | -0.2 | -152.2 | -0.19 | -145.9 |

### Yöne göre

| yon | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| long | 840 | 38.0 | 57.6 | -0.27 | -228.2 | -0.26 | -219.8 |
| short | 831 | 38.9 | 56.0 | -0.25 | -211.5 | -0.25 | -210.8 |

### Güç puanına göre (yıldız)

| puan | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| 3.0 | 939.0 | 41.7 | 55.5 | -0.24 | -221.2 | -0.22 | -210.8 |
| 4.0 | 360.0 | 31.7 | 58.1 | -0.25 | -90.1 | -0.21 | -77.2 |
| 2.0 | 350.0 | 38.0 | 58.6 | -0.34 | -119.1 | -0.38 | -132.0 |
| 5.0 | 22.0 | 13.6 | 63.6 | -0.42 | -9.3 | -0.48 | -10.6 |

### Aylara göre

| ay | sinyal | isabet_% | stop_% | ort_R_tp1 | top_R_tp1 | ort_R_parcali | top_R_parcali |
|---|---|---|---|---|---|---|---|
| 2026-04 | 38 | 39.5 | 55.3 | -0.26 | -9.9 | -0.26 | -9.7 |
| 2026-05 | 306 | 36.6 | 59.5 | -0.34 | -103.0 | -0.35 | -108.4 |
| 2026-06 | 223 | 35.4 | 60.5 | -0.28 | -62.1 | -0.26 | -57.6 |
| 2026-07 | 286 | 41.6 | 54.5 | -0.19 | -55.2 | -0.22 | -61.8 |
| 2026-08 | 285 | 40.7 | 52.6 | -0.22 | -63.1 | -0.22 | -63.6 |
| 2026-09 | 313 | 32.9 | 61.7 | -0.38 | -118.3 | -0.34 | -105.5 |
| 2026-10 | 220 | 44.5 | 50.9 | -0.13 | -28.2 | -0.11 | -24.0 |


Geçersiz/atlanan sinyal: 0
