"""
⚡ KISA VADE (RSI-2) sinyali — ma200.py tarafından çağrılır, aynı varlıkları ve aynı Telegram botunu kullanır.

SİSTEM (Larry Connors RSI-2, backtest: backtest/ertesi_acilis_testi.py):
  Şart  : günlük kapanış 200 MA'nın üstünde (yükseliş trendi)
  Sinyal: RSI(2) < 5  (birkaç günlük sert geri çekilme)
  Giriş : sinyalden SONRAKİ gün açılışta al (bot sabah çalıştığı için)
  Stop  : giriş − 3 × ATR(14)  (felaket stopu, gün içinde)
  Çıkış : günlük kapanış 5 günlük ortalamanın üstüne çıkınca → ertesi açılışta sat
Backtest (13 varlık, 10 yıl, ertesi açılış, %0,1 maliyet/yön): 466 işlem, kazanma %68,
işlem başı +%0,79, medyan 4 gün, ilk 5 yıl +%0,69 / son 5 yıl +%0,89.

İşlem durumu ma200_durum.json içinde "<sembol>|RSI2" anahtarıyla tutulur:
  bekliyor        -> sinyal geldi, ertesi açılışta girilecek
  acik            -> pozisyonda
  cikis_bekliyor  -> çıkış sinyali geldi, ertesi açılışta satılacak
"""
import numpy as np
import pandas as pd

RSI_ESIK = 5
STOP_ATR = 3.0
RISK_YUZDE = 1.0        # kasanın yüzdesi (giriş ile stop arası)
POZ_MAX_YUZDE = 20.0    # tek pozisyon kasanın en fazla bu yüzdesi
MALIYET = 0.001         # sonuç hesabında her yön için (komisyon + kayma)
BT_OZET = ("10 yıl backtest (13 varlık, 466 işlem): kazanma %68, işlem başı ort. +%0,8, "
           "medyan 4 gün. Kazançlar küçük ve sık; ara sıra stop büyük olabilir.")


def gostergeler(d):
    c = d["Close"]
    dlt = c.diff()
    up = dlt.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    dn = (-dlt.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    d["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    d["sma5"] = c.rolling(5).mean()
    pc = c.shift(1)
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return d


def sinyal_var(d):
    son = d.iloc[-1]
    return bool(not np.isnan(son["ma"]) and not np.isnan(son["rsi2"])
                and son["Close"] > son["ma"] and son["rsi2"] < RSI_ESIK)


def yeni_islem(d):
    son = d.iloc[-1]
    return {"tip": "RSI2", "durum": "bekliyor", "sinyal_tarih": str(d.index[-1].date()),
            "atr3": float(STOP_ATR * son["atr14"]), "giris": None, "stop": None,
            "son_kontrol": str(d.index[-1].date())}


def _f(x, fmt):
    return fmt(x) if x is not None else "-"


def al_mesaji(ad, fmt, kasa, d, t):
    son = d.iloc[-1]
    c = float(son["Close"]); mesafe = t["atr3"]
    risk_usd = kasa * RISK_YUZDE / 100
    miktar = min(risk_usd / mesafe, kasa * POZ_MAX_YUZDE / 100 / c)
    return (
        f"⚡ *{ad} — KISA VADE AL* (RSI-2)\n"
        f"Trend yukarı (200 MA üstü) ama son günlerde sert geri çekildi: RSI(2) = {son['rsi2']:.1f}.\n\n"
        f"*Giriş:* bugün AÇILIŞTA al (son kapanış {fmt(c)})\n"
        f"*Stop:* giriş fiyatının {fmt(mesafe)} altı (3×ATR, ~%{mesafe / c * 100:.1f}) → kapanışa göre ~{fmt(c - mesafe)}\n"
        f"*Çıkış:* bot, günlük kapanış 5 günlük ortalamanın üstüne çıkınca \"SAT\" mesajı atar "
        f"(şu an ort. {fmt(float(son['sma5']))}). Genelde 2–6 gün sürer.\n\n"
        f"*Pozisyon* (kasa {kasa:,.0f}$, risk %{RISK_YUZDE:g} = {risk_usd:,.0f}$, en fazla %{POZ_MAX_YUZDE:g}):\n"
        f"Miktar ~{miktar:,.4f} | Değer ~{miktar * c:,.0f}$\n"
        f"_Kısa süreli olduğu için perp'te de olur; funding etkisi önemsiz._\n\n"
        f"_{BT_OZET}_"
    )


def yonet(ad, fmt, t, d):
    """RSI-2 işlemini son kontrolden sonraki mumlarla günceller -> (mesajlar, kapandı_mı)."""
    msgs = []
    for tarih, row in d[d.index > pd.Timestamp(t["son_kontrol"])].iterrows():
        gun = str(tarih.date())
        if t["durum"] == "cikis_bekliyor":
            px = float(row["Open"])
            t["cikis"] = px; t["kapanis"] = gun
            t["sonuc_pct"] = round((px / t["giris"] - 1 - 2 * MALIYET) * 100, 2)
            t["son_kontrol"] = gun
            return msgs, True          # sonuç SAT mesajında tahmini verildi; burada sessizce kaydedilir
        if t["durum"] == "bekliyor":
            t["giris"] = float(row["Open"]); t["stop"] = t["giris"] - t["atr3"]
            t["durum"] = "acik"; t["giris_tarih"] = gun
        if row["Low"] <= t["stop"]:
            px = min(float(row["Open"]), t["stop"])
            t["cikis"] = px; t["kapanis"] = gun
            t["sonuc_pct"] = round((px / t["giris"] - 1 - 2 * MALIYET) * 100, 2)
            t["son_kontrol"] = gun
            msgs.append(f"🔴 *{ad}* (kısa vade) STOP oldu ({fmt(px)}). Sonuç: *%{t['sonuc_pct']:+.2f}*")
            return msgs, True
        if row["Close"] > row["sma5"]:
            t["durum"] = "cikis_bekliyor"
            tahmini = (float(row["Close"]) / t["giris"] - 1) * 100
            msgs.append(f"🔵 *{ad}* (kısa vade) SAT: kapanış 5 günlük ortalamanın üstüne çıktı.\n"
                        f"→ Bugün AÇILIŞTA sat. Giriş {fmt(t['giris'])}, son kapanış {fmt(float(row['Close']))} "
                        f"(tahmini sonuç %{tahmini:+.1f})")
        t["son_kontrol"] = gun
    return msgs, False


def ozet_satiri(ad, fmt, t):
    if t["durum"] == "bekliyor":
        return f"{ad} (kısa vade): açılışta giriş bekleniyor"
    ek = " — SAT bekliyor" if t["durum"] == "cikis_bekliyor" else ""
    return f"{ad} (kısa vade): giriş {_f(t['giris'], fmt)}, stop {_f(t['stop'], fmt)}{ek}"
