package com.example.gptasistan

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/** Public OMEGA v1 adapter. Device credentials unlock signing; the server enrolls the owner. */
object OwnerIdentity {
    private const val OWNER = "kral_omega_owner_v1"
    private const val DEVICE = "kral_omega_device_v1"

    @Synchronized private fun key(alias: String): KeyPair {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (store.containsAlias(alias)) return KeyPair(store.getCertificate(alias).publicKey,
            store.getKey(alias, null) as java.security.PrivateKey)
        val generator = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
        val builder = KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(true)
        if (Build.VERSION.SDK_INT >= 30) builder.setUserAuthenticationParameters(30,
            KeyProperties.AUTH_BIOMETRIC_STRONG or KeyProperties.AUTH_DEVICE_CREDENTIAL)
        else @Suppress("DEPRECATION") builder.setUserAuthenticationValidityDurationSeconds(30)
        if (Build.VERSION.SDK_INT >= 28) builder.setUnlockedDeviceRequired(true)
        generator.initialize(builder.build())
        return generator.generateKeyPair()
    }

    fun publicRegistration(ownerId: String): String {
        require(OmegaEnvelope.validOwner(ownerId))
        val owner = key(OWNER).public.encoded
        val device = key(DEVICE).public.encoded
        return JSONObject().put("contract", OmegaEnvelope.CONTRACT)
            .put("owner_id", ownerId).put("device_id", OmegaEnvelope.sha256(device))
            .put("owner_public_der_b64", encode(owner)).put("device_public_der_b64", encode(device)).toString(2)
    }

    fun sign(path: String, body: ByteArray, ownerId: String): Map<String, String> {
        val owner = key(OWNER)
        val device = key(DEVICE)
        val id = OmegaEnvelope.sha256(device.public.encoded)
        val timestamp = (System.currentTimeMillis() / 1000).toString()
        val nonce = ByteArray(24).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it.toInt() and 255) }
        val canonical = OmegaEnvelope.canonical(path, body, timestamp, nonce, ownerId, id)
        fun signature(pair: KeyPair): String = Signature.getInstance("SHA256withECDSA").run {
            initSign(pair.private); update(canonical); encode(sign())
        }
        return mapOf("X-Omega-Owner-Id" to ownerId, "X-Omega-Device-Id" to id,
            "X-Omega-Timestamp" to timestamp, "X-Omega-Nonce" to nonce,
            "X-Omega-Owner-Proof" to signature(owner), "X-Omega-Device-Proof" to signature(device))
    }

    private fun encode(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)
}

/** Wire format reused from OwnerOmegaV1Signer/OmegaV1Envelope at 639ac11; public source only. */
object OmegaEnvelope {
    const val CONTRACT = "OMEGA-OWNER-API-V1"
    const val CHAT = "/api/v1/owner/chat"
    const val MODELS = "/api/v1/owner/models"
    const val SOURCES = "/api/v1/owner/sources"
    fun validOwner(value: String) = value.matches(Regex("[A-Za-z0-9_-]{1,64}"))
    fun sha256(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes)
        .joinToString("") { "%02x".format(it.toInt() and 255) }

    fun canonical(path: String, body: ByteArray, timestamp: String, nonce: String, ownerId: String, deviceId: String): ByteArray {
        require(path in setOf(CHAT, MODELS, SOURCES))
        require(body.isNotEmpty() && body.size <= 65536)
        require(timestamp.matches(Regex("[0-9]{10}")))
        require(nonce.matches(Regex("[a-f0-9]{32,64}")))
        require(validOwner(ownerId) && deviceId.matches(Regex("[a-f0-9]{64}")))
        return "$CONTRACT\nPOST\n$path\n${sha256(body)}\n$timestamp\n$nonce\n$ownerId\n$deviceId".toByteArray(Charsets.UTF_8)
    }
}
