package com.example.gptasistan

import android.os.Bundle
import android.text.InputType
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Spinner
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
    private lateinit var mode: Spinner
    private lateinit var task: Spinner
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
        address = field("Owner API HTTPS kökü (PWA adresi değil)").apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
        }
        token = field("Owner oturum anahtarı").apply {
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        mode = Spinner(this).apply {
            adapter = ArrayAdapter(
                this@MainActivity, android.R.layout.simple_spinner_dropdown_item,
                arrayOf("Tek model", "Uzman ekip (fleet)")
            )
        }
        task = Spinner(this).apply {
            adapter = ArrayAdapter(
                this@MainActivity, android.R.layout.simple_spinner_dropdown_item,
                arrayOf("Genel", "Kod", "Araştırma", "Yazı")
            )
        }
        prompt = field("Yapay zekâya sor", 4)
        send = Button(this).apply { text = "Gönder" }
        val checkConnection = Button(this).apply { text = "Owner API bağlantısını kontrol et" }
        result = TextView(this).apply {
            text = "Bu istemci /v1/ask Bearer API kullanır; Railway PWA kullanıcı adı/şifresi bu alanlara ait değildir. Anahtar telefona kaydedilmez. /health testi model yanıtını doğrulamaz."
            textSize = 16f
            setTextIsSelectable(true)
        }
        column.addView(heading)
        column.addView(address)
        column.addView(token)
        column.addView(mode)
        column.addView(task)
        column.addView(prompt)
        column.addView(send)
        column.addView(checkConnection)
        column.addView(result)
        val scroll = ScrollView(this)
        scroll.addView(column, ViewGroup.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ))
        setContentView(scroll)
        send.setOnClickListener { sendPrompt() }
        checkConnection.setOnClickListener { checkOwnerApiHealth(checkConnection) }
    }


    private fun ownerRoot(): String? {
        val candidate = address.text.toString().trim().trimEnd('/')
        val parsed = try { URL(candidate) } catch (_: Exception) { return null }
        if (parsed.protocol != "https" || parsed.host.isBlank() ||
            parsed.userInfo != null || parsed.query != null || parsed.ref != null ||
            (parsed.path.isNotEmpty() && parsed.path != "/")) {
            return null
        }
        return candidate
    }

    /** An unauthenticated liveness probe only; never sends the owner token. */
    private fun checkOwnerApiHealth(button: Button) {
        val endpoint = ownerRoot()
        if (endpoint == null) {
            result.text = "Geçerli HTTPS Owner API kökü girin; PWA adresini burada kullanmayın."
            return
        }
        button.isEnabled = false
        result.text = "Owner API /health kontrol ediliyor (anahtar gönderilmiyor)..."
        executor.execute {
            val output = try {
                val connection = URL("$endpoint/health").openConnection() as HttpURLConnection
                try {
                    connection.requestMethod = "GET"
                    connection.connectTimeout = 10_000
                    connection.readTimeout = 10_000
                    connection.instanceFollowRedirects = false
                    connection.setRequestProperty("Accept", "application/json")
                    when (val status = connection.responseCode) {
                        200 -> {
                            val payload = ByteArrayOutputStream()
                            connection.inputStream.use { stream ->
                                val buffer = ByteArray(512)
                                while (true) {
                                    val n = stream.read(buffer)
                                    if (n < 0) break
                                    if (payload.size() + n > 4_096) {
                                        throw IllegalStateException("health_response_too_large")
                                    }
                                    payload.write(buffer, 0, n)
                                }
                            }
                            val mediaType = connection.contentType.orEmpty().substringBefore(';').trim()
                            val alive = mediaType.equals("application/json", ignoreCase = true) &&
                                JSONObject(payload.toString("UTF-8")).optString("status") == "alive"
                            if (alive) "OWNER_API_HEALTH=OBSERVED. Sunucu canlı; model ve kimlik doğrulaması henüz test edilmedi."
                            else "Bu adres beklenen Owner API /health sözleşmesini karşılamıyor."
                        }
                        401, 403 -> "HTTP $status: Bu adres oturum istiyor; PWA ile Owner API farklıdır."
                        404 -> "HTTP 404: /health bulunamadı. Yanlış sunucu veya farklı API."
                        301, 302, 303, 307, 308 -> "Yönlendirme reddedildi. Doğrudan HTTPS Owner API kökü gerekli."
                        else -> "Owner API sağlık kontrolü HTTP $status döndürdü."
                    }
                } finally {
                    connection.disconnect()
                }
            } catch (_: Exception) {
                "Owner API sağlık kontrolü başarısız: HTTPS, DNS veya /health yanıtını doğrulayın."
            }
            runOnUiThread {
                result.text = output
                button.isEnabled = true
            }
        }
    }

    private fun sendPrompt() {
        val endpoint = ownerRoot()
        val accessKey = token.text.toString()
        val question = prompt.text.toString().trim()
        val selectedMode = if (mode.selectedItemPosition == 1) "fleet" else "single"
        val selectedTask = arrayOf("general", "code", "research", "writing")[task.selectedItemPosition]
        if (endpoint == null || accessKey.length !in 32..512 || question.isEmpty()) {
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
                    val body = JSONObject().put("prompt", question).put("mode", selectedMode)
                        .put("task", selectedTask).toString().toByteArray(Charsets.UTF_8)
                    if (body.size > 16_384) throw IllegalArgumentException("Soru çok uzun")
                    connection.outputStream.use { it.write(body) }
                    val status = connection.responseCode
                    if (status != 200) {
                        when (status) {
                            401 -> "HTTP 401: Owner Bearer anahtarı reddedildi; PWA parolası geçerli değildir."
                            403 -> "HTTP 403: Bu Owner istemcisine erişim engellendi."
                            404 -> "HTTP 404: /v1/ask yok; sunucu farklı bir API kullanıyor."
                            429 -> "HTTP 429: Owner API yoğun. Güvenli aralıkla tekrar deneyin."
                            503 -> "HTTP 503: Model sağlayıcısı veya fleet hazır değil."
                            else -> "Sunucu HTTP $status döndürdü."
                        }
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
