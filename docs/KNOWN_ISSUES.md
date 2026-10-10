# Known issues
- Diğer repolar içe aktarılmadı; onların sözdizimi/lint durumu denetlenemedi.
- `agents/kral_safe/assistant.py` `mem.db` dosyasını çalışma dizininde oluşturur (artık `.gitignore`'da).
- Android derlemesi bu ortamda çalıştırılmadı (Gradle/SDK yok).
- `android.yml` her push'ta çalışır ve gradle wrapper yoksa indirir; sabitlenmemiş.
- Drive yükleme betikleri gerçek hesapla denenmedi.
- Açık PR'lar #33 (offline çekirdek) ve #34 (monorepo iskeleti) benzer işi kapsar; birleştirmeden önce çakışmalar çözülmeli.
