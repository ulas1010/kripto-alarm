"""
Kısa/orta vadeli sistemlerin 200 MA sistemiyle karşılaştırması (son 10 yıl, günlük veri).

Sistemler (hepsi sadece long, sinyal ve çıkışlar günlük KAPANIŞ ile):
  RSI-2 (Connors): kapanış > 200 MA ve RSI(2) < eşik -> kapanışta al; kapanış > 5 günlük ortalama -> sat.
                   Felaket stopu: giriş - k*ATR(14) (opsiyonel).
  Turtle         : kapanış > önceki N günün en yükseği -> al; stop giriş - 2*ATR(20);
                   kapanış < önceki M günün en düşüğü -> sat. (opsiyonel 200 MA filtresi)
  200 MA (bot)   : KIRILIM (%0,5 risk) + RETEST (%1 risk), karma 3R + MA çıkışı.

Maliyet: her yön %0,1 (komisyon + kayma). Aynı varlıkta aynı sistemin açık işlemi varken yenisine girilmez.
Portföy simülasyonu: spot, kaldıraçsız; işlem başı risk = özsermaye * risk / stop mesafesi,
tek pozisyon en fazla özsermayenin %20'si, nakit yetmezse küçültülür.
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "."); sys.path.insert(0, "backtest")
import ma200_backtest as B
import ma200_cikis_testi as C
import ma200_kirilim_testi as K

MALIYET = 0.001
NOMINAL_STOP = 0.10   # stopsuz sistemlerde pozisyon büyüklüğü için varsayılan risk mesafesi
TUM = [s for g in B.VARLIKLAR.values() for s in g]


# ---------------- Göstergeler ----------------
def rsi(close, n=2):
    dlt = close.diff()
    up = dlt.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-dlt.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


def atr(d, n):
    pc = d["Close"].shift(1)
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


# ---------------- İşlem üreticiler ----------------
# İşlem: dict(i, giris, stop, legs=[(oran, k, fiyat)], acik)
def _islem(i, g, st, legs, acik=False, **ek):
    return {"i": i, "giris": g, "stop": st, "legs": legs, "acik": acik, **ek}


def rsi2(d, esik=10, stop_atr=None, filtre=True):
    o, l, c, ma = (d[k].to_numpy() for k in ["Open", "Low", "Close", "ma"])
    r = rsi(d["Close"]).to_numpy()
    s5 = d["Close"].rolling(5).mean().to_numpy()
    a = atr(d, 14).to_numpy()
    n = len(d); out = []; i = 1
    while i < n:
        if not np.isnan(ma[i]) and not np.isnan(r[i]) and r[i] < esik and (c[i] > ma[i] or not filtre):
            g = c[i]
            st = g - stop_atr * a[i] if stop_atr else g * (1 - NOMINAL_STOP)
            for k in range(i + 1, n):
                if stop_atr and l[k] <= st:
                    out.append(_islem(i, g, st, [(1.0, k, min(o[k], st))])); break
                if c[k] > s5[k]:
                    out.append(_islem(i, g, st, [(1.0, k, c[k])])); break
            else:
                out.append(_islem(i, g, st, [(1.0, n - 1, c[n - 1])], acik=True)); k = n
            i = k + 1
            continue
        i += 1
    return out


def turtle(d, giris_n=20, cikis_n=10, filtre=False):
    o, l, c, ma = (d[k].to_numpy() for k in ["Open", "Low", "Close", "ma"])
    hh = d["High"].rolling(giris_n).max().shift(1).to_numpy()
    ll = d["Low"].rolling(cikis_n).min().shift(1).to_numpy()
    N = atr(d, 20).to_numpy()
    n = len(d); out = []; i = giris_n + 1
    while i < n:
        if not np.isnan(hh[i]) and c[i] > hh[i] and (not filtre or (not np.isnan(ma[i]) and c[i] > ma[i])):
            g = c[i]; st = g - 2 * N[i]
            for k in range(i + 1, n):
                if l[k] <= st:
                    out.append(_islem(i, g, st, [(1.0, k, min(o[k], st))])); break
                if c[k] < ll[k]:
                    out.append(_islem(i, g, st, [(1.0, k, c[k])])); break
            else:
                out.append(_islem(i, g, st, [(1.0, n - 1, c[n - 1])], acik=True)); k = n
            i = k + 1
            continue
        i += 1
    return out


def karma_legs(d, i, g, st):
    o, h, l, c, ma = (d[k].to_numpy() for k in ["Open", "High", "Low", "Close", "ma"])
    n = len(d); risk = g - st; hedef = g + 3 * risk; s = st; tp = None
    for k in range(i + 1, n):
        if l[k] <= s:
            px = min(o[k], s)
            return ([(1.0, k, px)] if tp is None else [(0.5, *tp), (0.5, k, px)]), False
        if tp is None and h[k] >= hedef:
            tp = (k, hedef if o[k] < hedef else o[k]); s = g
            continue
        if tp is not None and c[k] < ma[k]:
            return [(0.5, *tp), (0.5, k, c[k])], False
    legs = [(1.0, n - 1, c[n - 1])] if tp is None else [(0.5, *tp), (0.5, n - 1, c[n - 1])]
    return legs, True


def ma200_sistem(d, ret):
    out = []
    for tip, sig, risk in [("KIRILIM", K.kirilimlar(d, False), 0.005), ("RETEST", ret, 0.01)]:
        serbest = -1
        for i, g, st in sig:
            if i <= serbest or g <= st:
                continue
            legs, acik = karma_legs(d, i, g, st)
            serbest = max(k for _, k, _ in legs)
            out.append(_islem(i, g, st, legs, acik, risk=risk))
    return out


# ---------------- İstatistik ----------------
def getiri(t):
    return sum(f * (px / t["giris"] - 1) for f, _, px in t["legs"]) - 2 * MALIYET


def istatistik(kayit, yil):
    x = [t for t in kayit if not t["acik"]]
    if not x:
        return {}
    r = np.array([getiri(t) for t in x]) * 100
    R = np.array([getiri(t) / (1 - t["stop"] / t["giris"]) for t in x])
    gun = np.array([max(k for _, k, _ in t["legs"]) - t["i"] for t in x])
    kaz, kay = r[r > 0].sum(), -r[r <= 0].sum()
    return {"işlem": len(r), "yılda": round(len(r) / yil, 1), "kazanma%": round(100 * (r > 0).mean()),
            "ort %": round(r.mean(), 2), "medyan gün": int(np.median(gun)),
            "ort kazanç %": round(r[r > 0].mean(), 2) if (r > 0).any() else 0,
            "ort kayıp %": round(r[r <= 0].mean(), 2) if (r <= 0).any() else 0,
            "kâr faktörü": round(kaz / kay, 2) if kay else np.inf, "ort R": round(R.mean(), 2),
            "en kötü %": round(r.min(), 1)}


# ---------------- Portföy simülasyonu ----------------
def portfoy(islemler, fiyatlar, bas, risk_vars=0.01, cap=0.20):
    """islemler: [(sym, tarih_giris, t, {k: tarih})]. Spot, kaldıraçsız, günlük piyasa değeri."""
    px = pd.DataFrame(fiyatlar).sort_index().ffill()
    px = px[px.index >= bas]
    gir = {}; cik = {}
    for sym, tg, t, tarih in islemler:
        if tg < bas:
            continue
        gir.setdefault(tg, []).append((sym, t, tarih))
    nakit = 1.0; acik = []; ozs = []; maruz = []; alinan = 0
    for gun in px.index:
        # çıkışlar
        kalan = []
        for p in acik:
            for f, k, fiyat in p["legs"]:
                if p["tarih"][k] == gun and (f, k) not in p["kapali"]:
                    q = p["qty"] * f
                    nakit += q * fiyat * (1 - MALIYET); p["kapali"].add((f, k)); p["kalan"] -= q
            if p["kalan"] > 1e-12:
                kalan.append(p)
        acik = kalan
        deger = {p["sym"]: 0.0 for p in acik}
        for p in acik:
            deger[p["sym"]] += p["kalan"] * px.at[gun, p["sym"]]
        eq = nakit + sum(deger.values())
        # girişler (kapanışta)
        for sym, t, tarih in gir.get(gun, []):
            g = t["giris"]; mesafe = g - t["stop"]
            r = t.get("risk", risk_vars)
            q = min(eq * r / mesafe, eq * cap / g, max(nakit, 0) / (g * (1 + MALIYET)))
            if q <= 0:
                continue
            nakit -= q * g * (1 + MALIYET); alinan += 1
            acik.append({"sym": sym, "qty": q, "kalan": q, "legs": t["legs"], "tarih": tarih, "kapali": set()})
        pdeg = sum(p["kalan"] * px.at[gun, p["sym"]] for p in acik)
        eq = nakit + pdeg
        ozs.append(eq); maruz.append(pdeg / eq)
    e = pd.Series(ozs, index=px.index)
    yil = (e.index[-1] - e.index[0]).days / 365.25
    cagr = e.iloc[-1] ** (1 / yil) - 1
    dd = (e / e.cummax() - 1).min()
    yillik = e.resample("YE").last().pct_change().dropna()
    return {"yıllık getiri %": round(100 * cagr, 1), "max düşüş %": round(100 * dd, 1),
            "getiri/düşüş": round(cagr / -dd, 2) if dd < 0 else np.inf,
            "ort. maruziyet %": round(100 * np.mean(maruz)), "işlem": alinan,
            "kötü yıl %": round(100 * yillik.min(), 1) if len(yillik) else np.nan,
            "kazançlı yıl": f"{(yillik > 0).sum()}/{len(yillik)}"}


VARYANTLAR = {
    "RSI-2 <10, stopsuz": lambda d, ret: rsi2(d, 10, None),
    "RSI-2 <10, 3ATR stop": lambda d, ret: rsi2(d, 10, 3),
    "RSI-2 <5, 3ATR stop": lambda d, ret: rsi2(d, 5, 3),
    "RSI-2 <10, 3ATR, 200MA filtresiz": lambda d, ret: rsi2(d, 10, 3, filtre=False),
    "Turtle 20/10": lambda d, ret: turtle(d, 20, 10),
    "Turtle 20/10 + 200MA": lambda d, ret: turtle(d, 20, 10, filtre=True),
    "Turtle 55/20 + 200MA": lambda d, ret: turtle(d, 55, 20, filtre=True),
    "200 MA (bot)": lambda d, ret: ma200_sistem(d, ret),
}


def main():
    bas = pd.Timestamp.today().normalize() - pd.DateOffset(years=B.YIL)
    yari = bas + (pd.Timestamp.today() - bas) / 2
    sonuc = {ad: {"13": [], "50": [], "ilk": [], "son": []} for ad in VARYANTLAR}
    port = {ad: [] for ad in VARYANTLAR}
    fiyat13 = {}
    for sym in TUM:
        df = B.veri(sym)
        if df is None or len(df) < 300:
            continue
        d, ret = B.sinyaller(df)
        if sym in C.SECILMIS:
            fiyat13[sym] = d["Close"]
        tarih = dict(enumerate(d.index))
        for ad, f in VARYANTLAR.items():
            for t in f(d, ret):
                if d.index[t["i"]] < bas:
                    continue
                sonuc[ad]["50"].append(t)
                if sym in C.SECILMIS:
                    sonuc[ad]["13"].append(t)
                    sonuc[ad]["ilk" if d.index[t["i"]] < yari else "son"].append(t)
                    port[ad].append((sym, d.index[t["i"]], t, tarih))
        print("tamam:", sym)

    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 20)
    yil = B.YIL
    print("\n=== İŞLEM BAZINDA (13 varlık, maliyet dahil) ===")
    print(pd.DataFrame({ad: istatistik(v["13"], yil) for ad, v in sonuc.items()}).T.to_string())
    print("\n=== İŞLEM BAZINDA (50 varlık - sağlamlık kontrolü) ===")
    print(pd.DataFrame({ad: istatistik(v["50"], yil) for ad, v in sonuc.items()}).T.to_string())
    print("\n=== DÖNEM KARŞILAŞTIRMASI (13 varlık, işlem başı ort %) ===")
    for ad, v in sonuc.items():
        a, b = istatistik(v["ilk"], yil / 2), istatistik(v["son"], yil / 2)
        print(f"{ad:35s} ilk 5 yıl: {a.get('ort %', 0):+.2f}% ({a.get('işlem', 0)} işlem) | "
              f"son 5 yıl: {b.get('ort %', 0):+.2f}% ({b.get('işlem', 0)} işlem)")

    print("\n=== PORTFÖY (13 varlık, spot, işlem başı risk %1; 200 MA bottaki gibi %0,5/%1) ===")
    tablo = {ad: portfoy(port[ad], fiyat13, bas) for ad in VARYANTLAR}
    print(pd.DataFrame(tablo).T.to_string())
    print("\n=== KOMBİNASYONLAR (aynı kasa, sistemler birlikte) ===")
    for a, b in [("200 MA (bot)", "RSI-2 <10, 3ATR stop"), ("200 MA (bot)", "Turtle 20/10 + 200MA"),
                 ("200 MA (bot)", "RSI-2 <10, stopsuz")]:
        print(f"{a} + {b}:", portfoy(port[a] + port[b], fiyat13, bas))


if __name__ == "__main__":
    main()
