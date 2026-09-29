package com.example.gptasistan

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.mehmetcerdik.ownerai.BridgeClient
import com.mehmetcerdik.ownerai.OwnerAuth
import com.mehmetcerdik.ownerai.OwnerBrainActivity
import com.mehmetcerdik.ownerai.OwnerControlPlaneActivity
import com.mehmetcerdik.ownerai.OwnerMemory
import com.mehmetcerdik.ownerai.OwnerSession
import com.mehmetcerdik.ownerai.TrustedDeviceManager
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.security.MessageDigest

class MainActivity : AppCompatActivity() {
    private lateinit var statusView: TextView
    private lateinit var evidenceView: TextView
    private val handler = Handler(Looper.getMainLooper())
    private var selfTestTarget: Button? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 48)
        }

        container.addView(TextView(this).apply {
            text = "MEHMET Owner Companion · Hardened 1.5"
            textSize = 20f
        })
        statusView = TextView(this).apply {
            text = "OWNER_AUTH_REQUIRED"
            textSize = 16f
            setPadding(0, 20, 0, 20)
        }
        container.addView(statusView)

        container.addView(Button(this).apply {
            text = "OWNER Control Plane"
            setOnClickListener {
                OwnerAuth.require(this@MainActivity,
                    Runnable { startActivity(Intent(this@MainActivity, OwnerControlPlaneActivity::class.java)) },
                    java.util.function.Consumer { showStatus(it) })
            }
        })

        container.addView(Button(this).apply {
            text = "MEHMET AI — Brain / Memory / Models"
            setOnClickListener {
                OwnerAuth.require(this@MainActivity,
                    Runnable { startActivity(Intent(this@MainActivity, OwnerBrainActivity::class.java)) },
                    java.util.function.Consumer { showStatus(it) })
            }
        })

        if (BuildConfig.DEBUG) addDebugSelfTestControls(container)

        container.addView(Button(this).apply {
            text = "Owner Kanıtını Göster"
            setOnClickListener {
                OwnerAuth.require(this@MainActivity,
                    Runnable {
                        evidenceView.text = buildEvidence().toString(2)
                        refreshAuthenticatedStatus()
                    },
                    java.util.function.Consumer { showStatus(it) })
            }
        })

        evidenceView = TextView(this).apply {
            textSize = 12f
            text = "OWNER_AUTH_REQUIRED"
            setTextIsSelectable(false)
        }
        container.addView(evidenceView)

        container.addView(Button(this).apply {
            text = "Kanıtı Kopyala"
            setOnClickListener {
                OwnerAuth.require(this@MainActivity,
                    Runnable {
                        val evidence = buildEvidence().toString(2)
                        val clipboard = getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                        clipboard.setPrimaryClip(ClipData.newPlainText("MEHMET Owner evidence", evidence))
                        Toast.makeText(this@MainActivity, "Kanıt owner doğrulamasıyla panoya kopyalandı", Toast.LENGTH_SHORT).show()
                    },
                    java.util.function.Consumer { showStatus(it) })
            }
        })

        container.addView(Button(this).apply {
            text = "Kanıtı Paylaş"
            setOnClickListener {
                OwnerAuth.require(this@MainActivity,
                    Runnable {
                        val evidence = buildEvidence().toString(2)
                        val intent = Intent(Intent.ACTION_SEND).apply {
                            type = "application/json"
                            putExtra(Intent.EXTRA_TEXT, evidence)
                        }
                        startActivity(Intent.createChooser(intent, "Owner evidence paylaş"))
                    },
                    java.util.function.Consumer { showStatus(it) })
            }
        })

        setContentView(ScrollView(this).apply { addView(container) })

        if (BuildConfig.DEBUG && intent.getBooleanExtra("emulator_self_test", false)) {
            handler.postDelayed({
                OwnerAuth.require(this,
                    Runnable {
                        runBridgeSelfTest()
                        runLocalSelfTest()
                    },
                    java.util.function.Consumer { showStatus(it) })
            }, 2500)
        }
    }

    override fun onResume() {
        super.onResume()
        if (::statusView.isInitialized && OwnerSession.isAuthorized(this)) refreshAuthenticatedStatus()
    }

    private fun addDebugSelfTestControls(container: LinearLayout) {
        container.addView(TextView(this).apply {
            text = "DEBUG-ONLY local Accessibility self-test — absent from release manifest"
        })
        selfTestTarget = Button(this).apply {
            text = "SELF_TEST_TARGET"
            setOnClickListener {
                val prefs = getSharedPreferences("phone_agent_self_test", MODE_PRIVATE)
                val hits = prefs.getInt("target_hits", 0) + 1
                prefs.edit().putInt("target_hits", hits).apply()
            }
        }
        container.addView(selfTestTarget)
        container.addView(Button(this).apply {
            text = "DEBUG Self-Test"
            setOnClickListener {
                OwnerAuth.require(this@MainActivity,
                    Runnable { runLocalSelfTest() },
                    java.util.function.Consumer { showStatus(it) })
            }
        })
    }

    private fun runBridgeSelfTest() {
        if (!BuildConfig.DEBUG) return
        val arm = BridgeClient.arm(this, 60_000L)
        val read = BridgeClient.screenRead(this)
        getSharedPreferences("bridge_self_test", MODE_PRIVATE).edit()
            .putBoolean("signer_match", BridgeClient.verifyBridge(this))
            .putBoolean("arm_ok", arm.getBoolean("ok", false))
            .putBoolean("core_ok", arm.getBoolean("core_ok", false))
            .putBoolean("service_connected", arm.getBoolean("service_connected", false))
            .putBoolean("screen_read_ok", read.getBoolean("ok", false))
            .commit()
    }

    private fun runLocalSelfTest() {
        if (!BuildConfig.DEBUG) {
            showStatus("DEBUG_SELF_TEST_DISABLED_IN_RELEASE")
            return
        }
        val service = PhoneAgentAccessibilityService.instance ?: run {
            showStatus("DEBUG_ACCESSIBILITY_SERVICE_NOT_CONNECTED")
            return
        }
        val target = selfTestTarget ?: run {
            showStatus("DEBUG_SELF_TEST_TARGET_MISSING")
            return
        }
        val location = IntArray(2)
        target.getLocationOnScreen(location)
        val x = location[0] + target.width / 2f
        val y = location[1] + target.height / 2f
        val tapAccepted = service.execute(PhoneActionType.TAP, x = x, y = y)
        handler.postDelayed({ service.execute(PhoneActionType.CLICK_TEXT, text = "SELF_TEST_TARGET") }, 450)
        handler.postDelayed({ service.execute(PhoneActionType.SCROLL_FORWARD) }, 900)
        showStatus("DEBUG_SELF_TEST_STARTED tapAccepted=" + tapAccepted)
    }

    private fun refreshAuthenticatedStatus() {
        if (!OwnerSession.isAuthorized(this)) {
            statusView.text = "OWNER_AUTH_REQUIRED"
            evidenceView.text = "OWNER_AUTH_REQUIRED"
            return
        }
        statusView.text = "secureSession=" + OwnerSession.classification() +
            " · remainingMs=" + OwnerSession.remainingMs() +
            " · bridgeSignerMatch=" + BridgeClient.verifyBridge(this)
    }

    private fun showStatus(status: String) {
        statusView.text = status
        Toast.makeText(this, status, Toast.LENGTH_SHORT).show()
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
        val signerHash = signerSha256()
        val signerMatch = signerHash.equals(BuildConfig.EXPECTED_SIGNER_SHA256, ignoreCase = true)
        val packageMatch = packageName == "com.mehmetcerdik.ownerai"
        val versionMatch = versionCode == 7L && info.versionName == "1.5.0"
        val artifactPostcondition = if (
            apkHash.matches(Regex("^[0-9a-f]{64}$")) && signerMatch && packageMatch && versionMatch
        ) "PASS" else "FAIL"

        val bridge = BridgeClient.status(this)
        val memory = OwnerMemory(this)

        val device = JSONObject()
            .put("device_model", (Build.MANUFACTURER + " " + Build.MODEL).trim())
            .put("android_version", Build.VERSION.RELEASE + " (SDK " + Build.VERSION.SDK_INT + ")")
            .put("package_name", packageName)
            .put("version_name", info.versionName ?: "")
            .put("version_code", versionCode.toString())
            .put("artifact_sha256", apkHash)
            .put("signer_cert_sha256", signerHash)
            .put("expected_signer_cert_sha256", BuildConfig.EXPECTED_SIGNER_SHA256)
            .put("signer_match", signerMatch)
            .put("package_match", packageMatch)
            .put("version_match", versionMatch)
            .put("installer_package", installerPackageName())
            .put("artifact_postcondition_result", artifactPostcondition)

        val security = JSONObject()
            .put("trusted_device_registered", TrustedDeviceManager.isRegisteredAndActive(this))
            .put("trusted_device_hardware_backed", TrustedDeviceManager.isHardwareBacked())
            .put("secure_session_class", OwnerSession.classification())
            .put("secure_session_remaining_ms", OwnerSession.remainingMs())
            .put("audit_chain_valid", memory.verifyAuditChain())
            .put("bridge_signer_cert_sha256", BridgeClient.getBridgeSigner(this) ?: "")
            .put("bridge_signer_match", BridgeClient.verifyBridge(this))
            .put("bridge_service_connected", bridge.getBoolean("service_connected", false))
            .put("bridge_armed", bridge.getBoolean("armed", false))

        if (BuildConfig.DEBUG) {
            val events: JSONArray = PhoneAgentAccessibilityService.readEvents(this)
            security.put("debug_local_accessibility_declared", true)
            security.put("debug_events", events)
        } else {
            security.put("production_local_accessibility_declared", false)
        }

        return JSONObject()
            .put("version", 5)
            .put("status", if (artifactPostcondition == "PASS") "HARDENED_OWNER_EVIDENCE_CAPTURED" else "HARDENED_OWNER_EVIDENCE_FAIL")
            .put("git_head", BuildConfig.BUILD_GIT_SHA)
            .put("captured_at_epoch_ms", System.currentTimeMillis())
            .put("artifact", device)
            .put("security", security)
    }

    @Suppress("DEPRECATION")
    private fun signerSha256(): String = runCatching {
        val signatures = if (Build.VERSION.SDK_INT >= 28) {
            packageManager.getPackageInfo(packageName, PackageManager.GET_SIGNING_CERTIFICATES)
                .signingInfo?.apkContentsSigners
        } else {
            packageManager.getPackageInfo(packageName, PackageManager.GET_SIGNATURES).signatures
        }
        val first = signatures?.firstOrNull() ?: return@runCatching ""
        sha256Bytes(first.toByteArray())
    }.getOrDefault("")

    @Suppress("DEPRECATION")
    private fun installerPackageName(): String = runCatching {
        if (Build.VERSION.SDK_INT >= 30) {
            packageManager.getInstallSourceInfo(packageName).installingPackageName ?: ""
        } else {
            packageManager.getInstallerPackageName(packageName) ?: ""
        }
    }.getOrDefault("")

    private fun sha256Bytes(bytes: ByteArray): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(bytes)
        return digest.joinToString("") { "%02x".format(it) }
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
