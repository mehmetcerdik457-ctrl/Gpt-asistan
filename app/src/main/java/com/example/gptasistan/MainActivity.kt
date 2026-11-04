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
    private var initialState: Bundle? = null
    private val prefs by lazy { getSharedPreferences("kral_model", MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        initialState = savedInstanceState
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
        if (requestCode == 4702) {
            if (resultCode == Activity.RESULT_OK) {
                val hypotheses = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.toList()
                if (!hypotheses.isNullOrEmpty()) {
                    // The external recognizer can stop our Activity. Never reveal or
                    // modify an existing private draft without a fresh device unlock.
                    unlock {
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
        if (resultCode == Activity.RESULT_OK) completeUnlock(action)
        else { appUnlocked = false; showLocked() }
    }

    private fun completeUnlock(action: (() -> Unit)?) {
        appUnlocked = true
        try {
            if (uiReady) { contentRoot.visibility = View.VISIBLE; setContentView(contentRoot) }
            action?.invoke()
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
            setText(prefs.getString("endpoint", "")); isSingleLine = true
        }
        val email = EditText(this).apply {
            hint = "E-posta adresin"
            setText(prefs.getString("otp_email", EmailOtp.DEFAULT_EMAIL)); isSingleLine = true
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS
        }
        fields.addView(server); fields.addView(email)
        AlertDialog.Builder(this).setTitle("E-posta ile doğrula").setView(fields)
            .setMessage("Kayıtlı e-postana 6 haneli onay kodu gönderilir.")
            .setPositiveButton("Kod gönder") { _, _ ->
                val base = server.text.toString().trim().trimEnd('/')
                val address = email.text.toString().trim()
                if (!OwnerGateway.validBase(base) || !EmailOtp.validEmail(address)) {
                    notice("Geçerli HTTPS sunucu ve e-posta gir.")
                    return@setPositiveButton
                }
                prefs.edit { putString("endpoint", base); putString("otp_email", address) }
                thread {
                    val result = runCatching { EmailOtp.request(base, address) }
                    runOnUiThread {
                        if (isFinishing || isDestroyed) return@runOnUiThread
                        result.onSuccess { askOtpCode(base, it) }
                            .onFailure { notice(it.message ?: "Kod gönderilemedi.") }
                    }
                }
            }.setNegativeButton("Vazgeç", null).show()
    }

    private fun askOtpCode(base: String, challengeId: String) {
        val code = EditText(this).apply {
            hint = "6 haneli kod"
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
            filters = arrayOf(InputFilter.LengthFilter(6))
        }
        AlertDialog.Builder(this).setTitle("Onay kodu").setView(code)
            .setPositiveButton("Doğrula") { _, _ ->
                val entered = code.text.toString().trim()
                if (!EmailOtp.validCode(entered)) { notice("Kod 6 rakam olmalı."); return@setPositiveButton }
                thread {
                    val result = runCatching { EmailOtp.verify(base, challengeId, entered) }
                    runOnUiThread {
                        if (isFinishing || isDestroyed) return@runOnUiThread
                        if (result.getOrNull() == true) {
                            completeUnlock { if (!uiReady) buildContent(initialState) else setContentView(contentRoot) }
                        } else notice(result.exceptionOrNull()?.message ?: "Kod doğrulanamadı.")
                    }
                }
            }.setNegativeButton("Vazgeç", null).show()
    }

    private fun notice(message: String) {
        AlertDialog.Builder(this).setMessage(message).setPositiveButton("Tamam", null).show()
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
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        fun button(label: String, action: () -> Unit): Button {
            val b = Button(this).apply { text = label; setOnClickListener { action() } }
            actions.addView(b, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            return b
        }
        button(getString(R.string.action_memory)) { showLocal { store.memory() } }
        button(getString(R.string.action_tasks)) { showLocal { store.tasks() } }
        modelButton = button(getString(R.string.action_model)) { configureModel() }
        root.addView(actions)
        root.addView(Button(this).apply {
            text = getString(R.string.action_server_registration)
            setOnClickListener { unlock { showRegistration() } }
        })
        root.addView(Button(this).apply {
            text = getString(R.string.action_owner_bridge_status)
            setOnClickListener { showLocal { OwnerStatus.readOnlyReport(this@MainActivity) } }
        })
        root.addView(Button(this).apply {
            text = getString(R.string.action_voice_cihat)
            setOnClickListener { showHandoffMenu() }
        })
        root.addView(Button(this).apply {
            text = getString(R.string.action_expert_worker_tasks)
            setOnClickListener { showExpertMenu() }
        })
        connectionStatus = TextView(this).apply {
            text = if ((prefs.getString("endpoint", "") ?: "").isBlank())
                getString(R.string.status_model_not_configured) else getString(R.string.status_model_unverified)
        }
        root.addView(connectionStatus)
        root.addView(SwitchCompat(this).apply {
            text = getString(R.string.action_speak_replies)
            isChecked = prefs.getBoolean("speak_replies", false)
            setOnCheckedChangeListener { _, enabled ->
                prefs.edit { putBoolean("speak_replies", enabled) }
                if (!enabled) tts?.stop()
                else if (!ttsReady) connectionStatus.text = getString(R.string.status_tts_unavailable)
                else speakLatestReply()
            }
        })
        scroller = ScrollView(this)
        transcript = TextView(this).apply { textSize = 16f }
        scroller.addView(transcript)
        root.addView(scroller, LinearLayout.LayoutParams(-1, 0, 1f))
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
        root.addView(bottom)
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
            }.setNegativeButton("Vazgeç", null).show()
    }

    private fun showExpertMenu() {
        if (!appUnlocked || !uiReady || storageBlocked || session.state.value?.busy == true) return
        AlertDialog.Builder(this).setTitle("Uzman görevleri")
            .setItems(arrayOf("Yeni uzman görevi", "Görev durumunu yenile", "Görevi iptal et", "Sunucu işçi durumunu oku")) { _, index ->
                if (!appUnlocked || storageBlocked) return@setItems
                when (index) {
                    0 -> chooseExpert()
                    1 -> taskActionDialog(false)
                    2 -> taskActionDialog(true)
                    3 -> runOwnerAction("İşçi durumu", false) { app, base, _ ->
                        val result = OwnerGateway.localWorkers(app, base, ExpertTasks.statusBatch(), 2)
                        "Sunucuda iki salt okunur iş:\n${result.toString(2)}\nCanlı model isteği yapılmadı."
                    }
                }
            }.setNegativeButton("Vazgeç", null).show()
    }

    private fun chooseExpert() {
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
                        runOwnerAction("Uzman görevi", true) { app, base, model ->
                            ExpertTasks.report(OwnerGateway.submitTask(app, base, model, experts[index], text))
                        }
                    }.setNegativeButton("Vazgeç", null).show()
            }.setNegativeButton("Vazgeç", null).show()
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
            }.setNegativeButton("Vazgeç", null).show()
    }

    private fun runOwnerAction(
        label: String, needsModel: Boolean,
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
            session.runOwnerOperation(label) { operation(app, base, model) }
        }
    }

    private fun showCihatIdentity() {
        if (!appUnlocked || !uiReady || session.state.value?.busy == true) return
        val verified = CihatIdentity.inspect(this)
        AlertDialog.Builder(this)
            .setTitle("CİHAT uygulama kimliği")
            .setMessage(verified.report())
            .setPositiveButton("Tamam", null)
            .show()
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
        dialog.show()
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
            .show()
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
            }.setNegativeButton("Vazgeç", null).show()
    }

    private fun showLocal(action: () -> String) {
        if (!appUnlocked || !uiReady || storageBlocked) return
        try {
            store.saveMessage("assistant", action())
            session.refreshHistory()
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
                        .setPositiveButton("Tamam", null).show()
                } catch (_: Exception) { connectionStatus.text = getString(R.string.status_registration_failed) }
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
                    connectionStatus.text = getString(R.string.status_owner_server_invalid)
                } else unlock { refreshModels(base, identity) }
            }
            .setNeutralButton("Bağlantıyı kaldır") { _, _ ->
                OwnerGateway.clear()
                prefs.edit { remove("endpoint"); remove("model"); remove("owner_id") }
                session.resetConnectionStatus(getString(R.string.status_model_not_configured))
            }.setNegativeButton("Vazgeç", null).show()
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
                        }.setNegativeButton("Vazgeç", null).show()
                    } else session.resetConnectionStatus("Model doğrulaması bitti; seçim için bağlantıyı tekrar aç.")
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        if (!appUnlocked && pendingUnlock == null && !storageBlocked) showLocked()
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
