"""Turtle 20/10 + 200 MA (ertesi açılış) kriptoda nasıl? Coin bazında + portföy, son 10 yıl (veri ne kadar varsa)."""
import sys
import pandas as pd
sys.path.insert(0, "."); sys.path.insert(0, "backtest")
import ma200_backtest as B
import ertesi_acilis_testi as E
import kisa_vade_testi as V

KRIPTO = B.VARLIKLAR["Kripto"]


def main():
    bas = pd.Timestamp.today().normalize() - pd.DateOffset(years=B.YIL)
    yari = bas + (pd.Timestamp.today() - bas) / 2
    rows, tum, ilk, son, port, fiyat = [], [], [], [], [], {}
    for sym in KRIPTO:
        df = B.veri(sym)
        if df is None or len(df) < 300:
            continue
        d, _ = B.sinyaller(df); fiyat[sym] = d["Close"]; tarih = dict(enumerate(d.index))
        tr = [t for t in E.turtle_acilis(d, 20, 10, True) if d.index[t["i"]] >= bas]
        yil = (d.index[-1] - max(d.index[0], bas)).days / 365.25
        st = V.istatistik(tr, yil)
        rows.append({"coin": sym.split("-")[0], "veri yılı": round(yil, 1), **st})
        tum += tr
        for t in tr:
            (ilk if d.index[t["i"]] < yari else son).append(t)
            port.append((sym, d.index[t["i"] + 1], t, tarih))
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).sort_values("ort %", ascending=False).to_string(index=False))
    print("\nTÜM KRİPTO:", V.istatistik(tum, B.YIL))
    a, b = V.istatistik(ilk, 5), V.istatistik(son, 5)
    print(f"İlk 5 yıl: {a.get('ort %')}% ({a.get('işlem')} işlem) | Son 5 yıl: {b.get('ort %')}% ({b.get('işlem')} işlem)")
    print("PORTFÖY (tüm kripto, risk %1):", V.portfoy(port, fiyat, bas))
    for alt in [["BTC-USD", "ETH-USD"], ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"]]:
        p = [x for x in port if x[0] in alt]
        print(f"PORTFÖY {[s.split('-')[0] for s in alt]}:", V.portfoy(p, {s: fiyat[s] for s in alt if s in fiyat}, bas))


if __name__ == "__main__":
    main()
