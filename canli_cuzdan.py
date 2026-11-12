"""
WinningCircle Canlı Cüzdan takibi

https://www.winningcircle.io/canlicuzdan sayfasının kullandığı veriyi okur, bir önceki
durumla karşılaştırır ve değişiklikleri aynı Telegram botundan bildirir:
  AÇILDI      : yeni bir pozisyon göründü
  ARTIRILDI / AZALTILDI : açık pozisyonun büyüklüğü değişti
  KAPANDI     : geçmiş işlemlere yeni bir kayıt düştü (PnL ile)

Görülen durum canli_cuzdan_durum.json dosyasında tutulur. İlk çalıştırmada eski işlemler
gönderilmez; sadece o anki açık pozisyonların özeti gelir.

Not: Bu bir kopyalama (copy trade) sinyali değildir, sadece "şu hesapta şu oldu" bildirimi.
Bot 15 dakikada bir çalıştığı için bildirim gecikmeli gelir.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

ADRES = "https://www.winningcircle.io/api/efe-yolda/okx"
KOK = os.path.dirname(os.path.abspath(__file__))
DURUM = os.path.join(KOK, "canli_cuzdan_durum.json")
TR_SAAT = timezone(timedelta(hours=3))

HESAP = {"manual": "Efe Bulduk", "bot": "Oslo Bot"}
# Büyüklük en az bu kadar (%) değişmeden "artırıldı/azaltıldı" mesajı gönderilmez
MIN_DEGISIM_YUZDE = 2.0
NOT = "<i>Bilgi amaçlıdır, yatırım tavsiyesi değildir. Bildirim 15 dk'ya kadar gecikebilir.</i>"


def fmt(x, hane=None):
    """1234567.891 -> 1.234.567,89 ; küçük fiyatlarda daha çok hane."""
    x = float(x)
    if hane is None:
        hane = 2 if abs(x) >= 100 else 4 if abs(x) >= 1 else 6
    s = f"{x:,.{hane}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def isaretli(x):
    return ("+" if x >= 0 else "-") + "$" + fmt(abs(x), 2)


def varlik(inst_id):
    return inst_id.replace("-SWAP", "")


def anahtar(p):
    return f"{p.get('account')}|{p.get('instId')}|{p.get('side')}"


def baslik(p):
    k = p.get("lever") or 0
    kaldirac = f" {k:g}x" if k else ""
    return (f"{HESAP.get(p.get('account'), p.get('account'))} · "
            f"<b>{varlik(p['instId'])} {p['side'].upper()}</b>{kaldirac}")


def veri_cek():
    r = requests.get(ADRES, timeout=30, headers={"User-Agent": "Mozilla/5.0 (kripto-alarm)",
                                                 "Accept": "application/json"})
    r.raise_for_status()
    v = r.json()
    if not v.get("ok") or not isinstance(v.get("positions"), list) or not isinstance(v.get("history"), list):
        raise ValueError("beklenmeyen cevap")
    return v


def durum_oku():
    try:
        with open(DURUM, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def durum_yaz(d):
    d["gorulen"] = d["gorulen"][-500:]
    with open(DURUM, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


def pozisyon_satiri(p):
    return (f"{baslik(p)}\nGiriş: {fmt(p['avgPx'])} · Güncel: {fmt(p['markPx'])}\n"
            f"Büyüklük: ${fmt(p['notionalUsd'], 2)} · Açık PnL: {isaretli(p['upl'])}")


def kapanis_mesaji(h):
    kazanc = h.get("pnl", 0) >= 0
    kismi = " (kısmi)" if h.get("partial") else ""
    giris = f"Giriş: {fmt(h['avgPx'])} · " if h.get("avgPx") else ""
    oran = f" ({h['pnlRatio']:+.2f}%)".replace(".", ",") if h.get("pnlRatio") else ""
    return (f"{'✅' if kazanc else '❌'} <b>CANLI CÜZDAN — KAPANDI{kismi}</b>\n{baslik(h)}\n"
            f"{giris}Çıkış: {fmt(h['closePx'])}\nSonuç: <b>{isaretli(h['pnl'])}</b>{oran}")


def karsilastir(eski, v):
    """Eski durum ile yeni veriyi karşılaştırır -> (mesajlar, yeni durum)."""
    yeni_poz = {anahtar(p): p for p in v["positions"]}
    gorulen = set(eski["gorulen"])
    msgs = []

    for k, p in yeni_poz.items():
        e = eski["pozisyonlar"].get(k)
        if e is None:
            msgs.append("🔔 <b>CANLI CÜZDAN — AÇILDI</b>\n" + pozisyon_satiri(p))
        elif e.get("pos"):
            degisim = (p["pos"] - e["pos"]) / e["pos"] * 100
            if abs(degisim) >= MIN_DEGISIM_YUZDE:
                olay = "ARTIRILDI" if degisim > 0 else "AZALTILDI"
                msgs.append(f"{'➕' if degisim > 0 else '➖'} <b>CANLI CÜZDAN — {olay}</b> "
                            f"({degisim:+.0f}%)\n" + pozisyon_satiri(p))
            else:
                p = {**p, "pos": e["pos"]}   # küçük değişimler birikip eşiği geçebilsin
                yeni_poz[k] = p

    yeni_kayitlar = [h for h in v["history"] if h.get("id") and h["id"] not in gorulen]
    for h in sorted(yeni_kayitlar, key=lambda h: h.get("closedAt", 0)):
        msgs.append(kapanis_mesaji(h))

    # Listeden çıkan ama geçmişe henüz düşmeyen pozisyon
    kapanan = {anahtar(h) for h in yeni_kayitlar}
    for k, e in eski["pozisyonlar"].items():
        if k not in yeni_poz and k not in kapanan:
            msgs.append(f"ℹ️ <b>CANLI CÜZDAN — KAPANDI</b>\n{baslik(e)}\nSonuç geçmiş işlemlere düşünce ayrıca bildirilecek.")

    yeni = {"pozisyonlar": {k: {a: p.get(a) for a in ("account", "instId", "side", "pos", "avgPx", "lever")}
                            for k, p in yeni_poz.items()},
            "gorulen": eski["gorulen"] + [h["id"] for h in yeni_kayitlar]}
    return msgs, yeni


def ilk_mesaj(v):
    satirlar = [pozisyon_satiri(p) for p in v["positions"]] or ["Şu an açık işlem yok."]
    return ("👀 <b>Canlı Cüzdan takibi başladı</b>\n"
            f"Toplam: ${fmt(v['totalEq'], 2)} ({isaretli(v['change'])})\n\n" + "\n\n".join(satirlar))


def send_telegram(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[Telegram ayarlı değil]\n" + text + "\n")
        return
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data=dict(chat_id=chat, text=text, parse_mode="HTML",
                                disable_web_page_preview=True), timeout=30)
    print("Telegram:", r.status_code)
    r.raise_for_status()


def main():
    try:
        v = veri_cek()
    except Exception as e:  # noqa: BLE001
        # Veri gelmezse durum dosyasına dokunma: yanlış "kapandı" mesajı gitmesin
        print(f"Canlı cüzdan verisi alınamadı ({e.__class__.__name__}: {e})")
        return 0

    eski = durum_oku()
    if eski is None:
        yeni = {"pozisyonlar": {}, "gorulen": [h["id"] for h in v["history"] if h.get("id")]}
        _, yeni = karsilastir(yeni, v)
        msgs = [ilk_mesaj(v)]
    else:
        msgs, yeni = karsilastir(eski, v)

    if msgs:
        send_telegram("\n\n".join(msgs) + "\n\n" + NOT)
    else:
        print("Canlı cüzdan: değişiklik yok.")
    yeni["son_kontrol"] = datetime.now(TR_SAAT).strftime("%Y-%m-%d %H:%M")
    ayni = eski is not None and all(eski.get(a) == yeni.get(a) for a in ("pozisyonlar", "gorulen"))
    if msgs or not ayni:
        durum_yaz(yeni)   # değişiklik yoksa dosyayı yazma: her 15 dakikada boş commit oluşmasın
    return 0


if __name__ == "__main__":
    sys.exit(main())
