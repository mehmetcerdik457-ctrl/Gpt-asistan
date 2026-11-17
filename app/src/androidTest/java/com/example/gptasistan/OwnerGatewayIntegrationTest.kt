package com.example.gptasistan

import android.util.Base64
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayInputStream
import java.security.KeyFactory
import java.security.KeyStore
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.Signature
import java.security.cert.CertificateFactory
import java.security.spec.PKCS8EncodedKeySpec
import java.util.UUID
import javax.net.ssl.HttpsURLConnection
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManagerFactory

/** Actual Android HTTPS transport to the existing Python gateway; only OpenAI is mocked. */
@RunWith(AndroidJUnit4::class)
class OwnerGatewayIntegrationTest {
    private lateinit var base: String
    private lateinit var ownerKey: PrivateKey
    private lateinit var deviceKey: PrivateKey
    private lateinit var deviceId: String
    private lateinit var tls: SSLContext

    @Before fun requireDisposableConfiguredFixture() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        InstrumentationSafety.requireDisposableEmulator(instrumentation.targetContext.applicationContext)
        val args = InstrumentationRegistry.getArguments()
        val required = listOf("kralFixtureBase", "kralFixtureCa", "kralFixtureOwnerPrivate",
            "kralFixtureDevicePrivate", "kralFixtureDeviceId")
        assumeTrue("Requires the disposable local KRAL HTTPS fixture; not live acceptance.",
            required.all { !args.getString(it).isNullOrBlank() })
        base = args.getString("kralFixtureBase")!!
        require(base.startsWith("https://localhost:") && OwnerGateway.validBase(base))
        deviceId = args.getString("kralFixtureDeviceId")!!
        require(deviceId.matches(Regex("[a-f0-9]{64}")))
        fun privateKey(name: String): PrivateKey = KeyFactory.getInstance("EC").generatePrivate(
            PKCS8EncodedKeySpec(Base64.decode(args.getString(name), Base64.DEFAULT)))
        ownerKey = privateKey("kralFixtureOwnerPrivate")
        deviceKey = privateKey("kralFixtureDevicePrivate")
        val certificate = CertificateFactory.getInstance("X.509").generateCertificate(
            ByteArrayInputStream(Base64.decode(args.getString("kralFixtureCa"), Base64.DEFAULT)))
        val trustStore = KeyStore.getInstance(KeyStore.getDefaultType()).apply {
            load(null, null)
            setCertificateEntry("kral-disposable-fixture", certificate)
        }
        val managers = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm()).apply {
            init(trustStore)
        }
        tls = SSLContext.getInstance("TLS").apply { init(null, managers.trustManagers, SecureRandom()) }
    }

    private fun encode(bytes: ByteArray) = Base64.encodeToString(bytes,
        Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP)

    private fun sign(path: String, body: ByteArray, owner: String): Map<String, String> {
        val timestamp = (System.currentTimeMillis() / 1000).toString()
        val nonce = UUID.randomUUID().toString().replace("-", "")
        val canonical = OmegaEnvelope.canonical(path, body, timestamp, nonce, owner, deviceId)
        fun proof(key: PrivateKey) = Signature.getInstance("SHA256withECDSA").run {
            initSign(key)
            update(canonical)
            encode(sign())
        }
        return mapOf("X-Omega-Owner-Id" to owner, "X-Omega-Device-Id" to deviceId,
            "X-Omega-Timestamp" to timestamp, "X-Omega-Nonce" to nonce,
            "X-Omega-Owner-Proof" to proof(ownerKey), "X-Omega-Device-Proof" to proof(deviceKey))
    }

    private fun request(path: String, body: JSONObject): JSONObject =
        OwnerGateway.requestUsingTransport(base, path, "android-fixture", body, ::sign) {
            (it.openConnection() as HttpsURLConnection).apply {
                sslSocketFactory = tls.socketFactory
                // The platform hostname verifier remains unchanged.
            }
        }

    private fun selectedModel(): OwnerGateway.Model = OwnerGateway.parseModels(
        request(OmegaEnvelope.MODELS, JSONObject()), System.currentTimeMillis() / 1000
    ).single().also { assertEquals("fixture-model-001", it.id) }

    private fun task(input: String): OwnerGateway.Task {
        val model = selectedModel()
        val submitted = OwnerGateway.parseTask(request(OmegaEnvelope.TASKS, JSONObject()
            .put("input", input).put("model", model.id).put("expert", "code-reviewer")
            .put("tools", JSONArray()).put("requires_approval", false)))
        val deadline = System.nanoTime() + 15_000_000_000L
        var current = submitted
        while (current.status in setOf("queued", "running") && System.nanoTime() < deadline) {
            Thread.sleep(30)
            current = OwnerGateway.parseTask(request(OmegaEnvelope.TASK_STATUS,
                JSONObject().put("task_id", submitted.taskId)))
        }
        assertFalse("Task did not reach a terminal state", current.status in setOf("queued", "running"))
        return current
    }

    @Test fun signedAndroidTaskReachesGatewayAndReturnsResponsesEvidence() {
        val completed = task("KRAL_ACCEPT_SUCCESS")
        assertEquals("completed", completed.status)
        assertEquals("KRAL_OK", completed.result)
        assertTrue(completed.responseId?.startsWith("resp_") == true)
        assertTrue(completed.providerRequestId?.startsWith("req_") == true)
        assertEquals(completed.taskId, completed.clientRequestId)
        assertEquals(200, completed.providerHttpStatus)
        assertNull(completed.error)
    }

    @Test fun providerAccessFailuresRemainTypedInTheTaskContract() {
        val expected = mapOf(401 to "PROVIDER_AUTH_DENIED", 403 to "PROVIDER_MODEL_OR_PERMISSION_DENIED",
            404 to "PROVIDER_MODEL_NOT_AVAILABLE")
        for ((http, error) in expected) {
            val failed = task("KRAL_ACCEPT_$http")
            assertEquals("failed", failed.status)
            assertEquals(error, failed.error)
            assertEquals(http, failed.providerHttpStatus)
            assertNull(failed.result)
            assertNull(failed.resultSha256)
            assertNull(failed.responseId)
            assertFalse(failed.retryable)
            assertEquals(failed.taskId, failed.clientRequestId)
        }
    }

    @Test fun chatHttpErrorsUseTheSameTypedAndroidFailureParser() {
        for ((http, error) in mapOf(401 to "PROVIDER_AUTH_DENIED",
            403 to "PROVIDER_MODEL_OR_PERMISSION_DENIED", 404 to "PROVIDER_MODEL_NOT_AVAILABLE")) {
            val model = selectedModel()
            val failure = assertThrows(OwnerGateway.GatewayFailure::class.java) {
                request(OmegaEnvelope.CHAT, JSONObject().put("message", "KRAL_ACCEPT_$http")
                    .put("model", model.id).put("include_memory", false)
                    .put("client_request_id", UUID.randomUUID().toString().replace("-", "")))
            }
            assertEquals(error, failure.errorCode)
            assertEquals(http, failure.providerHttpStatus)
            assertEquals(error, failure.message)
            assertFalse(failure.toString().contains("KRAL_ACCEPT_"))
        }
    }

    @Test fun signedLocalMemoryRequiresExactApprovalAndExecutesOnlyOnce() {
        fun parse(value: JSONObject) = OwnerGateway.parseToolTask(value, "android-fixture", base)
        val status = parse(request(OmegaEnvelope.TOOL_TASKS, JSONObject().put("tool", "status")
            .put("arguments", JSONObject()).put("scope", "local.status")))
        assertEquals("completed", status.status)
        assertEquals("read_only", status.approvalClass)
        val pending = parse(request(OmegaEnvelope.TOOL_TASKS,
            OwnerGateway.localMemoryProposal("KRAL_ANDROID_APPROVAL_FIXTURE")))
        assertEquals("awaiting_approval", pending.status)
        assertEquals(0L, pending.toolsExecuted)
        assertNull(pending.memoryId)
        val observed = parse(request(OmegaEnvelope.TOOL_STATUS, OwnerGateway.localToolReference(pending)))
        assertEquals(pending.requestSha256, observed.requestSha256)
        assertEquals("awaiting_approval", observed.status)
        val body = OwnerGateway.localToolApproval(pending)
        val completed = parse(request(OmegaEnvelope.TOOL_APPROVE, body))
        assertEquals("completed", completed.status)
        assertEquals(pending.requestSha256, completed.requestSha256)
        assertEquals(pending.actor, completed.approvedBy)
        assertEquals(1L, completed.toolsExecuted)
        assertTrue((completed.memoryId ?: 0L) > 0L)
        assertEquals(listOf("proposed", "approved", "completed"), completed.audit.map { it.event })
        val duplicate = assertThrows(OwnerGateway.GatewayFailure::class.java) {
            request(OmegaEnvelope.TOOL_APPROVE, body)
        }
        assertEquals(409, duplicate.httpStatus)
        assertEquals("TOOL_TASK_NOT_PENDING", duplicate.errorCode)
    }
}
