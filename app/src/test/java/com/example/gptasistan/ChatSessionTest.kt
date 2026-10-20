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
import java.util.concurrent.CountDownLatch
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/** Real SQLite and worker tests. No live model, network, or phone is exercised. */
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
        application.deleteDatabase("kral_local.db")
    }

    @After fun tearDown() {
        releaseOnCleanup.forEach { it.countDown() }
        owners.forEach { it.clear() }
        workers.forEach { assertTrue(it.awaitTermination(5, TimeUnit.SECONDS)) }
        shadowOf(Looper.getMainLooper()).idle()
        application.deleteDatabase("kral_local.db")
    }

    private fun session(
        store: KralStore = KralStore(application),
        responder: (String, String, String) -> String
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

    @Test fun onePendingRequestRejectsSecondSendWithoutPersistingSecondDraft() {
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1).also { releaseOnCleanup.add(it) }
        val calls = AtomicInteger()
        val (session, worker) = session { _, _, _ ->
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
        val (session, worker) = session { _, _, _ ->
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
        val reopened = KralStore(application)
        try {
            assertEquals(listOf("Sen: Pencere kapanacak", "Model: Activity olmasa da korunmalı"),
                reopened.history().map { it.text })
        } finally { reopened.close() }
    }

    @Test fun databaseWriteFailureReturnsFalseAndNeverCallsProvider() {
        val store = KralStore(application)
        val calls = AtomicInteger()
        val (session, worker) = session(store) { _, _, _ -> calls.incrementAndGet(); "Çağrılmamalı" }
        store.writableDatabase.execSQL("DROP TABLE chat_messages")
        assertFalse(session.send(ENDPOINT, "test-model", "UI bu taslağı korumalı"))
        flush(worker)
        assertEquals(0, calls.get())
        assertFalse(session.state.value!!.busy)
        assertTrue(session.state.value!!.status.contains("Mesaj kaydedilemedi"))
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
        val (session, worker) = session { _, _, question -> "Yanıt: $question" }
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

    @Test fun refreshHistoryIncludesLocalCommandMessagesWithoutModelCall() {
        val (session, worker) = session { _, _, _ -> error("Çağrılmamalı") }
        val external = KralStore(application)
        try { external.saveMessage("system", "Yerel görev eklendi") }
        finally { external.close() }
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
