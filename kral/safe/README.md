# Kral Asistan — GitHub/Codespaces özel AI konsolu

Bu klasör public repoya gizli prompt veya anahtar yazmadan, GitHub Codespaces terminali içinde çalışan kişisel AI konsoludur.

## En kısa kurulum

GitHub'da bu branch için Codespace oluştururken **New with options** akışını kullan. Devcontainer artık iki secret'ı önerir:

- \`OPENAI_API_KEY\`
- isteğe bağlı \`HUGGINGFACE_TOKEN\`

İkisinden biri yeterlidir. Değer GitHub Codespaces secret olarak saklanır ve kaynak dosyaya yazılmaz. Codespace açıldığında toolchain doğrulaması ve \`./kral-ai --status\` otomatik çalışır.

## GitHub içinden, terminal açmadan kullanma

Bu repository artık GitHub Copilot cloud agent için bir ana giriş ajanı içerir:

- `Kral GitHub Master`
- profil: `.github/agents/github-master-ai.agent.md`
- repo-wide davranış: `.github/copilot-instructions.md`

GitHub'da `github.com/copilot/agents` sayfasında bu repository'yi ve çalışmak istediğin branch'i seçip **Kral GitHub Master** ajanını çağırabilirsin. Ajan gerektiğinde Android, CI/CD, güvenlik, test, forensic, review ve release uzman ajanlarına delege eder; sonuçları tek cevapta birleştirir.

GitHub.com Copilot Chat içinde bu repository bağlamını eklediğinde `.github/copilot-instructions.md` otomatik bağlama girer. Böylece basit repo sorularında doğrudan chat, çok adımlı uygulama işlerinde ise Kral GitHub Master aynı control-plane kurallarını kullanır.

Bu GitHub-native mod için OpenAI veya Hugging Face anahtarı gerekmez. Dış model sağlayıcı anahtarları yalnız `./kral-ai` özel runtime'ını kullanmak istediğinde gerekir.

## Çalıştırma

\`\`\`bash
./kral-ai
\`\`\`

Tek seferlik soru:

\`\`\`bash
./kral-ai --ask "Bu repodaki açık güvenlik risklerini özetle."
\`\`\`

Durum:

\`\`\`bash
./kral-ai --status
\`\`\`

## Sağlayıcı seçimi

Varsayılan \`KRAL_PROVIDER=auto\` davranışı:

1. \`OPENAI_API_KEY\` varsa OpenAI Responses API kullanılır.
2. OpenAI anahtarı yoksa \`HUGGINGFACE_TOKEN\` / \`HF_TOKEN\` varsa Hugging Face Responses API kullanılır.
3. İkisi de yoksa fail-closed olur; sahte AI cevabı üretmez.

Varsayılan modeller:

- OpenAI: \`gpt-5.6-luna\`
- Hugging Face: \`openai/gpt-oss-20b:cheapest\`

İstenirse \`OPENAI_MODEL\`, \`HF_MODEL\` veya \`KRAL_PROVIDER\` environment variable olarak değiştirilebilir.

## Secret yerleşimi

API anahtarını dosyaya, APK'ya, issue yorumuna veya GitHub Actions loguna koyma.

Codespaces secret'ları yalnız yetkili Codespace'e environment variable olarak gelir. Bu repository secret değerlerini kaynakta tutmaz.

## Yerel hafıza

Chat ve \`/kaydet\` notları varsayılan olarak:

\`\`\`text
~/.local/share/kral-asistan/mem.db
\`\`\`

altında SQLite olarak tutulur. Klasör \`0700\`, veritabanı \`0600\` izinleriyle korunur; repository çalışma ağacında değildir ve Git'e commit edilmez.

Komutlar:

- \`/durum\`
- \`/kaydet <metin>\`
- \`/liste\`
- \`/soyle <metin>\`
- \`/cik\`

Son konuşma bağlamının modele gönderilen miktarı \`KRAL_CONTEXT_TURNS\` ile sınırlandırılır. Varsayılan 8 turdur; \`0\` verilirse önceki chat bağlamı modele gönderilmez.

## Güvenlik modeli

- Public GitHub Issue/PR yorumları AI prompt yüzeyi olarak kullanılmaz.
- Secret değerleri yazdırılmaz.
- API çağrısı yalnız HTTPS üzerinden provider endpoint'ine gider.
- AI sağlayıcısı yapılandırılmamışsa uygulama fail-closed olur.
- Yerel hafıza public repository içine yazılmaz.
- Hiçbir ücretli plan, trial veya GPU otomatik başlatılmaz.
