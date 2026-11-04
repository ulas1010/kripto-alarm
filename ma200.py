"""
200 Günlük MA - Kırılım + Retest bildirim botu (karma çıkışlı sistem)

SİSTEM (10 yıllık backtest'te en kazançlı çıkan, bkz. backtest/ma200_cikis_testi.py):
  İki giriş türü (ikisi de aynı çıkış kurallarıyla yönetilir):
  KIRILIM AL: günlük kapanış 200 MA'nın üstüne çıktığı gün (ana giriş, %0,5 risk).
  RETEST AL : kırılımdan sonra fiyat MA'dan en az %5 uzaklaşır -> 120 gün içinde MA'ya
              geri gelir (%2 tolerans) ve yeşil mumla MA üstünde kapatır (MA yatay/yükselen)
              (kırılımı kaçırdıysan ya da ekleme için, %1 risk).
  Giriş = sinyal mumunun kapanışı.
  Stop  : min(sinyal mumunun dibi, MA) * 0.99  ->  1R = giriş - stop
  TP1   : 3R'de pozisyonun YARISI kapatılır, stop girişe (başabaş) çekilir.
  Kalan : günlük kapanış 200 MA'nın altına inince kapatılır (trendi sürer).

Bot her sabah son KAPANMIŞ günlük mumlara bakar. Yeni sinyal, TP1, stop ve çıkış
olaylarını Telegram'a yazar. Açık işlemler ma200_durum.json dosyasında tutulur.
"""
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import requests

KOK = os.path.dirname(os.path.abspath(__file__))
DURUM = os.path.join(KOK, "ma200_durum.json")

# ---------------- Sinyal ayarları ----------------
MA_LEN = 200            # hareketli ortalama uzunluğu
SLOPE_LEN = 20          # trend onayı: MA, 20 gün öncesinden düşük olmamalı
RETEST_WINDOW = 120     # kırılımdan sonra retest kaç gün içinde gelmeli
MIN_RUN_PCT = 5.0       # retest sayılması için fiyat önce MA'dan en az %X uzaklaşmalı
TOL_PCT = 2.0           # retest: mumun dibi MA'nın en fazla %X üstüne inmeli
NEAR_PCT = 3.0          # "yaklaşıyor" uyarısı: kapanış MA'ya %X yakın
STOP_BUF_PCT = 1.0      # stop: retest mumunun dibi / MA'nın %X altı

# ---------------- Çıkış ayarları ----------------
TP1_R = 3.0             # ilk kâr alma (pozisyonun yarısı)
TP1_ORAN = 0.5          # TP1'de kapatılacak kısım

# ---------------- Pozisyon büyüklüğü ----------------
KASA_USD = 1000.0       # işlem kasan (USD) — kendine göre değiştir
RISK_YUZDE = {"KIRILIM": 0.5, "RETEST": 1.0}   # işlem başına riske edilecek kasa yüzdesi (1R)

# Backtest özeti (mesajlarda gösterilir)
BT_OZET = {
    "KIRILIM": "10 yıl backtest (13 varlık, 308 işlem): kazanma %35, işlem başı ort. +1,3R. Çoğu işlem küçük stopla biter, kâr büyük trendlerden gelir.",
    "RETEST": "10 yıl backtest (13 varlık, 72 işlem): kazanma %49, işlem başı ort. +1,9R",
}
BASLIK = {"KIRILIM": "📈 *{} — KIRILIM AL* (200 MA)", "RETEST": "🟢 *{} — RETEST AL* (200 MA)"}

# Yahoo sembolü -> TxFlow / PopDEX adı
AD = {"GC=F": "XAU (Altın)", "SI=F": "XAG (Gümüş)", "CL=F": "CL (Petrol)",
      "BZ=F": "BRENT", "NG=F": "NATGAS", "HG=F": "XCU (Bakır)", "JPY=X": "USDJPY",
      "EURUSD=X": "EUR"}


def ad(sym):
    return AD.get(sym, sym.replace("-USD", ""))


def load_assets(path=None):
    path = path or os.path.join(KOK, "ma200_varliklar.txt")
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if line:
                out.append(line)
    return out


def fetch(symbol):
    import yfinance as yf
    df = yf.download(symbol, period="2y", interval="1d",
                     auto_adjust=False, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close"]].dropna()
    # Bugünün henüz kapanmamış mumunu at (kripto 7/24 işlem görür)
    today = datetime.now(timezone.utc).date()
    if len(df) and pd.Timestamp(df.index[-1]).date() >= today:
        df = df.iloc[:-1]
    return df


def analyze(df):
    """Son kapanmış mum için sinyalleri döndürür."""
    if df is None or len(df) < MA_LEN + SLOPE_LEN + 2:
        return None
    d = df.copy()
    d["ma"] = d["Close"].rolling(MA_LEN).mean()
    d["above"] = d["Close"] > d["ma"]
    valid = d["ma"].shift(1).notna()   # MA'nın ilk hesaplandığı gün kırılım sayılmaz
    d["cross_up"] = d["above"] & ~d["above"].shift(1, fill_value=False) & valid
    d["cross_dn"] = ~d["above"] & d["above"].shift(1, fill_value=False) & valid
    # Trend onayı: MA yatay ya da yükseliyor (en fazla %0.5 düşüşe izin)
    d["ma_up"] = d["ma"] >= d["ma"].shift(SLOPE_LEN) * 0.995

    touched = d["Low"] <= d["ma"] * (1 + TOL_PCT / 100)
    green = d["Close"] > d["Open"]
    d["retest_bar"] = d["above"] & d["ma_up"] & touched & green & ~d["cross_up"]

    last = d.iloc[-1]
    i = len(d) - 1
    sig = {"date": d.index[-1].date(), "close": float(last["Close"]),
           "ma": float(last["ma"]), "events": [], "d": d}
    sig["dist_pct"] = (sig["close"] / sig["ma"] - 1) * 100

    sig["ma_up"] = bool(last["ma_up"])
    if last["cross_up"]:
        sig["events"].append("KIRILIM_AL")
        sig["stop_kirilim"] = min(float(last["Low"]), sig["ma"]) * (1 - STOP_BUF_PCT / 100)
    if last["cross_dn"]:
        sig["events"].append("KIRILIM_ASAGI")

    if last["retest_bar"]:
        ups = d.index[d["cross_up"]]
        if len(ups):
            j = d.index.get_loc(ups[-1])
            since = d.iloc[j:i + 1]
            # Gerçek retest: fiyat önce MA'dan en az %MIN_RUN_PCT uzaklaşmış olmalı
            run = (since["Close"] >= since["ma"] * (1 + MIN_RUN_PCT / 100)).to_numpy()
            if run[:-1].any():
                k = int(run.argmax())
                after_run = since.iloc[k + 1:]   # uzaklaşma gününden SONRAKİ mumlar
                first_retest = not after_run["retest_bar"].iloc[:-1].any()
            else:
                first_retest = False
            if (i - j) <= RETEST_WINDOW and since["above"].all() and first_retest:
                stop = min(float(last["Low"]), sig["ma"]) * (1 - STOP_BUF_PCT / 100)
                sig["stop"] = stop
                sig["days_since_break"] = i - j
                sig["events"].append("RETEST_AL")

    prev = d.iloc[-2]
    prev_dist = (prev["Close"] / prev["ma"] - 1) * 100
    if (not sig["events"] and last["above"] and last["ma_up"]
            and 0 <= sig["dist_pct"] <= NEAR_PCT and prev_dist > NEAR_PCT):
        sig["events"].append("YAKLASIYOR")
    return sig


# ---------------- Yardımcılar ----------------
def fmt(x):
    if x >= 1000:
        return f"{x:,.0f}"
    if x >= 1:
        return f"{x:,.2f}"
    return f"{x:.6f}"


def r_sonuc(fiyat, t):
    return (fiyat - t["giris"]) / (t["giris"] - t["stop0"])


def durum_oku():
    try:
        with open(DURUM, encoding="utf-8") as f:
            s = json.load(f)
        for k in [k for k in s["acik"] if "|" not in k]:   # eski biçim -> RETEST
            s["acik"][k + "|RETEST"] = {"tip": "RETEST", **s["acik"].pop(k)}
        return s
    except (FileNotFoundError, json.JSONDecodeError):
        return {"acik": {}, "kapali": []}


def durum_yaz(s):
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1, default=str)


# ---------------- Mesajlar ----------------
def al_mesaji(sym, s, t):
    tip = t["tip"]
    risk = t["giris"] - t["stop0"]
    risk_pct = risk / t["giris"] * 100
    risk_usd = KASA_USD * RISK_YUZDE[tip] / 100
    miktar = risk_usd / risk
    deger = miktar * t["giris"]
    kaldirac = deger / KASA_USD
    return (
        BASLIK[tip].format(ad(sym)) + "\n"
        + (f"Kırılımdan {s['days_since_break']} gün sonra 200 MA test edildi, üstünde kapattı.\n\n"
           if tip == "RETEST" else
           f"Günlük kapanış 200 MA'nın üstüne çıktı (MA {'yükselen' if s['ma_up'] else 'düşen → olası trend dönüşü'}).\n\n")
        +
        f"*Giriş:* {fmt(t['giris'])}  _(günlük kapanış; fiyat bunun %1'den fazla üstündeyse kovalamak yerine geç)_\n"
        f"*Stop:* {fmt(t['stop0'])}  (−%{risk_pct:.1f})  → 1R = {fmt(risk)}\n"
        f"*TP1 ({TP1_R:g}R):* {fmt(t['tp1'])}  (+%{risk_pct * TP1_R:.1f}) → yarısını kapat, stopu girişe çek\n"
        f"*Kalan yarı:* günlük kapanış 200 MA altına inince kapat (MA şu an {fmt(s['ma'])})\n"
        f"Referans: 2R {fmt(t['giris'] + 2 * risk)} | 5R {fmt(t['giris'] + 5 * risk)}\n\n"
        f"*Pozisyon* (kasa {KASA_USD:,.0f}$, risk %{RISK_YUZDE[tip]:g} = {risk_usd:,.0f}$):\n"
        f"Miktar {miktar:,.4f} | Değer {deger:,.0f}$ | Kaldıraç ~{max(kaldirac, 1):.1f}x\n\n"
        f"_{BT_OZET[tip]}_"
    )


def islem_yonet(sym, t, d):
    """Açık işlemi son kontrol tarihinden sonraki mumlarla günceller. Mesaj listesi döndürür."""
    msgs = []
    son = pd.Timestamp(t["son_kontrol"])
    yeni = d[d.index > son]
    for tarih, row in yeni.iterrows():
        st = t["stop"]
        if row["Low"] <= st:
            cikis = min(float(row["Open"]), st)
            r_kalan = r_sonuc(cikis, t)
            if t["tp1_alindi"]:
                toplam = TP1_ORAN * TP1_R + (1 - TP1_ORAN) * r_kalan
                msgs.append(f"⚪ *{ad(sym)}* ({t['tip'].lower()}) kalan yarı başabaş stoptan çıktı ({fmt(cikis)}). "
                            f"İşlem sonucu: *{toplam:+.2f}R*")
            else:
                toplam = r_kalan
                msgs.append(f"🔴 *{ad(sym)}* ({t['tip'].lower()}) STOP oldu ({fmt(cikis)}). İşlem sonucu: *{toplam:+.2f}R*")
            t["sonuc_R"] = round(toplam, 2); t["kapanis"] = str(tarih.date())
            return msgs, True
        if not t["tp1_alindi"] and row["High"] >= t["tp1"]:
            t["tp1_alindi"] = True
            t["stop"] = t["giris"]
            msgs.append(f"🎯 *{ad(sym)}* ({t['tip'].lower()}) TP1 ({TP1_R:g}R) geldi: {fmt(t['tp1'])}\n"
                        f"→ Pozisyonun yarısını kapat (+{TP1_ORAN * TP1_R:.1f}R kasaya girdi), "
                        f"stopu girişe çek: {fmt(t['giris'])}\n"
                        f"→ Kalan yarı 200 MA altı günlük kapanışa kadar tutulur.")
            t["son_kontrol"] = str(tarih.date())
            continue
        if t["tp1_alindi"] and row["Close"] < row["ma"]:
            r_kalan = r_sonuc(float(row["Close"]), t)
            toplam = TP1_ORAN * TP1_R + (1 - TP1_ORAN) * r_kalan
            msgs.append(f"🏁 *{ad(sym)}* ({t['tip'].lower()}) günlük kapanış 200 MA altında ({fmt(row['Close'])}). "
                        f"Kalan yarıyı KAPAT.\nKalan yarı {r_kalan:+.2f}R | İşlem toplamı: *{toplam:+.2f}R*")
            t["sonuc_R"] = round(toplam, 2); t["kapanis"] = str(tarih.date())
            return msgs, True
        t["son_kontrol"] = str(tarih.date())
    return msgs, False


def bilgi_mesaji(sym, s, e, acik):
    if e == "KIRILIM_ASAGI" and not acik:
        return f"📉 *{ad(sym)}* 200 MA'nın ALTINA indi. Kapanış {fmt(s['close'])}, MA {fmt(s['ma'])}."
    if e == "YAKLASIYOR" and not acik:
        return (f"👀 *{ad(sym)}* yükseliş trendinde 200 MA'ya yaklaşıyor (%{s['dist_pct']:.1f} uzakta, "
                f"MA {fmt(s['ma'])}). Olası retest bölgesi.")
    return None


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[Telegram ayarlı değil]\n" + text)
        return
    for parca in [text[i:i + 3900] for i in range(0, len(text), 3900)]:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": parca, "parse_mode": "Markdown"},
                          timeout=20)
        if r.status_code != 200:   # Markdown hatasında düz metin dene
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              data={"chat_id": chat, "text": parca}, timeout=20)
        print("Telegram:", r.status_code)


def main():
    assets = load_assets()
    durum = durum_oku()
    msgs, errors, summary = [], [], []
    for sym in assets:
        try:
            s = analyze(fetch(sym))
            if s is None:
                errors.append(sym)
                continue
            d = s["d"]
            summary.append(f"{ad(sym)}: %{s['dist_pct']:+.1f}")

            # 1) Açık işlemleri yönet (KIRILIM ve RETEST ayrı ayrı)
            for tip in ("KIRILIM", "RETEST"):
                key = f"{sym}|{tip}"
                t = durum["acik"].get(key)
                if t:
                    m, kapandi = islem_yonet(sym, t, d)
                    msgs += m
                    if kapandi:
                        durum["kapali"].append({"varlik": sym, **t})
                        del durum["acik"][key]
            acik_var = any(k.startswith(sym + "|") for k in durum["acik"])

            # 2) Yeni sinyaller
            for e in s["events"]:
                if e in ("KIRILIM_AL", "RETEST_AL"):
                    tip = e.split("_")[0]
                    key = f"{sym}|{tip}"
                    if key in durum["acik"]:
                        msgs.append(f"ℹ️ *{ad(sym)}* yeni {tip.lower()} sinyali var ama aynı türde açık işlem zaten var, atlandı.")
                        continue
                    giris = s["close"]
                    stop = s["stop_kirilim"] if tip == "KIRILIM" else s["stop"]
                    if stop >= giris:
                        continue
                    t = {"tip": tip, "tarih": str(s["date"]), "giris": giris, "stop0": stop, "stop": stop,
                         "tp1": giris + TP1_R * (giris - stop), "tp1_alindi": False,
                         "son_kontrol": str(s["date"])}
                    durum["acik"][key] = t
                    msgs.append(al_mesaji(sym, s, t))
                else:
                    m = bilgi_mesaji(sym, s, e, acik_var)
                    if m:
                        msgs.append(m)
        except Exception as e:  # noqa
            errors.append(f"{sym} ({e.__class__.__name__}: {e})")

    durum_yaz(durum)

    always = os.environ.get("DAILY_SUMMARY", "0") == "1"
    if msgs or always:
        text = "\n\n".join(msgs) if msgs else "Bugün 200 MA sinyali yok."
        if always:
            text += "\n\n_200 MA'ya uzaklık:_\n" + "\n".join(summary)
            if durum["acik"]:
                text += "\n\n_Açık işlemler:_\n" + "\n".join(
                    f"{ad(k.split('|')[0])} ({v['tip'].lower()}): giriş {fmt(v['giris'])}, stop {fmt(v['stop'])}"
                    + (" (TP1 alındı)" if v["tp1_alindi"] else f", TP1 {fmt(v['tp1'])}")
                    for k, v in durum["acik"].items())
        if errors:
            text += "\n\n⚠️ Veri alınamadı: " + ", ".join(errors)
        send_telegram(text)
    else:
        print("Sinyal yok.", "Hatalar:", errors)


if __name__ == "__main__":
    sys.exit(main())
