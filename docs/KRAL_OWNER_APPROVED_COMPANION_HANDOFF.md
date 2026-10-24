# User-approved handoff to existing signed Owner Companion

Existing KRAL PR #46; reuse the already installed, signed Owner Companion
1.5.4/VC12 rather than reimplementing its existing UI and Bridge runtime.

The KRAL screen adds a button **Doğrulanmış Owner Companion'ı aç (izinli)**.
It only displays the handoff if both the configured Owner application
package and exact version+single Gen2 signing certificate were verified by
the existing `OwnerStatus` verifier. An explicit confirmation is mandatory
before `startActivity` launches the existing Owner 1.5.4 activity. The
identity is **rechecked** immediately before the start.

Missing Owner, old 1.5.0/1.5.1, bad signer, ambiguous signer or absent
launcher → no action, a readable explanation. A correctly signed installed
Bridge is displayed as information only and is NOT automatically installed,
granted Accessibility, launched, paired, or used for any device command.

No new Android permissions or manifests are needed; both package queries
were already present. No owner enrollment, model egress, real phone proof,
silent CİHAT access, Google Drive read at runtime, or cryptographic key
export. This is a safer navigational reuse of existing signed app binaries;
the existing Preview APK remains debug-signed and must never overwrite
the preserved signed Owner/Bridge.
