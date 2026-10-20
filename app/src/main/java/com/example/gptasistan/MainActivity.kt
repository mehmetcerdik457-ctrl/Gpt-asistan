package com.example.gptasistan

import android.os.Bundle
import android.content.Intent
import android.speech.tts.TextToSpeech
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import java.util.Locale
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener {
    private lateinit var store: KralStore
    private lateinit var transcript: TextView
    private lateinit var input: EditText
    private var tts: TextToSpeech? = null
    private var ttsReady = false
    private val prefs by lazy { getSharedPreferences("kral_model", MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = KralStore(this)
        tts = TextToSpeech(this, this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 24)
        }
        val header = TextView(this).apply {
            text = "KRAL ASİSTAN — kişisel, yerel ve güvenli"
            textSize = 19f
        }
        root.addView(header)
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        fun button(label: String, action: () -> Unit) {
            val b = Button(this).apply { text = label; setOnClickListener { action() } }
            actions.addView(b, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        button("Hafıza") { append(store.memory()) }
        button("Görevler") { append(store.tasks()) }
        button("Model") { configureModel() }
        root.addView(actions)
        val actions2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val status = Button(this).apply {
            text = "Owner / Bridge durumu (salt okunur)"
            setOnClickListener { append(OwnerStatus.readOnlyReport(this@MainActivity)) }
        }
        actions2.addView(status)
        root.addView(actions2)
        val scroller = ScrollView(this)
        transcript = TextView(this).apply { textSize = 16f; text = "Merhaba! " + KralCore.help() + "\n" }
        scroller.addView(transcript)
        root.addView(scroller, LinearLayout.LayoutParams(-1, 0, 1f))
        val bottom = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        input = EditText(this).apply { hint = "Bir şey yaz veya /yardim" ; isSingleLine = true }
        bottom.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        bottom.addView(Button(this).apply {
            text = "Gönder"
            setOnClickListener {
                val line = input.text.toString()
                input.text.clear()
                handle(line)
            }
        })
        root.addView(bottom)
        setContentView(root)
    }

    private fun append(message: String) {
        transcript.append("\n" + message + "\n")
    }

    private fun handle(raw: String) {
        when (val command = KralCore.parse(raw)) {
            is KralCommand.Save -> { store.saveMemory(command.value); append("✓ Hafızaya kaydedildi") }
            KralCommand.ListMemory -> append(store.memory())
            is KralCommand.AddTask -> { store.addTask(command.value); append("✓ Görev eklendi") }
            KralCommand.ListTasks -> append(store.tasks())
            is KralCommand.FinishTask -> append(
                if (store.finishTask(command.id)) "✓ Tamamlandı" else "Görev bulunamadı veya zaten tamamlandı"
            )
            is KralCommand.Speak -> {
                if (ttsReady) {
                    tts?.speak(command.value, TextToSpeech.QUEUE_FLUSH, null, "kral-spoken")
                    append("Sesli okuma istendi")
                } else append("Telefonda seslendirme hazır değil")
            }
            KralCommand.Help -> append(KralCore.help())
            is KralCommand.Chat -> {
                append("Sen: " + command.value)
                val endpoint = prefs.getString("endpoint", "") ?: ""
                val model = prefs.getString("model", "") ?: ""
                if (!ModelGateway.valid(endpoint) || model.isBlank()) {
                    append("Model henüz bağlanmadı. Yerel hafıza ve görevler çalışır; Model tuşundan güvenilir HTTPS sunucunu seç.")
                } else thread {
                    val answer = try {
                        ModelGateway.reply(endpoint, model, command.value)
                    } catch (_: Exception) { "Model bağlantısında hata. Ağ ve sunucu durumunu kontrol et." }
                    runOnUiThread { append("Model: " + answer) }
                }
            }
            KralCommand.Invalid -> append("Komut geçersiz. " + KralCore.help())
        }
    }

    private fun configureModel() {
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
            .setMessage("Yalnız yazdığın sohbet mesajı seçtiğin sunucuya gönderilir. Hafıza ve görevler otomatik gönderilmez. Anahtar kaydedilmez.")
            .setView(fields)
            .setPositiveButton("Kaydet") { _, _ ->
                val url = endpoint.text.toString().trim()
                val name = model.text.toString().trim()
                if (ModelGateway.valid(url) && name.isNotEmpty()) {
                    prefs.edit().putString("endpoint", url).putString("model", name).apply()
                    append("HTTPS model adresi kaydedildi (bağlantı doğrulaması yapılmadı)")
                } else append("Kaydedilmedi: geçerli HTTPS adresi ve model adı gerekli")
            }
            .setNeutralButton("Bağlantıyı kaldır") { _, _ ->
                prefs.edit().clear().apply()
                append("Model bağlantısı kaldırıldı")
            }
            .setNegativeButton("Vazgeç", null)
            .show()
    }

    override fun onInit(status: Int) {
        ttsReady = status == TextToSpeech.SUCCESS
        if (ttsReady) tts?.language = Locale("tr", "TR")
    }
    override fun onDestroy() {
        tts?.stop()
        tts?.shutdown()
        store.close()
        super.onDestroy()
    }
}
