package com.example.gptasistan

import android.os.Bundle
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
    private val prefs by lazy { getSharedPreferences("kral_model", MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = KralStore(this)
        session = ViewModelProvider(this)[ChatSession::class.java]
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 24)
        }
        root.addView(TextView(this).apply {
            text = "KRAL ASİSTAN — aday sürüm"
            textSize = 19f
        })
        root.addView(TextView(this).apply {
            text = "Bu adayda uygulama kilidi ve hesap girişi henüz yok."
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
            speakLatestReply()
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
                    if (!ModelGateway.valid(endpoint) || model.isBlank()) {
                        connectionStatus.text = "Model bağlantısı yapılandırılmadı"
                        recordLocal(raw) { "Model henüz bağlanmadı. Model tuşundan sana ait HTTPS hizmetini yapılandır." }
                    } else session.send(endpoint, model, command.value)
                }
                KralCommand.Invalid -> recordLocal(raw) { "Komut geçersiz. " + KralCore.help() }
            }
        } catch (_: Exception) {
            connectionStatus.text = "İşlem kaydedilemedi; yazdığın metin korundu. Depolama alanını kontrol et."
            false
        }
    }

    private fun speakLatestReply() {
        if (stopped || !ttsReady || !prefs.getBoolean("speak_replies", false)) return
        val reply = session.peekUnspokenReply() ?: return
        if (tts?.speak(reply.second.take(4000), TextToSpeech.QUEUE_FLUSH, null, "kral-reply") == TextToSpeech.SUCCESS)
            session.markSpoken(reply.first)
    }

    private fun configureModel() {
        if (session.state.value?.busy == true) return
        val fields = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 16, 24, 0)
        }
        val endpoint = EditText(this).apply {
            hint = "https://sunucu.example/v1/chat/completions"
            setText(prefs.getString("endpoint", ""))
            isSingleLine = true
        }
        val model = EditText(this).apply {
            hint = "Model kimliği"
            setText(prefs.getString("model", ""))
            isSingleLine = true
        }
        fields.addView(endpoint); fields.addView(model)
        AlertDialog.Builder(this)
            .setTitle("Model bağla (HTTPS)")
            .setMessage("Yalnız yazdığın sohbet mesajı seçtiğin sunucuya gönderilir. Geçmiş, hafıza ve görevler otomatik gönderilmez. Buraya API anahtarı yazma.")
            .setView(fields)
            .setPositiveButton("Kaydet") { _, _ ->
                val url = endpoint.text.toString().trim()
                val name = model.text.toString().trim()
                if (ModelGateway.valid(url) && name.isNotEmpty()) {
                    prefs.edit().putString("endpoint", url).putString("model", name).apply()
                    session.resetConnectionStatus()
                } else connectionStatus.text = "Geçerli HTTPS adresi ve model adı gerekli; adrese anahtar ekleme."
            }
            .setNeutralButton("Bağlantıyı kaldır") { _, _ ->
                prefs.edit().remove("endpoint").remove("model").apply()
                session.resetConnectionStatus("Model bağlantısı yapılandırılmadı")
            }
            .setNegativeButton("Vazgeç", null)
            .show()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("draft", input.text.toString())
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
        store.close()
        super.onDestroy()
    }
}
