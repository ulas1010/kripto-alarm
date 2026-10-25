"""
Geliştirme analizi: ayar kombinasyonlarını GELİŞTİRME döneminde sıralar,
en iyilerini hiç dokunulmamış DOĞRULAMA döneminde test eder.

Kurallar (sonuçları görmeden sabitlendi):
  * Bir varyantın değerlendirilmesi için geliştirme döneminde en az 60 işlem gerekir.
  * Sıralama ölçütü: geliştirme dönemindeki işlem başına ortalama R (komisyon dahil).
  * Doğrulamada "başarılı" sayılması için: ortalama R > 0 VE en az 40 işlem.
  * Ayrıca önceden tanımlanmış tek bir "Efloud'a en yakın" varyant ayrıca raporlanır.
"""
from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

KLASOR = Path(__file__).resolve().parent / "backtest"

BOYUTLAR = {
    "tf": ["hepsi", "1h"],
    "bolge": ["hepsi", "günlük", "güç4+"],
    "min_stop": [0.0, 0.5, 1.0],
    "trend": ["yok", "EMA yönünde", "yapı(G) yönünde", "yapı(4s) yönünde", "yapı(G) tersi"],
    "yapi": ["hepsi", "breaker+mitigation"],
    "giris": ["piyasa", "limit"],
}
EFLOUD_BENZERI = dict(tf="hepsi", bolge="günlük", min_stop=0.5, trend="yok", yapi="hepsi", giris="limit")


def yon_uyumu(trend, yon):
    if trend == "yükseliş":
        return "yönünde" if yon == "long" else "tersi"
    if trend == "düşüş":
        return "yönünde" if yon == "short" else "tersi"
    return "yatay"


def filtrele(d: pd.DataFrame, v: dict) -> pd.Series:
    m = pd.Series(True, index=d.index)
    if v["tf"] == "1h":
        m &= d["tf"] == "1h"
    if v["bolge"] == "günlük":
        m &= d["bolge_gunluk"].astype(bool)
    elif v["bolge"] == "güç4+":
        m &= d["bolge_puan"] >= 4
    m &= d["stop_yuzde"] >= v["min_stop"]
    t = v["trend"]
    if t == "EMA yönünde":
        m &= d["uyum_ema"] == "yönünde"
    elif t == "yapı(G) yönünde":
        m &= d["uyum_g"] == "yönünde"
    elif t == "yapı(4s) yönünde":
        m &= d["uyum_4s"] == "yönünde"
    elif t == "yapı(G) tersi":
        m &= d["uyum_g"] == "tersi"
    if v["yapi"] == "breaker+mitigation":
        m &= d["yapi"].isin(["breaker", "mitigation"])
    return m


def olc(d: pd.DataFrame, m: pd.Series, giris: str) -> dict:
    x = d[m]
    if giris == "limit":
        x = x[x["lim_durum"].isin(["stop", "hedef1", "süre doldu"])]
        r, durum = x["lim_r_tp1"], x["lim_durum"]
    else:
        x = x[x["durum"].isin(["stop", "hedef1", "süre doldu"])]
        r, durum = x["r_tp1"], x["durum"]
    if len(x) == 0:
        return dict(islem=0, isabet=np.nan, ort_R=np.nan, top_R=0.0, gunluk_islem=0.0)
    gun = (pd.to_datetime(d["gonderim"]).max() - pd.to_datetime(d["gonderim"]).min()).days or 1
    return dict(islem=len(x), isabet=round(100 * (durum == "hedef1").mean(), 1),
                ort_R=round(r.mean(), 3), top_R=round(r.sum(), 1), gunluk_islem=round(len(x) / gun, 2))


def hazirla(yol):
    d = pd.read_csv(yol)
    d["uyum_ema"] = [yon_uyumu(t, y) for t, y in zip(d["trend"], d["yon"])]
    d["uyum_g"] = [yon_uyumu(t, y) for t, y in zip(d["trend_yapi_g"], d["yon"])]
    d["uyum_4s"] = [yon_uyumu(t, y) for t, y in zip(d["trend_yapi_4s"], d["yon"])]
    return d


def main():
    dev = hazirla(KLASOR / "ham_gelistirme.csv")
    val = hazirla(KLASOR / "ham_dogrulama.csv")
    satirlar = []
    for kombin in itertools.product(*BOYUTLAR.values()):
        v = dict(zip(BOYUTLAR.keys(), kombin))
        a = olc(dev, filtrele(dev, v), v["giris"])
        satirlar.append({**v, **{f"G_{k}": x for k, x in a.items()}})
    tablo = pd.DataFrame(satirlar)
    uygun = tablo[tablo["G_islem"] >= 60].sort_values("G_ort_R", ascending=False)

    print(f"Toplam denenen varyant: {len(tablo)}, en az 60 işlemi olan: {len(uygun)}")
    print(f"Geliştirme döneminde pozitif ortalama R'ye sahip varyant: {(uygun['G_ort_R'] > 0).sum()}\n")

    ilk = uygun.head(10).copy()
    for i, row in ilk.iterrows():
        v = {k: row[k] for k in BOYUTLAR}
        b = olc(val, filtrele(val, v), v["giris"])
        for k, x in b.items():
            ilk.loc[i, f"D_{k}"] = x
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print("GELİŞTİRME dönemindeki en iyi 10 varyant ve DOĞRULAMA sonuçları:")
    print(ilk.to_string(index=False))

    print("\nÖnceden tanımlanmış 'Efloud'a en yakın' varyant:", EFLOUD_BENZERI)
    for ad, d in (("Geliştirme", dev), ("Doğrulama", val)):
        print(f"  {ad}: {olc(d, filtrele(d, EFLOUD_BENZERI), EFLOUD_BENZERI['giris'])}")

    print("\nTemel (filtre yok, piyasa girişi):")
    temel = dict(tf="hepsi", bolge="hepsi", min_stop=0.0, trend="yok", yapi="hepsi", giris="piyasa")
    for ad, d in (("Geliştirme", dev), ("Doğrulama", val)):
        print(f"  {ad}: {olc(d, filtrele(d, temel), 'piyasa')}")

    print("\nTek tek etkiler (diğer her şey temel, iki dönem):")
    for boyut, degerler in BOYUTLAR.items():
        for deg in degerler:
            v = dict(temel, **{boyut: deg})
            g = olc(dev, filtrele(dev, v), v["giris"])
            dd = olc(val, filtrele(val, v), v["giris"])
            print(f"  {boyut:9s} = {str(deg):18s} | G: {g['islem']:5d} işlem, ort {g['ort_R']:+.3f}R "
                  f"| D: {dd['islem']:5d} işlem, ort {dd['ort_R']:+.3f}R")
    tablo.to_csv(KLASOR / "varyantlar.csv", index=False)


if __name__ == "__main__":
    main()
