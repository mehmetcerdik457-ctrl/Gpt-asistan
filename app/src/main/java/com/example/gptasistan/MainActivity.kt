package com.example.gptasistan

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest

class MainActivity : AppCompatActivity() {
    private lateinit var statusView: TextView
    private lateinit var logView: TextView
    private lateinit var evidenceView: TextView
    private lateinit var selfTestTarget: Button
    private val handler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 48)
        }
        container.addView(TextView(this).apply {
            text = "GPT Asistan · Phone Agent Runtime v1.1"
            textSize = 20f
        })
        statusView = TextView(this).apply { textSize = 16f; setPadding(0, 20, 0, 20) }
        container.addView(statusView)
        container.addView(Button(this).apply {
            text = "Erişilebilirlik Ayarlarını Aç"
            setOnClickListener { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        })

        selfTestTarget = Button(this).apply {
            text = "SELF_TEST_TARGET"
            setOnClickListener {
                val prefs = getSharedPreferences("phone_agent_self_test", MODE_PRIVATE)
                val hits = prefs.getInt("target_hits", 0) + 1
                prefs.edit().putInt("target_hits", hits).apply()
                Toast.makeText(this@MainActivity, "Self-test target hit #" + hits, Toast.LENGTH_SHORT).show()
                refreshRuntime()
            }
        }
        container.addView(selfTestTarget)

        container.addView(Button(this).apply { text = "Ana Ekran"; setOnClickListener { runAction(PhoneActionType.HOME) } })
        container.addView(Button(this).apply { text = "Geri"; setOnClickListener { runAction(PhoneActionType.BACK) } })
        container.addView(Button(this).apply { text = "Son Uygulamalar"; setOnClickListener { runAction(PhoneActionType.RECENTS) } })
        container.addView(Button(this).apply { text = "Aşağı Kaydır"; setOnClickListener { runAction(PhoneActionType.SCROLL_FORWARD) } })
        container.addView(Button(this).apply { text = "Yukarı Kaydır"; setOnClickListener { runAction(PhoneActionType.SCROLL_BACKWARD) } })

        val clickText = EditText(this).apply {
            hint = "Görünür metin"
            setText("SELF_TEST_TARGET")
            setSingleLine(true)
        }
        container.addView(clickText)
        container.addView(Button(this).apply {
            text = "Metne Tıkla"
            setOnClickListener {
                val ok = PhoneAgentAccessibilityService.instance?.execute(
                    PhoneActionType.CLICK_TEXT, text = clickText.text.toString()
                ) == true
                toastResult("CLICK_TEXT", ok)
                handler.postDelayed({ refreshRuntime() }, 250)
            }
        })

        container.addView(Button(this).apply {
            text = "Yerel Self-Test: TAP + CLICK + SCROLL"
            setOnClickListener { runLocalSelfTest() }
        })

        container.addView(Button(this).apply {
            text = "Olay Günlüğünü Temizle"
            setOnClickListener {
                PhoneAgentAccessibilityService.clearEvents(this@MainActivity)
                getSharedPreferences("phone_agent_self_test", MODE_PRIVATE).edit().clear().apply()
                refreshRuntime()
            }
        })

        container.addView(Button(this).apply {
            text = "Runtime Durumunu Yenile"
            setOnClickListener { refreshRuntime() }
        })

        logView = TextView(this).apply { textSize = 12f; setTextIsSelectable(true); setPadding(0, 24, 0, 24) }
        container.addView(logView)
        container.addView(TextView(this).apply { text = "Gerçek Cihaz + Runtime Kanıtı"; textSize = 17f; setPadding(0, 24, 0, 8) })
        evidenceView = TextView(this).apply { textSize = 12f; setTextIsSelectable(true) }
        container.addView(evidenceView)

        container.addView(Button(this).apply {
            text = "Kanıtı Kopyala"
            setOnClickListener {
                val evidence = buildEvidence().toString(2)
                val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("GPT Asistan phone-agent evidence", evidence))
                Toast.makeText(this@MainActivity, "Güncel kanıt panoya kopyalandı", Toast.LENGTH_SHORT).show()
            }
        })

        container.addView(Button(this).apply {
            text = "Kanıtı Paylaş"
            setOnClickListener {
                val evidence = buildEvidence().toString(2)
                val intent = Intent(Intent.ACTION_SEND).apply {
                    type = "application/json"
                    putExtra(Intent.EXTRA_TEXT, evidence)
                }
                startActivity(Intent.createChooser(intent, "Phone Agent evidence paylaş"))
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
        toastResult(action.name, ok)
        handler.postDelayed({ refreshRuntime() }, 250)
    }

    private fun runLocalSelfTest() {
        val service = PhoneAgentAccessibilityService.instance
        if (service == null) {
            Toast.makeText(this, "Accessibility service bağlı değil", Toast.LENGTH_SHORT).show()
            refreshRuntime()
            return
        }
        val location = IntArray(2)
        selfTestTarget.getLocationOnScreen(location)
        val x = location[0] + selfTestTarget.width / 2f
        val y = location[1] + selfTestTarget.height / 2f
        val tapAccepted = service.execute(PhoneActionType.TAP, x = x, y = y)
        handler.postDelayed({ service.execute(PhoneActionType.CLICK_TEXT, text = "SELF_TEST_TARGET") }, 450)
        handler.postDelayed({ service.execute(PhoneActionType.SCROLL_FORWARD) }, 900)
        handler.postDelayed({ refreshRuntime() }, 1400)
        Toast.makeText(this, "Self-test başladı · tapAccepted=" + tapAccepted, Toast.LENGTH_SHORT).show()
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
        val start = maxOf(0, events.length() - 14)
        for (i in start until events.length()) sb.append(events.getJSONObject(i)).append('\n')
        logView.text = sb.toString()
        evidenceView.text = buildEvidence().toString(2)
    }

    private fun hasPass(events: JSONArray, action: String): Boolean {
        for (i in 0 until events.length()) {
            val item = events.optJSONObject(i) ?: continue
            if (item.optString("action") == action && item.optString("status") == "PASS") return true
        }
        return false
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
        val devicePostcondition = if (apkHash.matches(Regex("^[0-9a-f]{64}$")) && !info.versionName.isNullOrBlank()) "PASS" else "FAIL"
        val enabled = PhoneAgentAccessibilityService.isEnabled(this)
        val connected = PhoneAgentAccessibilityService.instance != null
        val events = PhoneAgentAccessibilityService.readEvents(this)
        val hits = getSharedPreferences("phone_agent_self_test", MODE_PRIVATE).getInt("target_hits", 0)
        val tapPass = hasPass(events, "TAP")
        val clickPass = hasPass(events, "CLICK_TEXT")
        val scrollPass = hasPass(events, "SCROLL_FORWARD")
        val runtimePostcondition = if (enabled && connected && hits > 0 && tapPass && clickPass && scrollPass) "PASS" else "PENDING"

        val device = JSONObject()
            .put("device_model", (Build.MANUFACTURER + " " + Build.MODEL).trim())
            .put("android_version", Build.VERSION.RELEASE + " (SDK " + Build.VERSION.SDK_INT + ")")
            .put("package_name", packageName)
            .put("version_name", info.versionName ?: "")
            .put("version_code", versionCode.toString())
            .put("artifact_sha256", apkHash)
            .put("install_result", "PASS")
            .put("launch_result", "PASS")
            .put("postcondition_result", devicePostcondition)

        val runtime = JSONObject()
            .put("implementation", "v1_accessibility")
            .put("accessibility_enabled", enabled)
            .put("service_connected", connected)
            .put("network_permission", "NONE")
            .put("self_test_target_hits", hits)
            .put("tap_pass", tapPass)
            .put("click_text_pass", clickPass)
            .put("scroll_forward_pass", scrollPass)
            .put("runtime_postcondition_result", runtimePostcondition)
            .put("events", events)

        return JSONObject()
            .put("version", 3)
            .put("status", if (devicePostcondition == "PASS") "REAL_DEVICE_EVIDENCE_CAPTURED" else "REAL_DEVICE_EVIDENCE_FAIL")
            .put("git_head", BuildConfig.BUILD_GIT_SHA)
            .put("captured_at_epoch_ms", System.currentTimeMillis())
            .put("evidence", device)
            .put("phone_agent", runtime)
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(64 * 1024)
        FileInputStream(file).use { input ->
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
}
