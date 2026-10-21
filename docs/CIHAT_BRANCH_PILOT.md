# KRAL GitHub branch pilot — Issue #40

Bu tek-seferlik kanıt testi `main` dalını veya mevcut APK'yı değiştirmez. Yalnızca `integration/cihat-github-task-bridge-20261021` dalına `.github/workflows/kral-branch-pilot.yml` eklendiğinde tetiklenir. Böylece varsayılan daldaki `issues` workflow'unun beklemesini aşarak, henüz merge yapılmadan **GitHub Actions'ın gerçekten Issue #40'a test kanıtı gönderip gönderemediğini** sınar.

Yalnız belirtilen repo ve dal, kaynak dalına push yapan owner GitHub aktörü, tek sabit Issue #40 ve o issue'nun `[KRAL-CHECK] ` başlığı kabul edilir. Workflow issue içeriğinden komut çalıştırmaz. Sabit `python -m unittest discover -s server/tests -v` testleri PASS olmazsa hiçbir başarı yorumu yazılmaz. Test sayı ve commit bilgisi gerçek koşumun logundan gelir. Model anahtarı gerekmez.

Bu pilot CİHAT AI 3.2.1'in canlı backend/modelini çalıştırmaz, telefon eylemine yetki vermez ve OMEGA'nın Owner + cihaz imza mekanizmasını atlamaz. Nihai sürekli görev mimarisi için taslak PR onaylı şekilde varsayılan dala alınmalı ve canlı model bağlantısı ayrıca doğrulanmalıdır.
