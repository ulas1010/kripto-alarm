"""
Gerçekçi uygulama testi: bot sabah çalıştığı için sinyal kapanışında değil, ERTESİ GÜN AÇILIŞINDA
girilir; çıkış sinyali de (MA/5 günlük ortalama vb.) ertesi açılışta uygulanır. Stoplar gün içinde.
13 varlık, son 10 yıl, %0,1 maliyet/yön.
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "."); sys.path.insert(0, "backtest")
import ma200_backtest as B
import ma200_cikis_testi as C
import ma200_kirilim_testi as K
import kisa_vade_testi as V


def rsi2_acilis(d, esik=5, stop_atr=3):
    o, l, c, ma = (d[k].to_numpy() for k in ["Open", "Low", "Close", "ma"])
    r = V.rsi(d["Close"]).to_numpy(); s5 = d["Close"].rolling(5).mean().to_numpy()
    a = V.atr(d, 14).to_numpy(); n = len(d); out = []; i = 1
    while i < n - 1:
        if not np.isnan(ma[i]) and not np.isnan(r[i]) and r[i] < esik and c[i] > ma[i]:
            g = o[i + 1]; st = g - stop_atr * a[i]
            k = i + 1; kayit = None
            while k < n:
                if l[k] <= st:
                    kayit = V._islem(i, g, st, [(1.0, k, min(o[k], st))]); break
                if c[k] > s5[k]:
                    if k + 1 < n:
                        kayit = V._islem(i, g, st, [(1.0, k + 1, o[k + 1])])
                    else:
                        kayit = V._islem(i, g, st, [(1.0, k, c[k])], acik=True)
                    k += 1; break
                k += 1
            else:
                kayit = V._islem(i, g, st, [(1.0, n - 1, c[n - 1])], acik=True)
            out.append(kayit); i = k + 1
            continue
        i += 1
    return out


def turtle_acilis(d, giris_n=20, cikis_n=10, filtre=True):
    o, l, c, ma = (d[k].to_numpy() for k in ["Open", "Low", "Close", "ma"])
    hh = d["High"].rolling(giris_n).max().shift(1).to_numpy()
    ll = d["Low"].rolling(cikis_n).min().shift(1).to_numpy()
    N = V.atr(d, 20).to_numpy(); n = len(d); out = []; i = giris_n + 1
    while i < n - 1:
        if not np.isnan(hh[i]) and c[i] > hh[i] and (not filtre or (not np.isnan(ma[i]) and c[i] > ma[i])):
            g = o[i + 1]; st = g - 2 * N[i]; k = i + 1
            while k < n:
                if l[k] <= st:
                    out.append(V._islem(i, g, st, [(1.0, k, min(o[k], st))])); break
                if c[k] < ll[k]:
                    if k + 1 < n:
                        out.append(V._islem(i, g, st, [(1.0, k + 1, o[k + 1])]))
                    else:
                        out.append(V._islem(i, g, st, [(1.0, k, c[k])], acik=True))
                    k += 1; break
                k += 1
            else:
                out.append(V._islem(i, g, st, [(1.0, n - 1, c[n - 1])], acik=True))
            i = k + 1
            continue
        i += 1
    return out


def ma200_acilis(d, ret):
    o, h, l, c, ma = (d[k].to_numpy() for k in ["Open", "High", "Low", "Close", "ma"])
    n = len(d); out = []
    for sig, risk in [(K.kirilimlar(d, False), 0.005), (ret, 0.01)]:
        serbest = -1
        for i, _, st in sig:
            if i <= serbest or i + 1 >= n:
                continue
            g = o[i + 1]
            if g <= st:
                continue
            hedef = g + 3 * (g - st); s = st; tp = None; legs = None; k = i + 1
            while k < n:
                if l[k] <= s:
                    px = min(o[k], s)
                    legs = [(1.0, k, px)] if tp is None else [(0.5, *tp), (0.5, k, px)]; break
                if tp is None and h[k] >= hedef:
                    tp = (k, hedef if o[k] < hedef else o[k]); s = g; k += 1; continue
                if tp is not None and c[k] < ma[k]:
                    legs = [(0.5, *tp), (0.5, k + 1, o[k + 1])] if k + 1 < n else None
                    break
                k += 1
            if legs is None:
                legs = [(1.0, n - 1, c[n - 1])] if tp is None else [(0.5, *tp), (0.5, n - 1, c[n - 1])]
                out.append(V._islem(i, g, st, legs, True, risk=risk)); serbest = n
                continue
            serbest = max(kk for _, kk, _ in legs)
            out.append(V._islem(i, g, st, legs, False, risk=risk))
    return out


SISTEM = {
    "RSI-2 <5, 3ATR (kapanış)": lambda d, r: V.rsi2(d, 5, 3),
    "RSI-2 <5, 3ATR (ertesi açılış)": lambda d, r: rsi2_acilis(d, 5, 3),
    "RSI-2 <10, 3ATR (ertesi açılış)": lambda d, r: rsi2_acilis(d, 10, 3),
    "Turtle 20/10+200MA (kapanış)": lambda d, r: V.turtle(d, 20, 10, True),
    "Turtle 20/10+200MA (ertesi açılış)": lambda d, r: turtle_acilis(d, 20, 10, True),
    "200 MA bot (kapanış)": lambda d, r: V.ma200_sistem(d, r),
    "200 MA bot (ertesi açılış)": lambda d, r: ma200_acilis(d, r),
}


def main():
    bas = pd.Timestamp.today().normalize() - pd.DateOffset(years=B.YIL)
    yari = bas + (pd.Timestamp.today() - bas) / 2
    s13 = {k: [] for k in SISTEM}; ilk = {k: [] for k in SISTEM}; son = {k: [] for k in SISTEM}
    port = {k: [] for k in SISTEM}; fiyat = {}
    for sym in C.SECILMIS:
        df = B.veri(sym)
        if df is None:
            continue
        d, ret = B.sinyaller(df); fiyat[sym] = d["Close"]; tarih = dict(enumerate(d.index))
        for ad, f in SISTEM.items():
            for t in f(d, ret):
                if d.index[t["i"]] < bas:
                    continue
                s13[ad].append(t); (ilk if d.index[t["i"]] < yari else son)[ad].append(t)
                # portföyde giriş günü = açılış girişinde i+1
                gi = t["i"] + (1 if "açılış" in ad else 0)
                port[ad].append((sym, d.index[gi], t, tarih))
    pd.set_option("display.width", 250)
    print("=== İŞLEM BAZINDA ===")
    print(pd.DataFrame({k: V.istatistik(v, B.YIL) for k, v in s13.items()}).T.to_string())
    print("\n=== DÖNEMLER (işlem başı ort %) ===")
    for k in SISTEM:
        a, b = V.istatistik(ilk[k], 5), V.istatistik(son[k], 5)
        print(f"{k:38s} ilk 5 yıl {a.get('ort %', 0):+.2f}% | son 5 yıl {b.get('ort %', 0):+.2f}%")
    print("\n=== PORTFÖY (spot, işlem başı risk %1; 200 MA %0,5/%1) ===")
    print(pd.DataFrame({k: V.portfoy(v, fiyat, bas) for k, v in port.items()}).T.to_string())
    for risk, cap in [(0.02, 0.25), (0.03, 0.33)]:
        print(f"RSI-2 <5 açılış, risk %{risk * 100:g}, tek pozisyon max %{cap * 100:g}:",
              V.portfoy(port["RSI-2 <5, 3ATR (ertesi açılış)"], fiyat, bas, risk, cap))
    print("200 MA bot açılış + RSI-2 <5 açılış (aynı kasa):",
          V.portfoy(port["200 MA bot (ertesi açılış)"] + port["RSI-2 <5, 3ATR (ertesi açılış)"], fiyat, bas))


if __name__ == "__main__":
    main()
