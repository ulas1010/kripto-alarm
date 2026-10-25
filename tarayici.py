"""
Kripto Onay (Confirmation) Alarmı
---------------------------------
Efloud'un "Confirmation (Onay) Mekanizmaları" videosundaki yapıları
BTC ve ETH üzerinde otomatik arar ve Telegram'a grafikli alarm gönderir.

Mantık:
  1) Günlük ve 4 saatlik grafikte önemli destek/direnç bölgeleri bulunur (HTF).
  2) Fiyat bu bölgelerdeyken 15dk / 1s grafikte onay yapıları aranır (LTF):
       - Breaker     : dip, tepe, daha düşük dip (likidite alımı) + tepenin kırılması
       - Mitigation  : dip, tepe, daha yüksek dip (eski dip bozulmadan) + tepenin kırılması
       - SFP         : fitille eski dibin altına sarkıp içeride kapanma + onay mumu
       - Retest      : bölgenin sert mumla kırılması, geri test, tekrar kaybedilmesi
  3) Bulunan her yeni yapı için giriş, stop ve iki hedef hesaplanır.

Bu bir yatırım tavsiyesi değildir; sadece "grafiğe bak" uyarısıdır.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import ayarlar

KOK = Path(__file__).resolve().parent
DURUM_DOSYASI = KOK / "durum.json"
TR_SAAT = timezone(timedelta(hours=3))  # İstanbul

TF_DAKIKA = {"15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
TF_ADI = {"15m": "15dk", "30m": "30dk", "1h": "1 saat", "4h": "4 saat", "1d": "Günlük"}

# Her zaman dilimi için: dönüş noktası (pivot) genişliği, canlı pencere (kaç kapanmış mum),
# yapının tamamlanması için beklenecek maksimum mum
LTF_AYAR = {
    "15m": dict(pivot=4, pencere=6, bekleme=48, bekleme_suresi=24),
    "30m": dict(pivot=3, pencere=4, bekleme=40, bekleme_suresi=16),
    "1h": dict(pivot=3, pencere=3, bekleme=36, bekleme_suresi=12),
}
HTF_PIVOT = {"1d": 5, "4h": 6}
HTF_AGIRLIK = {"1d": 2, "4h": 1}

YAPI_ADI = {
    "breaker": "Breaker",
    "mitigation": "Mitigation",
    "sfp": "SFP (Swing Failure)",
    "retest": "Kırılım + Retest",
}
YAPI_ACIKLAMA = {
    ("breaker", "long"): "Fiyat destekte eski dibin altındaki likiditeyi aldı, sonra ara tepeyi kırdı.",
    ("breaker", "short"): "Fiyat dirençte eski tepenin üstündeki likiditeyi aldı, sonra ara dibi kırdı.",
    ("mitigation", "long"): "Destekte ilk dipten sonra daha yüksek dip yaptı ve ara tepeyi kırdı.",
    ("mitigation", "short"): "Dirençte ilk tepeden sonra daha düşük tepe yaptı ve ara dibi kırdı.",
    ("sfp", "long"): "Fitil eski dibin altına sarktı ama mum üstünde kapattı; ardından yeşil onay mumu geldi.",
    ("sfp", "short"): "Fitil eski tepenin üstüne çıktı ama mum altında kapattı; ardından kırmızı onay mumu geldi.",
    ("retest", "long"): "Direnç sert mumla yukarı kırıldı, geri test edildi ve tekrar üstünde kapattı.",
    ("retest", "short"): "Destek sert mumla aşağı kırıldı, geri test edildi ve tekrar altında kapattı.",
}
YAPI_TABAN_PUAN = {"breaker": 3, "mitigation": 2, "sfp": 2, "retest": 2}


# ----------------------------------------------------------------------------
# VERİ
# ----------------------------------------------------------------------------
def _df(rows, cols=("t", "o", "h", "l", "c", "v")) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=list(cols)).astype(float)
    df["t"] = pd.to_datetime(df["t"].astype("int64"), unit="ms", utc=True)
    df = df.drop_duplicates("t").sort_values("t").reset_index(drop=True)
    return df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})


def _binance(sembol, tf, limit):
    url = "https://data-api.binance.vision/api/v3/klines"
    r = requests.get(url, params=dict(symbol=sembol, interval=tf, limit=min(limit, 1000)), timeout=20)
    r.raise_for_status()
    return _df([k[:6] for k in r.json()])


def _okx(sembol, tf, limit):
    inst = sembol.replace("USDT", "-USDT")
    bar = {"15m": "15m", "30m": "30m", "1h": "1H", "4h": "4Hutc", "1d": "1Dutc"}[tf]
    rows, after = [], None
    while len(rows) < limit:
        params = dict(instId=inst, bar=bar, limit=100)
        if after:
            params["after"] = after
        r = requests.get("https://www.okx.com/api/v5/market/history-candles", params=params, timeout=20)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            break
        rows += [d[:6] for d in data]
        after = data[-1][0]
        time.sleep(0.15)
    if not rows:
        raise RuntimeError("OKX boş döndü")
    return _df(rows)


def _kraken(sembol, tf, limit):
    pair = sembol.replace("BTC", "XBT")
    r = requests.get("https://api.kraken.com/0/public/OHLC",
                     params=dict(pair=pair, interval=TF_DAKIKA[tf]), timeout=20)
    r.raise_for_status()
    j = r.json()
    if j.get("error"):
        raise RuntimeError(str(j["error"]))
    key = [k for k in j["result"] if k != "last"][0]
    rows = [[int(k[0]) * 1000, k[1], k[2], k[3], k[4], k[6]] for k in j["result"][key]]
    return _df(rows).tail(limit).reset_index(drop=True)


KAYNAKLAR = [("Binance", _binance), ("OKX", _okx), ("Kraken", _kraken)]


def veri_cek(sembol, tf, limit=700) -> pd.DataFrame:
    """Sırayla birkaç borsayı dener; ilk çalışandan veriyi alır. Sadece kapanmış mumlar döner."""
    hatalar = []
    for ad, fn in KAYNAKLAR:
        try:
            df = fn(sembol, tf, limit)
            simdi = pd.Timestamp.now(tz="UTC")
            df = df[df["t"] + pd.Timedelta(minutes=TF_DAKIKA[tf]) <= simdi].reset_index(drop=True)
            if len(df) > 50:
                df.attrs["kaynak"] = ad
                return df
            hatalar.append(f"{ad}: az veri")
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"{ad}: {e}")
    raise RuntimeError(f"{sembol} {tf} verisi alınamadı -> " + " | ".join(hatalar))


# ----------------------------------------------------------------------------
# YARDIMCI HESAPLAR
# ----------------------------------------------------------------------------
def atr(df: pd.DataFrame, n=14) -> np.ndarray:
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    pc = np.roll(c, 1)
    pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).rolling(n, min_periods=1).mean().values


def pivotlar(df: pd.DataFrame, sol: int, sag: int):
    """Onaylanmış dönüş noktaları. Döner: [(index, fiyat, 'H'/'L'), ...] zaman sırasıyla."""
    h, l = df["high"].values, df["low"].values
    n = len(df)
    out = []
    for i in range(sol, n - sag):
        if h[i] > h[i - sol:i].max() and h[i] >= h[i + 1:i + sag + 1].max():
            out.append((i, h[i], "H"))
        if l[i] < l[i - sol:i].min() and l[i] <= l[i + 1:i + sag + 1].min():
            out.append((i, l[i], "L"))
    out.sort(key=lambda x: (x[0], 0 if x[2] == "L" else 1))
    return out


def ardisik_swingler(piv):
    """Aynı türden art arda gelen pivotları birleştirir -> tepe, dip, tepe, dip..."""
    sw = []
    for p in piv:
        if sw and sw[-1][2] == p[2]:
            if (p[2] == "H" and p[1] > sw[-1][1]) or (p[2] == "L" and p[1] < sw[-1][1]):
                sw[-1] = p
        else:
            sw.append(p)
    return sw


def gunluk_trend(df_d: pd.DataFrame) -> str:
    c = df_d["close"]
    e50 = c.ewm(span=50, adjust=False).mean().iloc[-1]
    e200 = c.ewm(span=200, adjust=False).mean().iloc[-1]
    son = c.iloc[-1]
    if son > e50 > e200:
        return "yükseliş"
    if son < e50 < e200:
        return "düşüş"
    return "yatay / kararsız"


def yapisal_trend(df: pd.DataFrame, k: int = 3) -> str:
    """Efloud'a yakın: tepe/dip yapısından trend.
    Yükselen tepe + yükselen dip = yükseliş, alçalan tepe + alçalan dip = düşüş.
    Son dönüş noktası kapanışla kırılırsa yön ona göre güncellenir (yapı kırılımı)."""
    sw = ardisik_swingler(pivotlar(df, k, k))
    tepeler = [p[1] for p in sw if p[2] == "H"][-2:]
    dipler = [p[1] for p in sw if p[2] == "L"][-2:]
    if len(tepeler) < 2 or len(dipler) < 2:
        return "yatay / kararsız"
    son = float(df["close"].iloc[-1])
    if son < dipler[-1]:
        return "düşüş"
    if son > tepeler[-1]:
        return "yükseliş"
    if tepeler[-1] > tepeler[-2] and dipler[-1] > dipler[-2]:
        return "yükseliş"
    if tepeler[-1] < tepeler[-2] and dipler[-1] < dipler[-2]:
        return "düşüş"
    return "yatay / kararsız"


# ----------------------------------------------------------------------------
# HTF BÖLGELERİ
# ----------------------------------------------------------------------------
@dataclass
class Bolge:
    alt: float
    ust: float
    puan: int
    kaynak: set = field(default_factory=set)
    ozel_etiket: str = ""
    aciklama: str = ""

    def icinde(self, fiyat, tol=0.0):
        return self.alt - tol <= fiyat <= self.ust + tol

    @property
    def etiket(self):
        if self.ozel_etiket:
            return self.ozel_etiket
        tf = "Günlük" if "1d" in self.kaynak else "4 saatlik"
        return f"{tf} bölge"


MANUEL_DOSYA = KOK / "bolgeler_manuel.json"


def manuel_bolgeler(sembol: str) -> list[Bolge]:
    """bolgeler_manuel.json: Efloud'un analizlerinden (veya elle) eklenen bölgeler.
    Biçim: {"BTCUSDT": [{"alt": 64000, "ust": 65000, "kaynak": "Efloud 25.10", "not": "..."}]}"""
    if not MANUEL_DOSYA.exists():
        return []
    try:
        veri = json.loads(MANUEL_DOSYA.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print("bolgeler_manuel.json okunamadı:", e)
        return []
    out = []
    for z in veri.get(sembol, []):
        out.append(Bolge(float(z["alt"]), float(z["ust"]), 9, {"manuel"},
                         ozel_etiket=f"⭐ {z.get('kaynak', 'Manuel')} bölgesi", aciklama=z.get("not", "")))
    return out


def bolgeleri_bul(htf: dict[str, pd.DataFrame], fiyat: float) -> list[Bolge]:
    adaylar = []
    for tf, df in htf.items():
        a = atr(df)
        k = HTF_PIVOT[tf]
        for i, p, tur in pivotlar(df, k, k):
            gen = 0.35 * a[i]
            if tur == "L":
                adaylar.append(Bolge(p, p + gen, HTF_AGIRLIK[tf], {tf}))
            else:
                adaylar.append(Bolge(p - gen, p, HTF_AGIRLIK[tf], {tf}))
    adaylar.sort(key=lambda b: b.alt)
    birlesik: list[Bolge] = []
    for b in adaylar:
        if birlesik and b.alt <= birlesik[-1].ust:
            s = birlesik[-1]
            s.ust = max(s.ust, b.ust)
            s.puan += b.puan
            s.kaynak |= b.kaynak
        else:
            birlesik.append(Bolge(b.alt, b.ust, b.puan, set(b.kaynak)))
    # Çok genişleyen bölgeleri sınırla (en fazla fiyatın %2.5'i)
    for b in birlesik:
        maxgen = fiyat * 0.025
        if b.ust - b.alt > maxgen:
            orta = (b.ust + b.alt) / 2
            b.alt, b.ust = orta - maxgen / 2, orta + maxgen / 2
    sinir = fiyat * ayarlar.BOLGE_MESAFE_YUZDE / 100
    return [b for b in birlesik
            if b.puan >= ayarlar.MIN_BOLGE_PUANI and abs((b.alt + b.ust) / 2 - fiyat) <= sinir]


# ----------------------------------------------------------------------------
# ONAY YAPILARI
# ----------------------------------------------------------------------------
@dataclass
class Sinyal:
    sembol: str
    tf: str
    yapi: str
    yon: str           # long / short
    i: int             # tetik mumunun index'i
    zaman: str
    giris: float
    stop: float
    geri_cekilme: float | None
    tp1: float = 0.0
    tp2: float = 0.0
    rr1: float = 0.0
    rr2: float = 0.0
    bolge_alt: float = 0.0
    bolge_ust: float = 0.0
    bolge_puan: int = 0
    bolge_etiket: str = ""
    noktalar: list = field(default_factory=list)  # [(index, fiyat, etiket)]
    trend: str = ""
    puan: int = 0

    @property
    def kimlik(self):
        return f"{self.sembol}|{self.tf}|{self.yapi}|{self.yon}|{self.zaman}"


def _bolge_bul(bolgeler, fiyatlar, tol):
    for b in sorted(bolgeler, key=lambda b: -b.puan):
        if any(b.icinde(f, tol) for f in fiyatlar):
            return b
    return None


def yapilari_tara(df: pd.DataFrame, tf: str, sembol: str, bolgeler: list[Bolge]) -> list[Sinyal]:
    if not bolgeler:
        return []
    ay = LTF_AYAR[tf]
    k, bekle = ay["pivot"], ay["bekleme"]
    o, h, l, c, v = (df[x].values for x in ("open", "high", "low", "close", "volume"))
    n = len(df)
    A = atr(df)
    piv = pivotlar(df, k, k)
    sw = ardisik_swingler(piv)
    zaman = lambda i: df["t"].iloc[i].strftime("%Y-%m-%dT%H:%M")  # noqa: E731
    out: list[Sinyal] = []

    def ekle(yapi, yon, i, giris, stop, gc, bolge, noktalar):
        if (yon == "long" and stop >= giris) or (yon == "short" and stop <= giris):
            return
        out.append(Sinyal(sembol, tf, yapi, yon, i, zaman(i), float(giris), float(stop),
                          None if gc is None else float(gc),
                          bolge_alt=bolge.alt, bolge_ust=bolge.ust, bolge_puan=bolge.puan,
                          bolge_etiket=bolge.etiket, noktalar=noktalar))

    # --- Breaker & Mitigation -------------------------------------------------
    if ayarlar.YAPILAR["breaker"] or ayarlar.YAPILAR["mitigation"]:
        for s in range(1, len(sw)):
            a, b = sw[s - 1], sw[s]
            for yon in ("long", "short"):
                if yon == "long" and not (a[2] == "L" and b[2] == "H"):
                    continue
                if yon == "short" and not (a[2] == "H" and b[2] == "L"):
                    continue
                atr_b = A[b[0]]
                if abs(b[1] - a[1]) < 1.5 * atr_b:   # anlamlı bir tepki olmalı
                    continue
                # Fiyat bölgeye yukarıdan (long) / aşağıdan (short) gelmiş olmalı
                onceki = slice(max(0, a[0] - 40), a[0])
                if a[0] < 5:
                    continue
                if yon == "long" and h[onceki].max() <= b[1]:
                    continue
                if yon == "short" and l[onceki].min() >= b[1]:
                    continue
                # b'den sonra geri çekilmenin ucu (c) ve b seviyesinin kırılması
                c_fiyat, c_i, tetik = None, None, None
                for j in range(b[0] + 1, min(n, b[0] + bekle)):
                    if yon == "long":
                        if c_fiyat is None or l[j] < c_fiyat:
                            c_fiyat, c_i = l[j], j
                        if c[j] > b[1]:
                            tetik = j
                            break
                    else:
                        if c_fiyat is None or h[j] > c_fiyat:
                            c_fiyat, c_i = h[j], j
                        if c[j] < b[1]:
                            tetik = j
                            break
                if tetik is None or c_i is None or c_i >= tetik:
                    continue
                if abs(b[1] - c_fiyat) < 0.6 * atr_b:  # gerçek bir geri çekilme olmalı
                    continue
                likidite_alindi = c_fiyat < a[1] if yon == "long" else c_fiyat > a[1]
                yapi = "breaker" if likidite_alindi else "mitigation"
                if not ayarlar.YAPILAR[yapi]:
                    continue
                tol = 0.3 * A[tetik]
                fiyatlar = [a[1], c_fiyat] if yapi == "breaker" else [a[1]]
                bolge = _bolge_bul(bolgeler, fiyatlar, tol)
                if bolge is None:
                    continue
                ekstrem = c_fiyat if yapi == "breaker" else min(a[1], c_fiyat) if yon == "long" else max(a[1], c_fiyat)
                tampon = 0.1 * A[tetik]
                stop = ekstrem - tampon if yon == "long" else ekstrem + tampon
                if yapi == "breaker":
                    etiketler = [(a[0], a[1], "Dip" if yon == "long" else "Tepe"),
                                 (b[0], b[1], "Kırılan seviye"),
                                 (c_i, c_fiyat, "Likidite alımı")]
                else:
                    etiketler = [(a[0], a[1], "1. dip" if yon == "long" else "1. tepe"),
                                 (b[0], b[1], "Kırılan seviye"),
                                 (c_i, c_fiyat, "Yüksek dip" if yon == "long" else "Alçak tepe")]
                ekle(yapi, yon, tetik, c[tetik], stop, b[1], bolge, etiketler)

    # --- SFP + onay mumu --------------------------------------------------------
    if ayarlar.YAPILAR["sfp"]:
        for (pi, pf, tur) in piv:
            yon = "long" if tur == "L" else "short"
            for j in range(pi + k + 1, min(n, pi + 120)):
                if yon == "long" and l[j] < pf:
                    if c[j] > pf and j + 1 < n and c[j + 1] > o[j + 1] and c[j + 1] > pf:
                        tol = 0.3 * A[j]
                        bolge = _bolge_bul(bolgeler, [pf, l[j]], tol)
                        if bolge and (pf - l[j]) <= 2.0 * A[j]:
                            ekle("sfp", "long", j + 1, c[j + 1], l[j] - 0.1 * A[j], None, bolge,
                                 [(pi, pf, "Eski dip"), (j, l[j], "Fitil (SFP)")])
                    break
                if yon == "short" and h[j] > pf:
                    if c[j] < pf and j + 1 < n and c[j + 1] < o[j + 1] and c[j + 1] < pf:
                        tol = 0.3 * A[j]
                        bolge = _bolge_bul(bolgeler, [pf, h[j]], tol)
                        if bolge and (h[j] - pf) <= 2.0 * A[j]:
                            ekle("sfp", "short", j + 1, c[j + 1], h[j] + 0.1 * A[j], None, bolge,
                                 [(pi, pf, "Eski tepe"), (j, h[j], "Fitil (SFP)")])
                    break

    # --- Kırılım + Retest ------------------------------------------------------
    if ayarlar.YAPILAR["retest"]:
        hacim_ort = pd.Series(v).rolling(20, min_periods=5).mean().values
        for bolge in bolgeler:
            tol = 0.0
            for bk in range(1, n):
                govde = abs(c[bk] - o[bk])
                sert = govde >= 0.8 * A[bk] or (hacim_ort[bk] > 0 and v[bk] >= 1.5 * hacim_ort[bk])
                if not sert:
                    continue
                # Aşağı kırılım (destek kaybı) -> short
                if c[bk] < bolge.alt <= c[bk - 1] and c[bk] < o[bk]:
                    yon = "short"
                elif c[bk] > bolge.ust >= c[bk - 1] and c[bk] > o[bk]:
                    yon = "long"
                else:
                    continue
                retest_i, tetik = None, None
                for j in range(bk + 1, min(n, bk + bekle)):
                    if yon == "short":
                        if c[j] > bolge.ust:
                            break  # bölge geri kazanıldı, iptal
                        if retest_i is None and h[j] >= bolge.alt - 0.2 * A[j]:
                            retest_i = j
                            if c[j] < bolge.alt and c[j] < o[j] and h[j] >= bolge.alt:
                                tetik = j  # tek mumda dokunup altında kırmızı kapattı
                                break
                            continue
                        if retest_i is not None and c[j] < bolge.alt and c[j] < c[retest_i]:
                            tetik = j
                            break
                    else:
                        if c[j] < bolge.alt:
                            break
                        if retest_i is None and l[j] <= bolge.ust + 0.2 * A[j]:
                            retest_i = j
                            if c[j] > bolge.ust and c[j] > o[j] and l[j] <= bolge.ust:
                                tetik = j
                                break
                            continue
                        if retest_i is not None and c[j] > bolge.ust and c[j] > c[retest_i]:
                            tetik = j
                            break
                if tetik is None:
                    continue
                if yon == "short":
                    stop = h[retest_i:tetik + 1].max() + 0.1 * A[tetik]
                    etiketler = [(bk, c[bk], "Sert kırılım"), (int(retest_i + np.argmax(h[retest_i:tetik + 1])),
                                                                h[retest_i:tetik + 1].max(), "Retest")]
                else:
                    stop = l[retest_i:tetik + 1].min() - 0.1 * A[tetik]
                    etiketler = [(bk, c[bk], "Sert kırılım"), (int(retest_i + np.argmin(l[retest_i:tetik + 1])),
                                                                l[retest_i:tetik + 1].min(), "Retest")]
                ekle("retest", yon, tetik, c[tetik], stop, None, bolge, etiketler)

    # --- Hedefler ve puan --------------------------------------------------------
    son = []
    son_sinyal = {}  # (bölge, yön) -> son sinyalin mum index'i
    for s in sorted(out, key=lambda s: (s.i, -YAPI_TABAN_PUAN[s.yapi])):
        anahtar = (round(s.bolge_alt, 8), s.yon)
        # Aynı bölgede aynı yöne kısa süre içinde tekrar sinyal verme (gürültüyü azaltır)
        if anahtar in son_sinyal and s.i - son_sinyal[anahtar] < ay["bekleme_suresi"]:
            continue
        hedef_belirle(s, df, piv, bolgeler)
        if s.rr1 < ayarlar.MIN_RISK_ODUL:
            continue
        son_sinyal[anahtar] = s.i
        son.append(s)
    return son


def hedef_belirle(s: Sinyal, df, piv, bolgeler):
    risk = abs(s.giris - s.stop)
    adaylar = []
    for (i, p, tur) in piv:
        if i >= s.i or i < s.i - 300:
            continue
        if s.yon == "long" and tur == "H" and p > s.giris:
            adaylar.append(p)
        if s.yon == "short" and tur == "L" and p < s.giris:
            adaylar.append(p)
    for b in bolgeler:
        if s.yon == "long" and b.alt > s.giris:
            adaylar.append(b.alt)
        if s.yon == "short" and b.ust < s.giris:
            adaylar.append(b.ust)
    adaylar = sorted(set(adaylar), key=lambda p: abs(p - s.giris))
    rr = lambda p: abs(p - s.giris) / risk  # noqa: E731
    tp1 = next((p for p in adaylar if 1.0 <= rr(p) <= 3.0), None)
    tp2 = next((p for p in adaylar if rr(p) >= 2.0 and (tp1 is None or abs(p - s.giris) > abs(tp1 - s.giris))), None)
    yon = 1 if s.yon == "long" else -1
    if tp1 is None:
        tp1 = s.giris + yon * 1.5 * risk
    if tp2 is None:
        tp2 = s.giris + yon * max(2.5 * risk, 1.5 * abs(tp1 - s.giris))
    s.tp1, s.tp2 = float(tp1), float(tp2)
    s.rr1, s.rr2 = round(rr(tp1), 2), round(rr(tp2), 2)
    puan = YAPI_TABAN_PUAN[s.yapi]
    if s.bolge_puan >= 4:
        puan += 1
    if s.rr1 >= 2:
        puan += 1
    s.puan = min(puan, 5)


def hala_gecerli(s: Sinyal, df) -> bool:
    """Tetikten sonra stop ya da TP1 görüldüyse sinyal bayatlamıştır."""
    sonra = df.iloc[s.i + 1:]
    if sonra.empty:
        return True
    if s.yon == "long":
        return sonra["low"].min() > s.stop and sonra["high"].max() < s.tp1
    return sonra["high"].max() < s.stop and sonra["low"].min() > s.tp1


# ----------------------------------------------------------------------------
# GRAFİK
# ----------------------------------------------------------------------------
def grafik_ciz(df, s: Sinyal | None, bolgeler, baslik, dosya, mum_sayisi=140, vurgu=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if s is not None:
        bas = max(0, s.i - mum_sayisi + 25)
        bit = min(len(df), s.i + 26)
    else:
        bit = len(df)
        bas = max(0, bit - mum_sayisi)
    d = df.iloc[bas:bit].reset_index(drop=True)
    x = np.arange(len(d))

    ARKA, IZGARA, YAZI = "#131722", "#2a2e39", "#d1d4dc"
    YESIL, KIRMIZI = "#26a69a", "#ef5350"
    fig, ax = plt.subplots(figsize=(11, 6), dpi=110)
    fig.patch.set_facecolor(ARKA)
    ax.set_facecolor(ARKA)
    for sp in ax.spines.values():
        sp.set_color(IZGARA)
    ax.tick_params(colors=YAZI, labelsize=8)
    ax.grid(color=IZGARA, linewidth=0.6)

    yukari = d["close"] >= d["open"]
    renk = np.where(yukari, YESIL, KIRMIZI)
    ax.vlines(x, d["low"], d["high"], color=renk, linewidth=0.9)
    govde_alt = np.minimum(d["open"], d["close"])
    govde_boy = np.maximum(abs(d["close"] - d["open"]), (d["high"].max() - d["low"].min()) * 0.0015)
    ax.bar(x, govde_boy, bottom=govde_alt, color=renk, width=0.65)

    ymin, ymax = d["low"].min(), d["high"].max()
    if s is not None:
        ymin = min(ymin, s.stop, s.tp1)
        ymax = max(ymax, s.stop, s.tp1)
    pad = (ymax - ymin) * 0.08
    ax.set_ylim(ymin - pad, ymax + pad)

    for b in bolgeler:
        if b.ust < ymin - pad or b.alt > ymax + pad:
            continue
        vurgulu = (s is not None and abs(b.alt - s.bolge_alt) < 1e-9) or (vurgu is not None and b is vurgu)
        ax.axhspan(b.alt, b.ust, color="#f0b90b" if vurgulu else "#5d6b8a",
                   alpha=0.28 if vurgulu else 0.15, zorder=0)
        ax.text(1, min(b.ust, ymax + pad * 0.6), f" {b.etiket} (güç {b.puan})", color=YAZI,
                fontsize=7, va="bottom" if b.ust <= ymax + pad * 0.6 else "top", alpha=0.8)

    if s is not None:
        xi = s.i - bas
        ax.axvline(xi, color="#f0b90b", linewidth=0.8, linestyle=":", alpha=0.8)
        cizgiler = [("Giriş", s.giris, "#ffffff"), ("Stop", s.stop, KIRMIZI),
                    ("Hedef 1", s.tp1, YESIL), ("Hedef 2", s.tp2, YESIL)]
        if s.geri_cekilme:
            cizgiler.append(("Geri çekilme girişi", s.geri_cekilme, "#90caf9"))
        cizgiler = [cz for cz in cizgiler if ymin - pad <= cz[1] <= ymax + pad]
        cizgiler.sort(key=lambda cz: cz[1])
        bosluk = (ymax - ymin + 2 * pad) * 0.035
        son_y = -1e18
        for ad, y, rk in cizgiler:
            ax.hlines(y, xi, len(d) - 1, color=rk, linewidth=1.3,
                      linestyles="--" if ad != "Giriş" else "-")
            ty = max(y, son_y + bosluk)
            son_y = ty
            ax.text(len(d) - 0.5, ty, f" {ad}: {fmt(y)}", color=rk, fontsize=8, va="center")
        for (ni, nf, et) in s.noktalar:
            if bas <= ni < bit:
                ax.annotate(et, (ni - bas, nf), xytext=(0, 14 if et in ("Kırılan seviye",) else -16),
                            textcoords="offset points", color="#f0b90b", fontsize=8, ha="center",
                            arrowprops=dict(arrowstyle="-", color="#f0b90b", lw=0.6))
        ok = "▲" if s.yon == "long" else "▼"
        ax.annotate(ok, (xi, s.giris), color=YESIL if s.yon == "long" else KIRMIZI,
                    fontsize=16, ha="center", va="center")

    adim = max(1, len(d) // 8)
    ax.set_xticks(x[::adim])
    ax.set_xticklabels([t.tz_convert(TR_SAAT).strftime("%d.%m %H:%M") for t in d["t"].iloc[::adim]])
    ax.set_xlim(-1, len(d) + 12)
    ax.set_title(baslik, color=YAZI, fontsize=12, loc="left")
    ax.yaxis.tick_right()
    fig.tight_layout()
    fig.savefig(dosya, facecolor=ARKA)
    plt.close(fig)
    return dosya


def fmt(p: float) -> str:
    if p >= 1000:
        return f"{p:,.0f}".replace(",", ".")
    if p >= 10:
        return f"{p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{p:.4f}"


def yuzde(a, b):
    return f"{(b - a) / a * 100:+.2f}%"


def gecikme_dk(s: Sinyal) -> int:
    """Yapının oluştuğu mumun kapanışından bu yana geçen dakika."""
    kapanis = pd.Timestamp(s.zaman, tz="UTC") + pd.Timedelta(minutes=TF_DAKIKA[s.tf])
    return int((pd.Timestamp.now(tz="UTC") - kapanis).total_seconds() // 60)


def sinyal_metni(s: Sinyal, ornek=False) -> str:
    emoji = "🟢" if s.yon == "long" else "🔴"
    yon = "LONG adayı" if s.yon == "long" else "SHORT adayı"
    coin = s.sembol.replace("USDT", "/USDT")
    trend_not = ""
    if s.trend:
        ters = (s.trend == "düşüş" and s.yon == "long") or (s.trend == "yükseliş" and s.yon == "short")
        ayni = (s.trend == "yükseliş" and s.yon == "long") or (s.trend == "düşüş" and s.yon == "short")
        ek = " → trend tersi (onay en çok burada işe yarar, hedefe sadık kal)" if ters else \
             " → trend yönünde" if ayni else " → yatay piyasa"
        trend_not = f"Günlük trend: {s.trend}{ek}\n"
    zaman_tr = pd.Timestamp(s.zaman, tz="UTC").tz_convert(TR_SAAT) + pd.Timedelta(minutes=TF_DAKIKA[s.tf])
    satirlar = [
        ("🧪 <b>ÖRNEK (geçmiş sinyal)</b>\n" if ornek else "")
        + f"{emoji} <b>{coin} • {TF_ADI[s.tf]} • {yon}</b>",
        f"Yapı: <b>{YAPI_ADI[s.yapi]}</b>",
        f"<i>{YAPI_ACIKLAMA[(s.yapi, s.yon)]}</i>",
        f"Bölge: {fmt(s.bolge_alt)} – {fmt(s.bolge_ust)} ({s.bolge_etiket})",
        trend_not.rstrip("\n"),
        "",
        f"Giriş: <b>{fmt(s.giris)}</b>" + (f"  |  Geri çekilmede: {fmt(s.geri_cekilme)}" if s.geri_cekilme else ""),
        f"Stop: <b>{fmt(s.stop)}</b> ({yuzde(s.giris, s.stop)})",
        f"Hedef 1: {fmt(s.tp1)} (R {s.rr1})",
        f"Hedef 2: {fmt(s.tp2)} (R {s.rr2})",
        f"Güç: {'★' * s.puan}{'☆' * (5 - s.puan)}",
        f"⏱️ Yapı {zaman_tr.strftime('%H:%M')} mum kapanışında oluştu"
        + ("" if ornek else f" ({gecikme_dk(s)} dk önce)"),
        "",
        "⚠️ Otomatik tespit. Grafiği kendin kontrol et, stopsuz işlem açma. Yatırım tavsiyesi değildir.",
    ]
    return "\n".join(x for x in satirlar if x is not None)


# ----------------------------------------------------------------------------
# TELEGRAM
# ----------------------------------------------------------------------------
class Telegram:
    def __init__(self, token, chat_id):
        self.token, self.chat_id = token, chat_id
        self.base = f"https://api.telegram.org/bot{token}"

    def mesaj(self, metin):
        if not self.token:
            print("[TELEGRAM YOK]\n" + metin + "\n")
            return
        requests.post(f"{self.base}/sendMessage", data=dict(chat_id=self.chat_id, text=metin,
                      parse_mode="HTML", disable_web_page_preview=True), timeout=30).raise_for_status()

    def foto(self, dosya, metin):
        if not self.token:
            print(f"[TELEGRAM YOK] foto: {dosya}\n{metin}\n")
            return
        with open(dosya, "rb") as f:
            r = requests.post(f"{self.base}/sendPhoto", data=dict(chat_id=self.chat_id,
                              caption=metin[:1024], parse_mode="HTML"), files=dict(photo=f), timeout=60)
        if not r.ok:
            print("Foto gönderilemedi, metin gönderiliyor:", r.text)
            self.mesaj(metin)

    def chat_bul(self):
        r = requests.get(f"{self.base}/getUpdates", timeout=30)
        r.raise_for_status()
        for u in reversed(r.json().get("result", [])):
            m = u.get("message") or u.get("channel_post") or {}
            if m.get("chat", {}).get("id"):
                return m["chat"]["id"]
        return None


# ----------------------------------------------------------------------------
# DURUM (aynı sinyali iki kez göndermemek için)
# ----------------------------------------------------------------------------
def durum_oku():
    if DURUM_DOSYASI.exists():
        try:
            return json.loads(DURUM_DOSYASI.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"gonderilen": [], "son_kalp_atisi": ""}


def durum_yaz(d):
    d["gonderilen"] = d["gonderilen"][-500:]
    DURUM_DOSYASI.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


# ----------------------------------------------------------------------------
# ANA AKIŞ
# ----------------------------------------------------------------------------
def sembol_analiz(sembol, veri=None):
    """veri: test için {tf: df} sözlüğü verilebilir."""
    def al(tf, lim):
        return veri[tf] if veri else veri_cek(sembol, tf, lim)
    htf = {tf: al(tf, 500 if tf == "4h" else 400) for tf in ayarlar.BOLGE_ZAMAN_DILIMLERI}
    df_d = htf.get("1d") if "1d" in htf else al("1d", 400)
    ltf = {tf: al(tf, 700) for tf in ayarlar.ONAY_ZAMAN_DILIMLERI}
    fiyat = float(ltf[ayarlar.ONAY_ZAMAN_DILIMLERI[0]]["close"].iloc[-1])
    manuel = manuel_bolgeler(sembol)
    # Manuel (Efloud) bölgelerle çakışan otomatik bölgeler çıkarılır; manuel olanlar öncelikli
    bolgeler = manuel + [b for b in bolgeleri_bul(htf, fiyat)
                         if not any(b.alt <= m.ust and b.ust >= m.alt for m in manuel)]
    # Efloud'a yakın: günlük grafikte tepe/dip yapısından trend (EMA yerine)
    trend = yapisal_trend(df_d.tail(150), 3)
    sinyaller = {}
    for tf, df in ltf.items():
        ss = yapilari_tara(df, tf, sembol, bolgeler)
        for s in ss:
            s.trend = trend
        sinyaller[tf] = ss
    return dict(htf=htf, ltf=ltf, bolgeler=bolgeler, trend=trend, fiyat=fiyat, sinyaller=sinyaller)


def ozet_gonder(tg: Telegram, analizler, gecici: Path, ek=""):
    for sembol, a in analizler.items():
        f = a["fiyat"]
        alt = sorted([b for b in a["bolgeler"] if b.ust < f], key=lambda b: -b.ust)[:2]
        ust = sorted([b for b in a["bolgeler"] if b.alt > f], key=lambda b: b.alt)[:2]
        icinde = [b for b in a["bolgeler"] if b.icinde(f)]
        satir = [f"📊 <b>{sembol.replace('USDT', '/USDT')}</b>  {fmt(f)}",
                 f"Günlük trend (tepe/dip yapısı): {a['trend']}"]
        if icinde:
            satir.append(f"📍 Fiyat şu an bir bölgenin içinde: {fmt(icinde[0].alt)} – {fmt(icinde[0].ust)}"
                         " → onay yapıları burada aranıyor")
        for b in ust[::-1]:
            satir.append(f"🔺 Direnç: {fmt(b.alt)} – {fmt(b.ust)} ({yuzde(f, b.alt)}, güç {b.puan})")
        for b in alt:
            satir.append(f"🔻 Destek: {fmt(b.alt)} – {fmt(b.ust)} ({yuzde(f, b.ust)}, güç {b.puan})")
        df4 = a["htf"].get("4h", next(iter(a["htf"].values())))
        dosya = grafik_ciz(df4, None, a["bolgeler"], f"{sembol} • 4 saatlik • bölgeler",
                           gecici / f"ozet_{sembol}.png", mum_sayisi=180)
        tg.foto(dosya, ek + "\n".join(satir))


# ----------------------------------------------------------------------------
# İZLEME MODU: işlem sinyali yok, sadece "fiyat önemli bölgeye geldi, grafiğe bak"
# ----------------------------------------------------------------------------
def izleme_metni(sembol, b: Bolge, tur: str, fiyat: float, trend: str) -> str:
    coin = sembol.replace("USDT", "/USDT")
    destek = tur == "destek"
    yon = "long" if destek else "short"
    yildiz = ""
    if trend == "yatay / kararsız":
        trend_not = "yatay piyasa → onay şart, hedefi range içinde tut"
    else:
        ters = (trend == "düşüş" and destek) or (trend == "yükseliş" and not destek)
        if ters:
            trend_not = (f"{trend} → buradan {yon} trend TERSİ olur. Backtest'te en zayıf grup; "
                         "çok net onay yoksa pas geç")
        else:
            yildiz = "⭐ "
            trend_not = (f"{trend} → buradan {yon} trend YÖNÜNDE olur. Backtest'te en iyi davranan "
                         "grup buydu (stopu en az %1 geniş tut)")
    if destek:
        bak = ["• <b>Breaker:</b> bölgede dip → tepe → daha düşük dip (likidite alımı), sonra o tepenin üstünde kapanış",
               "• <b>Mitigation:</b> eski dip bozulmadan daha yüksek dip, sonra tepenin üstünde kapanış",
               "• <b>SFP:</b> fitil eski dibin altına sarkıp mum üstünde kapanır + ardından yeşil mum",
               "• <b>Ters senaryo:</b> bölge sert kırmızı mumla aşağı kırılır, geri test edip altında kalırsa → destek kaybı (short fikri)"]
    else:
        bak = ["• <b>Breaker:</b> bölgede tepe → dip → daha yüksek tepe (likidite alımı), sonra o dibin altında kapanış",
               "• <b>Mitigation:</b> eski tepe aşılmadan daha düşük tepe, sonra dibin altında kapanış",
               "• <b>SFP:</b> fitil eski tepenin üstüne çıkıp mum altında kapanır + ardından kırmızı mum",
               "• <b>Ters senaryo:</b> bölge sert yeşil mumla yukarı kırılır, geri test edip üstünde kalırsa → direnç kazanımı (long fikri)"]
    return "\n".join([
        f"{yildiz}📍 <b>{coin} • {tur.upper()} bölgesine geldi</b>",
        f"Bölge: {fmt(b.alt)} – {fmt(b.ust)} ({b.etiket}"
        + ("" if "manuel" in b.kaynak else f", güç {b.puan}") + ")",
        *([f"📝 {b.aciklama}"] if b.aciklama else []),
        f"Fiyat: {fmt(fiyat)}",
        f"Günlük trend (tepe/dip yapısı): {trend_not}",
        "",
        "<b>15dk / 1 saatlikte şunlardan birini ara:</b>",
        *bak,
        "",
        "Onay yoksa işlem yok. Stop, yapının bozulduğu noktanın ötesine.",
        "ℹ️ Bu bir işlem sinyali değil, sadece izleme uyarısıdır.",
    ])


def kirilim_metni(sembol, b: Bolge, olay: str, fiyat: float, trend: str) -> str:
    coin = sembol.replace("USDT", "/USDT")
    if olay == "kayip":
        bas = f"🔻 <b>{coin} • bölge AŞAĞI KIRILDI</b> (15dk kapanış altında)"
        bak = ["• <b>Devam senaryosu (short fikri):</b> fiyat bölgeyi aşağıdan geri test edip yine altında "
               "kapanırsa → destek dirence döndü (kırılım + retest)",
               "• <b>Tuzak senaryosu (long fikri):</b> fiyat kısa sürede bölgenin üstüne geri kapanış yaparsa "
               "→ deviation / SFP olabilir, onay ara",
               "• Arada kalırsa işlem yok, bir sonraki bölgeyi bekle."]
    else:
        bas = f"🔺 <b>{coin} • bölge YUKARI KIRILDI</b> (15dk kapanış üstünde)"
        bak = ["• <b>Devam senaryosu (long fikri):</b> fiyat bölgeyi yukarıdan geri test edip yine üstünde "
               "kapanırsa → direnç desteğe döndü (kırılım + retest)",
               "• <b>Tuzak senaryosu (short fikri):</b> fiyat kısa sürede bölgenin altına geri kapanış yaparsa "
               "→ deviation / SFP olabilir, onay ara",
               "• Arada kalırsa işlem yok, bir sonraki bölgeyi bekle."]
    return "\n".join([
        bas,
        f"Bölge: {fmt(b.alt)} – {fmt(b.ust)} ({b.etiket})",
        *([f"📝 {b.aciklama}"] if b.aciklama else []),
        f"Fiyat: {fmt(fiyat)}",
        f"Günlük trend (tepe/dip yapısı): {trend}",
        "",
        "<b>Şimdi neye bak:</b>",
        *bak,
        "",
        "ℹ️ Bu bir işlem sinyali değil, sadece izleme uyarısıdır.",
    ])


def izleme_tara(tg, analizler, durum, gecici) -> int:
    """Olaylar:
      giris  : fiyat bir bölgeye dışarıdan girdi (otomatik + Efloud bölgeleri)
      icinde : fiyat bir Efloud bölgesinin içinde ve son 24 saatte haber verilmedi
      kayip / kazanim : fiyat bir Efloud bölgesini kapanışla kırdı (destek kaybı / direnç kazanımı)"""
    kayit = durum.setdefault("izleme", [])  # [{"sembol","orta","olay","zaman"}]
    simdi = pd.Timestamp.now(tz="UTC")
    bekleme = pd.Timedelta(hours=ayarlar.IZLEME_TEKRAR_SAAT)
    kayit[:] = [k for k in kayit if simdi - pd.Timestamp(k["zaman"]) < bekleme]

    def var_mi(sembol, orta, olaylar):
        return any(k["sembol"] == sembol and abs(k["orta"] - orta) / orta < 0.01
                   and k.get("olay", "giris") in olaylar for k in kayit)

    gonderilen = 0
    for sembol, a in analizler.items():
        d = a["ltf"]["15m"] if "15m" in a["ltf"] else next(iter(a["ltf"].values()))
        if len(d) < 40:
            continue
        son, onceki = d.iloc[-1], d.iloc[-2]
        kapanis = son["t"] + pd.Timedelta(minutes=15)
        if (simdi - kapanis).total_seconds() > 20 * 60:  # son mum taze değilse geç
            continue
        gecmis = d.iloc[-34:-1]  # son ~8 saat
        df1 = a["ltf"].get("1h", d)
        c = float(son["close"])
        for b in a["bolgeler"]:
            if b.puan < ayarlar.IZLEME_MIN_PUAN:
                continue
            manuel = "manuel" in b.kaynak
            orta = (b.alt + b.ust) / 2
            olay, tur = None, None

            # 1) Kırılım (sadece Efloud bölgeleri)
            if manuel and onceki["close"] >= b.alt and c < b.alt and (gecmis["close"] > b.ust).any():
                olay = "kayip"
            elif manuel and onceki["close"] <= b.ust and c > b.ust and (gecmis["close"] < b.alt).any():
                olay = "kazanim"
            # 2) Bölgeye dışarıdan giriş
            elif (son["low"] <= b.ust and son["high"] >= b.alt) and not \
                    (onceki["low"] <= b.ust and onceki["high"] >= b.alt):
                if onceki["close"] > b.ust:
                    olay, tur = "giris", "destek"
                elif onceki["close"] < b.alt:
                    olay, tur = "giris", "direnç"
            # 3) Zaten içinde (sadece Efloud bölgeleri)
            elif manuel and b.alt <= c <= b.ust:
                olay = "icinde"
                ref = float(d["close"].iloc[-33])
                tur = "destek" if ref >= orta else "direnç"

            if olay is None:
                continue
            if olay in ("giris", "icinde") and var_mi(sembol, orta, ("giris", "icinde")):
                continue
            if olay in ("kayip", "kazanim") and var_mi(sembol, orta, (olay,)):
                continue

            if olay in ("kayip", "kazanim"):
                metin = kirilim_metni(sembol, b, olay, c, a["trend"])
                baslik = f"{sembol} • 1 saat • bölge {'kaybı' if olay == 'kayip' else 'kazanımı'}"
            else:
                metin = izleme_metni(sembol, b, tur, c, a["trend"])
                if olay == "icinde":
                    metin = metin.replace("bölgesine geldi</b>", "bölgesinin İÇİNDE</b>", 1)
                baslik = f"{sembol} • 1 saat • {tur} bölgesi"
            dosya = grafik_ciz(df1, None, a["bolgeler"], baslik,
                               gecici / f"izleme_{sembol}_{olay}_{int(orta)}.png", mum_sayisi=120, vurgu=b)
            tg.foto(dosya, metin)
            kayit.append(dict(sembol=sembol, orta=float(orta), olay=olay, zaman=simdi.isoformat()))
            gonderilen += 1
    return gonderilen


def gunluk_ozet_gerekirse(tg, analizler, durum, gecici):
    bugun = datetime.now(TR_SAAT)
    if ayarlar.GUNLUK_OZET and bugun.hour >= 9 and durum.get("son_ozet") != bugun.strftime("%Y-%m-%d"):
        ozet_gonder(tg, analizler, gecici, ek="☀️ <b>Günlük özet</b>\n")
        durum["son_ozet"] = bugun.strftime("%Y-%m-%d")


def gh_not(seviye, mesaj):
    """GitHub Actions ekranında görünen kısa not (error/warning/notice)."""
    tek = str(mesaj).replace("\n", " | ")[:900]
    print(f"::{seviye}::{tek}", flush=True)


def calistir(mod: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    gecici = KOK / "_grafikler"
    gecici.mkdir(exist_ok=True)

    gh_not("notice", f"mod={mod} token={'var' if token else 'YOK'} chat_id={'var' if chat_id else 'yok'}")
    if token and not chat_id:
        bulunan = Telegram(token, None).chat_bul()
        if not bulunan:
            gh_not("error", "Chat ID bulunamadi. Telegram'da kendi botunu acip Baslat'a (/start) bas, sonra testi tekrar calistir.")
            sys.exit(1)
        chat_id = str(bulunan)
        Telegram(token, chat_id).mesaj(
            "👋 Merhaba! Bot sana ulaşabiliyor.\n\n"
            f"Senin Chat ID'n: <code>{chat_id}</code>\n\n"
            "Bunu GitHub'da <b>TELEGRAM_CHAT_ID</b> adıyla secret olarak ekle "
            "(kurulum rehberindeki 4. adım), sonra testi tekrar çalıştır.")
        print("Chat ID Telegram'a gönderildi:", chat_id)
        return
    tg = Telegram(token, chat_id)
    if mod == "ozet" and not ayarlar.GUNLUK_OZET:
        print("Günlük özet kapalı (ayarlar.py).")
        return

    durum = durum_oku()
    gonderilen_liste = list(durum["gonderilen"])
    gonderilen = set(gonderilen_liste)

    def isaretle(kimlik):
        if kimlik not in gonderilen:
            gonderilen.add(kimlik)
            gonderilen_liste.append(kimlik)
    analizler = {}
    for sembol in ayarlar.SEMBOLLER:
        try:
            analizler[sembol] = sembol_analiz(sembol)
        except Exception as e:  # noqa: BLE001
            gh_not("warning", f"{sembol} analiz edilemedi: {e}")
    if not analizler:
        gh_not("error", "Hicbir borsadan veri alinamadi.")
        sys.exit(1)

    if mod == "test" and ayarlar.CALISMA_MODU == "izleme":
        tg.mesaj("✅ <b>Bot İZLEME moduna geçti.</b>\n\n"
                 "Artık giriş/stop/hedef içeren işlem sinyali gönderilmeyecek "
                 "(backtest'te otomatik sinyaller kârsız çıktı).\n\n"
                 "Bunun yerine fiyat günlük/4 saatlik <b>güçlü bir bölgeye</b> geldiğinde "
                 "haber vereceğim. O zaman grafiği açıp Efloud'un onay yapılarını sen arayacaksın. "
                 "Mesajda neye bakman gerektiği yazacak.\n\nGüncel bölge haritası:")
        ozet_gonder(tg, analizler, gecici)

    elif mod == "test":
        tg.mesaj("✅ <b>Kripto Onay Alarmı kuruldu ve çalışıyor.</b>\n"
                 "15 dakikada bir BTC ve ETH taranacak. Önce güncel bölge haritası, "
                 "ardından sistemin son günlerde yakaladığı birkaç örnek sinyal geliyor.")
        ozet_gonder(tg, analizler, gecici)
        hepsi = [(s, a["ltf"][tf]) for a in analizler.values() for tf, ss in a["sinyaller"].items() for s in ss]
        hepsi.sort(key=lambda x: x[0].zaman, reverse=True)
        for s, df in hepsi[:3]:
            d = grafik_ciz(df, s, analizler[s.sembol]["bolgeler"],
                           f"{s.sembol} • {TF_ADI[s.tf]} • {YAPI_ADI[s.yapi]} ({s.yon.upper()})",
                           gecici / f"ornek_{s.sembol}_{s.i}.png")
            tg.foto(d, sinyal_metni(s, ornek=True))
        if not hepsi:
            tg.mesaj("Son günlerde kriterlere uyan bir yapı oluşmamış; yeni yapı oluşunca haber vereceğim.")
        for s, df in hepsi:
            if s.i >= len(df) - LTF_AYAR[s.tf]["pencere"]:
                isaretle(s.kimlik)

    elif mod == "ozet":
        if durum.get("son_ozet") != datetime.now(TR_SAAT).strftime("%Y-%m-%d"):
            ozet_gonder(tg, analizler, gecici, ek="☀️ <b>Günlük özet</b>\n")
            durum["son_ozet"] = datetime.now(TR_SAAT).strftime("%Y-%m-%d")

    elif ayarlar.CALISMA_MODU == "izleme":  # tara (izleme modu)
        n = izleme_tara(tg, analizler, durum, gecici)
        for sembol, an in analizler.items():  # Actions ekranında kısa durum notu
            f = an["fiyat"]
            alt = max([b for b in an["bolgeler"] if b.ust < f], key=lambda b: b.ust, default=None)
            ust = min([b for b in an["bolgeler"] if b.alt > f], key=lambda b: b.alt, default=None)
            gh_not("notice", f"{sembol} {f:.2f} | trend {an['trend']} | alttaki bölge "
                   f"{(f'{alt.alt:.0f}-{alt.ust:.0f} ({yuzde(f, alt.ust)}, {alt.etiket})') if alt else '-'} | üstteki "
                   f"{(f'{ust.alt:.0f}-{ust.ust:.0f} ({yuzde(f, ust.alt)}, {ust.etiket})') if ust else '-'}")
        print(f"İzleme taraması bitti. Uyarı: {n}")
        gunluk_ozet_gerekirse(tg, analizler, durum, gecici)

    else:  # tara (sinyal modu)
        yeni = 0
        for sembol, a in analizler.items():
            for tf, ss in a["sinyaller"].items():
                df = a["ltf"][tf]
                for s in ss:
                    if s.i < len(df) - LTF_AYAR[tf]["pencere"]:
                        continue  # eski sinyal
                    if s.kimlik in gonderilen:
                        continue
                    isaretle(s.kimlik)
                    gec = gecikme_dk(s)
                    if gec > ayarlar.MAKS_GECIKME_DAKIKA.get(tf, 30):
                        gh_not("notice", f"Geç kalınmış sinyal gönderilmedi ({gec} dk): {s.kimlik}")
                        continue
                    if not hala_gecerli(s, df):
                        continue
                    d = grafik_ciz(df, s, a["bolgeler"],
                                   f"{s.sembol} • {TF_ADI[s.tf]} • {YAPI_ADI[s.yapi]} ({s.yon.upper()})",
                                   gecici / f"sinyal_{s.sembol}_{s.tf}_{s.i}.png")
                    tg.foto(d, sinyal_metni(s))
                    yeni += 1
        print(f"Tarama bitti. Yeni sinyal: {yeni}")
        # Günlük özet: her gün 09:00'dan sonraki ilk taramada bir kez gönderilir
        bugun = datetime.now(TR_SAAT)
        if ayarlar.GUNLUK_OZET and bugun.hour >= 9 and durum.get("son_ozet") != bugun.strftime("%Y-%m-%d"):
            ozet_gonder(tg, analizler, gecici, ek="☀️ <b>Günlük özet</b>\n")
            durum["son_ozet"] = bugun.strftime("%Y-%m-%d")

    simdi = datetime.now(timezone.utc)
    durum["gonderilen"] = gonderilen_liste
    son = durum.get("son_kalp_atisi") or "2000-01-01"
    if (simdi - datetime.fromisoformat(son[:10]).replace(tzinfo=timezone.utc)).days >= 7:
        durum["son_kalp_atisi"] = simdi.strftime("%Y-%m-%d")  # GitHub'ın botu durdurmaması için
    durum_yaz(durum)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--mod", default="tara", choices=["tara", "ozet", "test"])
    try:
        calistir(p.parse_args().mod)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        gh_not("error", f"{type(e).__name__}: {e} :: {traceback.format_exc()[-600:]}")
        raise
