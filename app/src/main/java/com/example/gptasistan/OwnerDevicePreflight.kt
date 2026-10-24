package com.example.gptasistan

import android.app.KeyguardManager
import android.content.Context
import android.security.keystore.KeyInfo
import java.security.KeyFactory
import java.security.KeyStore
import java.security.PrivateKey
import java.security.interfaces.ECPublicKey

/** Read-only and fail-closed device readiness; never creates/uses an Owner key. */
object OwnerDevicePreflight {
    private const val OWNER = "kral_omega_owner_v1"
    private const val DEVICE = "kral_omega_device_v1"

    enum class KeyState { MISSING, AUTH_REQUIRED_P256, UNKNOWN }
    data class Facts(
        val secureLock: Boolean,
        val owner: KeyState,
        val device: KeyState,
        val preview: Boolean
    )

    internal fun report(facts: Facts): String {
        fun describe(state: KeyState) = when (state) {
            KeyState.MISSING -> "Bu kurulumda yok; otomatik anahtar üretilmedi"
            KeyState.AUTH_REQUIRED_P256 -> "Mevcut P-256; kullanıcı doğrulaması şartı görünüyor"
            KeyState.UNKNOWN -> "Anahtarın güvenlik özellikleri doğrulanamadı"
        }
        val lock = if (facts.secureLock) "Güvenli ekran kilidi var" else "Güvenli ekran kilidi yok"
        val preview = if (facts.preview)
            "ÖNİZLEME: Değişen debug imzalarıyla gerçek Owner kaydı oluşturma."
        else "Üretim APK imzası ve sunucu onayı ayrıca incelenmeli."
        return "OWNER CİHAZ HAZIRLIK KONTROLÜ\n\n" +
            "Ekran kilidi: " + lock + "\n" +
            "Owner anahtarı: " + describe(facts.owner) + "\n" +
            "Cihaz anahtarı: " + describe(facts.device) + "\n\n" +
            preview + "\n\n" +
            "Bu kontrol anahtar OLUŞTURMAZ, imza ATMAZ, bilgi GÖNDERMEZ ve " +
            "Owner kaydı ya da model yürütmesi AÇMAZ.\n\n" +
            "GERÇEK OWNER KABULÜ DEĞİLDİR. Fiziksel cihaz onayı, " +
            "sabit üretim imzası, sunucu kaydı ve bağımsız yetkilendirme gereklidir."
    }

    private fun existing(store: KeyStore, alias: String): KeyState {
        if (!store.containsAlias(alias)) return KeyState.MISSING
        return try {
            val privateKey = store.getKey(alias, null) as? PrivateKey ?: return KeyState.UNKNOWN
            val publicKey = store.getCertificate(alias)?.publicKey as? ECPublicKey
                ?: return KeyState.UNKNOWN
            if (publicKey.params.curve.field.fieldSize != 256) return KeyState.UNKNOWN
            val info = KeyFactory.getInstance("EC", "AndroidKeyStore")
                .getKeySpec(privateKey, KeyInfo::class.java)
            if (info.isUserAuthenticationRequired) KeyState.AUTH_REQUIRED_P256 else KeyState.UNKNOWN
        } catch (_: Exception) { KeyState.UNKNOWN }
    }

    fun readOnlyFacts(context: Context): Facts {
        val screenLock = try {
            (context.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager).isDeviceSecure
        } catch (_: Exception) { false }
        val states = try {
            val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            existing(store, OWNER) to existing(store, DEVICE)
        } catch (_: Exception) { KeyState.UNKNOWN to KeyState.UNKNOWN }
        return Facts(screenLock, states.first, states.second,
            context.packageName.endsWith(".genesis.cihatpreview"))
    }

    fun readOnlyReport(context: Context): String = report(readOnlyFacts(context))
}
