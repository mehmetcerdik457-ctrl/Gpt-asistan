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
        responder: (String, String, String, Boolean) -> String
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

    @Test fun historySharingDefaultsOffAndExplicitOptInReachesResponder() {
        val observed = mutableListOf<Boolean>()
        val (session, worker) = session { _, _, _, includeHistory ->
            observed.add(includeHistory)
            "Yanıt"
        }
        assertTrue(session.send(ENDPOINT, "test-model", "Varsayılan"))
        flush(worker)
        assertEquals(listOf(false), observed)

        assertTrue(session.send(ENDPOINT, "test-model", "Açık", includeHistory = true))
        flush(worker)
        assertEquals(listOf(false, true), observed)
    }

    @Test fun onePendingRequestRejectsSecondSendWithoutPersistingSecondDraft() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1).also { releaseOnCleanup.add(it) }
        val calls = AtomicInteger()
        val (session, worker) = session { _, _, _, _ ->
            calls.incrementAndGet()
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            "Birinci yanıt"
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
    }

    @Test fun clearingViewModelDuringRequestDoesNotInterruptOrLoseDurableReply() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1).also { releaseOnCleanup.add(it) }
        val (session, worker) = session { _, _, _, _ ->
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            "Activity olmasa da korunmalı"
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
        val (session, worker) = session(store) { _, _, _, _ -> calls.incrementAndGet(); "Çağrılmamalı" }
        assertFalse(session.send(ENDPOINT, "test-model", "UI bu taslağı korumalı"))
        flush(worker)
        assertEquals(0, calls.get())
        assertFalse(session.state.value!!.busy)
        assertTrue(session.state.value!!.status.contains("Mesaj kaydedilemedi"))
    }

    @Test fun providerFailureIsDurableGenericTextAndNeverSuccessOrSpeech() {
        val (session, worker) = session { _, _, _, _ -> throw IOException("private provider detail") }
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
        val (session, worker) = session { _, _, question, _ -> "Yanıt: $question" }
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
        val (session, worker) = session { _, _, _, _ -> error("Çağrılmamalı") }
        assertFalse(session.send(ENDPOINT, "test-model", "a".repeat(8001)))
        flush(worker)
        assertTrue(session.history.value!!.isEmpty())
        assertTrue(session.state.value!!.status.contains("8000"))
    }

    @Test fun refreshHistoryIncludesLocalCommandMessagesWithoutModelCall() {
        val (session, worker) = session { _, _, _, _ -> error("Çağrılmamalı") }
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
        val (session, worker) = session { _, _, _, _ ->
            entered.countDown()
            check(release.await(5, TimeUnit.SECONDS))
            "Gerçek başarı durumu"
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
