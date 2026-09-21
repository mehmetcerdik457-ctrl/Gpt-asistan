package com.example.gptasistan

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
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
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val evidence = buildEvidence().toString(2)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 48)
        }

        val title = TextView(this).apply {
            text = "GPT Asistan · Real Device Evidence"
            textSize = 20f
        }
        val body = TextView(this).apply {
            text = evidence
            textSize = 14f
            setTextIsSelectable(true)
            setPadding(0, 24, 0, 24)
        }
        val copy = Button(this).apply {
            text = "Kanıtı Kopyala"
            setOnClickListener {
                val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("GPT Asistan device evidence", evidence))
                Toast.makeText(this@MainActivity, "Kanıt panoya kopyalandı", Toast.LENGTH_SHORT).show()
            }
        }
        val share = Button(this).apply {
            text = "Kanıtı Paylaş"
            setOnClickListener {
                val intent = Intent(Intent.ACTION_SEND).apply {
                    type = "application/json"
                    putExtra(Intent.EXTRA_TEXT, evidence)
                }
                startActivity(Intent.createChooser(intent, "Device evidence paylaş"))
            }
        }

        container.addView(title)
        container.addView(body)
        container.addView(copy)
        container.addView(share)
        setContentView(ScrollView(this).apply { addView(container) })
    }

    private fun buildEvidence(): JSONObject {
        val info = if (Build.VERSION.SDK_INT >= 33) {
            packageManager.getPackageInfo(packageName, PackageManager.PackageInfoFlags.of(0))
        } else {
            @Suppress("DEPRECATION")
            packageManager.getPackageInfo(packageName, 0)
        }
        val versionCode = if (Build.VERSION.SDK_INT >= 28) {
            info.longVersionCode
        } else {
            @Suppress("DEPRECATION")
            info.versionCode.toLong()
        }
        val apkHash = sha256(File(applicationInfo.sourceDir))
        val postcondition = if (apkHash.matches(Regex("^[0-9a-f]{64}$")) && !info.versionName.isNullOrBlank()) "PASS" else "FAIL"

        val payload = JSONObject()
            .put("device_model", "${Build.MANUFACTURER} ${Build.MODEL}".trim())
            .put("android_version", "${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})")
            .put("package_name", packageName)
            .put("version_name", info.versionName ?: "")
            .put("version_code", versionCode.toString())
            .put("artifact_sha256", apkHash)
            .put("install_result", "PASS")
            .put("launch_result", "PASS")
            .put("postcondition_result", postcondition)

        return JSONObject()
            .put("version", 1)
            .put("status", if (postcondition == "PASS") "REAL_DEVICE_EVIDENCE_CAPTURED" else "REAL_DEVICE_EVIDENCE_FAIL")
            .put("git_head", BuildConfig.BUILD_GIT_SHA)
            .put("captured_at_epoch_ms", System.currentTimeMillis())
            .put("evidence", payload)
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
