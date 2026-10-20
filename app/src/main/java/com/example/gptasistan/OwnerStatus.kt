package com.example.gptasistan

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import java.security.MessageDigest

// The September 2026 preserved Owner/Bridge signer reference. This is only
// a read-only package integrity hint, NOT owner authentication or permission.
object OwnerStatus {
    private const val EXPECTED_CERT_SHA256 =
        "279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448"

    @Suppress("DEPRECATION")
    private fun status(context: Context, pkg: String): String {
        val pm = context.packageManager
        return try {
            val flags = if (Build.VERSION.SDK_INT >= 28)
                PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
            val info = pm.getPackageInfo(pkg, flags)
            val signers = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners
                else info.signatures
            val verified = signers?.any { signature ->
                val digest = MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())
                digest.joinToString("") { "%02x".format(it.toInt() and 0xff) }
                    .equals(EXPECTED_CERT_SHA256, true)
            } == true
            if (verified) "kurulu; tarihsel imza eşleşiyor" else "kurulu; imza doğrulanamadı"
        } catch (_: PackageManager.NameNotFoundException) {
            "kurulu görünmüyor"
        } catch (_: Exception) {
            "durum belirlenemedi"
        }
    }
    fun readOnlyReport(context: Context): String =
        "Owner: " + status(context, "com.mehmetcerdik.ownerai") +
        "\nBridge: " + status(context, "com.mehmetcerdik.ownerbridge") +
        "\nBu kontrol OWNER yetkisi vermez. Ayrıcalıklı telefon eylemleri kapalıdır."
}
