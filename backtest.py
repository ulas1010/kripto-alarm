"""
BACKTEST - Bot geçmişte çalışıyor olsaydı hangi sinyalleri gönderirdi ve sonuçları ne olurdu?

Nasıl çalışır (geleceği görmeden):
  * Seçilen dönemi 15 dakika 15 dakika "canlıymış gibi" ilerletir.
  * Her adımda botun sadece O ANA KADAR kapanmış mumları görmesine izin verilir
    (canlı bottaki gibi son 700 mum, 4 saatlik ve günlük bölgeler de o ana kadarki veriden).
  * Canlı botun o anda göndereceği sinyaller kaydedilir (aynı tazelik kuralları ile).
  * Sonra sinyalden sonraki 15 dakikalık mumlarla stop mu hedef mi önce geldi diye bakılır.
    Aynı mumda hem stop hem hedef görülürse STOP sayılır (kötümser varsayım).
  * Komisyon: giriş+çıkış toplam %0.1 düşülür.

Ölçülen iki strateji:
  * "TP1"  : pozisyonun tamamı Hedef 1'de kapatılır.
  * "Parçalı": yarısı Hedef 1'de alınır, stop girişe çekilir, kalan yarısı Hedef 2'de.
Belirli bir süre içinde ne stop ne hedef gelirse o anki fiyattan kapatılır.

Kullanım:  python backtest.py --ay 6
"""
from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import ayarlar
import tarayici as T

KOMISYON = 0.001  # giriş + çıkış toplamı
MAKS_SURE_MUM15 = {"15m": 2 * 96, "30m": 3 * 96, "1h": 5 * 96}  # 15dk'lık mum cinsinden bekleme süresi
CIKTI = T.KOK / "backtest"


# ----------------------------------------------------------------------------
# GEÇMİŞ VERİ
# ----------------------------------------------------------------------------
def _binance_gecmis(sembol, tf, bas_ms, bit_ms):
    rows, cur = [], bas_ms
    while cur < bit_ms:
        r = requests.get("https://data-api.binance.vision/api/v3/klines",
                         params=dict(symbol=sembol, interval=tf, startTime=cur, endTime=bit_ms, limit=1000),
                         timeout=30)
        r.raise_for_status()
        k = r.json()
        if not k:
            break
        rows += [x[:6] for x in k]
        yeni = k[-1][0] + T.TF_DAKIKA[tf] * 60_000
        if yeni <= cur:
            break
        cur = yeni
        time.sleep(0.1)
    return T._df(rows)


def _okx_gecmis(sembol, tf, bas_ms, bit_ms):
    inst = sembol.replace("USDT", "-USDT")
    bar = {"15m": "15m", "30m": "30m", "1h": "1H", "4h": "4Hutc", "1d": "1Dutc"}[tf]
    rows, after = [], bit_ms
    while True:
        r = requests.get("https://www.okx.com/api/v5/market/history-candles",
                         params=dict(instId=inst, bar=bar, limit=100, after=after), timeout=30)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            break
        rows += [d[:6] for d in data]
        after = int(data[-1][0])
        if after <= bas_ms:
            break
        time.sleep(0.12)
    df = T._df(rows)
    return df[df["t"] >= pd.Timestamp(bas_ms, unit="ms", tz="UTC")].reset_index(drop=True)


def gecmis_veri(sembol, tf, bas: pd.Timestamp, bit: pd.Timestamp) -> pd.DataFrame:
    hatalar = []
    for ad, fn in (("Binance", _binance_gecmis), ("OKX", _okx_gecmis)):
        try:
            df = fn(sembol, tf, int(bas.timestamp() * 1000), int(bit.timestamp() * 1000))
            df = df[df["t"] + pd.Timedelta(minutes=T.TF_DAKIKA[tf]) <= bit].reset_index(drop=True)
            if len(df) > 100:
                print(f"  {sembol} {tf}: {len(df)} mum ({ad})", flush=True)
                return df
            hatalar.append(f"{ad}: az veri ({len(df)})")
        except Exception as e:  # noqa: BLE001
            hatalar.append(f"{ad}: {e}")
    raise RuntimeError(f"{sembol} {tf} geçmiş verisi alınamadı: " + " | ".join(hatalar))


# ----------------------------------------------------------------------------
# SİMÜLASYON
# ----------------------------------------------------------------------------
def simule_et(sembol, veri: dict[str, pd.DataFrame], bas: pd.Timestamp):
    """Canlı botu adım adım taklit eder. Döner: gönderilecek sinyal listesi (dict)."""
    kayitlar = []
    gorulen = set()
    htf_tf = list(ayarlar.BOLGE_ZAMAN_DILIMLERI)
    htf_kapanis = {tf: (veri[tf]["t"] + pd.Timedelta(minutes=T.TF_DAKIKA[tf])).values for tf in htf_tf + ["1d"]}
    d15 = veri["15m"]
    fiyat_kapanis = (d15["t"] + pd.Timedelta(minutes=15)).values
    bolge_onbellek = {}

    for tf in ayarlar.ONAY_ZAMAN_DILIMLERI:
        df = veri[tf]
        kap = (df["t"] + pd.Timedelta(minutes=T.TF_DAKIKA[tf])).values
        bas_idx = int(np.searchsorted(kap, np.datetime64(bas.tz_convert(None))))
        bas_idx = max(bas_idx, 200)
        maks_gec = ayarlar.MAKS_GECIKME_DAKIKA.get(tf, 30)
        t0 = time.time()
        for idx in range(bas_idx, len(df)):
            simdi = kap[idx]
            pencere = df.iloc[max(0, idx - 699): idx + 1].reset_index(drop=True)
            # o anki fiyat = son kapanmış 15dk mumu
            fi = int(np.searchsorted(fiyat_kapanis, simdi, side="right")) - 1
            fiyat = float(d15["close"].iloc[fi])
            # HTF: o ana kadar kapanmış mumlar
            htf_sayilar = tuple(int(np.searchsorted(htf_kapanis[h], simdi, side="right")) for h in htf_tf)
            anahtar = (htf_sayilar, round(fiyat, -1 if fiyat > 1000 else 0))
            if anahtar not in bolge_onbellek:
                htf = {h: veri[h].iloc[max(0, n - (500 if h == "4h" else 400)): n].reset_index(drop=True)
                       for h, n in zip(htf_tf, htf_sayilar)}
                bolge_onbellek.clear()
                bolge_onbellek[anahtar] = T.bolgeleri_bul(htf, fiyat)
            bolgeler = bolge_onbellek[anahtar]
            if not bolgeler:
                continue
            nd = int(np.searchsorted(htf_kapanis["1d"], simdi, side="right"))
            trend = T.gunluk_trend(veri["1d"].iloc[max(0, nd - 400): nd])
            n = len(pencere)
            for s in T.yapilari_tara(pencere, tf, sembol, bolgeler):
                if s.i < n - T.LTF_AYAR[tf]["pencere"] or s.kimlik in gorulen:
                    continue
                gorulen.add(s.kimlik)
                # canlı bot: tetik mumu kapanışından bu yana geçen süre (+1 dk çalışma gecikmesi)
                tetik_kapanis = pencere["t"].iloc[s.i] + pd.Timedelta(minutes=T.TF_DAKIKA[tf])
                gec = (pd.Timestamp(simdi, tz="UTC") - tetik_kapanis).total_seconds() / 60 + 1
                if gec > maks_gec:
                    continue
                if not T.hala_gecerli(s, pencere):
                    continue
                s.trend = trend
                kayitlar.append(dict(
                    sembol=sembol, tf=tf, yapi=s.yapi, yon=s.yon, trend=trend,
                    gonderim=pd.Timestamp(simdi, tz="UTC"), tetik=s.zaman,
                    giris=float(pencere["close"].iloc[-1]), stop=s.stop, tp1=s.tp1, tp2=s.tp2,
                    rr1_plan=s.rr1, rr2_plan=s.rr2, puan=s.puan, bolge_puan=s.bolge_puan))
            if (idx - bas_idx) % 2000 == 0:
                print(f"  {sembol} {tf}: {idx - bas_idx}/{len(df) - bas_idx} adım, "
                      f"{len(kayitlar)} sinyal, {time.time() - t0:.0f} sn", flush=True)
    return kayitlar


def sonuc_hesapla(k: dict, d15: pd.DataFrame) -> dict:
    t_arr = (d15["t"]).values
    bas = int(np.searchsorted(t_arr, np.datetime64(k["gonderim"].tz_convert(None))))
    bitis = min(len(d15), bas + MAKS_SURE_MUM15[k["tf"]])
    h, l, c = d15["high"].values, d15["low"].values, d15["close"].values
    e, sl, tp1, tp2 = k["giris"], k["stop"], k["tp1"], k["tp2"]
    uzun = k["yon"] == "long"
    risk = abs(e - sl)
    if risk <= 0 or (uzun and (e <= sl or e >= tp1)) or (not uzun and (e >= sl or e <= tp1)):
        return dict(durum="geçersiz", r_tp1=np.nan, r_parcali=np.nan, sure_saat=np.nan)
    R = lambda p: ((p - e) if uzun else (e - p)) / risk  # noqa: E731
    ucret = KOMISYON * e / risk

    sonuc_tp1 = None
    parcali_kar, yari_alindi, stop_seviye = 0.0, False, sl
    sonuc_parcali = None
    son_j = bas
    for j in range(bas, bitis):
        son_j = j
        stop_vurdu = (l[j] <= stop_seviye) if uzun else (h[j] >= stop_seviye)
        sl_ilk = (l[j] <= sl) if uzun else (h[j] >= sl)
        tp1_vurdu = (h[j] >= tp1) if uzun else (l[j] <= tp1)
        tp2_vurdu = (h[j] >= tp2) if uzun else (l[j] <= tp2)
        # --- TP1 stratejisi
        if sonuc_tp1 is None:
            if sl_ilk:
                sonuc_tp1 = ("stop", -1.0, j)
            elif tp1_vurdu:
                sonuc_tp1 = ("hedef1", R(tp1), j)
        # --- Parçalı strateji
        if sonuc_parcali is None:
            if not yari_alindi:
                if sl_ilk:
                    sonuc_parcali = ("stop", -1.0, j)
                elif tp1_vurdu:
                    yari_alindi, parcali_kar, stop_seviye = True, 0.5 * R(tp1), e
                    if tp2_vurdu:
                        sonuc_parcali = ("hedef2", parcali_kar + 0.5 * R(tp2), j)
            else:
                if stop_vurdu:
                    sonuc_parcali = ("hedef1+başabaş", parcali_kar, j)
                elif tp2_vurdu:
                    sonuc_parcali = ("hedef2", parcali_kar + 0.5 * R(tp2), j)
        if sonuc_tp1 is not None and sonuc_parcali is not None:
            break
    if bitis <= bas:
        return dict(durum="veri yok", r_tp1=np.nan, r_parcali=np.nan, sure_saat=np.nan)
    if sonuc_tp1 is None:
        sonuc_tp1 = ("süre doldu", R(c[son_j]), son_j)
    if sonuc_parcali is None:
        sonuc_parcali = ("süre doldu", parcali_kar + (0.5 if yari_alindi else 1.0) * R(c[son_j]), son_j)
    return dict(durum=sonuc_tp1[0], r_tp1=round(sonuc_tp1[1] - ucret, 3),
                durum_parcali=sonuc_parcali[0], r_parcali=round(sonuc_parcali[1] - ucret, 3),
                sure_saat=round((sonuc_tp1[2] - bas + 1) * 0.25, 1), ucret_R=round(ucret, 3))


# ----------------------------------------------------------------------------
# RAPOR
# ----------------------------------------------------------------------------
def trend_iliskisi(row):
    if row["trend"] == "yatay / kararsız":
        return "yatay piyasa"
    ters = (row["trend"] == "düşüş" and row["yon"] == "long") or (row["trend"] == "yükseliş" and row["yon"] == "short")
    return "trend tersi" if ters else "trend yönünde"


def ozet_tablo(df: pd.DataFrame, grup: str | list) -> pd.DataFrame:
    g = df.groupby(grup)
    t = pd.DataFrame({
        "sinyal": g.size(),
        "isabet_%": g.apply(lambda x: round(100 * (x["durum"] == "hedef1").mean(), 1)),
        "stop_%": g.apply(lambda x: round(100 * (x["durum"] == "stop").mean(), 1)),
        "ort_R_tp1": g["r_tp1"].mean().round(2),
        "top_R_tp1": g["r_tp1"].sum().round(1),
        "ort_R_parcali": g["r_parcali"].mean().round(2),
        "top_R_parcali": g["r_parcali"].sum().round(1),
    })
    return t.sort_values("sinyal", ascending=False)


def md_tablo(t: pd.DataFrame, baslik: str) -> str:
    t = t.reset_index()
    cols = list(t.columns)
    satir = [f"### {baslik}", "", "| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in t.iterrows():
        satir.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(satir) + "\n"


def rapor_yaz(df: pd.DataFrame, bas, bit) -> tuple[str, str]:
    gecerli = df[df["durum"].isin(["stop", "hedef1", "süre doldu"])].copy()
    gecerli["trend_iliskisi"] = gecerli.apply(trend_iliskisi, axis=1)
    genel = ozet_tablo(gecerli.assign(hepsi="TÜMÜ"), "hepsi")
    md = [f"# Backtest sonucu ({bas:%d.%m.%Y} – {bit:%d.%m.%Y})", "",
          "R = risk birimi. +1R = stop mesafesi kadar kâr, -1R = stopla tam kayıp. Komisyon (%0.1) düşülmüştür.",
          "isabet_% = Hedef 1'in stoptan önce geldiği sinyallerin oranı.", "",
          md_tablo(genel, "Genel"),
          md_tablo(ozet_tablo(gecerli, "yapi"), "Yapıya göre"),
          md_tablo(ozet_tablo(gecerli, "trend_iliskisi"), "Trende göre"),
          md_tablo(ozet_tablo(gecerli, ["yapi", "trend_iliskisi"]), "Yapı × trend"),
          md_tablo(ozet_tablo(gecerli, "tf"), "Zaman dilimine göre"),
          md_tablo(ozet_tablo(gecerli, "sembol"), "Coine göre"),
          md_tablo(ozet_tablo(gecerli, "yon"), "Yöne göre"),
          md_tablo(ozet_tablo(gecerli, "puan"), "Güç puanına göre (yıldız)")]
    gecerli["ay"] = gecerli["gonderim"].dt.strftime("%Y-%m")
    md.append(md_tablo(ozet_tablo(gecerli, "ay").sort_index(), "Aylara göre"))
    md.append(f"\nGeçersiz/atlanan sinyal: {len(df) - len(gecerli)}\n")

    # Telegram için kısa özet
    def satir(ad, x):
        if len(x) == 0:
            return f"{ad}: sinyal yok"
        return (f"{ad}: {len(x)} sinyal • isabet %{100 * (x['durum'] == 'hedef1').mean():.0f} • "
                f"ort {x['r_tp1'].mean():+.2f}R • toplam {x['r_tp1'].sum():+.1f}R")
    tg = [f"📊 <b>Backtest ({bas:%d.%m.%Y} – {bit:%d.%m.%Y})</b>",
          "BTC + ETH, 15dk ve 1 saat. Tüm pozisyon Hedef 1'de kapatılmış gibi, komisyon dahil.", "",
          satir("<b>TÜMÜ</b>", gecerli), ""]
    for y in gecerli["yapi"].unique():
        tg.append(satir(T.YAPI_ADI[y], gecerli[gecerli["yapi"] == y]))
    tg.append("")
    for tr in ["trend tersi", "yatay piyasa", "trend yönünde"]:
        tg.append(satir(tr.capitalize(), gecerli[gecerli["trend_iliskisi"] == tr]))
    tg += ["", "Ayrıntılı tablo depoda: backtest/sonuc.md",
           "⚠️ Geçmiş sonuç gelecek için garanti değildir."]
    return "\n".join(md), "\n".join(tg)


# ----------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ay", type=int, default=6)
    p.add_argument("--telegram", action="store_true")
    a = p.parse_args()

    bit = pd.Timestamp.now(tz="UTC").floor("15min")
    bas = bit - pd.DateOffset(months=a.ay)
    print(f"Dönem: {bas} – {bit}", flush=True)
    CIKTI.mkdir(exist_ok=True)

    tum = []
    for sembol in ayarlar.SEMBOLLER:
        print(f"{sembol} verisi indiriliyor...", flush=True)
        veri = {
            "15m": gecmis_veri(sembol, "15m", bas - pd.Timedelta(minutes=15 * 720), bit),
            "1h": gecmis_veri(sembol, "1h", bas - pd.Timedelta(hours=720), bit),
            "4h": gecmis_veri(sembol, "4h", bas - pd.Timedelta(hours=4 * 520), bit),
            "1d": gecmis_veri(sembol, "1d", bas - pd.Timedelta(days=420), bit),
        }
        for tf in ayarlar.ONAY_ZAMAN_DILIMLERI:
            if tf not in veri:
                veri[tf] = gecmis_veri(sembol, tf, bas - pd.Timedelta(minutes=T.TF_DAKIKA[tf] * 720), bit)
        print(f"{sembol} simüle ediliyor...", flush=True)
        kayit = simule_et(sembol, veri, bas)
        for k in kayit:
            k.update(sonuc_hesapla(k, veri["15m"]))
        tum += kayit
        print(f"{sembol}: {len(kayit)} sinyal", flush=True)

    if not tum:
        metin = "Backtest: dönem boyunca hiç sinyal oluşmadı."
        print(metin)
        return
    df = pd.DataFrame(tum)
    df.to_csv(CIKTI / "sinyaller.csv", index=False)
    md, tg = rapor_yaz(df, bas, bit)
    (CIKTI / "sonuc.md").write_text(md, encoding="utf-8")
    print(md)
    if a.telegram:
        T.Telegram(os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")).mesaj(tg)


if __name__ == "__main__":
    main()
