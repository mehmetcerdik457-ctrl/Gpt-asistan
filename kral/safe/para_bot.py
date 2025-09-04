# -*- coding: utf-8 -*-
import os, datetime, time, argparse
from duckduckgo_search import DDGS

QUERIES = [
  "freelance yazılım işi", "uzaktan android geliştirici",
  "wordpress site yaptırmak istiyorum", "e-ticaret ürün listeleme işi",
  "video altyazı çeviri türkçe", "ses deşifre işi türkçe"
]
PER_QUERY_LIMIT = 5
OUTDIR = "kral/para"; os.makedirs(OUTDIR, exist_ok=True)

def search_all():
    day = datetime.datetime.now().strftime("%Y%m%d")
    md = os.path.join(OUTDIR, f"gunluk-{day}.md")
    with open(md,"a",encoding="utf-8") as f:
        f.write(f"\n\n# {datetime.datetime.now():%Y-%m-%d %H:%M} Günlük fırsatlar\n")
        for q in QUERIES:
            f.write(f"\n## {q}\n")
            try:
                cnt=0
                for r in DDGS().text(q, region="tr-tr", safesearch="moderate"):
                    f.write(f"- **{r.get('title','')}**\n  {r.get('href','')}\n  {r.get('body','')}\n")
                    cnt+=1
                    if cnt>=PER_QUERY_LIMIT: break
                if cnt==0: f.write("- Sonuç bulunamadı.\n")
            except Exception as e:
                f.write(f"- Arama hatası: {repr(e)}\n")
    taslak=os.path.join(OUTDIR,"mail-taslak.txt")
    with open(taslak,"w",encoding="utf-8") as f:
        f.write("""Konu: Hızlı ve uygun maliyetli çözüm için teklif

Merhaba,
İlanınızı gördüm. Kısa sürede kaliteli teslimat yapabilirim.
- Android/WordPress/Python/Çeviri
- Hızlı iletişim, şeffaf teslim
Bugün küçük bir deneme ile başlayalım mı?
Saygılarımla,
Mehmet
""")
    print("✓ Güncellendi:", md, taslak)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--once",action="store_true")
    args=ap.parse_args()
    if args.once: search_all()
    else:
        print("Kral Para Botu: her 60 dk çalışıyor (Ctrl+C ile çıkış)")
        while True: search_all(); time.sleep(3600)
