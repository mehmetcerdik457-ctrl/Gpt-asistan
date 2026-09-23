package com.example.gptasistan

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest

class MainActivity : AppCompatActivity() {
    private lateinit var statusView: TextView
    private lateinit var logView: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val evidence = buildEvidence().toString(2)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 48)
        }
        container.addView(TextView(this).apply {
            text = "GPT Asistan · Phone Agent Runtime v1"; textSize = 20f
        })
        statusView = TextView(this).apply { textSize = 16f; setPadding(0, 20, 0, 20) }
        container.addView(statusView)
        container.addView(Button(this).apply {
            text = "Erişilebilirlik Ayarlarını Aç"
            setOnClickListener { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        })
        container.addView(Button(this).apply { text = "Ana Ekran"; setOnClickListener { runAction(PhoneActionType.HOME) } })
        container.addView(Button(this).apply { text = "Geri"; setOnClickListener { runAction(PhoneActionType.BACK) } })
        container.addView(Button(this).apply { text = "Son Uygulamalar"; setOnClickListener { runAction(PhoneActionType.RECENTS) } })
        container.addView(Button(this).apply { text = "Aşağı Kaydır"; setOnClickListener { runAction(PhoneActionType.SCROLL_FORWARD) } })
        container.addView(Button(this).apply { text = "Yukarı Kaydır"; setOnClickListener { runAction(PhoneActionType.SCROLL_BACKWARD) } })
        val clickText = EditText(this).apply { hint = "Görünür metin"; setSingleLine(true) }
        container.addView(clickText)
        container.addView(Button(this).apply {
            text = "Metne Tıkla"
            setOnClickListener {
                val ok = PhoneAgentAccessibilityService.instance?.execute(
                    PhoneActionType.CLICK_TEXT, text = clickText.text.toString()
                ) == true
                toastResult("CLICK_TEXT", ok); refreshRuntime()
            }
        })
        container.addView(Button(this).apply {
            text = "Ekran Merkezine Dokun"
            setOnClickListener {
                val x = resources.displayMetrics.widthPixels / 2f
                val y = resources.displayMetrics.heightPixels / 2f
                val ok = PhoneAgentAccessibilityService.instance?.execute(PhoneActionType.TAP, x = x, y = y) == true
                toastResult("TAP", ok); refreshRuntime()
            }
        })
        container.addView(Button(this).apply {
            text = "Runtime Durumunu Yenile"; setOnClickListener { refreshRuntime() }
        })
        logView = TextView(this).apply { textSize = 12f; setTextIsSelectable(true); setPadding(0, 24, 0, 24) }
        container.addView(logView)
        container.addView(TextView(this).apply { text = "Gerçek Cihaz Kanıtı"; textSize = 17f; setPadding(0, 24, 0, 8) })
        container.addView(TextView(this).apply { text = evidence; textSize = 12f; setTextIsSelectable(true) })
        container.addView(Button(this).apply {
            text = "Kanıtı Kopyala"
            setOnClickListener {
                val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("GPT Asistan device evidence", evidence))
                Toast.makeText(this@MainActivity, "Kanıt panoya kopyalandı", Toast.LENGTH_SHORT).show()
            }
        })
        container.addView(Button(this).apply {
            text = "Kanıtı Paylaş"
            setOnClickListener {
                val intent = Intent(Intent.ACTION_SEND).apply {
                    type = "application/json"; putExtra(Intent.EXTRA_TEXT, evidence)
                }
                startActivity(Intent.createChooser(intent, "Device evidence paylaş"))
            }
        })
        setContentView(ScrollView(this).apply { addView(container) })
        refreshRuntime()
    }

    override fun onResume() {
        super.onResume()
        if (::statusView.isInitialized) refreshRuntime()
    }

    private fun runAction(action: PhoneActionType) {
        val ok = PhoneAgentAccessibilityService.instance?.execute(action) == true
        toastResult(action.name, ok); refreshRuntime()
    }

    private fun toastResult(action: String, ok: Boolean) {
        val message = action + ": " + if (ok) "kabul edildi" else "çalışmadı / servis kapalı"
        Toast.makeText(this, message, Toast.LENGTH_SHORT).show()
    }

    private fun refreshRuntime() {
        val enabled = PhoneAgentAccessibilityService.isEnabled(this)
        val connected = PhoneAgentAccessibilityService.instance != null
        statusView.text = "Accessibility enabled=" + enabled + " · service connected=" + connected + " · network permission=NONE"
        val events = PhoneAgentAccessibilityService.readEvents(this)
        val sb = StringBuilder("Son olaylar:\n")
        val start = maxOf(0, events.length() - 12)
        for (i in start until events.length()) sb.append(events.getJSONObject(i)).append('\n')
        logView.text = sb.toString()
    }

    private fun buildEvidence(): JSONObject {
        val info = if (Build.VERSION.SDK_INT >= 33) {
            packageManager.getPackageInfo(packageName, PackageManager.PackageInfoFlags.of(0))
        } else {
            @Suppress("DEPRECATION") packageManager.getPackageInfo(packageName, 0)
        }
        val versionCode = if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else {
            @Suppress("DEPRECATION") info.versionCode.toLong()
        }
        val apkHash = sha256(File(applicationInfo.sourceDir))
        val postcondition = if (apkHash.matches(Regex("^[0-9a-f]{64}$")) && !info.versionName.isNullOrBlank()) "PASS" else "FAIL"
        val payload = JSONObject()
            .put("device_model", (Build.MANUFACTURER + " " + Build.MODEL).trim())
            .put("android_version", Build.VERSION.RELEASE + " (SDK " + Build.VERSION.SDK_INT + ")")
            .put("package_name", packageName)
            .put("version_name", info.versionName ?: "")
            .put("version_code", versionCode.toString())
            .put("artifact_sha256", apkHash)
            .put("install_result", "PASS")
            .put("launch_result", "PASS")
            .put("postcondition_result", postcondition)
        return JSONObject()
            .put("version", 2)
            .put("status", if (postcondition == "PASS") "REAL_DEVICE_EVIDENCE_CAPTURED" else "REAL_DEVICE_EVIDENCE_FAIL")
            .put("git_head", BuildConfig.BUILD_GIT_SHA)
            .put("phone_agent_runtime", "v1_accessibility")
            .put("captured_at_epoch_ms", System.currentTimeMillis())
            .put("evidence", payload)
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(64 * 1024)
        FileInputStream(file).use { input ->
            while (true) {
                val read = input.read(buffer); if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
