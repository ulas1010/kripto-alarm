"""
Gerçek veriyle kuru çalıştırma: Telegram'a mesaj ATMAZ, durum.json'a yazmaz.
Son ~1 haftadaki Sweep → BOS → OTE kurulumlarını listeler ve grafiklerini çizer.
Çalıştır:  python testler/canli_kuru.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ayarlar  # noqa: E402
import tarayici as T  # noqa: E402

cikti = Path(__file__).resolve().parent / "_kuru"
cikti.mkdir(exist_ok=True)
toplam = {"kurulum": 0, "geldi": 0, "hedef": 0, "stop": 0, "acik": 0}
for sembol in ayarlar.OTE_SEMBOLLER:
    try:
        a = T.sembol_analiz(sembol)
    except Exception as e:  # noqa: BLE001
        print(f"!! {sembol} veri alınamadı: {e}")
        continue
    kaynak = {tf: df.attrs.get("kaynak") for tf, df in a["ltf"].items()}
    print(f"\n=== {sembol} fiyat {T.fmt(a['fiyat'])} | trend {a['trend']} | bölge {len(a['bolgeler'])} "
          f"(Efloud {sum('manuel' in b.kaynak for b in a['bolgeler'])}) | veri {kaynak}")
    for tf in ayarlar.OTE_ZAMAN_DILIMLERI:
        df = a["ltf"][tf]
        for k in T.ote_tara(df, tf, sembol, a["bolgeler"]):
            if k.stop_yuzde < ayarlar.OTE_MIN_STOP_YUZDE:
                continue
            toplam["kurulum"] += 1
            sonuc = ""
            if k.durum == "geldi":
                toplam["geldi"] += 1
                sonra = df.iloc[k.dolum_i:]
                uzun = k.yon == "long"
                sonuc = "açık"
                for _, m in sonra.iterrows():
                    if (m["low"] <= k.stop) if uzun else (m["high"] >= k.stop):
                        sonuc = "stop"
                        break
                    if (m["high"] >= k.tepe) if uzun else (m["low"] <= k.tepe):
                        sonuc = "hedef1"
                        break
                toplam[{"stop": "stop", "hedef1": "hedef", "açık": "acik"}[sonuc]] += 1
            _, teyit, zayif = T.ote_kontrol(k, a)
            print(f"  {tf} {k.yon:5} sweep {k.zaman(k.sweep_i)} BOS {k.zaman(k.bos_i)} | {k.durum:28} | "
                  f"OTE {T.fmt(k.ote[0])}-{T.fmt(k.ote[1])} stop {T.fmt(k.stop)} (%{k.stop_yuzde:.2f}) R {k.rr} | "
                  f"{k.bolge.etiket} | teyit {teyit}/3 zayıf {zayif} {('-> ' + sonuc) if sonuc else ''}")
            i = k.dolum_i if k.dolum_i is not None else k.bos_i
            T.grafik_ciz(df, T._ote_sinyal(k, i), a["bolgeler"],
                         f"{sembol} • {T.TF_ADI[tf]} • {k.yon.upper()} • {k.durum}",
                         cikti / f"{sembol}_{tf}_{k.yon}_{k.sweep_i}.png", ote=k.ote, tum_hedef=False, cizgi_bas=k.bos_i)
            if k.durum == "geldi":
                (cikti / f"{sembol}_{tf}_{k.yon}_{k.sweep_i}.txt").write_text(T.ote_geldi_metni(k, a, 0), encoding="utf-8")
print("\nÖZET:", toplam)
