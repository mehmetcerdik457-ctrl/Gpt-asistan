# Migration report
- Açık PR'lar kontrol edildi: #33, #34 (benzer kapsam, birleşmemiş), #35 (bu PR). Bu PR kendi dalından, mevcut `main` üzerinde çalıştı; #33/#34 içeriği alınmadı, çakışma riski var.
- Taşınan: `kral/safe/` -> `agents/kral_safe/` (`git mv`, geçmiş korunur). Veri kaybı yok.
- Eklenen: `core/`, `tests/`, `backup/`, `evidence/`, `scripts/validate_structure.sh`, `.github/workflows/backup-drive.yml`, docs, MANIFEST.
- Kökte bırakılan: Android `app/` (Gradle yolu).
- İçe aktarılmayan: diğer repolar (bu ortamda yalnızca bu repo klonlanabilir); tek tek içe aktarım sonraki adım.
- Doğrulama: `python -m unittest discover -s tests` (6 test geçti), `bash scripts/validate_structure.sh`.
- Sonraki adımlar: repoları `agents/`, `tools/`, `apps/` altına içe aktar; #33/#34 ile birleştir; Drive secret'larını ekle ve workflow'u çalıştır; lisans seç.
