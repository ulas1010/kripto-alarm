"""
Kırılımda direkt giriş vs. Retest girişi (aynı 13 varlık, aynı çıkış kuralları, son 10 yıl).
Kırılım girişi: günlük kapanış 200 MA'nın üstüne çıktığı gün, kapanıştan giriş.
  Stop: min(mum dibi, MA) * 0.99 (retest ile aynı mantık).
  K-filtreli: ayrıca MA yatay/yükselen olmalı (retest'teki trend onayı).
Her iki yöntemde de aynı varlıkta açık işlem varken yeni işleme girilmez (gerçekçi).
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "."); sys.path.insert(0, "backtest")
import ma200 as M
import ma200_backtest as B
import ma200_cikis_testi as C


def kirilimlar(d, filtreli):
    o, l, c, ma, up = (d[k].to_numpy() for k in ["Open", "Low", "Close", "ma", "ma_up"])
    out = []
    for i in range(1, len(d)):
        if np.isnan(ma[i]) or np.isnan(ma[i - 1]):
            continue
        if c[i] > ma[i] and c[i - 1] <= ma[i - 1] and (up[i] or not filtreli):
            out.append((i, c[i], min(l[i], ma[i]) * (1 - M.STOP_BUF_PCT / 100)))
    return out


def bitis_gunu(d, i, giris, stop):
    """Karma 3R+trend çıkışının kapandığı bar (çakışmayı önlemek için)."""
    o, h, l, c, ma = (d[k].to_numpy() for k in ["Open", "High", "Low", "Close", "ma"])
    risk = giris - stop; hedef = giris + 3 * risk; st = stop; tp = False
    for k in range(i + 1, len(d)):
        if l[k] <= st:
            return k
        if not tp and h[k] >= hedef:
            tp, st = True, giris; continue
        if tp and c[k] < ma[k]:
            return k
    return len(d)


def main():
    bas = pd.Timestamp.today() - pd.DateOffset(years=B.YIL)
    kayit = []
    for sym in C.SECILMIS:
        df = B.veri(sym)
        if df is None or len(df) < 300:
            continue
        d, ret = B.sinyaller(df)
        for yontem, sig in [("Retest (mevcut)", ret),
                            ("Kırılım filtreli", kirilimlar(d, True)),
                            ("Kırılım ham", kirilimlar(d, False))]:
            serbest = -1
            for i, g, st in sig:
                if d.index[i] < bas or i <= serbest or g <= st:
                    continue
                serbest = bitis_gunu(d, i, g, st)
                row = {"yontem": yontem, "varlik": sym, "tarih": d.index[i], "risk%": 100 * (g - st) / g}
                for ad, (mod, rr) in C.VARYANT.items():
                    row[ad] = C.sim(d, i, g, st, mod, rr)
                kayit.append(row)
    k = pd.DataFrame(kayit)
    k.to_csv("backtest/ma200_kirilim_islemler.csv", index=False)
    pd.set_option("display.width", 250)
    yari = bas + (pd.Timestamp.today() - bas) / 2
    for y in k.yontem.unique():
        x = k[k.yontem == y]
        print(f"\n=== {y} | stop medyan %{x['risk%'].median():.1f} | yılda {len(x) / B.YIL:.1f} işlem ===")
        t = pd.DataFrame({ad: C.metrik(x[["tarih"]].assign(R=x[ad])) for ad in C.VARYANT}).T
        t["yıllık % (risk %1)"] = (t["toplam R"] / B.YIL).round(1)
        print(t.to_string())
        for bas_, son_, ad_ in [(bas, yari, "ilk 5 yıl"), (yari, pd.Timestamp.today(), "son 5 yıl")]:
            z = x[(x.tarih >= bas_) & (x.tarih < son_)]["Karma 3R+trend"].dropna()
            print(f"   Karma 3R+trend {ad_}: {len(z)} işlem, ort {z.mean():+.2f}R, toplam {z.sum():+.1f}R")


if __name__ == "__main__":
    main()
