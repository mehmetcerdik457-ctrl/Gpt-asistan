package com.example.gptasistan

import android.os.Bundle
import android.text.InputType
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import org.json.JSONObject

/** Owner client only. Provider keys and the owner token are never bundled in the APK. */
class MainActivity : AppCompatActivity() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var address: EditText
    private lateinit var token: EditText
    private lateinit var prompt: EditText
    private lateinit var result: TextView
    private lateinit var send: Button

    private fun field(hint: String, lines: Int = 1): EditText {
        return EditText(this).apply {
            this.hint = hint
            minLines = lines
            if (lines > 1) {
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val pad = (16 * resources.displayMetrics.density).toInt()
            setPadding(pad, pad, pad, pad)
        }
        val heading = TextView(this).apply {
            text = "MEHMET AI — Owner Client"
            textSize = 22f
        }
        address = field("Sunucu kökü: https://ai.example.com").apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        token = field("Owner oturum anahtarı").apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        prompt = field("Yapay zekâya sor", 4)
        send = Button(this).apply { text = "Gönder" }
        result = TextView(this).apply {
            text = "Bağlantı için kendi HTTPS sunucunuzu ve oturum anahtarınızı girin. Bilgiler telefona kaydedilmez."
            textSize = 16f
            setTextIsSelectable(true)
        }
        column.addView(heading)
        column.addView(address)
        column.addView(token)
        column.addView(prompt)
        column.addView(send)
        column.addView(result)
        val scroll = ScrollView(this)
        scroll.addView(column, ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ))
        setContentView(scroll)
        send.setOnClickListener { sendPrompt() }
    }

    private fun sendPrompt() {
        val endpoint = address.text.toString().trim().trimEnd('/')
        val accessKey = token.text.toString()
        val question = prompt.text.toString().trim()
        val url = try { URL(endpoint) } catch (_: Exception) { null }
        if (url == null || url.protocol != "https" || url.host.isNullOrBlank() ||
            url.userInfo != null || url.query != null || url.ref != null ||
            (url.path.isNotEmpty() && url.path != "/") || accessKey.length < 32 || question.isEmpty()) {
            result.text = "HTTPS sunucu kökü, geçerli owner anahtarı ve soru gereklidir."
            return
        }
        send.isEnabled = false
        result.text = "Yanıt bekleniyor..."
        executor.execute {
            val output = try {
                val connection = URL(endpoint + "/v1/ask").openConnection() as HttpURLConnection
                try {
                    connection.requestMethod = "POST"
                    connection.connectTimeout = 15_000
                    connection.readTimeout = 120_000
                    connection.setRequestProperty("Authorization", "Bearer " + accessKey)
                    connection.setRequestProperty("Content-Type", "application/json")
                    connection.setRequestProperty("Accept", "application/json")
                    connection.instanceFollowRedirects = false
                    connection.doOutput = true
                    val body = JSONObject().put("prompt", question).toString().toByteArray(Charsets.UTF_8)
                    if (body.size > 16_384) throw IllegalArgumentException("Soru çok uzun")
                    connection.outputStream.use { it.write(body) }
                    val status = connection.responseCode
                    if (status != 200) {
                        "Sunucu HTTP " + status + " döndürdü."
                    } else {
                        val bytes = ByteArrayOutputStream()
                        connection.inputStream.use { stream ->
                            val buffer = ByteArray(4096)
                            while (true) {
                                val count = stream.read(buffer)
                                if (count < 0) break
                                if (bytes.size() + count > 256_000) throw IllegalStateException("Yanıt sınırı aşıldı")
                                bytes.write(buffer, 0, count)
                            }
                        }
                        JSONObject(bytes.toString("UTF-8")).getString("answer")
                    }
                } finally {
                    connection.disconnect()
                }
            } catch (_: Exception) {
                "Bağlantı kurulamadı veya yanıt geçersiz. HTTPS, sunucu ve ağ ayarlarını kontrol edin."
            }
            runOnUiThread {
                result.text = output
                send.isEnabled = true
            }
        }
    }

    override fun onDestroy() {
        executor.shutdownNow()
        super.onDestroy()
    }
}
