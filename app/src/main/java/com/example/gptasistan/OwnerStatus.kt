package com.example.gptasistan

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import java.security.MessageDigest

/** Local only: exact-version, sole GEN2 signer check. Never Owner authorization. */
object OwnerStatus {
    const val GEN2_CERT_SHA256 = "279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448"
    const val OWNER_PACKAGE = "com.mehmetcerdik.ownerai"
    const val BRIDGE_PACKAGE = "com.mehmetcerdik.ownerbridge"
    data class Reference(val pkg: String, val version: String, val code: Long, val launcher: Boolean)
    val OWNER = Reference(OWNER_PACKAGE, "1.5.4", 12L, true)
    val BRIDGE = Reference(BRIDGE_PACKAGE, "1.2.1", 4L, false)

    enum class Verdict { MATCH, MISSING, WRONG_VERSION, WRONG_SIGNER, AMBIGUOUS_SIGNER, NO_LAUNCHER, UNKNOWN }
    data class Finding(val ref: Reference, val verdict: Verdict, val observedVersion: String? = null, val observedCode: Long? = null) {
        val matches: Boolean get() = verdict == Verdict.MATCH
        fun report(): String {
            val label = when (verdict) {
                Verdict.MATCH -> "Beklenen imzalı sürüm kurulu"
                Verdict.MISSING -> "Kurulu değil"
                Verdict.WRONG_VERSION -> "Sürümü farklı"
                Verdict.WRONG_SIGNER -> "GEN2 imzası farklı"
                Verdict.AMBIGUOUS_SIGNER -> "Tek imzacı doğrulanamadı"
                Verdict.NO_LAUNCHER -> "Owner başlatılamıyor"
                Verdict.UNKNOWN -> "Güvenilir sonuç yok"
            }
            return ref.pkg + ": " + label + "\n" +
                "Beklenen: " + ref.version + " (" + ref.code + ")" + "\n" +
                "Kurulu: " + (observedVersion ?: "?") + " (" + (observedCode?.toString() ?: "?") + ")"
        }
    }

    fun decide(ref: Reference, version: String?, code: Long, signerHashes: List<String>, launchable: Boolean): Verdict {
        if (signerHashes.size != 1 || signerHashes.single().length != 64)
            return Verdict.AMBIGUOUS_SIGNER
        if (!signerHashes.single().equals(GEN2_CERT_SHA256, ignoreCase = true))
            return Verdict.WRONG_SIGNER
        if (version != ref.version || code != ref.code)
            return Verdict.WRONG_VERSION
        if (ref.launcher && !launchable) return Verdict.NO_LAUNCHER
        return Verdict.MATCH
    }

    /** Only the exact known signed Owner *launcher* can be offered for user handoff. */
    fun canOfferOwnerLaunch(finding: Finding): Boolean =
        finding.ref.pkg == OWNER_PACKAGE && finding.ref.launcher &&
            finding.ref.version == OWNER.version && finding.ref.code == OWNER.code &&
            finding.matches

    @Suppress("DEPRECATION")
    fun inspect(context: Context, ref: Reference): Finding = try {
        val pm = context.packageManager
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES
            else PackageManager.GET_SIGNATURES
        val info = pm.getPackageInfo(ref.pkg, flags)
        val signers = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners
            else info.signatures
        val hashes = signers?.map { signature ->
            MessageDigest.getInstance("SHA-256").digest(signature.toByteArray())
                .joinToString("") { "%02x".format(it.toInt() and 255) }
        }.orEmpty()
        val code = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode
            else info.versionCode.toLong()
        val launchable = !ref.launcher || pm.getLaunchIntentForPackage(ref.pkg) != null
        Finding(ref, decide(ref, info.versionName, code, hashes, launchable), info.versionName, code)
    } catch (_: PackageManager.NameNotFoundException) {
        Finding(ref, Verdict.MISSING)
    } catch (_: Exception) {
        Finding(ref, Verdict.UNKNOWN)
    }

    fun readOnlyReport(context: Context): String {
        val owner = inspect(context, OWNER)
        val bridge = inspect(context, BRIDGE)
        val conclusion = if (owner.matches && bridge.matches)
            "Beklenen Owner/Bridge sürümleri ve GEN2 imzası eşleşiyor. Gerçek telefon işlevi ve Owner kaydı henüz kanıtlanmaz."
        else "Beklenen Owner/Bridge sürümünün en az biri doğrulanamadı. Eski APK/verileri silme, üzerine farklı imza yükleme."
        return "OWNER / BRIDGE — SALT OKUNUR\n\n" + owner.report() + "\n\n" +
            bridge.report() + "\n\n" + conclusion + "\nOwner yetkisi verilmedi."
    }
}
