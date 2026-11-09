"""
🐢 TURTLE sinyali (ana sistem) — ma200.py tarafından çağrılır, aynı varlıkları ve aynı Telegram botunu kullanır.

SİSTEM (Richard Dennis'in Kaplumbağa kuralları, 200 MA filtreli; backtest: backtest/ertesi_acilis_testi.py):
  Sinyal: günlük kapanış önceki 20 günün en yükseğinin üstünde VE 200 MA'nın üstünde
  Giriş : sinyalden SONRAKİ gün açılışta al
  Stop  : giriş − 2 × ATR(20)  (gün içinde)
  Çıkış : günlük kapanış önceki 10 günün en düşüğünün altına inerse → ertesi açılışta sat
Backtest (13 varlık, 10 yıl, ertesi açılış, %0,1 maliyet/yön): 513 işlem, kazanma %39,
işlem başı +%4,7, medyan 16 gün; portföy (risk %1): yıllık %25, en kötü düşüş −%22.

İşlem durumu ma200_durum.json içinde "<sembol>|TURTLE" anahtarıyla tutulur:
  bekliyor -> ertesi açılışta girilecek | acik -> pozisyonda | cikis_bekliyor -> ertesi açılışta satılacak
"""
import numpy as np
import pandas as pd

GIRIS_N = 20
CIKIS_N = 10
STOP_ATR = 2.0
RISK_YUZDE = 1.0        # kasanın yüzdesi (giriş ile stop arası)
POZ_MAX_YUZDE = 20.0    # tek pozisyon kasanın en fazla bu yüzdesi
MALIYET = 0.001
BT_OZET = ("10 yıl backtest (13 varlık, 513 işlem): kazanma %39, işlem başı ort. +%4,7, medyan 16 gün. "
           "Çoğu işlem küçük kayıpla biter, kâr büyük trendlerden gelir.")


def gostergeler(d):
    d["t_hh"] = d["High"].rolling(GIRIS_N).max().shift(1)
    d["t_ll"] = d["Low"].rolling(CIKIS_N).min().shift(1)
    pc = d["Close"].shift(1)
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1)
    d["atr20"] = tr.ewm(alpha=1 / 20, adjust=False).mean()
    return d


def sinyal_var(d):
    s = d.iloc[-1]
    return bool(not np.isnan(s["t_hh"]) and not np.isnan(s["ma"])
                and s["Close"] > s["t_hh"] and s["Close"] > s["ma"])


def yeni_islem(d):
    s = d.iloc[-1]
    return {"tip": "TURTLE", "durum": "bekliyor", "sinyal_tarih": str(d.index[-1].date()),
            "mesafe": float(STOP_ATR * s["atr20"]), "giris": None, "stop": None,
            "son_kontrol": str(d.index[-1].date())}


def al_mesaji(ad, fmt, kasa, d, t, kripto=False):
    s = d.iloc[-1]
    c = float(s["Close"]); m = t["mesafe"]
    risk_usd = kasa * RISK_YUZDE / 100
    miktar = min(risk_usd / m, kasa * POZ_MAX_YUZDE / 100 / c)
    return (
        f"🐢 *{ad} — TURTLE AL*\n"
        f"Kapanış {fmt(c)}, son {GIRIS_N} günün zirvesini ({fmt(float(s['t_hh']))}) kırdı; 200 MA üstünde.\n\n"
        + ("*Giriş:* ŞİMDİ al (kripto günlük mumu 03:00'te açıldı; fiyat çok kaçtıysa miktarı küçült)\n"
           if kripto else "*Giriş:* bugün AÇILIŞTA al\n")
        +
        f"*Stop:* giriş fiyatının {fmt(m)} altı (2×ATR, ~%{m / c * 100:.1f}) → kapanışa göre ~{fmt(c - m)}\n"
        f"*Çıkış:* günlük kapanış son {CIKIS_N} günün dibinin altına inerse bot \"SAT\" mesajı atar "
        f"(şu an dip {fmt(float(s['t_ll']))}, her gün yukarı kayar)\n\n"
        f"*Pozisyon* (kasa {kasa:,.0f}$, risk %{RISK_YUZDE:g} = {risk_usd:,.0f}$, en fazla %{POZ_MAX_YUZDE:g}):\n"
        f"Miktar ~{miktar:,.4f} | Değer ~{miktar * c:,.0f}$\n\n"
        f"_{BT_OZET}_"
    )


def yonet(ad, fmt, t, d, kripto=False):
    """Turtle işlemini son kontrolden sonraki mumlarla günceller -> (mesajlar, kapandı_mı)."""
    msgs = []
    for tarih, row in d[d.index > pd.Timestamp(t["son_kontrol"])].iterrows():
        gun = str(tarih.date())
        if t["durum"] == "cikis_bekliyor":
            px = float(row["Open"])
            t.update(cikis=px, kapanis=gun, son_kontrol=gun,
                     sonuc_pct=round((px / t["giris"] - 1 - 2 * MALIYET) * 100, 2))
            return msgs, True
        if t["durum"] == "bekliyor":
            t["giris"] = float(row["Open"]); t["stop"] = t["giris"] - t["mesafe"]
            t["durum"] = "acik"; t["giris_tarih"] = gun
        if row["Low"] <= t["stop"]:
            px = min(float(row["Open"]), t["stop"])
            t.update(cikis=px, kapanis=gun, son_kontrol=gun,
                     sonuc_pct=round((px / t["giris"] - 1 - 2 * MALIYET) * 100, 2))
            msgs.append(f"🔴 *{ad}* (turtle) STOP oldu ({fmt(px)}). Sonuç: *%{t['sonuc_pct']:+.2f}* (≈ −1R)")
            return msgs, True
        if row["Close"] < row["t_ll"]:
            t["durum"] = "cikis_bekliyor"
            tahmini = (float(row["Close"]) / t["giris"] - 1) * 100
            msgs.append(f"🔵 *{ad}* (turtle) SAT: kapanış son {CIKIS_N} günün dibinin altına indi.\n"
                        f"→ {'ŞİMDİ' if kripto else 'Bugün AÇILIŞTA'} sat. Giriş {fmt(t['giris'])}, son kapanış {fmt(float(row['Close']))} "
                        f"(tahmini sonuç %{tahmini:+.1f})")
        t["son_kontrol"] = gun
    return msgs, False


def ozet_satiri(ad, fmt, t):
    if t["durum"] == "bekliyor":
        return f"{ad} (turtle): açılışta giriş bekleniyor"
    ek = " — SAT bekliyor" if t["durum"] == "cikis_bekliyor" else ""
    return f"{ad} (turtle): giriş {fmt(t['giris'])}, stop {fmt(t['stop'])}{ek}"
