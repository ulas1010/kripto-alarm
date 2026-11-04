"""
200 Günlük MA - Kırılım + Retest bildirim botu
Kural: 200 MA + Trend Onayı + Geri Çekilme (retest) Onayı

Her çalıştığında ma200_varliklar.txt'deki varlıkların günlük verisini çeker,
son KAPANMIŞ günlük muma bakar ve sinyal varsa Telegram'a mesaj atar.
"""
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import requests

# ---------------- Ayarlar ----------------
MA_LEN = 200            # hareketli ortalama uzunluğu
SLOPE_LEN = 20          # trend onayı: MA, bu kadar gün öncesinden yüksek olmalı
RETEST_WINDOW = 120     # kırılımdan sonra retest kaç gün içinde gelmeli
MIN_RUN_PCT = 5.0       # retest sayılması için fiyat önce MA'dan en az %X uzaklaşmalı
TOL_PCT = 2.0           # retest: mumun dibi MA'nın en fazla %X üstüne inmeli
NEAR_PCT = 3.0          # "yaklaşıyor" uyarısı: kapanış MA'ya %X yakın
STOP_BUF_PCT = 1.0      # stop: retest mumunun dibi / MA'nın %X altı
RR = 5.0                # risk/ödül oranı (hedef hesaplamak için)


def load_assets(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ma200_varliklar.txt")
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
    d["cross_up"] = d["above"] & ~d["above"].shift(1, fill_value=False)
    d["cross_dn"] = ~d["above"] & d["above"].shift(1, fill_value=False)
    # Trend onayı: MA yatay ya da yükseliyor (en fazla %0.5 düşüşe izin)
    d["ma_up"] = d["ma"] >= d["ma"].shift(SLOPE_LEN) * 0.995

    # Retest: kırılımdan sonra (pencere içinde) mum MA'ya inip üstünde yeşil kapatıyor
    touched = d["Low"] <= d["ma"] * (1 + TOL_PCT / 100)
    green = d["Close"] > d["Open"]
    d["retest_bar"] = d["above"] & d["ma_up"] & touched & green & ~d["cross_up"]

    last = d.iloc[-1]
    i = len(d) - 1
    sig = {"date": d.index[-1].date(), "close": float(last["Close"]),
           "ma": float(last["ma"]), "events": []}
    sig["dist_pct"] = (sig["close"] / sig["ma"] - 1) * 100

    if last["cross_up"]:
        sig["events"].append("KIRILIM_YUKARI")
    if last["cross_dn"]:
        sig["events"].append("KIRILIM_ASAGI")

    if last["retest_bar"]:
        # Son yukarı kırılım nerede? Pencere içinde mi ve o zamandan beri MA üstünde mi kaldı?
        ups = d.index[d["cross_up"]]
        if len(ups):
            j = d.index.get_loc(ups[-1])
            since = d.iloc[j:i + 1]
            # Gerçek retest: fiyat önce MA'dan en az %MIN_RUN_PCT uzaklaşmış olmalı,
            # sonra geri gelmeli. Uzaklaştığı ilk günü bul.
            run = (since["Close"] >= since["ma"] * (1 + MIN_RUN_PCT / 100)).to_numpy()
            if run[:-1].any():
                k = int(run.argmax())
                after_run = since.iloc[k:]
                # Uzaklaşmadan sonraki İLK retest mi? (bildirimi tekrar tekrar atmasın)
                first_retest = not after_run["retest_bar"].iloc[:-1].any()
            else:
                first_retest = False
            if (i - j) <= RETEST_WINDOW and since["above"].all() and first_retest:
                stop = min(float(last["Low"]), sig["ma"]) * (1 - STOP_BUF_PCT / 100)
                risk = sig["close"] - stop
                sig["stop"] = stop
                sig["target"] = sig["close"] + RR * risk
                sig["risk_pct"] = risk / sig["close"] * 100
                sig["days_since_break"] = i - j
                sig["events"].append("RETEST_AL")

    # Yaklaşma uyarısı (bilgi amaçlı): trendde, MA üstünde ve MA'ya çok yakın
    # Sadece bölgeye ilk girdiği gün bildir (her gün tekrar etmesin)
    prev = d.iloc[-2]
    prev_dist = (prev["Close"] / prev["ma"] - 1) * 100
    if (not sig["events"] and last["above"] and last["ma_up"]
            and 0 <= sig["dist_pct"] <= NEAR_PCT and prev_dist > NEAR_PCT):
        sig["events"].append("YAKLASIYOR")
    return sig


def fmt(x):
    return f"{x:,.2f}" if x >= 1 else f"{x:.6f}"


def build_message(symbol, s):
    lines = []
    for e in s["events"]:
        if e == "RETEST_AL":
            lines.append(
                f"🟢 *{symbol}* RETEST AL sinyali\n"
                f"Kırılımdan {s['days_since_break']} gün sonra 200 MA test edildi, üstünde kapattı.\n"
                f"Giriş: {fmt(s['close'])} | Stop: {fmt(s['stop'])} (-%{s['risk_pct']:.1f})\n"
                f"Hedef (1:{RR:g}): {fmt(s['target'])}")
        elif e == "KIRILIM_YUKARI":
            lines.append(f"📈 *{symbol}* 200 MA'yı YUKARI kırdı. Kapanış {fmt(s['close'])}, "
                         f"MA {fmt(s['ma'])}. Retest bekleniyor.")
        elif e == "KIRILIM_ASAGI":
            lines.append(f"📉 *{symbol}* 200 MA'nın ALTINA indi. Kapanış {fmt(s['close'])}, "
                         f"MA {fmt(s['ma'])}.")
        elif e == "YAKLASIYOR":
            lines.append(f"👀 *{symbol}* yükseliş trendinde 200 MA'ya yaklaşıyor "
                         f"(%{s['dist_pct']:.1f} uzakta). Olası retest.")
    return "\n".join(lines)


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[Telegram ayarlı değil]\n" + text)
        return
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
                      timeout=20)
    print("Telegram:", r.status_code)


def main():
    assets = load_assets()
    msgs, errors, summary = [], [], []
    for sym in assets:
        try:
            s = analyze(fetch(sym))
            if s is None:
                errors.append(sym)
                continue
            summary.append(f"{sym}: %{s['dist_pct']:+.1f}")
            if s["events"]:
                msgs.append(build_message(sym, s))
        except Exception as e:  # noqa
            errors.append(f"{sym} ({e.__class__.__name__})")

    always = os.environ.get("DAILY_SUMMARY", "0") == "1"
    if msgs or always:
        text = "\n\n".join(msgs) if msgs else "Bugün sinyal yok."
        if always:
            text += "\n\n_200 MA'ya uzaklık:_\n" + "\n".join(summary)
        if errors:
            text += "\n\n⚠️ Veri alınamadı: " + ", ".join(errors)
        send_telegram(text)
    else:
        print("Sinyal yok.", "Hatalar:", errors)


if __name__ == "__main__":
    sys.exit(main())
