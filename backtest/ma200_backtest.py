"""
200 MA Retest stratejisinin backtest'i (ma200.py ile birebir aynı sinyal kuralı).

Sinyal: 200 MA yukarı kırılır -> fiyat MA'dan en az %5 uzaklaşır -> 120 gün içinde
MA'ya geri gelir (%2 tolerans), MA yatay/yükselen, yeşil mumla MA üstünde kapatır.
Giriş: sinyal mumunun kapanışı. Stop: min(mum dibi, MA) * 0.99.
Çıkış varyantları: sabit 2R / 3R / 5R hedef, ya da "MA altında kapanınca çık" (trend takibi).
Aynı gün hem stop hem hedef görülürse STOP sayılır (kötümser). Komisyon yok.
"""
import sys
import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, ".")
import ma200 as M  # aynı ayarlar

YIL = 10
VARLIKLAR = {
    "Kripto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "DOGE-USD", "LINK-USD",
               "AVAX-USD", "LTC-USD", "BCH-USD", "NEAR-USD", "AAVE-USD", "XMR-USD", "ZEC-USD",
               "XLM-USD", "UNI7083-USD", "SUI20947-USD", "TAO22974-USD", "HYPE32196-USD"],
    "Hisse/ETF": ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "META", "AMZN", "MSFT", "GOOGL", "AMD",
                  "INTC", "AVGO", "TSM", "MU", "QCOM", "PLTR", "COIN", "MSTR", "HOOD", "ARM",
                  "MRVL", "RKLB", "ASTS"],
    "Emtia": ["GC=F", "SI=F", "CL=F", "BZ=F", "NG=F", "HG=F"],
    "Forex": ["JPY=X", "EURUSD=X"],
}
TXFLOW_AD = {"GC=F": "XAU", "SI=F": "XAG", "CL=F": "CL", "BZ=F": "BRENT", "NG=F": "NATGAS",
             "HG=F": "XCU", "JPY=X": "USDJPY", "EURUSD=X": "EUR"}


def veri(sym):
    df = yf.download(sym, period=f"{YIL + 1}y", interval="1d", auto_adjust=False, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close"]].dropna()


def sinyaller(df):
    d = df.copy()
    d["ma"] = d["Close"].rolling(M.MA_LEN).mean()
    d["ma_up"] = d["ma"] >= d["ma"].shift(M.SLOPE_LEN) * 0.995
    o, h, l, c, ma, up = (d[k].to_numpy() for k in ["Open", "High", "Low", "Close", "ma", "ma_up"])
    out = []
    j = None; run = False; done = False
    for i in range(1, len(d)):
        if np.isnan(ma[i]) or np.isnan(ma[i - 1]):
            continue
        above, prev_above = c[i] > ma[i], c[i - 1] > ma[i - 1]
        if above and not prev_above:          # yukarı kırılım
            j, done = i, False
            run = c[i] >= ma[i] * (1 + M.MIN_RUN_PCT / 100)
            continue
        if not above:
            j = None
            continue
        if j is None:
            continue
        retest_bar = up[i] and l[i] <= ma[i] * (1 + M.TOL_PCT / 100) and c[i] > o[i]
        if retest_bar and run and not done:
            done = True
            if i - j <= M.RETEST_WINDOW:
                stop = min(l[i], ma[i]) * (1 - M.STOP_BUF_PCT / 100)
                out.append((i, c[i], stop))
        if c[i] >= ma[i] * (1 + M.MIN_RUN_PCT / 100):
            run = True
    return d, out


def islem(d, i, giris, stop, rr):
    """Sabit R hedefli ya da rr=None ise 'MA altında kapanınca çık' sonucu (R cinsinden)."""
    risk = giris - stop
    if risk <= 0:
        return None
    o, h, l, c, ma = (d[k].to_numpy() for k in ["Open", "High", "Low", "Close", "ma"])
    hedef = giris + rr * risk if rr else None
    for k in range(i + 1, len(d)):
        if l[k] <= stop:
            cikis = min(o[k], stop)            # boşlukla açılırsa daha kötü fiyat
            return (cikis - giris) / risk
        if hedef and h[k] >= hedef:
            return rr if o[k] < hedef else (o[k] - giris) / risk
        if rr is None and c[k] < ma[k]:
            return (c[k] - giris) / risk
    return np.nan  # hâlâ açık


def main():
    bas = pd.Timestamp.today() - pd.DateOffset(years=YIL)
    rows = []
    for grup, liste in VARLIKLAR.items():
        for sym in liste:
            try:
                df = veri(sym)
                if df is None or len(df) < 300:
                    print("veri yok:", sym); continue
                d, sig = sinyaller(df)
                sig = [s for s in sig if d.index[s[0]] >= bas]
                r = {"grup": grup, "varlik": TXFLOW_AD.get(sym, sym.split("-")[0]),
                     "yil": round((d.index[-1] - max(d.index[0], bas)).days / 365, 1), "islem": len(sig)}
                for ad, rr in [("2R", 2), ("3R", 3), ("5R", 5), ("trend", None)]:
                    res = [islem(d, *s, rr) for s in sig]
                    res = [x for x in res if x is not None and not np.isnan(x)]
                    r[f"{ad}_kazan%"] = round(100 * np.mean([x > 0 for x in res]), 0) if res else np.nan
                    r[f"{ad}_ortR"] = round(np.mean(res), 2) if res else np.nan
                    r[f"{ad}_topR"] = round(np.sum(res), 1) if res else 0.0
                r["son_sinyal"] = str(d.index[sig[-1][0]].date()) if sig else ""
                rows.append(r)
                print(sym, len(sig), "işlem")
            except Exception as e:
                print("hata:", sym, e)
    t = pd.DataFrame(rows)
    t.to_csv("backtest/ma200_sonuc.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print("\n=== SONUÇ ===")
    print(t.sort_values("3R_topR", ascending=False).to_string(index=False))
    tum = t[t.islem > 0]
    print("\nToplam işlem:", int(tum.islem.sum()))
    for ad in ["2R", "3R", "5R", "trend"]:
        w = (tum[f"{ad}_ortR"] * tum.islem).sum() / tum.islem.sum()
        print(f"{ad}: işlem başı ort. {w:.2f}R, toplam {tum[f'{ad}_topR'].sum():.1f}R")
    for g in t.grup.unique():
        x = tum[tum.grup == g]
        if len(x):
            print(g, "| işlem", int(x.islem.sum()), "| 3R toplam", round(x["3R_topR"].sum(), 1),
                  "| trend toplam", round(x["trend_topR"].sum(), 1))


if __name__ == "__main__":
    main()
