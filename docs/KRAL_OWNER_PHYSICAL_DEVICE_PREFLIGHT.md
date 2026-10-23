# KRAL physical-device readiness check, no key generation

Existing PR46 Android app now has an Owner cihaz ön kontrolü button.
The user may inspect local device-lock status and existing AndroidKeyStore
owner and device aliases, including KeyInfo user-authentication requirement
and EC P-256 type. No key is generated, deleted, signed, enrolled, transmitted,
or uploaded by this preflight. Unknown or inaccessible keys are displayed as
UNVERIFIED; existing keys do not establish server-side Owner approval.

The existing public-registration UI is unchanged functionally except that
debug-preview users receive an explicit second warning before any new
persistent key is generated. An ephemeral CI debug-signing identity cannot
be considered suitable for long-term authenticated Owner enrollment.

No backend enrollment/write, provider activation, model egress or production
signer is introduced. Full acceptance still needs a stable release signer,
actual Owner phone, secure server registration and live integration.
