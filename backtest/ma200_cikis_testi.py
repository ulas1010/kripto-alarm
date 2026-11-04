"""
200 MA Retest: hangi ÇIKIŞ yöntemi en kazançlı? (seçilmiş liste + tüm liste)
Varyantlar: sabit 2R/3R/5R, trend (MA altı kapanışta çık),
karma H2/H3 (yarısı 2R/3R'de kâr al, stop girişe çekilir, kalan yarı MA altı kapanışa kadar tutulur).
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "."); sys.path.insert(0, "backtest")
import ma200_backtest as B

SECILMIS = ["NVDA", "GOOGL", "META", "AMD", "AVGO", "MRVL", "MU", "MSTR", "ARM",
            "GC=F", "SI=F", "SPY", "ETH-USD"]


def sim(d, i, giris, stop, mod, rr=None):
    risk = giris - stop
    if risk <= 0:
        return None
    o, h, l, c, ma = (d[k].to_numpy() for k in ["Open", "High", "Low", "Close", "ma"])
    if mod == "sabit":
        hedef = giris + rr * risk
        for k in range(i + 1, len(d)):
            if l[k] <= stop:
                return (min(o[k], stop) - giris) / risk
            if h[k] >= hedef:
                return rr if o[k] < hedef else (o[k] - giris) / risk
        return np.nan
    if mod == "trend":
        for k in range(i + 1, len(d)):
            if l[k] <= stop:
                return (min(o[k], stop) - giris) / risk
            if c[k] < ma[k]:
                return (c[k] - giris) / risk
        return np.nan
    # karma: yarısı rr'de, sonra stop girişe, kalan MA altı kapanışta
    hedef = giris + rr * risk
    yarim = None; st = stop
    for k in range(i + 1, len(d)):
        if l[k] <= st:
            r = (min(o[k], st) - giris) / risk
            return r if yarim is None else 0.5 * yarim + 0.5 * r
        if yarim is None and h[k] >= hedef:
            yarim = rr if o[k] < hedef else (o[k] - giris) / risk
            st = giris
            continue
        if yarim is not None and c[k] < ma[k]:
            return 0.5 * yarim + 0.5 * (c[k] - giris) / risk
    return np.nan


VARYANT = {"2R": ("sabit", 2), "3R": ("sabit", 3), "5R": ("sabit", 5),
           "Karma 2R+trend": ("karma", 2), "Karma 3R+trend": ("karma", 3), "Trend": ("trend", None)}


def metrik(tr):
    tr = tr.dropna().sort_values("tarih")
    r = tr["R"].to_numpy()
    if not len(r):
        return {}
    eq = np.cumsum(r); dd = (eq - np.maximum.accumulate(np.r_[0, eq])[1:]).min()
    seri = m = 0
    for x in r:
        seri = seri + 1 if x <= 0 else 0; m = max(m, seri)
    top3 = np.sort(r)[-3:].sum()
    return {"işlem": len(r), "kazanma%": round(100 * (r > 0).mean()), "ort R": round(r.mean(), 2),
            "medyan R": round(np.median(r), 2), "toplam R": round(r.sum(), 1),
            "en iyi 3 hariç": round(r.sum() - top3, 1), "max DD (R)": round(dd, 1),
            "max ardışık kayıp": m}


def main():
    bas = pd.Timestamp.today() - pd.DateOffset(years=B.YIL)
    tum = [s for g in B.VARLIKLAR.values() for s in g]
    kayit = []
    for sym in tum:
        df = B.veri(sym)
        if df is None or len(df) < 300:
            continue
        d, sig = B.sinyaller(df)
        for i, g, st in sig:
            if d.index[i] < bas:
                continue
            row = {"varlik": sym, "tarih": d.index[i], "risk%": 100 * (g - st) / g}
            for ad, (mod, rr) in VARYANT.items():
                row[ad] = sim(d, i, g, st, mod, rr)
            kayit.append(row)
    k = pd.DataFrame(kayit)
    k.to_csv("backtest/ma200_islemler.csv", index=False)
    pd.set_option("display.width", 250)
    yari = bas + (pd.Timestamp.today() - bas) / 2
    for baslik, x in [("SEÇİLMİŞ LİSTE", k[k.varlik.isin(SECILMIS)]),
                      ("SEÇİLMİŞ - ilk 5 yıl", k[k.varlik.isin(SECILMIS) & (k.tarih < yari)]),
                      ("SEÇİLMİŞ - son 5 yıl", k[k.varlik.isin(SECILMIS) & (k.tarih >= yari)]),
                      ("TÜM 50 VARLIK", k)]:
        print(f"\n=== {baslik} ===")
        t = pd.DataFrame({ad: metrik(x[["tarih"]].assign(R=x[ad])) for ad in VARYANT}).T
        print(t.to_string())
    s = k[k.varlik.isin(SECILMIS)]
    print("\nSeçilmiş listede stop mesafesi (%): medyan", round(s["risk%"].median(), 1),
          "| %25-%75:", round(s["risk%"].quantile(.25), 1), "-", round(s["risk%"].quantile(.75), 1))
    print("Yılda ortalama sinyal (seçilmiş):", round(len(s) / B.YIL, 1))


if __name__ == "__main__":
    main()
