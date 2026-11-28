# ORBA / KRAL Genesis — offline Play release and revenue readiness

Read-only source and optional AAB audit. No app upload, live Play Console session, banking access, registration, payment or AdMob account changes.

## Usage

    python3 scripts/orba_play_preflight.py --repo-root . --output orba-preflight.json
    python3 scripts/orba_play_preflight.py --repo-root . --aab /path/to/existing/app-release.aab --strict
    python3 -m unittest discover -s server/tests -p test_orba_play_preflight.py -v

Default exit 0 means the read-only report was produced, **not** that publishing is ready. --strict exits 2 while required external-account evidence is unknown; parse errors return 1. This tool never builds, signs or publishes an artifact and never reads signing secrets.

## Check boundaries

| Category | Result source | What it does not prove |
| --- | --- | --- |
| Package, version, target SDK, release debug flags | Gradle configuration | ORBA registered package or upload approval |
| Declared Android permissions | AndroidManifest.xml | Completed Data Safety form |
| Mobile Ads / Play Billing dependency presence | Gradle dependency strings | App monetization or payout approval |
| AAB JAR signing, when existing AAB supplied | jarsigner -verify -verbose | Play upload signing-key match or Play App Signing enrollment |
| Real developer identity and app inventory | External account | NOT_CHECKED by this tool |
| Google Payments merchant, payout bank, tax status | External account | NOT_CHECKED by this tool |
| AdMob account, real ad IDs, app-ads.txt | External account | NOT_CHECKED by this tool |
| Public privacy policy, consent, physical phone | External evidence | NOT_CHECKED by this tool |

## Release gates (evidence required, never invented)

1. Verify the current ORBA developer account and the application's exact package ID in an authenticated Play Console session. Account IDs, personal emails, card numbers and IBANs belong in private evidence only.
2. Confirm the enrolled Play upload certificate before signing a release AAB; debug and unsigned AAB files are not production-ready. Keep all current user's device data intact.
3. Confirm identity/phone/device verification, testing access, linked merchant/payment profile and payout account using only masked status fields.
4. Prepare public privacy policy, product and support site, accurate Data Safety disclosure, screenshots and store listing. Validate against actually deployed models and data flows.
5. Confirm the user's pricing and business model before first publication. Free Play downloads cannot later become paid downloads under the same package ID. Play Billing concerns qualifying in-app digital purchases; paid-download apps do not universally need Play Billing.
6. For advertising, verify a real AdMob account and publisher ID, user consent flows and app-ads.txt. Do not fabricate IDs or create an advertising campaign.
7. All existing source, signing materials, GitHub main and installed APKs are preserved. This branch does not merge or start release workflows.

KRAL source PR: https://github.com/mehmetcerdik457-ctrl/Gpt-asistan/pull/92
Google Play Data Safety: https://support.google.com/googleplay/android-developer/answer/10787469
Google Play pricing: https://support.google.com/googleplay/android-developer/answer/6334373

Production status remains BLOCKED until authenticated account evidence, compatible owner signing and permitted release are verified.
