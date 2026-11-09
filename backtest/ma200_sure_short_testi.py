"""
1) Süre analizi: KIRILIM ve RETEST işlemleri ne kadar sürüyor? (stop, TP1, tam çıkış)
2) Fonlama maliyeti: perp'te tutulan süre boyunca ödenen funding R cinsinden ne kadar?
3) SHORT testi: günlük kapanış 200 MA altına inince short (aynı kuralların aynası).
   Stop = max(mum tepesi, MA) * 1.01, TP1 = 3R'de yarısı, kalan yarı kapanış MA üstüne çıkınca.
Aynı 13 varlık, son 10 yıl, aynı varlıkta aynı türden açık işlem varken yenisine girilmez.
"""
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, "."); sys.path.insert(0, "backtest")
import ma200 as M
import ma200_backtest as B
import ma200_cikis_testi as C
import ma200_kirilim_testi as K

# Yıllık funding varsayımları (pozisyon değerinin yüzdesi, long öder)
FUNDING_YILLIK = [5, 10, 20]


def karma_detay(d, i, giris, stop, yon=1):
    """Karma 3R+trend çıkışı; yon=1 long, -1 short. (R, tp1_gun, bitis_gun, sonuc_turu)"""
    o, h, l, c, ma = (d[k].to_numpy() for k in ["Open", "High", "Low", "Close", "ma"])
    risk = (giris - stop) * yon
    if risk <= 0:
        return None
    hedef = giris + yon * 3 * risk
    st = stop; tp_gun = None
    for k in range(i + 1, len(d)):
        vurdu = l[k] <= st if yon == 1 else h[k] >= st
        if vurdu:
            px = min(o[k], st) if yon == 1 else max(o[k], st)
            r = (px - giris) * yon / risk
            if tp_gun is None:
                return r, None, k - i, "stop"
            return 0.5 * 3 + 0.5 * r, tp_gun, k - i, "tp1+basabas"
        if tp_gun is None:
            ulasti = h[k] >= hedef if yon == 1 else l[k] <= hedef
            if ulasti:
                tp_gun = k - i; st = giris
                continue
        if tp_gun is not None:
            cikis = c[k] < ma[k] if yon == 1 else c[k] > ma[k]
            if cikis:
                return 0.5 * 3 + 0.5 * (c[k] - giris) * yon / risk, tp_gun, k - i, "tp1+ma_cikis"
    return None  # hâlâ açık


def short_kirilimlar(d):
    h, c, ma = (d[k].to_numpy() for k in ["High", "Close", "ma"])
    out = []
    for i in range(1, len(d)):
        if np.isnan(ma[i]) or np.isnan(ma[i - 1]):
            continue
        if c[i] < ma[i] and c[i - 1] >= ma[i - 1]:
            out.append((i, c[i], max(h[i], ma[i]) * (1 + M.STOP_BUF_PCT / 100)))
    return out


def main():
    bas = pd.Timestamp.today() - pd.DateOffset(years=B.YIL)
    kayit = []
    for sym in C.SECILMIS:
        df = B.veri(sym)
        if df is None or len(df) < 300:
            continue
        d, ret = B.sinyaller(df)
        for tip, sig, yon in [("KIRILIM long", K.kirilimlar(d, False), 1),
                              ("RETEST long", ret, 1),
                              ("KIRILIM short", short_kirilimlar(d), -1)]:
            serbest = -1
            for i, g, st in sig:
                if d.index[i] < bas or i <= serbest:
                    continue
                r = karma_detay(d, i, g, st, yon)
                if r is None:
                    continue
                R, tp, bitis, tur = r
                serbest = i + bitis
                kayit.append({"tip": tip, "varlik": sym, "tarih": d.index[i], "R": R,
                              "stop%": abs(g - st) / g * 100, "tp1_gun": tp, "sure_gun": bitis, "tur": tur})
    k = pd.DataFrame(kayit)
    k.to_csv("backtest/ma200_sure_short.csv", index=False)
    pd.set_option("display.width", 250)

    for tip in k.tip.unique():
        x = k[k.tip == tip]
        print(f"\n=== {tip}: {len(x)} işlem, kazanma %{100 * (x.R > 0).mean():.0f}, "
              f"ort {x.R.mean():+.2f}R, toplam {x.R.sum():+.1f}R, medyan stop %{x['stop%'].median():.1f} ===")
        print("Sonuç türü dağılımı:", x.tur.value_counts().to_dict())
        st = x[x.tur == "stop"]
        tp = x[x.tp1_gun.notna()]
        print(f"Stop olanlar: medyan {st.sure_gun.median():.0f} gün sonra stop "
              f"(%25-%75: {st.sure_gun.quantile(.25):.0f}-{st.sure_gun.quantile(.75):.0f})")
        if len(tp):
            print(f"TP1'e ulaşanlar (%{100 * len(tp) / len(x):.0f}): medyan {tp.tp1_gun.median():.0f} gün "
                  f"(%25-%75: {tp.tp1_gun.quantile(.25):.0f}-{tp.tp1_gun.quantile(.75):.0f}), "
                  f"tam çıkış medyan {tp.sure_gun.median():.0f} gün "
                  f"(%25-%75: {tp.sure_gun.quantile(.25):.0f}-{tp.sure_gun.quantile(.75):.0f}, en uzun {tp.sure_gun.max():.0f})")
        # Funding etkisi: kalan yarı TP1 sonrası yarım pozisyon
        for f in FUNDING_YILLIK:
            gunluk = f / 100 / 365
            # TP1 öncesi tam pozisyon, sonrası yarım pozisyon (takvim günü ~ işlem günü*1.4 hisse için)
            tam = x.tp1_gun.fillna(x.sure_gun)
            yarim = (x.sure_gun - tam).clip(lower=0)
            maliyet_pct = gunluk * 1.4 * (tam + 0.5 * yarim) * 100        # pozisyon değerinin %'si
            maliyet_R = maliyet_pct / x["stop%"]
            yon = 1 if "long" in tip else -1   # short funding'i genelde ALIR (pozitif funding'de)
            net = x.R - yon * maliyet_R
            print(f"  Funding yıllık %{f}: işlem başı maliyet ort {maliyet_R.mean():.2f}R → "
                  f"net ort {net.mean():+.2f}R, toplam {net.sum():+.1f}R")


if __name__ == "__main__":
    main()
