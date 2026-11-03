package com.example.gptasistan

import android.app.Application
import android.os.Handler
import android.os.Looper
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.RejectedExecutionException

/** Owns chat work independently of any Activity or speech engine. */
class ChatSession internal constructor(
    application: Application,
    private val store: ChatStore,
    private val worker: ExecutorService,
    private val responder: (String, String, String) -> OwnerGateway.Reply
) : AndroidViewModel(application) {
    constructor(application: Application) : this(
        application,
        KralStore(application.applicationContext),
        Executors.newSingleThreadExecutor(),
        { endpoint, model, question -> OwnerGateway.replyWithMetadata(application, endpoint, model, question) }
    )

    data class State(
        val busy: Boolean, val status: String,
        val responseId: String? = null, val providerRequestId: String? = null,
        val clientRequestId: String? = null,
        val providerHttpStatus: Int? = null, val providerErrorCode: String? = null,
        val retryable: Boolean = false, val retryAfterSeconds: Long? = null,
        val errorCode: String? = null,
    )

    private val main = Handler(Looper.getMainLooper())
    private val mutableHistory = MutableLiveData<List<ChatEntry>>(emptyList())
    private val mutableState = MutableLiveData(State(false, "Henüz model isteği yapılmadı"))
    val history: LiveData<List<ChatEntry>> = mutableHistory
    val state: LiveData<State> = mutableState
    private var pending = false
    private var cleared = false
    private val speechLock = Any()
    private var replySequence = 0L
    private var unspokenReply: Pair<Long, String>? = null

    init { refreshHistory() }

    /** False means the caller must retain its draft. Call only on the main thread. */
    fun send(endpoint: String, model: String, question: String): Boolean {
        requireMainThread()
        if (cleared || pending || worker.isShutdown || question.isBlank()) return false
        if (question.length > 8000) {
            mutableState.value = State(false, "Sohbet mesajı en fazla 8000 karakter olabilir; taslağın korundu.")
            return false
        }
        if (!ModelGateway.valid(endpoint) || model.isBlank()) {
            mutableState.value = State(false, "Model bağlantısı yapılandırılmadı")
            return false
        }
        try {
            store.saveMessage("user", "Sen: " + question)
        } catch (_: Exception) {
            mutableState.value = State(false, "Mesaj kaydedilemedi. Depolama alanını kontrol et.")
            return false
        }
        pending = true
        refreshHistory()
        mutableState.value = State(true, "Model yanıtı bekleniyor…")
        try {
            worker.execute { completeRequest(endpoint, model, question) }
        } catch (_: RejectedExecutionException) {
            // The user message is already durable. Treat this as an accepted
            // request that failed, rather than asking the UI to send it twice.
            pending = false
            mutableState.value = State(false, "Model isteği başlatılamadı")
        }
        return true
    }

    /** Refresh after local commands; never call this from a background thread. */
    fun refreshHistory() {
        requireMainThread()
        if (cleared) return
        try {
            mutableHistory.value = store.history()
        } catch (_: Exception) {
            mutableState.value = State(pending, "Sohbet geçmişi okunamadı. Depolama alanını kontrol et.")
        }
    }

    /** Configuration edits invalidate a previous successful-connection status. */
    fun resetConnectionStatus(status: String = "Model adresi kayıtlı; bağlantı doğrulanmadı") {
        requireMainThread()
        if (cleared || pending) return
        mutableState.value = State(false, status)
    }

    /** Owner-confirmed task/status calls share the chat queue and encrypted history.
     * No automatic retries, polling, speech, or execution of returned text.
     */
    fun runOwnerOperation(label: String, operation: () -> String): Boolean {
        requireMainThread()
        if (cleared || pending || worker.isShutdown) return false
        pending = true
        mutableState.value = State(true, "$label bekleniyor…")
        try {
            worker.execute {
                var status = "$label yanıtı alındı"
                var failure: OwnerGateway.GatewayFailure? = null
                val report = try {
                    operation().also { require(it.isNotBlank() && it.length <= 40000) }
                } catch (error: OwnerGateway.GatewayFailure) {
                    failure = error
                    status = "$label başarısız: ${error.errorCode}. Otomatik yeniden denenmedi."
                    status
                } catch (_: Exception) {
                    status = "$label doğrulanamadı. İstek otomatik yeniden denenmedi; taslak korundu."
                    status
                }
                try { store.saveMessage("assistant", report) }
                catch (_: Exception) { status = "$label sonucu geçmişe kaydedilemedi." }
                val finalStatus = status
                val error = failure
                main.post {
                    if (!cleared) refreshHistory()
                    pending = false
                    mutableState.value = State(false, finalStatus,
                        providerRequestId = error?.providerRequestId,
                        providerHttpStatus = error?.httpStatus, providerErrorCode = error?.providerErrorCode,
                        retryable = error?.retryable ?: false,
                        retryAfterSeconds = error?.retryAfterSeconds, errorCode = error?.errorCode)
                }
            }
        } catch (_: RejectedExecutionException) {
            pending = false
            mutableState.value = State(false, "$label başlatılamadı; taslak korundu.")
            return false
        }
        return true
    }

    // The ID is a session-scoped delivery token, not a database row ID. Retaining
    // this ViewModel through rotation also retains which reply was consumed.
    fun peekUnspokenReply(): Pair<Long, String>? = synchronized(speechLock) { unspokenReply }

    fun markSpoken(id: Long) = synchronized(speechLock) {
        if (unspokenReply?.first == id) unspokenReply = null
    }

    private fun completeRequest(endpoint: String, model: String, question: String) {
        var gatewayFailure: OwnerGateway.GatewayFailure? = null
        val reply = try {
            responder(endpoint, model, question).takeIf { it.text.isNotBlank() }
        } catch (failure: OwnerGateway.GatewayFailure) {
            gatewayFailure = failure
            null
        } catch (_: Exception) { null }
        val answer = reply?.text
        var status: String
        if (answer != null) {
            try {
                store.saveMessage("assistant", "Model: " + answer)
                synchronized(speechLock) {
                    replySequence++
                    unspokenReply = replySequence to answer
                }
                status = "Son model isteği başarılı: " + model
            } catch (_: Exception) {
                status = "Model yanıtı geçmişe kaydedilemedi. Depolama alanını kontrol et."
            }
        } else {
            status = "Son model isteği başarısız"
            try {
                store.saveMessage("assistant",
                    "Model yanıtı alınamadı. Bağlantıyı, hizmet yetkilerini ve model adını kontrol et.")
            } catch (_: Exception) {
                status = "Model hatası geçmişe kaydedilemedi. Depolama alanını kontrol et."
            }
        }
        val finalStatus = status
        main.post {
            // Keep pending true until this main-thread publication, so an old
            // completion cannot overwrite a newer request's busy state.
            if (!cleared) {
                // Include local command records written while the model ran.
                refreshHistory()
            }
            pending = false
            mutableState.value = State(
                false, finalStatus, reply?.responseId,
                reply?.providerRequestId ?: gatewayFailure?.providerRequestId,
                reply?.clientRequestId, gatewayFailure?.httpStatus,
                gatewayFailure?.providerErrorCode, gatewayFailure?.retryable ?: false,
                gatewayFailure?.retryAfterSeconds, gatewayFailure?.errorCode
            )
        }
    }

    override fun onCleared() {
        cleared = true
        // shutdown() does not interrupt accepted work. Closing is queued after
        // the current request, so even a cleared ViewModel persists its answer.
        worker.execute { store.close() }
        worker.shutdown()
        super.onCleared()
    }

    private fun requireMainThread() {
        check(Looper.myLooper() == Looper.getMainLooper()) { "Sohbet işlemi ana thread'den çağrılmalı" }
    }
}
