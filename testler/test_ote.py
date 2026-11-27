"""
Sweep → BOS → OTE kuralının yapay veriyle testi (internet gerekmez).
Çalıştır:  python testler/test_ote.py
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ayarlar  # noqa: E402
import tarayici as T  # noqa: E402


def seri(yollar, bitis_simdi=True, tf_dk=15):
    """Kapanış yolundan OHLC mumları üretir. yollar: [(hedef_kapanis, mum_sayisi), ...]"""
    kap = [100.0]
    for hedef, adet in yollar:
        bas = kap[-1]
        kap += list(np.linspace(bas, hedef, adet + 1)[1:])
    kap = np.array(kap)
    o = np.r_[kap[0], kap[:-1]]
    h = np.maximum(o, kap) + 0.15
    l = np.minimum(o, kap) - 0.15
    n = len(kap)
    son = pd.Timestamp.now(tz="UTC").floor(f"{tf_dk}min") - pd.Timedelta(minutes=tf_dk)
    t = pd.date_range(end=son, periods=n, freq=f"{tf_dk}min")
    return pd.DataFrame(dict(t=t, open=o, high=h, low=l, close=kap, volume=1.0))


def long_ornek():
    # düşüş → dip (90) → tepki tepe (95) → tekrar düşüş, sweep fitili 89'a, kapanış 90.6 → BOS 95 üstü → tepe ~99
    df = seri([(100, 30), (92, 20), (90, 6), (95, 8), (91.5, 8), (90.6, 1), (93, 4), (96, 3), (99, 6)])
    sw = 30 + 20 + 6 + 8 + 8 + 1  # sweep mumu (90.6 kapanışlı)
    df.loc[sw, "low"] = 89.0
    return df, sw


def ote_ekle(df, hedef, adet=5):
    """Seriye OTE'ye kadar geri çekilme ekler."""
    son = df["close"].iloc[-1]
    kap = np.linspace(son, hedef, adet + 1)[1:]
    o = np.r_[son, kap[:-1]]
    ek = pd.DataFrame(dict(t=0, open=o, high=np.maximum(o, kap) + 0.1, low=np.minimum(o, kap) - 0.1, close=kap, volume=1.0))
    df = pd.concat([df, ek], ignore_index=True)
    df["t"] = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("15min") - pd.Timedelta(minutes=15),
                            periods=len(df), freq="15min")
    return df


def ayna(df):
    """Fiyatı 200'e göre ters çevirir: long kurulumu short kurulumuna dönüşür."""
    d = df.copy()
    d["open"], d["close"] = 200 - df["open"], 200 - df["close"]
    d["high"], d["low"] = 200 - df["low"], 200 - df["high"]
    return d


def bolge(alt, ust, rol=""):
    return T.Bolge(alt, ust, 9, {"manuel"}, ozel_etiket="⭐ Test bölgesi", rol=rol)


hatalar = []


def kontrol(kosul, mesaj):
    print(("OK   " if kosul else "HATA ") + mesaj)
    if not kosul:
        hatalar.append(mesaj)


# 1) LONG: kırılım taze, henüz OTE yok
df, sw = long_ornek()
B = [bolge(88.5, 90.5, "destek")]
kur = [k for k in T.ote_tara(df, "15m", "TESTUSDT", B) if k.yon == "long"]
kontrol(len(kur) == 1, f"long kurulum bulundu ({len(kur)})")
k = kur[0]
kontrol(abs(k.seviye - (90 - 0.15)) < 0.2 and k.sweep_i == sw, f"sweep doğru mumda (seviye {k.seviye:.2f}, mum {k.sweep_i})")
kontrol(abs(k.uc - 89.0) < 0.01, f"sweep ucu fitilin ucu ({k.uc:.2f})")
kontrol(94.5 < k.bos_seviye < 95.5, f"BOS seviyesi son kısa vadeli tepe ({k.bos_seviye:.2f})")
kontrol(k.durum == "bekliyor", f"OTE henüz gelmedi ({k.durum})")
a1, a2 = k.ote
beklenen_g = k.tepe - 0.705 * (k.tepe - k.uc)
kontrol(abs(k.giris - beklenen_g) < 1e-9 and a1 < k.giris < a2, f"OTE {a1:.2f}–{a2:.2f}, giriş {k.giris:.2f}")
kontrol(k.stop < k.uc, f"stop sweep dibinin altında ({k.stop:.2f} < {k.uc:.2f})")

# 2) LONG: fiyat OTE'ye geldi
df2 = ote_ekle(df, k.giris - 0.2)
k2 = [x for x in T.ote_tara(df2, "15m", "TESTUSDT", B) if x.yon == "long"][0]
kontrol(k2.durum == "geldi" and k2.dolum_i is not None, f"OTE dolumu ({k2.durum}, mum {k2.dolum_i})")
kontrol(k2.rr > 1.5, f"Hedef 1 = kırılım sonrası tepe, R {k2.rr}")

# 3) Gövde dibin altında kapanırsa kurulum yok
df3 = df.copy()
df3.loc[sw, "close"] = 89.4
kontrol(not [x for x in T.ote_tara(df3, "15m", "TESTUSDT", B) if x.yon == "long"], "gövde altta kapanınca sweep sayılmadı")

# 4) Bölge dışında sweep → kurulum yok
kontrol(not [x for x in T.ote_tara(df, "15m", "TESTUSDT", [bolge(60, 61)]) if x.yon == "long"], "bölge dışındaki sweep yok sayıldı")

# 5) Direnç rolündeki Efloud bölgesinde long aranmaz
kontrol(not [x for x in T.ote_tara(df, "15m", "TESTUSDT", [bolge(88.5, 90.5, "direnç")]) if x.yon == "long"], "dirençte long aranmadı")

# 6) SHORT: aynı serinin aynası
dfs = ayna(df2)
Bs = [bolge(200 - 90.5, 200 - 88.5, "direnç")]
ks = [x for x in T.ote_tara(dfs, "15m", "TESTUSDT", Bs) if x.yon == "short"]
kontrol(len(ks) == 1, f"short kurulum bulundu ({len(ks)})")
if ks:
    s = ks[0]
    kontrol(abs(s.giris - (200 - k2.giris)) < 1e-6 and abs(s.stop - (200 - k2.stop)) < 1e-6 and s.durum == "geldi",
            f"short seviyeleri long'un aynası (giriş {s.giris:.2f}, stop {s.stop:.2f})")

# 7) Uçtan uca: mesajlar, grafik, kâğıt takip, aynı mesajı ikinci kez atmama
eski = ayarlar.OTE_SEMBOLLER
ayarlar.OTE_SEMBOLLER = ["TESTUSDT"]
h4 = df2.set_index("t").resample("4h", label="left", origin="epoch").agg(
    dict(open="first", high="max", low="min", close="last", volume="sum")).dropna().reset_index()
an = {"TESTUSDT": dict(ltf={"15m": df}, htf={"4h": h4}, bolgeler=B, trend="düşüş", trend_4s="düşüş", fiyat=float(df["close"].iloc[-1]))}
durum = {"gonderilen": [], "kagit": {"sayac": 0, "acik": [], "kapali": []}}
gonderilen = set()
tg = T.Telegram(None, None)
with tempfile.TemporaryDirectory() as g:
    g = Path(g)
    an["TESTUSDT"]["ltf"]["15m"] = df.iloc[:k.bos_i + 1].copy().assign(
        t=pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("15min") - pd.Timedelta(minutes=15), periods=k.bos_i + 1, freq="15min"))
    n1, n2 = T.ote_alarm_tara(tg, an, durum, g, gonderilen, gonderilen.add)
    kontrol((n1, n2) == (1, 0), f"1/2 mesajı gönderildi ({n1}, {n2})")
    an["TESTUSDT"]["ltf"]["15m"] = df2
    n1, n2 = T.ote_alarm_tara(tg, an, durum, g, gonderilen, gonderilen.add)
    kontrol((n1, n2) == (0, 1), f"2/2 mesajı gönderildi ({n1}, {n2})")
    kontrol(len(durum["kagit"]["acik"]) == 1 and durum["kagit"]["acik"][0]["yapi"] == "ote", "kâğıt takip açıldı")
    n1, n2 = T.ote_alarm_tara(tg, an, durum, g, gonderilen, gonderilen.add)
    kontrol((n1, n2) == (0, 0), "aynı mesaj ikinci kez gönderilmedi")
    kontrol(len(list(g.glob("ote*.png"))) == 2, "iki grafik çizildi")
    # kâğıt takip: fiyat hedefe giderse kapanır
    tepe = durum["kagit"]["acik"][0]["tp1"]
    df4 = ote_ekle(df2, tepe + 1, adet=8)
    an["TESTUSDT"]["ltf"]["15m"] = df4
    kap = T.kagit_guncelle(tg, an, durum)
    kontrol(kap == 1 and durum["kagit"]["kapali"][-1]["sonuc"] == "hedef1", "kâğıt takip hedefte kapandı")
    import shutil
    for f in g.glob("ote*.png"):
        shutil.copy(f, Path(__file__).parent / f"_ornek_{f.name}")
ayarlar.OTE_SEMBOLLER = eski

print()
print("SONUÇ:", "tüm testler geçti" if not hatalar else f"{len(hatalar)} hata")
sys.exit(1 if hatalar else 0)
