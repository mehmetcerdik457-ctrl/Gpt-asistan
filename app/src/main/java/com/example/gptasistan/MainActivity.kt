package com.example.gptasistan

import android.os.Bundle
import android.app.KeyguardManager
import android.app.Activity
import android.content.Intent
import android.view.View
import android.view.WindowManager
import kotlin.concurrent.thread
import android.speech.tts.TextToSpeech
import android.text.InputFilter
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.lifecycle.ViewModelProvider
import java.util.Locale

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener {
    private lateinit var store: KralStore
    private lateinit var session: ChatSession
    private lateinit var transcript: TextView
    private lateinit var input: EditText
    private lateinit var sendButton: Button
    private lateinit var modelButton: Button
    private lateinit var connectionStatus: TextView
    private lateinit var scroller: ScrollView
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private var stopped = false
    private var appUnlocked = false
    private var uiReady = false
    private var pendingUnlock: (() -> Unit)? = null
    private lateinit var contentRoot: LinearLayout
    private var initialState: Bundle? = null
    private val prefs by lazy { getSharedPreferences("kral_model", MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        initialState = savedInstanceState
        showLocked()
    }

    private fun showLocked() {
        val locked = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 48, 24, 24)
        }
        locked.addView(TextView(this).apply { text = "KRAL ASİSTAN — cihaz kilidiyle aç"; textSize = 20f })
        locked.addView(Button(this).apply {
            text = "Kilidi aç"
            setAllCaps(false)
            setOnClickListener { unlock {
                if (!uiReady) buildContent(initialState) else setContentView(contentRoot)
            } }
        })
        setContentView(locked)
    }

    @Suppress("DEPRECATION")
    private fun unlock(action: () -> Unit) {
        if (pendingUnlock != null) return
        val manager = getSystemService(KEYGUARD_SERVICE) as KeyguardManager
        if (!manager.isDeviceSecure) {
            AlertDialog.Builder(this).setMessage("Önce Android ayarlarından güvenli ekran kilidi oluştur.")
                .setPositiveButton("Tamam", null).show()
            return
        }
        val prompt = manager.createConfirmDeviceCredentialIntent("KRAL ASİSTAN", "Kişisel kayıtlarına ve sunucu isteğine erişimi doğrula")
            ?: return
        pendingUnlock = action
        startActivityForResult(prompt, 4701)
    }

    @Deprecated("Activity result used for the platform device credential screen")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 4701) return
        val action = pendingUnlock
        pendingUnlock = null
        if (resultCode == Activity.RESULT_OK) {
            appUnlocked = true
            if (uiReady) { contentRoot.visibility = View.VISIBLE; setContentView(contentRoot) }
            action?.invoke()
        } else { appUnlocked = false; showLocked() }
    }

    private fun buildContent(savedInstanceState: Bundle?) {
        store = KralStore(this)
        session = ViewModelProvider(this)[ChatSession::class.java]
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 24)
        }
        contentRoot = root
        uiReady = true
        root.addView(TextView(this).apply {
            text = "KRAL ASİSTAN — aday sürüm"
            textSize = 19f
        })
        root.addView(TextView(this).apply {
            text = "Cihaz kilidi açık. Sunucu erişimi kayıtlı sahip ve cihaz imzasıyla doğrulanır."
        })
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        fun button(label: String, action: () -> Unit): Button {
            val b = Button(this).apply { text = label; setOnClickListener { action() } }
            actions.addView(b, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            return b
        }
        button("Hafıza") { showLocal { store.memory() } }
        button("Görevler") { showLocal { store.tasks() } }
        modelButton = button("Model") { configureModel() }
        root.addView(actions)
        root.addView(Button(this).apply {
            text = "Sunucuya kayıt bilgisi"
            setOnClickListener { unlock { showRegistration() } }
        })
        root.addView(Button(this).apply {
            text = "Owner / Bridge durumu (salt okunur)"
            setOnClickListener { showLocal { OwnerStatus.readOnlyReport(this@MainActivity) } }
        })
        connectionStatus = TextView(this).apply {
            text = if ((prefs.getString("endpoint", "") ?: "").isBlank())
                "Model bağlantısı yapılandırılmadı" else "Model adresi kayıtlı; bağlantı doğrulanmadı"
        }
        root.addView(connectionStatus)
        root.addView(SwitchCompat(this).apply {
            text = "Yanıtları Türkçe seslendir"
            isChecked = prefs.getBoolean("speak_replies", false)
            setOnCheckedChangeListener { _, enabled ->
                prefs.edit().putBoolean("speak_replies", enabled).apply()
                if (!enabled) tts?.stop()
                else if (!ttsReady) connectionStatus.text = "Telefonda Türkçe seslendirme hazır değil"
                else speakLatestReply()
            }
        })
        scroller = ScrollView(this)
        transcript = TextView(this).apply { textSize = 16f }
        scroller.addView(transcript)
        root.addView(scroller, LinearLayout.LayoutParams(-1, 0, 1f))
        val bottom = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        input = EditText(this).apply {
            hint = "Bir şey yaz veya /yardim"
            isSingleLine = true
            filters = arrayOf(InputFilter.LengthFilter(16000))
            setText(savedInstanceState?.getString("draft").orEmpty())
        }
        bottom.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        sendButton = Button(this).apply {
            text = "Gönder"
            setOnClickListener {
                val line = input.text.toString().trim()
                if (line.isNotEmpty() && handle(line)) input.text.clear()
            }
        }
        bottom.addView(sendButton)
        root.addView(bottom)
        setContentView(root)
        session.history.observe(this) { history ->
            transcript.text = if (history.isEmpty()) "Merhaba! " + KralCore.help() + "\n"
                else history.joinToString("\n\n") { it.text } + "\n"
            scroller.post { scroller.fullScroll(ScrollView.FOCUS_DOWN) }
        }
        session.state.observe(this) { state ->
            sendButton.isEnabled = !state.busy
            modelButton.isEnabled = !state.busy
            if (state.status.isNotBlank()) connectionStatus.text = state.status
            if (appUnlocked) speakLatestReply()
        }
        tts = TextToSpeech(this, this)
    }

    private fun showLocal(action: () -> String) {
        try {
            store.saveMessage("assistant", action())
            session.refreshHistory()
        } catch (_: Exception) {
            connectionStatus.text = "Kayıt okunamadı veya kaydedilemedi. Depolama alanını kontrol et."
        }
    }

    // Keep command changes and their conversation record in one transaction.
    private fun recordLocal(raw: String, action: () -> String): Boolean {
        val db = store.writableDatabase
        db.beginTransaction()
        try {
            val reply = action()
            store.saveMessage("user", "Sen: " + raw)
            store.saveMessage("assistant", reply)
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        session.refreshHistory()
        return true
    }

    private fun handle(raw: String): Boolean {
        if (session.state.value?.busy == true) return false
        return try {
            when (val command = KralCore.parse(raw)) {
                is KralCommand.Save -> recordLocal(raw) {
                    store.saveMemory(command.value); "✓ Hafızaya kaydedildi"
                }
                KralCommand.ListMemory -> recordLocal(raw) { store.memory() }
                is KralCommand.Recall -> recordLocal(raw) { store.recall(command.query) }
                is KralCommand.AddTask -> recordLocal(raw) {
                    store.addTask(command.value); "✓ Görev eklendi"
                }
                KralCommand.ListTasks -> recordLocal(raw) { store.tasks() }
                is KralCommand.FinishTask -> recordLocal(raw) {
                    if (store.finishTask(command.id)) "✓ Tamamlandı" else "Görev bulunamadı veya zaten tamamlandı"
                }
                is KralCommand.Speak -> {
                    val accepted = recordLocal(raw) {
                        if (ttsReady) "Sesli okuma istendi" else "Telefonda Türkçe seslendirme hazır değil"
                    }
                    if (accepted && ttsReady)
                        tts?.speak(command.value.take(4000), TextToSpeech.QUEUE_FLUSH, null, "kral-spoken")
                    accepted
                }
                KralCommand.Help -> recordLocal(raw) { KralCore.help() }
                is KralCommand.Chat -> {
                    val endpoint = prefs.getString("endpoint", "") ?: ""
                    val model = prefs.getString("model", "") ?: ""
                    val owner = prefs.getString("owner_id", "").orEmpty()
                    if (!OwnerGateway.validBase(endpoint) ||
                        OwnerGateway.verifiedModels(endpoint, owner).none { it.id == model }) {
                        connectionStatus.text = "Doğrulanmış model yok; Model tuşuyla bağlantıyı yenile."
                        false
                    } else {
                        unlock {
                            if (OwnerGateway.verifiedModels(endpoint, owner).none { it.id == model }) {
                                session.resetConnectionStatus("Model doğrulamasının süresi doldu; Model tuşuyla yenile.")
                            } else if (session.send(endpoint, model, command.value) && input.text.toString().trim() == raw)
                                input.text.clear()
                        }
                        false
                    }
                }
                KralCommand.Invalid -> recordLocal(raw) { "Komut geçersiz. " + KralCore.help() }
            }
        } catch (_: Exception) {
            connectionStatus.text = "İşlem kaydedilemedi; yazdığın metin korundu. Depolama alanını kontrol et."
            false
        }
    }

    private fun speakLatestReply() {
        if (stopped || !appUnlocked || !ttsReady || !prefs.getBoolean("speak_replies", false)) return
        val reply = session.peekUnspokenReply() ?: return
        if (tts?.speak(reply.second.take(4000), TextToSpeech.QUEUE_FLUSH, null, "kral-reply") == TextToSpeech.SUCCESS)
            session.markSpoken(reply.first)
    }

    private fun showRegistration() {
        val owner = EditText(this).apply {
            hint = "Sunucuda tanımlanacak sahip kimliği"
            setText(prefs.getString("owner_id", ""))
            isSingleLine = true
        }
        AlertDialog.Builder(this).setTitle("Sunucu kaydı").setView(owner)
            .setMessage("Bu açık anahtar bilgilerini yalnız yönettiğin sunucuda kaydet. Burada kimlik yazmak sunucu yetkisi vermez.")
            .setPositiveButton("Açık bilgileri göster") { _, _ ->
                try {
                    val registration = OwnerIdentity.publicRegistration(owner.text.toString().trim())
                    val text = TextView(this).apply { this.text = registration; setTextIsSelectable(true); setPadding(24, 24, 24, 24) }
                    AlertDialog.Builder(this).setTitle("Yalnız açık kayıt bilgileri").setView(ScrollView(this).apply { addView(text) })
                        .setPositiveButton("Tamam", null).show()
                } catch (_: Exception) { connectionStatus.text = "Kayıt anahtarları oluşturulamadı; ekran kilidini ve sahip kimliğini kontrol et." }
            }.setNegativeButton("Vazgeç", null).show()
    }

    private fun configureModel() {
        if (session.state.value?.busy == true) return
        val fields = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 16, 24, 0) }
        val endpoint = EditText(this).apply {
            hint = "https://sana-ait-sunucu.example"
            setText(prefs.getString("endpoint", "")); isSingleLine = true
        }
        val owner = EditText(this).apply {
            hint = "Sunucuda kayıtlı sahip kimliği"
            setText(prefs.getString("owner_id", "")); isSingleLine = true
        }
        fields.addView(endpoint); fields.addView(owner)
        AlertDialog.Builder(this).setTitle("Doğrulanmış modeller")
            .setMessage("Sana ait HTTPS sunucusu sahip ve cihaz imzanı doğrular. Yalnız canlı yanıtla doğrulanan modeller listelenir. Geçmiş ve hafıza otomatik gönderilmez.")
            .setView(fields)
            .setPositiveButton("Bağlantıyı doğrula") { _, _ ->
                val base = endpoint.text.toString().trim().trimEnd('/')
                val identity = owner.text.toString().trim()
                if (!OwnerGateway.validBase(base) || !OmegaEnvelope.validOwner(identity)) {
                    connectionStatus.text = "Geçerli HTTPS sunucu kökü ve sahip kimliği gerekli."
                } else unlock { refreshModels(base, identity) }
            }
            .setNeutralButton("Bağlantıyı kaldır") { _, _ ->
                OwnerGateway.clear()
                prefs.edit().remove("endpoint").remove("model").remove("owner_id").apply()
                session.resetConnectionStatus("Model bağlantısı yapılandırılmadı")
            }.setNegativeButton("Vazgeç", null).show()
    }

    private fun refreshModels(base: String, identity: String) {
        modelButton.isEnabled = false
        sendButton.isEnabled = false
        connectionStatus.text = "Sahip imzası ve canlı model yanıtı doğrulanıyor…"
        thread {
            val models = try { OwnerGateway.models(base, identity) } catch (_: Exception) { null }
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                modelButton.isEnabled = true
                sendButton.isEnabled = true
                if (models == null) {
                    session.resetConnectionStatus("Bağlantı doğrulanamadı. Sunucu kaydını, ekran kilidini ve HTTPS adresini kontrol et.")
                } else {
                    prefs.edit().putString("endpoint", base).putString("owner_id", identity).remove("model").apply()
                    if (models.isEmpty()) {
                        session.resetConnectionStatus("Sunucuya erişildi; canlı yanıtla doğrulanmış model bulunamadı.")
                    } else if (appUnlocked) {
                        val labels = models.map { "${it.provider} / ${it.id} (${it.latencyMs} ms)" }.toTypedArray()
                        AlertDialog.Builder(this).setTitle("Canlı doğrulanan modeli seç").setItems(labels) { _, index ->
                            val selected = models[index]
                            if (appUnlocked && OwnerGateway.verifiedModels(base, identity).any { it == selected }) {
                                prefs.edit().putString("model", selected.id).apply()
                                session.resetConnectionStatus("Doğrulanmış model: ${selected.provider} / ${selected.id}")
                            } else session.resetConnectionStatus("Model doğrulamasının süresi doldu; bağlantıyı yenile.")
                        }.setNegativeButton("Vazgeç", null).show()
                    } else session.resetConnectionStatus("Model doğrulaması bitti; seçim için bağlantıyı tekrar aç.")
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (!appUnlocked && pendingUnlock == null) showLocked()
    }

    override fun onStop() {
        appUnlocked = false
        if (uiReady) contentRoot.visibility = View.INVISIBLE
        tts?.stop()
        super.onStop()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        if (uiReady) outState.putString("draft", input.text.toString())
        super.onSaveInstanceState(outState)
    }

    override fun onInit(status: Int) {
        if (stopped) return
        val language = if (status == TextToSpeech.SUCCESS) tts?.setLanguage(Locale("tr", "TR")) else null
        ttsReady = language != null && language != TextToSpeech.LANG_MISSING_DATA &&
            language != TextToSpeech.LANG_NOT_SUPPORTED
        runOnUiThread { if (!stopped) speakLatestReply() }
    }

    override fun onDestroy() {
        stopped = true
        tts?.stop()
        tts?.shutdown()
        if (uiReady) store.close()
        pendingUnlock = null
        super.onDestroy()
    }
}
