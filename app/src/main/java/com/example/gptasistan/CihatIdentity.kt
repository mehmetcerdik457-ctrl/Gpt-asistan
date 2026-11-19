package com.example.gptasistan

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import java.security.MessageDigest

/**
 * Strict forensic-reference verifier for the *existing* CİHAT 3.2.1 APK.
 *
 * Certificate/version evidence comes from the preserved 3.2.1 (893) static
 * forensic verification report; this is application identification only.
 * A verified package does NOT establish Owner identity, API access, model
 * availability or permission to operate CİHAT without user confirmation.
 */
object CihatIdentity {
    const val PACKAGE_NAME = CihatHandoff.PACKAGE_NAME
    const val EXPECTED_VERSION_CODE = 893L
    const val FORENSIC_SIGNER_SHA256 =
        "7b4a4b483ad4fdfa7bcab3c4ba9fd5a0461cab208fc7120a4d8d2f4901b3a097"

    enum class State {
        VERIFIED_321, NOT_INSTALLED, VERSION_MISMATCH, SIGNER_MISMATCH,
        NOT_LAUNCHABLE, UNAVAILABLE
    }

    data class Result(
        val state: State,
        val versionCode: Long? = null,
        val signerSha256: String? = null
    ) {
        val verified: Boolean get() = state == State.VERIFIED_321
        fun report(): String = buildString {
            append("CİHAT 3.2.1 uygulama kimliği: ")
            append(state.name)
            append("\nPaket: ")
            append(PACKAGE_NAME)
            append("\nSürüm kodu: ")
            append(versionCode?.toString() ?: "bilinmiyor")
            append("\nİmza SHA-256: ")
            append(signerSha256 ?: "bilinmiyor")
            append("\nReferans: 3.2.1 (893), statik APK imza kaydı.")
            append("\nBu kontrol canlı model yanıtı, sahip yetkisi veya telefon eylem izni vermez.")
            if (!verified) append("\nEşleşme yok: CİHAT'a otomatik veya onaylı geçiş başlatılmaz.")
        }
    }

    /** Pure verifier also covered by JVM tests. Exactly one current signer. */
    fun decide(versionCode: Long, currentSignerHashes: List<String>, launchable: Boolean): State {
        if (versionCode != EXPECTED_VERSION_CODE) return State.VERSION_MISMATCH
        if (currentSignerHashes.size != 1 ||
            !currentSignerHashes.single().equals(FORENSIC_SIGNER_SHA256, ignoreCase = true)
        ) return State.SIGNER_MISMATCH
        return if (launchable) State.VERIFIED_321 else State.NOT_LAUNCHABLE
    }

    @Suppress("DEPRECATION")
    fun inspect(context: Context): Result {
        return try {
            val pm = context.packageManager
            val flags = if (Build.VERSION.SDK_INT >= 28)
                PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
            val info = pm.getPackageInfo(PACKAGE_NAME, flags)
            val certs = if (Build.VERSION.SDK_INT >= 28)
                info.signingInfo?.apkContentsSigners else info.signatures
            val currentHashes = certs?.map { signature ->
                MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())
                    .joinToString("") { b -> "%02x".format(b.toInt() and 0xff) }
            }.orEmpty()
            val version = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode
                else info.versionCode.toLong()
            val launchable = pm.getLaunchIntentForPackage(PACKAGE_NAME) != null
            Result(decide(version, currentHashes, launchable),
                version, currentHashes.singleOrNull())
        } catch (_: PackageManager.NameNotFoundException) {
            Result(State.NOT_INSTALLED)
        } catch (_: RuntimeException) {
            Result(State.UNAVAILABLE)
        } catch (_: java.security.GeneralSecurityException) {
            Result(State.UNAVAILABLE)
        }
    }
}
