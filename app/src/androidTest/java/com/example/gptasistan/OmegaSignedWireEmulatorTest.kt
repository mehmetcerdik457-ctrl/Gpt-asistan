package com.example.gptasistan

import android.util.Base64
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.ByteArrayOutputStream
import java.net.URL
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.SecureRandom
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.spec.ECGenParameterSpec
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/** Disposable Android SOFTWARE keys, not real enrolled Owner AndroidKeyStore keys. */
@RunWith(AndroidJUnit4::class)
class OmegaSignedWireEmulatorTest {
    private val root = "https://127.0.0.1:18443"
    private fun b64(bytes: ByteArray): String = Base64.encodeToString(
        bytes, Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)

    private fun pair(): KeyPair = KeyPairGenerator.getInstance("EC").run {
        initialize(ECGenParameterSpec("secp256r1"), SecureRandom())
        generateKeyPair()
    }

    private fun conn(path: String): HttpsURLConnection {
        val testApp = InstrumentationRegistry.getInstrumentation().context
        val cert = testApp.assets.open("omega-ci-loopback-cert.der").use {
            CertificateFactory.getInstance("X.509").generateCertificate(it)
        }
        val store = KeyStore.getInstance(KeyStore.getDefaultType())
        store.load(null)
        store.setCertificateEntry("ci-only", cert)
        val tm = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm())
        tm.init(store)
        val tls = SSLContext.getInstance("TLS")
        tls.init(null, tm.trustManagers, null)
        val c = URL(root + path).openConnection() as HttpsURLConnection
        c.sslSocketFactory = tls.socketFactory
        // Default hostname verification remains intact.
        c.instanceFollowRedirects = false
        c.connectTimeout = 5000
        c.readTimeout = 5000
        c.setRequestProperty("Content-Type", "application/json")
        return c
    }

    private fun post(path: String, bytes: ByteArray, headers: Map<String, String> = emptyMap()):
        Pair<Int, JSONObject> {
        val c = conn(path)
        try {
            c.requestMethod = "POST"
            c.doOutput = true
            headers.forEach { (name, value) -> c.setRequestProperty(name, value) }
            c.outputStream.use { it.write(bytes) }
            val code = c.responseCode
            val stream = if (code in 200..299) c.inputStream else c.errorStream
            require(stream != null)
            val buffer = ByteArrayOutputStream()
            stream.use { src ->
                val block = ByteArray(512)
                while (true) {
                    val n = src.read(block)
                    if (n < 0) break
                    require(buffer.size() + n <= 4096)
                    if (n > 0) buffer.write(block, 0, n)
                }
            }
            return code to JSONObject(buffer.toString("UTF-8"))
        } finally {
            c.disconnect()
        }
    }

    private fun headers(path: String, body: ByteArray, o: KeyPair, d: KeyPair): Map<String,String> {
        val id = OmegaEnvelope.sha256(d.public.encoded)
        val ts = (System.currentTimeMillis() / 1000).toString()
        val nonce = ByteArray(24).also { SecureRandom().nextBytes(it) }
            .joinToString("") { "%02x".format(it.toInt() and 255) }
        // Original *production* Android signed envelope function.
        val canonical = OmegaEnvelope.canonical(path, body, ts, nonce, "synthetic-ci-owner", id)
        fun sign(k: KeyPair) = Signature.getInstance("SHA256withECDSA").run {
            initSign(k.private)
            update(canonical)
            b64(sign())
        }
        return mapOf("X-Omega-Owner-Id" to "synthetic-ci-owner",
            "X-Omega-Device-Id" to id, "X-Omega-Timestamp" to ts,
            "X-Omega-Nonce" to nonce, "X-Omega-Owner-Proof" to sign(o),
            "X-Omega-Device-Proof" to sign(d))
    }

    private fun denied(result: Pair<Int, JSONObject>, expected: String) {
        assertEquals(403, result.first)
        assertEquals(expected, result.second.getString("error"))
    }

    @Test fun androidGeneratedP256DualProofIsValidButNeverAuthorizes() {
        assumeTrue("dedicated CI TLS job only",
            InstrumentationRegistry.getArguments().getString("omega_tls_test") == "true")
        val owner = pair()
        val device = pair()
        assertFalse(owner.public.encoded.contentEquals(device.public.encoded))
        val registration = JSONObject()
            .put("owner_id", "synthetic-ci-owner")
            .put("device_id", OmegaEnvelope.sha256(device.public.encoded))
            .put("owner_public_der_b64", b64(owner.public.encoded))
            .put("device_public_der_b64", b64(device.public.encoded))
        val provision = post("/__ci__/synthetic-key-provision",
            registration.toString().toByteArray(Charsets.UTF_8))
        assertEquals(201, provision.first)
        assertTrue(provision.second.getBoolean("ci_fixture_bound"))
        assertFalse(provision.second.getBoolean("owner_identity_verified"))
        assertFalse(provision.second.getBoolean("execution_enabled"))

        val empty = "{}".toByteArray(Charsets.UTF_8)
        val signedModels = headers(OmegaEnvelope.MODELS, empty, owner, device)
        denied(post(OmegaEnvelope.MODELS, empty, signedModels), "OWNER_EXECUTION_NOT_APPROVED")
        denied(post(OmegaEnvelope.MODELS, empty, signedModels),
            "OWNER_AUTH_REPLAY_OR_STORAGE_DENIED")
        val original = headers(OmegaEnvelope.MODELS, empty, owner, device)
        denied(post(OmegaEnvelope.MODELS, """{"model":"injected"}""".toByteArray(), original),
            "OWNER_AUTH_DENIED")
        val misroute = headers(OmegaEnvelope.MODELS, empty, owner, device)
        denied(post(OmegaEnvelope.CHAT, empty, misroute), "OWNER_AUTH_DENIED")
        val chat = """{"message":"CI synthetic data"}""".toByteArray(Charsets.UTF_8)
        denied(post(OmegaEnvelope.CHAT, chat, headers(OmegaEnvelope.CHAT, chat, owner, device)),
            "OWNER_EXECUTION_NOT_APPROVED")
        println("OMEGA_ANDROID_SIGNATURE_MODELS=VALID_BUT_DENIED")
        println("OMEGA_ANDROID_SIGNATURE_REPLAY_TAMPER_MISROUTE=DENIED")
        println("OMEGA_ANDROID_SIGNATURE_CHAT=VALID_BUT_DENIED")
    }
}
