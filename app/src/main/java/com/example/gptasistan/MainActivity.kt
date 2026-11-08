package com.example.gptasistan

import android.os.Bundle
import android.os.Build
import android.app.KeyguardManager
import android.app.Activity
import android.content.Intent
import android.content.ActivityNotFoundException
import android.speech.RecognizerIntent
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
import androidx.core.content.edit
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.ViewModelProvider
import java.util.Locale
import java.util.UUID

class MainActivity : AppCompatActivity(), TextToSpeech.OnInitListener {
    private lateinit var store: KralStore
    private lateinit var orchestrator: KralCoreOrchestrator
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
    private var storageBlocked = false
    private var pendingUnlock: (() -> Unit)? = null
    private lateinit var contentRoot: LinearLayout
    private lateinit var controlSections: KralControlSections
    private var initialState: Bundle? = null
    private var foreground = false
    private var otpGeneration = 0L
    private var reminderPermissionPending = false
    private val visibleDialogs = mutableSetOf<AlertDialog>()
    private val prefs by lazy { getSharedPreferences("kral_model", MODE_PRIVATE) }
    private val backups by lazy {
        BackupUi(this,
            store = { if (appUnlocked && uiReady && !storageBlocked) store else null },
            authorize = { action ->
                if (!storageBlocked && !isFinishing && !isDestroyed) unlock {
                    if (!uiReady && !storageBlocked) buildContent(initialState)
                    if (appUnlocked && uiReady && !storageBlocked && !isFinishing && !isDestroyed) action()
                }
            },
            showDialog = { builder, dismissed -> builder.showProtected(dismissed) },
            notice = { notice(it) },
            refresh = { session.refreshHistory() })
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        initialState = savedInstanceState
        backups.restorePendingState(savedInstanceState)
        showLocked()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.action != LocalTaskReminders.OPEN_ACTION) return
        // A notification may reuse a foreground Activity without onStop().
        // Its PendingIntent must still pass through the owner gate.
        appUnlocked = false
        pendingUnlock = null
        reminderPermissionPending = false
        otpGeneration++
        visibleDialogs.toList().forEach { it.dismiss() }
        if (uiReady) contentRoot.visibility = View.INVISIBLE
        tts?.stop()
        showLocked()
    }

    // Android 15+ enforces edge-to-edge for modern targets. Protect lock and
    // conversation controls from overlapping system navigation/status bars.
    private fun applySystemBarInsets(root: LinearLayout, left: Int, top: Int, right: Int, bottom: Int) {
        if (Build.VERSION.SDK_INT < 35) return
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(left + bars.left, top + bars.top, right + bars.right, bottom + bars.bottom)
            insets
        }
    }

    private fun showLocked() {
        val locked = layoutInflater.inflate(
            R.layout.activity_main, findViewById<ViewGroup>(android.R.id.content), false
        ) as LinearLayout
        applySystemBarInsets(locked, 24, 48, 24, 24)
        locked.findViewById<Button>(R.id.unlock_button).setOnClickListener {
            unlock { if (!uiReady) buildContent(initialState) else setContentView(contentRoot) }
        }
        locked.addView(Button(this).apply {
            text = "E-posta ile doğrula"
            setOnClickListener { showEmailOtp() }
        })
        setContentView(locked)
    }

    @Suppress("DEPRECATION")
    private fun unlock(action: () -> Unit) {
        if (pendingUnlock != null) return
        val manager = getSystemService(KEYGUARD_SERVICE) as KeyguardManager
        if (!manager.isDeviceSecure) {
            AlertDialog.Builder(this).setMessage("Önce Android ayarlarından güvenli ekran kilidi oluştur.")
                .setPositiveButton("Tamam", null).showProtected()
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
        if (backups.onActivityResult(requestCode, resultCode, data)) return
        if (requestCode == 4702) {
            if (resultCode == Activity.RESULT_OK) {
                val hypotheses = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.toList()
                if (!hypotheses.isNullOrEmpty()) {
                    // The external recognizer can stop our Activity. Never reveal or
                    // modify an existing private draft without a fresh device unlock.
                    unlock {
                        if (!uiReady && !storageBlocked) buildContent(initialState)
                        if (appUnlocked && uiReady && !storageBlocked && !isFinishing && !isDestroyed &&
                            session.state.value?.busy != true
                        ) {
                            val merged = SpeechDraft.merge(input.text.toString(), hypotheses)
                            if (merged != null) {
                                input.setText(merged)
                                input.setSelection(input.text.length)
                                connectionStatus.text = getString(R.string.status_speech_draft_added)
                            } else connectionStatus.text = getString(R.string.status_speech_not_recognized)
                        }
                    }
                }
            }
            return
        }
        if (requestCode != 4701) return
        val action = pendingUnlock
        pendingUnlock = null
        if (action == null) {
            // A recreation during the credential screen loses its in-memory
            // action/URI. Never replay the result or silently lose the operation.
            if (resultCode == Activity.RESULT_OK) notice(
                "Doğrulama isteği artık geçerli değil. Kilidi açıp işlemi yeniden başlat.")
            return
        }
        if (resultCode == Activity.RESULT_OK) completeUnlock(action)
        else { appUnlocked = false; showLocked() }
    }

    private fun completeUnlock(action: (() -> Unit)?) {
        appUnlocked = true
        try {
            if (uiReady) { contentRoot.visibility = View.VISIBLE; setContentView(contentRoot) }
            action?.invoke()
            if (uiReady) session.refreshHistory()
        } catch (_: Exception) {
            // Do not create a new plaintext DB, reset the key, or discard the old data.
            appUnlocked = false
            uiReady = false
            storageBlocked = true
            if (::store.isInitialized) runCatching { store.close() }
            showStorageBlocked()
        }
    }

    private fun showEmailOtp() {
        val fields = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 16, 24, 0) }
        val server = EditText(this).apply {
            hint = "https://sana-ait-sunucu.example"
            setText(prefs.getString("otp_endpoint", prefs.getString("endpoint", ""))); isSingleLine = true
        }
        val email = EditText(this).apply {
            hint = "E-posta adresin"
            setText(prefs.getString("otp_email", EmailOtp.DEFAULT_EMAIL)); isSingleLine = true
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
        }
        fields.addView(server); fields.addView(email)
        AlertDialog.Builder(this).setTitle("E-posta ile doğrula").setView(fields)
            .setMessage("Kayıtlı e-postana 6 haneli kod gönderilir. Kişisel kayıtlarını açmak için ardından Android ekran kilidi doğrulanır.")
            .setPositiveButton("Kod gönder") { _, _ ->
                val base = server.text.toString().trim().trimEnd('/')
                val address = email.text.toString().trim()
                if (!OwnerGateway.validBase(base) || !EmailOtp.validEmail(address)) {
                    notice("Geçerli HTTPS sunucu ve e-posta gir.")
                    return@setPositiveButton
                }
                val generation = ++otpGeneration
                thread {
                    val result = runCatching { EmailOtp.request(base, address) }
                    runOnUiThread {
                        if (!acceptOtpCallback(generation)) return@runOnUiThread
                        result.onSuccess { askOtpCode(base, address, it) }
                            .onFailure { notice("Kod gönderilemedi. Sunucu bağlantısını ve posta ayarlarını kontrol et.") }
                    }
                }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun askOtpCode(base: String, address: String, challengeId: String) {
        val code = EditText(this).apply {
            hint = "6 haneli kod"
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
            filters = arrayOf(InputFilter.LengthFilter(6))
        }
        AlertDialog.Builder(this).setTitle("Onay kodu").setView(code)
            .setPositiveButton("Doğrula") { _, _ ->
                val entered = code.text.toString().trim()
                if (!EmailOtp.validCode(entered)) { notice("Kod 6 rakam olmalı."); return@setPositiveButton }
                val generation = ++otpGeneration
                thread {
                    val result = runCatching { EmailOtp.verify(base, challengeId, entered) }
                    runOnUiThread {
                        if (!acceptOtpCallback(generation)) return@runOnUiThread
                        if (result.getOrNull() == true) confirmVerifiedEmail(base, address)
                        else notice("Kod doğrulanamadı. Yeni kod isteyip tekrar dene.")
                    }
                }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun acceptOtpCallback(generation: Long) =
        foreground && generation == otpGeneration && !isFinishing && !isDestroyed && !storageBlocked

    /** E-mail proves mailbox access, never authority to decrypt this device's history. */
    internal fun confirmVerifiedEmail(base: String, address: String) {
        if (!foreground || isFinishing || isDestroyed || storageBlocked ||
            !OwnerGateway.validBase(base) || !EmailOtp.validEmail(address)) return
        unlock {
            // A login form must not replace the owner-signed model gateway configuration.
            prefs.edit { putString("otp_endpoint", base); putString("otp_email", address) }
            if (!uiReady) buildContent(initialState) else setContentView(contentRoot)
        }
    }

    /** Dismiss private previews whenever Android puts the application behind its lock gate. */
    private fun AlertDialog.Builder.showProtected(dismissed: () -> Unit = {}): AlertDialog {
        val dialog = create()
        visibleDialogs.add(dialog)
        dialog.setOnDismissListener { visibleDialogs.remove(dialog); dismissed() }
        dialog.window?.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        dialog.show()
        return dialog
    }

    private fun notice(message: String) {
        AlertDialog.Builder(this).setMessage(message).setPositiveButton("Tamam", null).showProtected()
    }

    /** After a failed encrypted DB preflight, never offer an unsafe reset/retry path. */
    private fun showStorageBlocked() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 48, 24, 24)
        }
        applySystemBarInsets(root, 24, 48, 24, 24)
        root.addView(TextView(this).apply {
            text = getString(R.string.storage_preserved_title)
            textSize = 20f
        })
        root.addView(TextView(this).apply {
            text = getString(R.string.storage_preserved_message)
        })
        root.addView(Button(this).apply {
            text = getString(R.string.action_close_app)
            setOnClickListener { finish() }
        })
        setContentView(root)
    }

    private fun buildContent(savedInstanceState: Bundle?) {
        store = KralStore(this)
        try {
            orchestrator = KralCoreOrchestrator(store)
            session = ViewModelProvider(this)[ChatSession::class.java]
        } catch (error: Exception) {
            store.close()
            throw error
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 24)
        }
        applySystemBarInsets(root, 24, 24, 24, 24)
        contentRoot = root
        uiReady = true
        root.addView(TextView(this).apply {
            text = getString(R.string.candidate_title)
            textSize = 19f
        })
        root.addView(TextView(this).apply {
            text = getString(R.string.owner_unlocked_notice)
        })
        // Navigation only changes visible views. Owner authentication, local
        // storage encryption, backups, OTP and network calls retain their
        // original action handlers in this version.
        connectionStatus = TextView(this).apply {
            text = if ((prefs.getString("endpoint", "") ?: "").isBlank())
                getString(R.string.status_model_not_configured) else getString(R.string.status_model_unverified)
        }
        root.addView(connectionStatus)

        controlSections = KralControlSections(this)
        controlSections.attach(root)
        controlSections.tasks.addView(Button(this).apply {
            text = getString(R.string.action_memory)
            setOnClickListener { showMemoryMenu() }
        })
        controlSections.tasks.addView(Button(this).apply {
            text = getString(R.string.action_tasks)
            setOnClickListener { showLocalTaskMenu() }
        })
        controlSections.tasks.addView(Button(this).apply {
            text = getString(R.string.action_expert_worker_tasks)
            setOnClickListener { showExpertMenu() }
        })
        controlSections.tasks.addView(TextView(this).apply {
            text = getString(R.string.notice_expert_tasks)
        })

        modelButton = Button(this).apply {
            text = getString(R.string.action_model)
            setOnClickListener { configureModel() }
        }
        controlSections.system.addView(modelButton)
        controlSections.system.addView(Button(this).apply {
            text = getString(R.string.action_server_registration)
            setOnClickListener { unlock { showRegistration() } }
        })
        controlSections.system.addView(Button(this).apply {
            text = getString(R.string.action_owner_bridge_status)
            setOnClickListener {
                controlSections.show(KralControlSections.Page.CHAT)
                showLocal { OwnerStatus.readOnlyReport(this@MainActivity) }
            }
        })
        controlSections.system.addView(TextView(this).apply {
            text = getString(R.string.notice_omega_unverified)
        })
        controlSections.system.addView(SwitchCompat(this).apply {
            text = getString(R.string.action_speak_replies)
            isChecked = prefs.getBoolean("speak_replies", false)
            setOnCheckedChangeListener { _, enabled ->
                prefs.edit { putBoolean("speak_replies", enabled) }
                if (!enabled) tts?.stop()
                else if (!ttsReady) connectionStatus.text = getString(R.string.status_tts_unavailable)
                else speakLatestReply()
            }
        })

        controlSections.chat.addView(Button(this).apply {
            text = getString(R.string.action_voice_cihat)
            setOnClickListener { showHandoffMenu() }
        })
        scroller = ScrollView(this)
        transcript = TextView(this).apply { textSize = 16f }
        scroller.addView(transcript)
        controlSections.chat.addView(scroller, LinearLayout.LayoutParams(-1, 0, 1f))
        val bottom = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        input = EditText(this).apply {
            hint = getString(R.string.hint_message)
            isSingleLine = true
            filters = arrayOf(InputFilter.LengthFilter(16000))
            setText(savedInstanceState?.getString("draft").orEmpty())
        }
        bottom.addView(input, LinearLayout.LayoutParams(0, -2, 1f))
        sendButton = Button(this).apply {
            text = getString(R.string.action_send)
            setOnClickListener {
                val line = input.text.toString().trim()
                if (line.isNotEmpty() && handle(line)) input.text.clear()
            }
        }
        bottom.addView(sendButton)
        controlSections.chat.addView(bottom)
        setContentView(root)
        session.history.observe(this) { history ->
            transcript.text = if (history.isEmpty()) getString(R.string.greeting_help, KralCore.help())
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

    private fun memoryControlsReady() = appUnlocked && uiReady && !storageBlocked &&
        session.state.value?.busy != true && !isFinishing && !isDestroyed

    private fun showLocalTaskMenu() {
        if (!memoryControlsReady()) return
        AlertDialog.Builder(this).setTitle("Yerel görevler")
            .setItems(arrayOf("Görevleri göster", "Arka plan hatırlatıcısı")) { _, index ->
                if (!memoryControlsReady()) return@setItems
                if (index == 0) showLocal { store.tasks() } else showReminderSettings()
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun showReminderSettings() {
        if (!memoryControlsReady()) return
        val status = LocalTaskReminders.status(this)
        val description = "Açık yerel görev varsa Android arka planda genel bir hatırlatma gösterir. " +
            "Görev metni bildirimde görünmez; dokununca cihaz doğrulaması gerekir. " +
            "İnternet veya model kullanılmaz. Android'in pil ve zamanlama koşullarına göre " +
            "15 dakika veya daha uzun aralıklarla çalışır.\n\n" +
            "Hatırlatıcı: ${if (status.enabled) "açık" else "kapalı"}. " +
            "Zamanlama: ${if (status.scheduled) "kayıtlı" else "kayıtlı değil"}. " +
            "Bildirim izni: ${if (status.notificationsAllowed) "açık" else "kapalı"}."
        AlertDialog.Builder(this).setTitle("Yerel görev hatırlatıcısı").setMessage(description)
            .setPositiveButton(if (status.enabled) "Kapat" else "Etkinleştir") { _, _ ->
                if (!memoryControlsReady()) return@setPositiveButton
                unlock {
                    if (!memoryControlsReady()) return@unlock
                    if (status.enabled) {
                        val saved = LocalTaskReminders.disable(this)
                        notice(if (saved) "Yerel görev hatırlatıcısı kapatıldı."
                            else "Zamanlanan iş durduruldu fakat kapalı ayarı kaydedilemedi. Ayarı yeniden kontrol et.")
                    } else requestReminderPermissionOrEnable()
                }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun requestReminderPermissionOrEnable() {
        if (!memoryControlsReady()) return
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(
                android.Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            reminderPermissionPending = true
            requestPermissions(arrayOf(android.Manifest.permission.POST_NOTIFICATIONS), 4705)
        } else enableLocalReminders()
    }

    private fun enableLocalReminders() {
        if (!memoryControlsReady()) return
        val message = when (LocalTaskReminders.enable(this)) {
            LocalTaskReminders.EnableResult.ENABLED -> "Yerel görev hatırlatıcısı zamanlandı."
            LocalTaskReminders.EnableResult.NOTIFICATIONS_BLOCKED -> "Bildirim izni veya kanalı kapalı; hatırlatıcı etkinleştirilmedi."
            LocalTaskReminders.EnableResult.SCHEDULE_FAILED -> "Android hatırlatıcıyı zamanlayamadı; etkinleştirilmedi."
            LocalTaskReminders.EnableResult.STORAGE_FAILED -> "Hatırlatıcı ayarı kaydedilemedi; etkinleştirilmedi."
        }
        notice(message)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != 4705) return
        val pending = reminderPermissionPending
        reminderPermissionPending = false
        if (!pending || !foreground || isFinishing || isDestroyed) {
            notice("Bildirim ayarını Görevler menüsünden yeniden aç.")
            return
        }
        if (permissions.size == 1 && permissions[0] == android.Manifest.permission.POST_NOTIFICATIONS &&
            grantResults.size == 1 && grantResults[0] == android.content.pm.PackageManager.PERMISSION_GRANTED) {
            unlock { if (memoryControlsReady()) enableLocalReminders() }
        } else notice("Bildirim izni verilmedi; hatırlatıcı etkinleştirilmedi.")
    }

    private fun showMemoryMenu() {
        if (!memoryControlsReady()) return
        AlertDialog.Builder(this).setTitle(getString(R.string.action_memory))
            .setItems(arrayOf(getString(R.string.action_memory_show), getString(R.string.action_memory_delete), getString(R.string.backup_title))) { _, index ->
                if (!memoryControlsReady()) return@setItems
                when (index) {
                    0 -> showLocal { store.memory() }
                    1 -> chooseMemoryForDeletion()
                    2 -> backups.showMenu()
                }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun chooseMemoryForDeletion() {
        if (!memoryControlsReady()) return
        val entries = try { store.memoryEntries() } catch (_: Exception) {
            connectionStatus.text = getString(R.string.status_record_read_failed)
            return
        }
        if (entries.isEmpty()) {
            notice(getString(R.string.status_memory_empty))
            return
        }
        val labels = entries.map { "#${it.id} · ${it.ts}\n${it.text.take(160)}" }.toTypedArray()
        AlertDialog.Builder(this).setTitle(getString(R.string.title_memory_select_delete))
            .setItems(labels) { _, index ->
                if (!memoryControlsReady()) return@setItems
                val selected = entries[index]
                unlock { if (memoryControlsReady()) confirmMemoryDeletion(selected) }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun confirmMemoryDeletion(selected: MemoryEntry) {
        if (!memoryControlsReady()) return
        val preview = TextView(this).apply {
            text = "#${selected.id} · ${selected.ts}\n\n${selected.text}"
            setPadding(24, 16, 24, 16)
        }
        AlertDialog.Builder(this).setTitle(getString(R.string.title_memory_confirm_delete))
            .setMessage(getString(R.string.message_memory_confirm_delete))
            .setView(ScrollView(this).apply { addView(preview) })
            .setPositiveButton(getString(R.string.action_memory_delete_selected)) { _, _ ->
                if (!memoryControlsReady()) return@setPositiveButton
                try {
                    connectionStatus.text = getString(if (store.deleteMemory(selected))
                        R.string.status_memory_deleted else R.string.status_memory_selection_changed)
                } catch (_: Exception) {
                    connectionStatus.text = getString(R.string.status_memory_delete_failed)
                }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun showHandoffMenu() {
        if (!appUnlocked || !uiReady || storageBlocked || session.state.value?.busy == true) return
        AlertDialog.Builder(this).setTitle(getString(R.string.action_voice_cihat))
            .setItems(arrayOf("Sesle taslak yaz", "CİHAT kurulumunu doğrula", "CİHAT'ı aç", "Panodan taslak al")) { _, index ->
                if (!appUnlocked || storageBlocked) return@setItems
                when (index) {
                    0 -> requestSpeechDraft()
                    1 -> showCihatIdentity()
                    2 -> openInstalledCihat()
                    3 -> previewClipboardReply()
                }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun showExpertMenu() {
        if (!appUnlocked || !uiReady || storageBlocked || session.state.value?.busy == true) return
        AlertDialog.Builder(this).setTitle("Uzman görevleri")
            .setItems(arrayOf("Yeni uzman görevi", "Görev durumunu yenile", "Görevi iptal et", "Sunucu işçi durumunu oku",
                "Bekleyen gönderimi yeniden dene", "Bekleyen gönderimi bırak")) { _, index ->
                if (!appUnlocked || storageBlocked) return@setItems
                when (index) {
                    0 -> chooseExpert()
                    1 -> taskActionDialog(false)
                    2 -> taskActionDialog(true)
                    3 -> runOwnerAction("İşçi durumu", false) { app, base, _ ->
                        val result = OwnerGateway.localWorkers(app, base, ExpertTasks.statusBatch(), 2)
                        "Sunucuda iki salt okunur iş:\n${result.toString(2)}\nCanlı model isteği yapılmadı."
                    }
                    4 -> retryPendingTask()
                    5 -> discardPendingTask()
                }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun chooseExpert() {
        if (session.pendingTaskSubmission != null) {
            notice("Önce bekleyen uzman gönderimini yeniden dene veya menüden bırak. Yeni gönderim ayrı bir görev ve ücret oluşturabilir.")
            return
        }
        val experts = OwnerGateway.EXPERTS.toList()
        AlertDialog.Builder(this).setTitle("Uzman rolü seç")
            .setItems(experts.toTypedArray()) { _, index ->
                if (!appUnlocked || storageBlocked || session.state.value?.busy == true) return@setItems
                val draft = EditText(this).apply {
                    hint = "Yalnız bu görev metni gönderilir"
                    filters = arrayOf(InputFilter.LengthFilter(8000))
                    if (input.text.length <= 8000) setText(input.text)
                }
                AlertDialog.Builder(this).setTitle("Uzman: ${experts[index]}")
                    .setMessage("Seçili modele yalnız bu metin gönderilir; sağlayıcı ücretlendirebilir. " +
                        "Uzman öneri üretir. Dosya, hesap veya dış sistemde işlem yapmaz.")
                    .setView(draft)
                    .setPositiveButton("Görevi gönder") { _, _ ->
                        val text = draft.text.toString().trim()
                        if (text.isBlank()) return@setPositiveButton
                        if (!memoryControlsReady()) return@setPositiveButton
                        val submission = try {
                            OwnerGateway.prepareTaskSubmission(
                                prefs.getString("endpoint", "").orEmpty(),
                                prefs.getString("owner_id", "").orEmpty(),
                                prefs.getString("model", "").orEmpty(), experts[index], text)
                        } catch (_: Exception) {
                            notice("Gönderim hazırlanamadı; sunucu/model doğrulamasını yenile. Hiçbir görev başlatılmadı.")
                            return@setPositiveButton
                        }
                        if (session.retainTaskSubmission(submission)) sendPreparedTask(submission)
                    }.setNegativeButton("Vazgeç", null).showProtected()
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun sendPreparedTask(submission: TaskSubmission) {
        if (!memoryControlsReady()) return
        if (!submission.matches(prefs.getString("endpoint", "").orEmpty(),
                prefs.getString("owner_id", "").orEmpty(), prefs.getString("model", "").orEmpty())) {
            notice("Bekleyen gönderimin sunucu, sahip veya modeli değişmiş. Önce eski ayarları geri getir ya da gönderimi bırak.")
            return
        }
        runOwnerAction("Uzman görevi", false,
            onRecorded = { session.forgetTaskSubmission(submission) }) { app, base, _ ->
            ExpertTasks.report(OwnerGateway.submitTask(app, base, submission))
        }
    }

    private fun retryPendingTask() {
        if (!memoryControlsReady()) return
        val submission = session.pendingTaskSubmission ?: run {
            notice("Bu oturumda bekleyen gönderim yok. Önceki gönderimin kimliği geçmişteyse durumunu sorgula.")
            return
        }
        AlertDialog.Builder(this).setTitle("Aynı gönderimi yeniden dene")
            .setMessage("Aynı görev kimliği kullanılır; sunucu daha önce kabul ettiyse ikinci görev başlatmaz. " +
                "Uygulama kapanınca bekleyen metin tutulmaz; gönderim kimliği geçmişte kalır.\n\nKimlik: ${submission.requestId}")
            .setPositiveButton("Yeniden dene") { _, _ ->
                if (memoryControlsReady() && session.pendingTaskSubmission === submission) sendPreparedTask(submission)
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun discardPendingTask() {
        if (!memoryControlsReady()) return
        val submission = session.pendingTaskSubmission ?: run { notice("Bekleyen gönderim yok."); return }
        AlertDialog.Builder(this).setTitle("Bekleyen gönderimi bırak")
            .setMessage("Yalnız bu telefondaki yeniden deneme metni bırakılır. Sunucunun kabul ettiği görevi iptal etmez. " +
                "Yeni gönderim ayrı ücret oluşturabilir; önce geçmişteki kimlikle durumu kontrol edebilirsin.")
            .setPositiveButton("Bırak") { _, _ ->
                if (!memoryControlsReady()) return@setPositiveButton
                unlock { if (memoryControlsReady()) session.forgetTaskSubmission(submission) }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun taskActionDialog(cancel: Boolean) {
        val idField = EditText(this).apply { hint = "Geçmişteki 32 karakterlik görev kimliği"; isSingleLine = true }
        AlertDialog.Builder(this).setTitle(if (cancel) "Görevi iptal et" else "Görev durumunu yenile")
            .setMessage(if (cancel) "Başlamış sağlayıcı isteği uzaktan durdurulamaz; dönen sonucu bastırılır."
                else "Sunucudaki görev durumu ve varsa yanıt özeti okunur.")
            .setView(idField).setPositiveButton(if (cancel) "İptal iste" else "Yenile") { _, _ ->
                val id = idField.text.toString().trim()
                if (!ExpertTasks.validTaskId(id)) {
                    connectionStatus.text = getString(R.string.status_task_id_invalid)
                    return@setPositiveButton
                }
                runOwnerAction(if (cancel) "Görev iptali" else "Görev durumu", false) { app, base, _ ->
                    ExpertTasks.report(if (cancel) OwnerGateway.cancelTask(app, base, id)
                        else OwnerGateway.taskStatus(app, base, id))
                }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun runOwnerAction(
        label: String, needsModel: Boolean,
        onRecorded: (() -> Unit)? = null,
        operation: (android.content.Context, String, String) -> String,
    ) {
        if (!appUnlocked || !uiReady || storageBlocked || session.state.value?.busy == true) return
        val base = prefs.getString("endpoint", "").orEmpty()
        val owner = prefs.getString("owner_id", "").orEmpty()
        val model = prefs.getString("model", "").orEmpty()
        if (!OwnerGateway.validBase(base) || !OmegaEnvelope.validOwner(owner)) {
            connectionStatus.text = getString(R.string.status_owner_server_required)
            return
        }
        val app = applicationContext
        unlock {
            if (!appUnlocked || storageBlocked || session.state.value?.busy == true) return@unlock
            if (needsModel && OwnerGateway.verifiedModels(base, owner).none { it.id == model }) {
                connectionStatus.text = getString(R.string.status_model_verification_required)
                return@unlock
            }
            session.runOwnerOperation(label, onRecorded) { operation(app, base, model) }
        }
    }

    private fun showCihatIdentity() {
        if (!appUnlocked || !uiReady || session.state.value?.busy == true) return
        val verified = CihatIdentity.inspect(this)
        AlertDialog.Builder(this)
            .setTitle("CİHAT uygulama kimliği")
            .setMessage(verified.report())
            .setPositiveButton("Tamam", null)
            .showProtected()
    }

    // User-mediated handoff, not a privileged API or silent CİHAT automation.
    private fun openInstalledCihat() {
        if (!appUnlocked || session.state.value?.busy == true) {
            connectionStatus.text = getString(R.string.status_unlock_and_wait)
            return
        }
        val installed = CihatIdentity.inspect(this)
        if (!installed.verified) {
            connectionStatus.text =
                getString(R.string.status_cihat_identity_unverified)
            return
        }
        val launch = try {
            packageManager.getLaunchIntentForPackage(CihatHandoff.PACKAGE_NAME)
        } catch (_: RuntimeException) { null }
        if (launch == null) {
            connectionStatus.text = getString(R.string.status_cihat_not_launchable)
            return
        }
        val draft = CihatHandoff.copyableDraft(input.text.toString())
        val dialog = AlertDialog.Builder(this)
            .setTitle("Mevcut CİHAT AI uygulaması")
            .setMessage(
                "KRAL CİHAT'ı açabilir ama CİHAT'ın sohbetine otomatik mesaj gönderemez veya yanıt okuyamaz. " +
                "Metni kopyala seçeneği yalnızca bu mesaj kutusundaki metni Android panosuna koyar. " +
                "Pano içeriği başka uygulamalarda görülebilir; şifre, anahtar ve özel bilgiler için kullanma. " +
                "Sohbet geçmişi veya hafıza otomatik aktarılmaz."
            )
            .setPositiveButton("Yalnız aç") { _, _ ->
                try {
                    if (!appUnlocked || !uiReady || storageBlocked || !CihatIdentity.inspect(this).verified)
                        return@setPositiveButton
                    startActivity(launch)
                }
                catch (_: RuntimeException) {
                    connectionStatus.text = getString(R.string.status_cihat_launch_failed)
                }
            }
            .setNegativeButton("Vazgeç", null)
        if (draft != null) {
            dialog.setNeutralButton("Metni kopyala ve aç") { _, _ ->
                try {
                    if (!appUnlocked || !uiReady || storageBlocked || !CihatIdentity.inspect(this).verified)
                        return@setNeutralButton
                    val clipboard = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
                    val clip = android.content.ClipData.newPlainText("KRAL'dan CİHAT'a metin", draft)
                    if (android.os.Build.VERSION.SDK_INT >= 33) {
                        clip.description.extras = android.os.PersistableBundle().apply {
                            putBoolean(android.content.ClipDescription.EXTRA_IS_SENSITIVE, true)
                        }
                    }
                    clipboard.setPrimaryClip(clip)
                    startActivity(launch)
                } catch (_: RuntimeException) {
                    connectionStatus.text = getString(R.string.status_cihat_clipboard_failed)
                }
            }
        }
        dialog.showProtected()
    }

    /** Manual reply return: user explicitly inspects untrusted clipboard. */
    private fun previewClipboardReply() {
        if (!appUnlocked || !uiReady || session.state.value?.busy == true) {
            if (uiReady) connectionStatus.text = getString(R.string.status_unlock_and_wait)
            return
        }
        val reply = try {
            val clipboard = getSystemService(CLIPBOARD_SERVICE) as? android.content.ClipboardManager
            val clip = clipboard?.primaryClip
            if (clip != null && clip.itemCount == 1 &&
                clip.description.hasMimeType(android.content.ClipDescription.MIMETYPE_TEXT_PLAIN)
            ) CihatHandoff.importableReply(clip.getItemAt(0).text) else null
        } catch (_: RuntimeException) { null }
        if (reply == null) {
            connectionStatus.text = getString(R.string.status_clipboard_invalid)
            return
        }
        val overwrite = if (input.text.isNotBlank())
            "Mevcut taslak bu metinle değiştirilecek.\n\n" else ""
        AlertDialog.Builder(this)
            .setTitle("Panodaki metni KRAL'a al")
            .setMessage(
                "Panodaki metnin CİHAT'tan geldiği doğrulanamaz. Önce kontrol et. " +
                "Aktarım yalnızca taslağı doldurur, sohbeti/hafızayı kaydetmez ve mesaj göndermez.\n\n" +
                overwrite + "PANODAKİ METİN:\n" + reply
            )
            .setPositiveButton("Taslağa aktar") { _, _ ->
                if (appUnlocked && !isFinishing && !isDestroyed &&
                    session.state.value?.busy != true
                ) {
                    input.setText(reply)
                    input.setSelection(reply.length)
                    connectionStatus.text = getString(R.string.status_clipboard_draft_added)
                }
            }
            .setNegativeButton("Vazgeç", null)
            .showProtected()
    }

    private fun requestSpeechDraft() {
        if (!appUnlocked || !uiReady || session.state.value?.busy == true) return
        AlertDialog.Builder(this).setTitle("Sesle yaz")
            .setMessage(
                "Telefonun konuşma tanıma hizmeti sesini işleyebilir. " +
                "Yalnız senin onayınla başlatılır; tanınan metin yalnız taslağa eklenir, " +
                "otomatik gönderilmez veya hafızaya kaydedilmez."
            )
            .setPositiveButton("Konuşmayı başlat") { _, _ ->
                if (!appUnlocked || isFinishing || isDestroyed ||
                    session.state.value?.busy == true
                ) return@setPositiveButton
                try {
                    val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                        putExtra(RecognizerIntent.EXTRA_LANGUAGE, "tr-TR")
                        putExtra(RecognizerIntent.EXTRA_PROMPT, "Türkçe konuş")
                    }
                    startActivityForResult(intent, 4702)
                } catch (_: ActivityNotFoundException) {
                    connectionStatus.text = getString(R.string.status_recognizer_unavailable)
                } catch (_: SecurityException) {
                    connectionStatus.text = getString(R.string.status_recognizer_denied)
                }
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun showLocal(action: () -> String) {
        if (!appUnlocked || !uiReady || storageBlocked) return
        try {
            store.saveMessage("assistant", action())
            session.refreshHistory()
            // Read-only memory/task/Owner results are rendered in the chat
            // transcript. Return to it only after a successful DB write.
            if (::controlSections.isInitialized)
                controlSections.show(KralControlSections.Page.CHAT)
        } catch (_: Exception) {
            connectionStatus.text = getString(R.string.status_record_read_failed)
        }
    }

    // Keep command changes and their conversation record in one transaction.
    private fun recordLocal(raw: String, action: () -> String): Boolean {
        // Recheck immediately before any local write; a backgrounded UI may have been re-locked.
        check(OwnerExecutionPolicy.decide(KralCore.parse(raw),
            OwnerExecutionContext(appUnlocked, !storageBlocked)) ==
            OwnerExecutionDecision.ALLOW_LOCAL_ROUTINE) { "OWNER_LOCAL_DENIED" }
        val operationId = "ui-" + UUID.randomUUID().toString()
        orchestrator.execute(operationId, "local-command", raw) {
            val reply = action()
            store.saveMessage("user", "Sen: " + raw)
            store.saveMessage("assistant", reply)
            reply
        }
        session.refreshHistory()
        return true
    }

    private fun handle(raw: String): Boolean {
        if (session.state.value?.busy == true) return false
        return try {
            val command = KralCore.parse(raw)
            val remoteVerified = if (command is KralCommand.Chat && appUnlocked && !storageBlocked) {
                val endpoint = prefs.getString("endpoint", "").orEmpty()
                val owner = prefs.getString("owner_id", "").orEmpty()
                val model = prefs.getString("model", "").orEmpty()
                OwnerGateway.validBase(endpoint) &&
                    OwnerGateway.verifiedModels(endpoint, owner).any { it.id == model }
            } else false
            val decision = OwnerExecutionPolicy.decide(command,
                OwnerExecutionContext(appUnlocked, !storageBlocked, remoteVerified))
            if (decision != OwnerExecutionDecision.ALLOW_LOCAL_ROUTINE &&
                decision != OwnerExecutionDecision.ALLOW_SIGNED_REMOTE_ATTEMPT) {
                connectionStatus.text = when (decision) {
                    OwnerExecutionDecision.DENY_OWNER_LOCKED -> getString(R.string.status_owner_locked)
                    OwnerExecutionDecision.DENY_STORAGE_UNAVAILABLE -> getString(R.string.status_storage_unavailable)
                    OwnerExecutionDecision.DENY_REMOTE_NOT_VERIFIED -> getString(R.string.status_remote_model_not_verified)
                    else -> getString(R.string.status_operation_denied)
                }
                false
            } else when (command) {
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
                        if (ttsReady) "Sesli okuma istendi" else getString(R.string.status_tts_unavailable)
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
                        connectionStatus.text = getString(R.string.status_remote_model_not_verified)
                        false
                    } else {
                        unlock {
                            if (OwnerExecutionPolicy.decide(command, OwnerExecutionContext(
                                    appUnlocked, !storageBlocked,
                                    OwnerGateway.validBase(endpoint) &&
                                        OwnerGateway.verifiedModels(endpoint, owner).any { it.id == model }
                                )) != OwnerExecutionDecision.ALLOW_SIGNED_REMOTE_ATTEMPT) {
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
            connectionStatus.text = getString(R.string.status_record_write_failed)
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
                        .setPositiveButton("Tamam", null).showProtected()
                } catch (_: Exception) { connectionStatus.text = getString(R.string.status_registration_failed) }
            }.setNegativeButton("Vazgeç", null).showProtected()
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
                    connectionStatus.text = getString(R.string.status_owner_server_invalid)
                } else unlock { refreshModels(base, identity) }
            }
            .setNeutralButton("Bağlantıyı kaldır") { _, _ ->
                OwnerGateway.clear()
                prefs.edit { remove("endpoint"); remove("model"); remove("owner_id") }
                session.resetConnectionStatus(getString(R.string.status_model_not_configured))
            }.setNegativeButton("Vazgeç", null).showProtected()
    }

    private fun refreshModels(base: String, identity: String) {
        modelButton.isEnabled = false
        sendButton.isEnabled = false
        connectionStatus.text = getString(R.string.status_model_verifying)
        thread {
            val models = try { OwnerGateway.models(base, identity) } catch (_: Exception) { null }
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                modelButton.isEnabled = true
                sendButton.isEnabled = true
                if (models == null) {
                    session.resetConnectionStatus("Bağlantı doğrulanamadı. Sunucu kaydını, ekran kilidini ve HTTPS adresini kontrol et.")
                } else {
                    prefs.edit { putString("endpoint", base); putString("owner_id", identity); remove("model") }
                    if (models.isEmpty()) {
                        session.resetConnectionStatus("Sunucuya erişildi; canlı yanıtla doğrulanmış model bulunamadı.")
                    } else if (appUnlocked) {
                        val labels = models.map { "${it.provider} / ${it.id} (${it.latencyMs} ms)" }.toTypedArray()
                        AlertDialog.Builder(this).setTitle("Canlı doğrulanan modeli seç").setItems(labels) { _, index ->
                            val selected = models[index]
                            if (appUnlocked && OwnerGateway.verifiedModels(base, identity).any { it == selected }) {
                                prefs.edit { putString("model", selected.id) }
                                session.resetConnectionStatus("Doğrulanmış model: ${selected.provider} / ${selected.id}")
                            } else session.resetConnectionStatus("Model doğrulamasının süresi doldu; bağlantıyı yenile.")
                        }.setNegativeButton("Vazgeç", null).showProtected()
                    } else session.resetConnectionStatus("Model doğrulaması bitti; seçim için bağlantıyı tekrar aç.")
                }
            }
        }
    }

    override fun onStart() {
        super.onStart()
        foreground = true
    }

    override fun onResume() {
        super.onResume()
        if (!appUnlocked && pendingUnlock == null && !storageBlocked) showLocked()
    }

    override fun onStop() {
        foreground = false
        otpGeneration++
        visibleDialogs.toList().forEach { it.dismiss() }
        appUnlocked = false
        if (uiReady) contentRoot.visibility = View.INVISIBLE
        tts?.stop()
        super.onStop()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        backups.savePendingState(outState)
        // A recreated screen stays locked before input exists. Keep the already
        // saved draft through further recreations, including external pickers.
        val draft = if (uiReady) input.text.toString() else initialState?.getString("draft")
        if (draft != null) {
            var end = minOf(draft.length, 16000)
            if (end < draft.length && end > 0 && Character.isHighSurrogate(draft[end - 1])) end--
            outState.putString("draft", draft.substring(0, end))
        }
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
