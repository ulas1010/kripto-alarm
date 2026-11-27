"""
On-chain seviye uyarıları (Barış Kardeş yayınlarındaki yöntem)

Ne yapar?
  1) SPOT ALIM BÖLGELERİ (BTC): Fiyat kademeli alım bölgelerinden birine girince haber verir
     ve o bölge için ayırdığın nakit payını hatırlatır. Bölgeler her gün ücretsiz kaynaklardan
     otomatik güncellenir (Realized Price, kısa/uzun vadeci maliyetleri, MVRV 0.8).
  2) GÜNLÜK KAPANIŞ KIRILIMLARI (BTC, ETH): Önemli bir seviye günlük kapanışla yukarı kırılınca
     düşük kaldıraçlı trade fikri (giriş, stop, pozisyon büyüklüğü), aşağı kaybedilince uyarı gönderir.
  3) GÜNLÜK ÖZET (~09:00 TR): fiyat, on-chain seviyeler, Barış'ın 3 yükseliş kriteri, en yakın seviyeler.

Bot emir GÖNDERMEZ; sadece Telegram'a bilgi verir. Yatırım tavsiyesi değildir.

Veri kaynakları (hepsi ücretsiz, anahtar gerekmez):
  - Fiyat: Binance / OKX / Kraken (tarayici.veri_cek)
  - Realized Price: Coin Metrics Community API (1 gün gecikmeli)
  - STH / LTH maliyeti, True Market Mean: BGeometrics ücretsiz API (7 GÜN GECİKMELİ;
    ücretsiz limit saatte 10, günde 15 istek -> kod en çok saatte 9, günde 14 istek atar)

Seviyeler: onchain_seviyeler.json  |  Durum: onchain_durum.json
Çalıştırma: python onchain_uyari.py [--mod tara|test] [--kuru]
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from tarayici import veri_cek

KOK = Path(__file__).resolve().parent
SEVIYE_DOSYASI = KOK / "onchain_seviyeler.json"
DURUM_DOSYASI = KOK / "onchain_durum.json"
TR = timezone(timedelta(hours=3))

SEMBOLLER = ["BTCUSDT", "ETHUSDT"]
ADLAR = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}

# BGeometrics ücretsiz limit: saatte 10, günde 15 -> en çok %99'u (aşağı yuvarlı)
BG_SAAT_LIMIT = 9
BG_GUN_LIMIT = 14
BG_UCLAR = {"sth_rp": "sth-realized-price", "lth_rp": "lth-realized-price", "tmm": "true-market-mean"}
OTO_ADLAR = {"rp": "Realized Price", "sth_rp": "Kısa vadeci (STH) maliyeti",
             "lth_rp": "Uzun vadeci (LTH) maliyeti", "tmm": "True Market Mean"}

KURU = False  # --kuru: mesaj göndermez, durum kaydetmez


# ----------------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------------
def fmt(x: float) -> str:
    if x is None:
        return "?"
    return f"{x:,.0f}".replace(",", ".") if x >= 100 else f"{x:,.2f}"


def yuzde(a: float, b: float) -> str:
    return f"%{(a / b - 1) * 100:+.1f}"


def json_oku(yol: Path, varsayilan):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return varsayilan


def telegram(metin: str):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if KURU or not token or not chat:
        print("----- [mesaj] -----\n" + metin + "\n")
        return
    for parca in [metin[i:i + 3900] for i in range(0, len(metin), 3900)]:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": parca, "disable_web_page_preview": "true"},
                          timeout=20)
        print("Telegram:", r.status_code)


# ----------------------------------------------------------------------------
# On-chain veriler
# ----------------------------------------------------------------------------
def cm_realized_price():
    """Coin Metrics Community: Realized Price = fiyat / MVRV."""
    r = requests.get("https://community-api.coinmetrics.io/v4/timeseries/asset-metrics",
                     params=dict(assets="btc", metrics="CapMVRVCur,PriceUSD",
                                 page_size=1, paging_from="end"), timeout=20)
    r.raise_for_status()
    s = r.json()["data"][-1]
    return float(s["PriceUSD"]) / float(s["CapMVRVCur"]), s["time"][:10]


def bg_izin(durum) -> bool:
    simdi = datetime.now(timezone.utc)
    s = durum.setdefault("bg_sayac", {})
    gun, saat = simdi.strftime("%Y-%m-%d"), simdi.strftime("%Y-%m-%dT%H")
    if s.get("gun") != gun:
        s.update(gun=gun, gun_n=0)
    if s.get("saat") != saat:
        s.update(saat=saat, saat_n=0)
    if s["gun_n"] >= BG_GUN_LIMIT or s["saat_n"] >= BG_SAAT_LIMIT:
        print("BGeometrics ücretsiz limit sınırına gelindi, istek atılmadı.")
        return False
    s["gun_n"] += 1
    s["saat_n"] += 1
    return True


def bg_son(uc: str):
    """BGeometrics /last: {'d': '2026-11-20', 'unixTs': ..., '<metrik>': 73129.19, ...}"""
    r = requests.get(f"https://bitcoin-data.com/v1/{uc}/last", timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:150]}")
    j = r.json()
    if isinstance(j, list):
        j = j[-1]
    sayilar = []
    for k, v in j.items():  # değerler sayı ya da metin ("73129.19") olarak gelebiliyor
        if k in ("unixTs", "d", "delayed", "message") or isinstance(v, bool):
            continue
        try:
            sayilar.append(float(v))
        except (TypeError, ValueError):
            pass
    if not sayilar:
        raise RuntimeError(f"beklenmeyen cevap: {str(j)[:150]}")
    deger = sayilar[0]
    return deger, j.get("d", "?")


def onchain_guncelle(durum) -> list[str]:
    """Günde bir kez on-chain değerleri yeniler. Başarısız olanlar eski değerle kalır."""
    bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    oc = durum.setdefault("onchain", {})
    sorunlar = []
    if oc.get("_rp_gun") != bugun:
        try:
            v, d = cm_realized_price()
            oc["rp"] = {"deger": v, "tarih": d, "kaynak": "Coin Metrics"}
            oc["_rp_gun"] = bugun
        except Exception as e:  # noqa: BLE001
            sorunlar.append(f"Realized Price alınamadı ({e})")
    for anahtar, uc in BG_UCLAR.items():
        if oc.get(f"_{anahtar}_gun") == bugun:
            continue
        if not bg_izin(durum):
            sorunlar.append(f"{OTO_ADLAR[anahtar]}: ücretsiz istek limiti doldu")
            continue
        try:
            v, d = bg_son(uc)
            oc[anahtar] = {"deger": v, "tarih": d, "kaynak": "BGeometrics (7 gün gecikmeli)"}
            oc[f"_{anahtar}_gun"] = bugun
        except Exception as e:  # noqa: BLE001
            sorunlar.append(f"{OTO_ADLAR[anahtar]} alınamadı ({e})")
    return sorunlar


def oto_deger(durum, anahtar):
    k = durum.get("onchain", {}).get(anahtar)
    return k["deger"] if k else None


# ----------------------------------------------------------------------------
# Seviye listeleri
# ----------------------------------------------------------------------------
def spot_bolgeleri(cfg, durum):
    out = []
    for b in cfg["spot_bolgeleri"]["liste"]:
        taban = b.get("fiyat") or oto_deger(durum, b.get("oto"))
        if taban:
            out.append({**b, "seviye": taban * b.get("carpan", 1.0)})
    return out


def kirilim_seviyeleri(cfg, durum, sembol):
    out = [{**s, "seviye": s["fiyat"]} for s in cfg["seviyeler"].get(sembol, [])]
    if sembol == "BTCUSDT":
        for s in cfg["oto_seviyeler"]["liste"]:
            v = oto_deger(durum, s["oto"])
            if v:
                kaynak = durum["onchain"][s["oto"]]["kaynak"]
                out.append({**s, "seviye": v * s.get("carpan", 1.0), "kaynak": f"otomatik · {kaynak}"})
    return out


# ----------------------------------------------------------------------------
# 1) Spot alım bölgeleri (saatlik mumlar)
# ----------------------------------------------------------------------------
def spot_kontrol(cfg, durum, h1: pd.DataFrame):
    a = cfg["ayarlar"]
    sd = durum.setdefault("spot", {})
    son = durum.get("son_saat")
    yeni = h1[h1["t"] > pd.Timestamp(son)] if son else h1.tail(1)
    if yeni.empty:
        return
    en_dip, kapanis = float(yeni["low"].min()), float(h1["close"].iloc[-1])
    simdi = datetime.now(timezone.utc)
    for b in spot_bolgeleri(cfg, durum):
        L = b["seviye"]
        if b["ad"] not in sd:  # yeni bölge / ilk çalıştırma: zaten içindeysek alarm atma, özette görünür
            sd[b["ad"]] = {"tetik": kapanis <= L, "seviye": L}
            continue
        k = sd[b["ad"]]
        if k.get("tetik") and kapanis >= L * (1 + a["spot_yeniden_kurma_yuzde"] / 100):
            k["tetik"] = False  # fiyat bölgeden yeterince uzaklaştı, tekrar kurulsun
        if not k.get("tetik") and en_dip <= L:
            k.update(tetik=True, zaman=simdi.isoformat(), seviye=L)
            telegram(
                f"🟢 SPOT ALIM BÖLGESİ: {b['ad']}\n\n"
                f"BTC {fmt(L)} seviyesine geldi (şu an {fmt(kapanis)}).\n"
                f"Planındaki pay: spot nakdinin %{b['pay_yuzde']}'i\n\n"
                f"{b.get('not', '')}\n\n"
                "Barış: bu bölgeleri tek nokta değil bir dönem olarak düşün, tamamını tek seferde kullanma.")
        elif not k.get("tetik") and kapanis <= L * (1 + a["yaklasma_yuzde"] / 100):
            once = k.get("yaklasma")
            if not once or simdi - datetime.fromisoformat(once) > timedelta(hours=24):
                k["yaklasma"] = simdi.isoformat()
                telegram(f"👀 Spot bölgesine yaklaşıyor: {b['ad']}\n"
                         f"BTC {fmt(kapanis)}, bölge {fmt(L)} ({yuzde(L, kapanis)} uzakta).")


# ----------------------------------------------------------------------------
# 2) Günlük kapanış kırılımları
# ----------------------------------------------------------------------------
def trade_fikri(cfg, giris, stop) -> str:
    a = cfg["ayarlar"]
    mesafe = (giris - stop) / giris * 100
    satirlar = [f"Giriş ≈ {fmt(giris)} (kapanış) · Stop {fmt(stop)} (%{mesafe:.1f} aşağıda)"]
    if mesafe > 8:
        satirlar.append("⚠️ Stop çok uzak (%8'den fazla). Kaldıraçlı trade için uygun değil, spot düşün.")
        return "\n".join(satirlar)
    kasa = a.get("kasa_usd")
    if kasa:
        risk = kasa * a["trade_risk_yuzde"] / 100
        poz = risk / (mesafe / 100)
        teminat = poz / a["maks_kaldirac"]
        satirlar.append(f"Risk: %{a['trade_risk_yuzde']:g} = {fmt(risk)}$ · Pozisyon ≈ {fmt(poz)}$ "
                        f"→ {a['maks_kaldirac']}x kaldıraçla teminat ≈ {fmt(teminat)}$")
        if teminat > kasa:
            satirlar.append("⚠️ Gereken teminat kasanı aşıyor; pozisyonu küçült.")
    else:
        satirlar.append(f"Kasa ayarlanmadı: işlem başına kasanın %{a['trade_risk_yuzde']:g}'ini riske et, "
                        f"en çok {a['maks_kaldirac']}x kaldıraç.")
    return "\n".join(satirlar)


def gunluk_kontrol(cfg, durum, sembol, d1: pd.DataFrame):
    a = cfg["ayarlar"]
    anahtar = f"son_gun_{sembol}"
    son = durum.get(anahtar)
    son_t = d1["t"].iloc[-1]
    if not son:  # ilk çalıştırma: geçmişi taramadan başla
        durum[anahtar] = son_t.isoformat()
        return
    seviyeler = kirilim_seviyeleri(cfg, durum, sembol)
    for i in d1.index[d1["t"] > pd.Timestamp(son)]:
        if i == 0:
            continue
        onceki, mum = float(d1["close"].iloc[i - 1]), d1.iloc[i]
        c, gun = float(mum["close"]), mum["t"].strftime("%d.%m")
        for s in seviyeler:
            L, rol = s["seviye"], s.get("rol", "ikisi")
            notu = f"\n{s['not']}" if s.get("not") else ""
            kaynak = f" ({s.get('kaynak')})" if s.get("kaynak") else ""
            if onceki < L <= c and rol in ("direnç", "ikisi"):
                stop = min(L, float(mum["low"])) * (1 - a["stop_tampon_yuzde"] / 100)
                telegram(f"📈 {ADLAR[sembol]} GÜNLÜK KAPANIŞ ÜSTÜNDE: {s['ad']} {fmt(L)}{kaynak}\n"
                         f"{gun} kapanışı {fmt(c)}{notu}\n\n"
                         f"Düşük kaldıraçlı long fikri:\n{trade_fikri(cfg, c, stop)}\n\n"
                         "Girmeden önce grafiğe bak; seviyeye geri test daha iyi giriş verebilir.")
            elif onceki > L >= c and rol in ("destek", "ikisi"):
                telegram(f"📉 {ADLAR[sembol]} GÜNLÜK KAPANIŞ ALTINDA: {s['ad']} {fmt(L)}{kaynak}\n"
                         f"{gun} kapanışı {fmt(c)}{notu}\n\n"
                         "Açık kaldıraçlı long varsa stopunu kontrol et. Barış: altında kapanış satış baskısı demek.")
    durum[anahtar] = son_t.isoformat()


# ----------------------------------------------------------------------------
# 3) Günlük özet
# ----------------------------------------------------------------------------
def ozet(cfg, durum, veriler, sorunlar) -> str:
    satirlar = [f"🧭 ON-CHAIN ÖZET · {datetime.now(TR):%d.%m.%Y %H:%M}"]
    if "BTCUSDT" in veriler:
        d1 = veriler["BTCUSDT"]["1d"]
        p = float(veriler["BTCUSDT"]["1h"]["close"].iloc[-1])
        satirlar.append(f"\nBTC {fmt(p)}")
        ma200 = float(d1["close"].tail(200).mean()) if len(d1) >= 200 else None
        kriterler = [("200 günlük ortalama", ma200), ("Kısa vadeci maliyeti", oto_deger(durum, "sth_rp")),
                     ("True Market Mean", oto_deger(durum, "tmm"))]
        skor = sum(1 for _, v in kriterler if v and p > v)
        satirlar.append(f"\nBarış'ın yükseliş kriterleri: {skor}/3")
        for n, v in kriterler:
            satirlar.append(f"  {'✅' if v and p > v else '❌'} {n}: {fmt(v)}" + (f" ({yuzde(v, p)})" if v else ""))
        satirlar.append("\nSpot alım bölgeleri:")
        for b in spot_bolgeleri(cfg, durum):
            tetik = durum.get("spot", {}).get(b["ad"], {}).get("tetik")
            satirlar.append(f"  {'🟢' if tetik else '⚪'} {fmt(b['seviye'])} ({yuzde(b['seviye'], p)}) "
                            f"· %{b['pay_yuzde']} · {b['ad']}")
    for sembol, v in veriler.items():
        p = float(v["1h"]["close"].iloc[-1])
        sv = sorted(kirilim_seviyeleri(cfg, durum, sembol), key=lambda s: s["seviye"])
        ust = [s for s in sv if s["seviye"] > p][:3]
        alt = [s for s in sv if s["seviye"] <= p][-3:][::-1]
        satirlar.append(f"\n{ADLAR[sembol]} {fmt(p)} · en yakın seviyeler")
        for s in ust[::-1]:
            satirlar.append(f"  ↑ {fmt(s['seviye'])} ({yuzde(s['seviye'], p)}) {s['ad']}")
        for s in alt:
            satirlar.append(f"  ↓ {fmt(s['seviye'])} ({yuzde(s['seviye'], p)}) {s['ad']}")
    oc = durum.get("onchain", {})
    tarihler = [f"{OTO_ADLAR[k]} {oc[k]['tarih']}" for k in OTO_ADLAR if k in oc]
    if tarihler:
        satirlar.append("\nVeri tarihleri: " + " · ".join(tarihler))
    if sorunlar:
        satirlar.append("⚠️ " + " | ".join(sorunlar))
    satirlar.append("Elle girilen seviyeler: Barış yayını 23.11 (yeni yayını Claude'a at, güncellesin).")
    return "\n".join(satirlar)


# ----------------------------------------------------------------------------
def main():
    global KURU
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", default="tara", choices=["tara", "test"])
    ap.add_argument("--kuru", action="store_true", help="mesaj gönderme, durumu kaydetme")
    arg = ap.parse_args()
    KURU = arg.kuru

    cfg = json_oku(SEVIYE_DOSYASI, None)
    durum = json_oku(DURUM_DOSYASI, {})
    sorunlar = onchain_guncelle(durum)
    if sorunlar:
        print("On-chain sorunlar:", sorunlar)

    veriler = {}
    for sembol in SEMBOLLER:
        try:
            veriler[sembol] = {"1h": veri_cek(sembol, "1h", 72), "1d": veri_cek(sembol, "1d", 400)}
        except Exception as e:  # noqa: BLE001
            sorunlar.append(f"{ADLAR[sembol]} fiyatı alınamadı ({e})")

    if "BTCUSDT" in veriler:
        spot_kontrol(cfg, durum, veriler["BTCUSDT"]["1h"])
        durum["son_saat"] = veriler["BTCUSDT"]["1h"]["t"].iloc[-1].isoformat()
    for sembol, v in veriler.items():
        gunluk_kontrol(cfg, durum, sembol, v["1d"])

    simdi_tr = datetime.now(TR)
    bugun = simdi_tr.strftime("%Y-%m-%d")
    if arg.mod == "test" or (simdi_tr.hour >= 9 and durum.get("son_ozet") != bugun):
        telegram(ozet(cfg, durum, veriler, sorunlar))
        if arg.mod != "test":
            durum["son_ozet"] = bugun
    elif sorunlar:
        print("Sorunlar:", sorunlar)

    if not KURU:
        DURUM_DOSYASI.write_text(json.dumps(durum, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
