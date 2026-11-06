package com.example.gptasistan

import android.app.Application
import android.os.Looper
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode
import java.io.IOException
import java.time.Instant
import java.util.concurrent.CountDownLatch
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** Chat lifecycle tests use a deterministic store; SQLCipher persistence is tested on Android. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@LooperMode(LooperMode.Mode.PAUSED)
class ChatSessionTest {
    private lateinit var application: Application
    private val owners = mutableListOf<ViewModelStore>()
    private val workers = mutableListOf<ExecutorService>()
    private val releaseOnCleanup = mutableListOf<CountDownLatch>()

    @Before fun setUp() {
        application = RuntimeEnvironment.getApplication()
        TestChatRows.clear()
    }

    @After fun tearDown() {
        releaseOnCleanup.forEach { it.countDown() }
        owners.forEach { it.clear() }
        workers.forEach { assertTrue(it.awaitTermination(5, TimeUnit.SECONDS)) }
        shadowOf(Looper.getMainLooper()).idle()
    }

    private fun session(
        store: ChatStore = InMemoryChatStore(),
        responder: (String, String, String) -> OwnerGateway.Reply
    ): Pair<ChatSession, ExecutorService> {
        val worker = Executors.newSingleThreadExecutor().also { workers.add(it) }
        val session = ChatSession(application, store, worker, responder)
        val owner = ViewModelStore().also { owners.add(it) }
        owner.put("chat", session)
        return session to worker
    }

    private fun flush(worker: ExecutorService) {
        worker.submit {}.get(5, TimeUnit.SECONDS)
        shadowOf(Looper.getMainLooper()).idle()
    }

    @Test fun ownerOperationIsSerializedWithChatAndStoredWithoutSpeechOrExecution() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1).also { releaseOnCleanup.add(it) }
        val (session, worker) = session { _, _, _ -> testReply("unused") }
        assertTrue(session.runOwnerOperation("Uzman görevi") {
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            "Görev kimliği: " + "a".repeat(32)
        })
        assertTrue(entered.await(5, TimeUnit.SECONDS))
        assertFalse(session.send(ENDPOINT, "test-model", "korunacak taslak"))
        assertFalse(session.runOwnerOperation("duplicate") { error("must not run") })
        release.countDown()
        flush(worker)
        assertEquals(listOf("Görev kimliği: " + "a".repeat(32)), session.history.value!!.map { it.text })
        assertNull(session.peekUnspokenReply())
        assertFalse(session.state.value!!.busy)
    }

    @Test fun ownerOperationDoesNotEchoRawProviderErrorOrAutomaticallyRetry() {
        val (session, worker) = session { _, _, _ -> testReply("unused") }
        val calls = AtomicInteger()
        assertTrue(session.runOwnerOperation("Görev") {
            calls.incrementAndGet()
            throw IOException("SENSITIVE_ERROR_SENTINEL")
        })
        flush(worker)
        assertEquals(1, calls.get())
        assertFalse(session.history.value!!.single().text.contains("SENSITIVE_ERROR_SENTINEL"))
        assertTrue(session.history.value!!.single().text.contains("otomatik yeniden denenmedi"))
        assertFalse(session.state.value!!.busy)
    }

    @Test fun taskSubmissionCannotStartWithoutDurableIdentifierReceipt() {
        val (session, worker) = session(InMemoryChatStore(failWrites = true)) { _, _, _ -> error("No provider") }
        val submission = TaskSubmission.create("https://example.invalid", "owner", "model",
            "test-engineer", "PRIVATE_TASK_SENTINEL")
        assertFalse(session.retainTaskSubmission(submission))
        assertNull(session.pendingTaskSubmission)
        assertTrue(session.state.value!!.status.contains("başlatılmadı"))
        flush(worker)
        assertTrue(session.history.value!!.isEmpty())
    }

    @Test fun verifiedTaskWithFailedHistoryWriteRetainsExactRequestUntilRecordedRetry() {
        var failWrites = false
        val storage = object : ChatStore {
            override fun saveMessage(role: String, text: String) {
                if (failWrites) throw IOException("storage outage")
                TestChatRows.append(role, text)
            }
            override fun history(limit: Int) = TestChatRows.history(limit)
            override fun close() = Unit
        }
        val (session, worker) = session(storage) { _, _, _ -> error("No chat provider") }
        val submission = TaskSubmission.create("https://example.invalid", "owner", "model",
            "test-engineer", "PRIVATE_TASK_SENTINEL")
        assertTrue(session.retainTaskSubmission(submission))
        assertTrue(session.history.value!!.single().text.contains(submission.requestId))
        assertFalse(session.history.value!!.single().text.contains(submission.input))
        val calls = AtomicInteger()
        failWrites = true
        assertTrue(session.runOwnerOperation("Task", onRecorded = { session.forgetTaskSubmission(submission) }) {
            calls.incrementAndGet()
            "verified ${submission.requestId}"
        })
        flush(worker)
        assertSame(submission, session.pendingTaskSubmission)
        assertEquals(1, calls.get())
        assertFalse(session.retainTaskSubmission(TaskSubmission.create(
            "https://example.invalid", "owner", "model", "test-engineer", "new task")))
        failWrites = false
        assertTrue(session.runOwnerOperation("Task", onRecorded = { session.forgetTaskSubmission(submission) }) {
            assertSame(submission, session.pendingTaskSubmission)
            calls.incrementAndGet()
            "verified ${submission.requestId}"
        })
        flush(worker)
        assertEquals(2, calls.get())
        assertNull(session.pendingTaskSubmission)
        assertEquals(2, session.history.value!!.size)
    }

    @Test fun uncertainTaskTransportRetainsIdentifierAndNeverRetriesAutomatically() {
        val (session, worker) = session { _, _, _ -> error("No chat provider") }
        val submission = TaskSubmission.create("https://example.invalid", "owner", "model",
            "test-engineer", "PRIVATE_TASK_SENTINEL")
        assertTrue(session.retainTaskSubmission(submission))
        val calls = AtomicInteger()
        assertTrue(session.runOwnerOperation("Task", onRecorded = { session.forgetTaskSubmission(submission) }) {
            calls.incrementAndGet()
            throw IOException("PRIVATE_PROVIDER_ERROR")
        })
        flush(worker)
        assertEquals(1, calls.get())
        assertSame(submission, session.pendingTaskSubmission)
        assertTrue(session.history.value!!.any { it.text.contains(submission.requestId) })
        assertTrue(session.history.value!!.none { it.text.contains("PRIVATE_") })
        session.forgetTaskSubmission(submission)
        assertNull(session.pendingTaskSubmission)
    }

    @Test fun onePendingRequestRejectsSecondSendWithoutPersistingSecondDraft() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1).also { releaseOnCleanup.add(it) }
        val calls = AtomicInteger()
        val (session, worker) = session { _, _, _ ->
            calls.incrementAndGet()
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            testReply("Birinci yanıt")
        }
        assertTrue(session.send(ENDPOINT, "test-model", "İlk mesaj"))
        assertTrue(entered.await(5, TimeUnit.SECONDS))
        assertTrue(session.state.value!!.busy)
        assertFalse(session.send(ENDPOINT, "test-model", "Korunacak ikinci taslak"))
        assertEquals(listOf("Sen: İlk mesaj"), session.history.value!!.map { it.text })
        release.countDown()
        flush(worker)
        assertEquals(1, calls.get())
        assertFalse(session.state.value!!.busy)
        assertEquals(listOf("Sen: İlk mesaj", "Model: Birinci yanıt"), session.history.value!!.map { it.text })
        assertEquals("resp_synthetic_123", session.state.value!!.responseId)
        assertEquals("req_synthetic_123", session.state.value!!.providerRequestId)
        assertEquals("a".repeat(32), session.state.value!!.clientRequestId)
    }

    @Test fun clearingViewModelDuringRequestDoesNotInterruptOrLoseDurableReply() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1).also { releaseOnCleanup.add(it) }
        val (session, worker) = session { _, _, _ ->
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            testReply("Activity olmasa da korunmalı")
        }
        assertTrue(session.send(ENDPOINT, "test-model", "Pencere kapanacak"))
        assertTrue(entered.await(5, TimeUnit.SECONDS))
        owners.single().clear()
        assertFalse(session.send(ENDPOINT, "test-model", "Kapanmış oturum"))
        release.countDown()
        assertTrue(worker.awaitTermination(5, TimeUnit.SECONDS))
        shadowOf(Looper.getMainLooper()).idle()
        val reopened = InMemoryChatStore()
        assertEquals(
            listOf("Sen: Pencere kapanacak", "Model: Activity olmasa da korunmalı"),
            reopened.history().map { it.text },
        )
        reopened.close()
    }

    @Test fun databaseWriteFailureReturnsFalseAndNeverCallsProvider() {
        val store = InMemoryChatStore(failWrites = true)
        val calls = AtomicInteger()
        val (session, worker) = session(store) { _, _, _ -> calls.incrementAndGet(); testReply("Çağrılmamalı") }
        assertFalse(session.send(ENDPOINT, "test-model", "UI bu taslağı korumalı"))
        flush(worker)
        assertEquals(0, calls.get())
        assertFalse(session.state.value!!.busy)
        assertTrue(session.state.value!!.status.contains("Mesaj kaydedilemedi"))
    }

    @Test fun providerRateLimitMetadataSurvivesInStateWithoutRawErrorBody() {
        val failure = OwnerGateway.parseGatewayFailure(502, org.json.JSONObject()
            .put("error", "PROVIDER_QUOTA_OR_RATE_LIMIT")
            .put("provider_request_id", "req_synthetic_429")
            .put("provider_http_status", 429)
            .put("provider_error_code", "rate_limit_exceeded")
            .put("retryable", true).put("retry_after_seconds", 7)
            .put("private_detail", "secret prompt").toString())
        val (session, worker) = session { _, _, _ -> throw failure }
        assertTrue(session.send(ENDPOINT, "test-model", "Hız sınırı testi"))
        flush(worker)
        val state = session.state.value!!
        assertEquals(502, state.providerHttpStatus)
        assertEquals("req_synthetic_429", state.providerRequestId)
        assertEquals("rate_limit_exceeded", state.providerErrorCode)
        assertTrue(state.retryable)
        assertEquals(7L, state.retryAfterSeconds)
        assertEquals("PROVIDER_QUOTA_OR_RATE_LIMIT", state.errorCode)
        assertFalse(session.history.value!!.any { it.text.contains("secret prompt") })
    }

    @Test fun providerFailureIsDurableGenericTextAndNeverSuccessOrSpeech() {
        val (session, worker) = session { _, _, _ -> throw IOException("private provider detail") }
        assertTrue(session.send(ENDPOINT, "test-model", "Hata denemesi"))
        flush(worker)
        assertFalse(session.state.value!!.busy)
        assertEquals("Son model isteği başarısız", session.state.value!!.status)
        assertEquals(listOf("user", "assistant"), session.history.value!!.map { it.role })
        assertFalse(session.history.value!!.any { it.text.contains("private provider detail") })
        assertTrue(session.history.value!!.last().text.contains("Model yanıtı alınamadı"))
        assertNull(session.peekUnspokenReply())
    }

    @Test fun retainedViewModelKeepsConsumedSpeechAndStaleTokenCannotConsumeNewReply() {
        val (session, worker) = session { _, _, question -> testReply("Yanıt: $question") }
        val retained = ViewModelStore().also { owners.add(it) }
        val factory = object : ViewModelProvider.Factory {
            @Suppress("UNCHECKED_CAST")
            override fun <T : ViewModel> create(modelClass: Class<T>): T = session as T
        }
        val beforeRecreation = ViewModelProvider(retained, factory)[ChatSession::class.java]
        assertTrue(beforeRecreation.send(ENDPOINT, "test-model", "Bir"))
        flush(worker)
        val first = beforeRecreation.peekUnspokenReply()!!
        beforeRecreation.markSpoken(first.first)
        val afterRecreation = ViewModelProvider(retained, factory)[ChatSession::class.java]
        assertSame(beforeRecreation, afterRecreation)
        assertNull(afterRecreation.peekUnspokenReply())
        assertTrue(afterRecreation.send(ENDPOINT, "test-model", "İki"))
        flush(worker)
        val second = afterRecreation.peekUnspokenReply()!!
        assertTrue(second.first > first.first)
        afterRecreation.markSpoken(first.first)
        assertEquals(second, afterRecreation.peekUnspokenReply())
        afterRecreation.markSpoken(second.first)
        assertNull(afterRecreation.peekUnspokenReply())
        // Only one owner should clear this instance during cleanup.
        owners.first().clear()
        owners.remove(retained)
    }

    @Test fun oversizedChatRetainsDraftWithoutPersistingOrCallingProvider() {
        val (session, worker) = session { _, _, _ -> error("Çağrılmamalı") }
        assertFalse(session.send(ENDPOINT, "test-model", "a".repeat(8001)))
        flush(worker)
        assertTrue(session.history.value!!.isEmpty())
        assertTrue(session.state.value!!.status.contains("8000"))
    }

    @Test fun refreshHistoryIncludesLocalCommandMessagesWithoutModelCall() {
        val (session, worker) = session { _, _, _ -> error("Çağrılmamalı") }
        val external = InMemoryChatStore()
        external.saveMessage("system", "Yerel görev eklendi")
        external.close()
        session.refreshHistory()
        assertEquals(listOf("Yerel görev eklendi"), session.history.value!!.map { it.text })
        flush(worker)
        assertFalse(session.state.value!!.busy)
    }

    @Test fun connectionStatusResetInvalidatesOldSuccessButCannotHidePendingRequest() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1).also { releaseOnCleanup.add(it) }
        val (session, worker) = session { _, _, _ ->
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            testReply("Gerçek başarı durumu")
        }
        assertTrue(session.send(ENDPOINT, "test-model", "Bağlantı denemesi"))
        assertTrue(entered.await(5, TimeUnit.SECONDS))
        session.resetConnectionStatus()
        assertTrue(session.state.value!!.busy)
        assertEquals("Model yanıtı bekleniyor…", session.state.value!!.status)
        release.countDown()
        flush(worker)
        assertTrue(session.state.value!!.status.contains("başarılı"))
        val savedHistory = session.history.value
        session.resetConnectionStatus()
        assertEquals(ChatSession.State(false, "Model adresi kayıtlı; bağlantı doğrulanmadı"),
            session.state.value)
        session.resetConnectionStatus("Model bağlantısı yapılandırılmadı")
        assertEquals(ChatSession.State(false, "Model bağlantısı yapılandırılmadı"), session.state.value)
        assertEquals(savedHistory, session.history.value)
    }

    private companion object { const val ENDPOINT = "https://example.invalid/v1/chat/completions" }
}

private fun testReply(text: String) = OwnerGateway.Reply(
    text, "test-model", "openai", "resp_synthetic_123", "req_synthetic_123", "a".repeat(32), 1L
)

private class InMemoryChatStore(private val failWrites: Boolean = false) : ChatStore {
    override fun saveMessage(role: String, text: String) {
        if (failWrites) throw IOException("simulated write failure")
        TestChatRows.append(role, text)
    }

    override fun history(limit: Int): List<ChatEntry> = TestChatRows.history(limit)

    override fun close() = Unit
}

private object TestChatRows {
    private val entries = mutableListOf<ChatEntry>()
    private var nextId = 1L

    @Synchronized fun clear() {
        entries.clear()
        nextId = 1L
    }

    @Synchronized fun append(role: String, text: String) {
        entries.add(ChatEntry(nextId++, Instant.now().toString(), role, text))
    }

    @Synchronized fun history(limit: Int): List<ChatEntry> = entries.takeLast(limit)
}
