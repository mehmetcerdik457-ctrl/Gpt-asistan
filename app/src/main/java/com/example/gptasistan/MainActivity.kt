package com.example.gptasistan

import android.os.Bundle
import android.app.KeyguardManager
import android.app.Activity
import android.content.Intent
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
    private var appUnlocked = false
    private var sourceInspectionBusy = false
    private var localAuditBusy = false
    private var uiReady = false
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

    private fun showLocked() {
        val locked = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 48, 24, 24)
        }
        locked.addView(TextView(this).apply { text = "KRAL ASİSTAN — cihaz kilidiyle aç"; textSize = 20f })
        locked.addView(Button(this).apply {
            text = "Kilidi aç"
            setAllCaps(false)
            setOnClickListener { unlock {
                if (!uiReady) buildContent(initialState) else setContentView(contentRoot)
            } }
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
                val uri = data?.data
                if (uri?.scheme == "content") {
                    // Re-authenticate after returning from an external document picker.
                    unlock { inspectSelectedLocalSource(uri) }
                }
            }
            return
        }
        if (requestCode != 4701) return
        val action = pendingUnlock
        pendingUnlock = null
        if (resultCode == Activity.RESULT_OK) {
            appUnlocked = true
            if (uiReady) { contentRoot.visibility = View.VISIBLE; setContentView(contentRoot) }
            action?.invoke()
        } else { appUnlocked = false; showLocked() }
    }

    private fun buildContent(savedInstanceState: Bundle?) {
        store = KralStore(this)
        session = ViewModelProvider(this)[ChatSession::class.java]
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 24, 24, 24)
        }
        contentRoot = root
        uiReady = true
        root.addView(TextView(this).apply {
            text = "KRAL ASİSTAN — aday sürüm"
            textSize = 19f
        })
        root.addView(TextView(this).apply {
            text = "Cihaz kilidi açık. Sunucu erişimi kayıtlı sahip ve cihaz imzasıyla doğrulanır."
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
            text = "Owner cihaz ön kontrolü (salt okunur)"
            setAllCaps(false)
            setOnClickListener { showOwnerDevicePreflight() }
        })
        root.addView(Button(this).apply {
            text = "Sunucuya kayıt bilgisi"
            setOnClickListener { unlock { showRegistration() } }
        })
        root.addView(Button(this).apply {
            text = "Owner / Bridge durumu (salt okunur)"
            setOnClickListener { showLocal { OwnerStatus.readOnlyReport(this@MainActivity) } }
        })
        root.addView(Button(this).apply {
            text = "OMEGA durumunu kontrol et (salt okunur)"
            setAllCaps(false)
            setOnClickListener { showOmegaReadOnlyStatus() }
        })
        root.addView(Button(this).apply {
            text = "CİHAT kurulumunu doğrula (salt okunur)"
            setAllCaps(false)
            setOnClickListener { showCihatIdentity() }
        })
        root.addView(Button(this).apply {
            text = "CİHAT AI'ı aç (mevcut uygulama)"
            setAllCaps(false)
            setOnClickListener { openInstalledCihat() }
        })
        root.addView(Button(this).apply {
            text = "CİHAT yanıtını panodan al (önizleme)"
            setAllCaps(false)
            setOnClickListener { previewClipboardReply() }
        })
        root.addView(Button(this).apply {
            text = "Owner kaynak dosyasını incele (imzalı, salt okunur)"
            setAllCaps(false)
            setOnClickListener { showOwnerSourceInspection() }
        })
        root.addView(Button(this).apply {
            text = "Telefondan dosya seç ve SHA-256 hesapla (çevrimdışı)"
            setAllCaps(false)
            setOnClickListener { openLocalSourcePicker() }
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
        root.addView(SwitchCompat(this).apply {
            text = "Önceki model sohbetlerini paylaş"
            isChecked = prefs.getBoolean("share_chat_context", false)
            setOnCheckedChangeListener { _, enabled ->
                prefs.edit().putBoolean("share_chat_context", enabled).apply()
            }
        })
        root.addView(TextView(this).apply {
            text = "Kapalıysa yalnızca yazdığın ileti gönderilir. Açıkken en fazla 3 önceki model sohbeti bu sağlayıcıya da gönderilir."
            textSize = 12f
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
            if (appUnlocked) speakLatestReply()
        }
        tts = TextToSpeech(this, this)
    }

    /** One explicitly user-selected document, never a storage-wide scan. */
    private fun openLocalSourcePicker() {
        if (!appUnlocked || !uiReady || localAuditBusy || isFinishing || isDestroyed ||
            session.state.value?.busy == true) return
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        try {
            startActivityForResult(intent, 4702)
        } catch (_: RuntimeException) {
            connectionStatus.text = "Android dosya seçicisi açılamadı."
        }
    }

    /** No persistent URI grant, copy, upload, extraction or chat/memory write. */
    private fun inspectSelectedLocalSource(uri: android.net.Uri) {
        if (!appUnlocked || !uiReady || localAuditBusy || isFinishing || isDestroyed ||
            session.state.value?.busy == true || uri.scheme != "content") return
        localAuditBusy = true
        connectionStatus.text = "Telefondaki seçili dosya salt okunur inceleniyor…"
        thread {
            val report = try {
                val fields = arrayOf(android.provider.OpenableColumns.DISPLAY_NAME,
                    android.provider.OpenableColumns.SIZE)
                val metadata = contentResolver.query(uri, fields, null, null, null)?.use { c ->
                    if (!c.moveToFirst()) null else {
                        val nameIndex = c.getColumnIndex(android.provider.OpenableColumns.DISPLAY_NAME)
                        val sizeIndex = c.getColumnIndex(android.provider.OpenableColumns.SIZE)
                        if (nameIndex < 0 || c.isNull(nameIndex)) null else {
                            val name = c.getString(nameIndex)
                            val size = if (sizeIndex >= 0 && !c.isNull(sizeIndex))
                                c.getLong(sizeIndex) else null
                            Pair(name, size)
                        }
                    }
                } ?: throw SecurityException("LOCAL_SOURCE_METADATA_DENIED")
                require(LocalSourceEvidence.validDisplayName(metadata.first))
                require(metadata.second == null || metadata.second in 0..LocalSourceEvidence.MAX_BYTES)
                val input = contentResolver.openInputStream(uri)
                    ?: throw SecurityException("LOCAL_SOURCE_READ_DENIED")
                input.use { LocalSourceEvidence.scan(it, metadata.first, metadata.second).report() }
            } catch (_: Exception) {
                "Dosya incelenemedi. Yalnızca desteklenen türde, en fazla 128 MB " +
                    "olan, Android tarafından okunabilir bir dosya seç. Hiçbir kayıt değişmedi."
            }
            runOnUiThread {
                localAuditBusy = false
                if (!isFinishing && !isDestroyed && appUnlocked && uiReady) {
                    AlertDialog.Builder(this)
                        .setTitle("Yerel dosya SHA-256 sonucu")
                        .setMessage(report)
                        .setPositiveButton("Tamam", null)
                        .show()
                }
            }
        }
    }

    /** Explicit user-initiated, read-only phone package inspection. */
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
            connectionStatus.text = "Önce cihaz kilidini aç ve mevcut işlemin bitmesini bekle."
            return
        }
        val installed = CihatIdentity.inspect(this)
        if (!installed.verified) {
            connectionStatus.text =
                "CİHAT 3.2.1 kimliği doğrulanamadı. Kurulum doğrulama ekranını incele; eski APK'ları silme."
            return
        }
        val launch = try {
            packageManager.getLaunchIntentForPackage(CihatHandoff.PACKAGE_NAME)
        } catch (_: RuntimeException) { null }
        if (launch == null) {
            connectionStatus.text = "Bu telefonda açılabilir CİHAT AI (3.2.1) bulunamadı. Mevcut uygulamanı kontrol et."
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
                try { startActivity(launch) }
                catch (_: RuntimeException) {
                    connectionStatus.text = "CİHAT uygulaması açılamadı; cihazdaki kurulumu kontrol et."
                }
            }
            .setNegativeButton("Vazgeç", null)
        if (draft != null) {
            dialog.setNeutralButton("Metni kopyala ve aç") { _, _ ->
                try {
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
                    connectionStatus.text = "CİHAT açılamadı veya Android panosuna metin kopyalanamadı."
                }
            }
        }
        dialog.show()
    }

    /** Manual reply return: user explicitly inspects untrusted clipboard. */
    private fun previewClipboardReply() {
        if (!appUnlocked || !uiReady || session.state.value?.busy == true) {
            if (uiReady) connectionStatus.text = "Önce cihaz kilidini aç ve mevcut işlemin bitmesini bekle."
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
            connectionStatus.text = "Panoda en fazla 2000 karakterlik düz metin yok; hiçbir kayıt değişmedi."
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
                    connectionStatus.text = "Yalnız taslağa aktarıldı; gönderim veya kayıt yapılmadı."
                }
            }
            .setNegativeButton("Vazgeç", null)
            .show()
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
                    val owner = prefs.getString("owner_id", "").orEmpty()
                    if (!OwnerGateway.validBase(endpoint) ||
                        OwnerGateway.verifiedModels(endpoint, owner).none { it.id == model }) {
                        connectionStatus.text = "Doğrulanmış model yok; Model tuşuyla bağlantıyı yenile."
                        false
                    } else {
                        unlock {
                            if (OwnerGateway.verifiedModels(endpoint, owner).none { it.id == model }) {
                                session.resetConnectionStatus("Model doğrulamasının süresi doldu; Model tuşuyla yenile.")
                            } else if (session.send(
                                    endpoint, model, command.value,
                                    prefs.getBoolean("share_chat_context", false),
                                ) && input.text.toString().trim() == raw)
                                input.text.clear()
                        }
                        false
                    }
                }
                KralCommand.Invalid -> recordLocal(raw) { "Komut geçersiz. " + KralCore.help() }
            }
        } catch (_: Exception) {
            connectionStatus.text = "İşlem kaydedilemedi; yazdığın metin korundu. Depolama alanını kontrol et."
            false
        }
    }

    private fun speakLatestReply() {
        if (stopped || !appUnlocked || !ttsReady || !prefs.getBoolean("speak_replies", false)) return
        val reply = session.peekUnspokenReply() ?: return
        if (tts?.speak(reply.second.take(4000), TextToSpeech.QUEUE_FLUSH, null, "kral-reply") == TextToSpeech.SUCCESS)
            session.markSpoken(reply.first)
    }

    private fun showOmegaReadOnlyStatus() {
        val endpoint = EditText(this).apply {
            hint = "https://omega-sunucusu.example"
            isSingleLine = true
        }
        AlertDialog.Builder(this)
            .setTitle("OMEGA — salt okunur bağlantı testi")
            .setMessage("Yalnız senin girdiğin HTTPS adresine /api/health isteği yapılır. " +
                "Sahip imzası, anahtar, hafıza veya mesaj gönderilmez. " +
                "Bu kontrol Owner yetkisi vermez.")
            .setView(endpoint)
            .setPositiveButton("Durumu kontrol et") { _, _ ->
                val address = endpoint.text.toString().trim()
                if (!OmegaReadOnlyStatus.validBase(address)) {
                    connectionStatus.text = "OMEGA için HTTPS kök adresi gerekli."
                } else {
                    connectionStatus.text = "OMEGA salt okunur bağlantı kontrolü yapılıyor…"
                    thread {
                        val report = try {
                            OmegaReadOnlyStatus.fetch(address).message
                        } catch (_: Exception) {
                            "OMEGA güvenli durum yanıtı doğrulanamadı; Owner veya model " +
                                "yürütmesine izin verilmedi."
                        }
                        runOnUiThread {
                            if (!isFinishing && !isDestroyed && appUnlocked) {
                                AlertDialog.Builder(this)
                                    .setTitle("OMEGA bağlantı durumu")
                                    .setMessage(report)
                                    .setPositiveButton("Tamam", null)
                                    .show()
                            }
                        }
                    }
                }
            }
            .setNegativeButton("Vazgeç", null)
            .show()
    }

    /** Explicit Owner action only: no provider call, auto-enrollment or chat write. */
    private fun showOwnerSourceInspection() {
        if (!appUnlocked || !uiReady || isFinishing || isDestroyed ||
            session.state.value?.busy == true || sourceInspectionBusy) return
        // Do not let an inspection silently create AndroidKeyStore identities.
        val facts = OwnerDevicePreflight.readOnlyFacts(this)
        if (!facts.secureLock ||
            facts.owner != OwnerDevicePreflight.KeyState.AUTH_REQUIRED_P256 ||
            facts.device != OwnerDevicePreflight.KeyState.AUTH_REQUIRED_P256) {
            AlertDialog.Builder(this).setTitle("Owner anahtarı doğrulanamadı")
                .setMessage("Bu telefonda mevcut, kullanıcı doğrulamalı Owner ve cihaz " +
                    "anahtarları hazır değil. Yeni anahtar oluşturulmayacak, ağ isteği " +
                    "yapılmayacak. Önce cihaz ön kontrolü ve gerçek sunucu kaydını doğrula.")
                .setPositiveButton("Tamam", null).show()
            return
        }
        val inputs = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 12, 24, 0)
        }
        val endpoint = EditText(this).apply {
            hint = "https://sana-ait-sunucu.example"
            isSingleLine = true
            setText(prefs.getString("endpoint", ""))
            filters = arrayOf(InputFilter.LengthFilter(256))
        }
        val owner = EditText(this).apply {
            hint = "Sunucuda kayıtlı Owner kimliği"
            isSingleLine = true
            setText(prefs.getString("owner_id", ""))
            filters = arrayOf(InputFilter.LengthFilter(64))
        }
        val file = EditText(this).apply {
            hint = "İzinli sunucu klasöründe dosya: ornek.apk"
            isSingleLine = true
            filters = arrayOf(InputFilter.LengthFilter(512))
        }
        inputs.addView(endpoint); inputs.addView(owner); inputs.addView(file)
        AlertDialog.Builder(this)
            .setTitle("KRAL kaynak incelemesi")
            .setMessage("Yalnızca senin seçtiğin HTTPS sunucusuna, yazdığın dosya " +
                "adını içeren çift imzalı istek gönderilir. Sunucunun önceden " +
                "izin verdiği klasör incelenir. Anahtarlar, sohbet ve hafıza " +
                "gönderilmez. İzin veriyorsan 'İncele'ye dokun. Bu bir " +
                "üretim Owner kabul testi değildir.")
            .setView(inputs)
            .setPositiveButton("İncele") { _, _ ->
                val base = endpoint.text.toString().trim().trimEnd('/')
                val identity = owner.text.toString().trim()
                val sourceId = file.text.toString().trim()
                if (!OwnerGateway.validBase(base) || !OmegaEnvelope.validOwner(identity) ||
                    !OwnerSourceInspection.validSourceId(sourceId)) {
                    connectionStatus.text = "HTTPS kökü, Owner kimliği veya dosya adı geçersiz."
                } else unlock {
                    if (!appUnlocked || !uiReady || sourceInspectionBusy) return@unlock
                    sourceInspectionBusy = true
                    connectionStatus.text = "İmzalı kaynak incelemesi yapılıyor…"
                    thread {
                        val report = try {
                            OwnerSourceInspection.inspect(base, identity, sourceId).report()
                        } catch (_: Exception) {
                            "Kaynak incelemesi doğrulanamadı. İstek, sunucu klasörü, " +
                                "Owner kaydı veya HTTPS kontrolünü denetle. " +
                                "Dosya ya da model çalıştırılmadı."
                        }
                        runOnUiThread {
                            sourceInspectionBusy = false
                            if (!isFinishing && !isDestroyed && appUnlocked && uiReady) {
                                AlertDialog.Builder(this)
                                    .setTitle("İmzalı kaynak inceleme sonucu")
                                    .setMessage(report)
                                    .setPositiveButton("Tamam", null).show()
                            }
                        }
                    }
                }
            }
            .setNeutralButton("İzinli dosyaları listele") { _, _ ->
                val base = endpoint.text.toString().trim().trimEnd('/')
                val identity = owner.text.toString().trim()
                if (!OwnerGateway.validBase(base) || !OmegaEnvelope.validOwner(identity)) {
                    connectionStatus.text = "Dosya listesi için geçerli HTTPS ve Owner kimliği gerekli."
                } else unlock { showOwnerSourceChoices(base, identity) }
            }
            .setNegativeButton("Vazgeç", null).show()
    }

    /** Signed, read-only candidates; each selection requires another explicit signed action. */
    private fun showOwnerSourceChoices(base: String, owner: String) {
        if (!appUnlocked || !uiReady || isFinishing || isDestroyed || sourceInspectionBusy ||
            session.state.value?.busy == true) return
        sourceInspectionBusy = true
        connectionStatus.text = "İzinli kaynak adları isteniyor…"
        thread {
            val listing = try {
                OwnerSourceInspection.listAvailable(base, owner)
            } catch (_: Exception) { null }
            runOnUiThread {
                sourceInspectionBusy = false
                if (isFinishing || isDestroyed || !appUnlocked || !uiReady) return@runOnUiThread
                if (listing == null) {
                    connectionStatus.text = "İmzalı kaynak listesi alınamadı; Owner ve sunucu kaydını kontrol et."
                    return@runOnUiThread
                }
                if (listing.entries.isEmpty()) {
                    connectionStatus.text = if (listing.truncated)
                        "Kaynak listeleme sınırına ulaşıldı; sonuç eksik." else
                        "İzinli klasörde gösterilebilir kaynak bulunmadı."
                    return@runOnUiThread
                }
                val labels = listing.entries.map { it.label() }.toTypedArray()
                AlertDialog.Builder(this)
                    .setTitle(if (listing.truncated) "İzinli dosyalar (eksik liste)" else
                        "İzinli dosyalar (test edilmemiş)")
                    .setItems(labels) { _, index ->
                        val sourceId = listing.entries[index].sourceId
                        unlock {
                            if (!appUnlocked || !uiReady || sourceInspectionBusy ||
                                isFinishing || isDestroyed) return@unlock
                            sourceInspectionBusy = true
                            connectionStatus.text = "Seçilen kaynak imzalı olarak inceleniyor…"
                            thread {
                                val report = try {
                                    OwnerSourceInspection.inspect(base, owner, sourceId).report()
                                } catch (_: Exception) {
                                    "Kaynak incelemesi doğrulanamadı. İzinli klasörü ve Owner kaydını kontrol et."
                                }
                                runOnUiThread {
                                    sourceInspectionBusy = false
                                    if (!isFinishing && !isDestroyed && appUnlocked && uiReady) {
                                        AlertDialog.Builder(this)
                                            .setTitle("Seçilen kaynak inceleme sonucu")
                                            .setMessage(report)
                                            .setPositiveButton("Tamam", null).show()
                                    }
                                }
                            }
                        }
                    }
                    .setNegativeButton("Vazgeç", null).show()
            }
        }
    }

    private fun showOwnerDevicePreflight() {
        if (!appUnlocked || !uiReady || isFinishing || isDestroyed) return
        AlertDialog.Builder(this)
            .setTitle("Owner cihaz hazırlığı — salt okunur")
            .setMessage(OwnerDevicePreflight.readOnlyReport(this))
            .setPositiveButton("Tamam", null).show()
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
                val reveal = {
                    try {
                        val registration = OwnerIdentity.publicRegistration(owner.text.toString().trim())
                        val text = TextView(this).apply {
                            this.text = registration
                            setTextIsSelectable(true)
                            setPadding(24, 24, 24, 24)
                        }
                        AlertDialog.Builder(this).setTitle("Yalnız açık kayıt bilgileri")
                            .setView(ScrollView(this).apply { addView(text) })
                            .setPositiveButton("Tamam", null).show()
                    } catch (_: Exception) {
                        connectionStatus.text = "Kayıt anahtarları okunamadı veya oluşturulamadı; cihaz kilidini kontrol et."
                    }
                }
                if (packageName.endsWith(".genesis.cihatpreview")) {
                    AlertDialog.Builder(this)
                        .setTitle("Önizleme: gerçek Owner kaydı için uygun değil")
                        .setMessage("Bu APK debug imzalıdır. Burada kalıcı Owner anahtarları üretmek, sonraki farklı imzalı APK'ya güvenli geçiş sağlamaz. Bu işlem sunucu yetkisi de vermez. Yalnız deneme anahtarı oluşturmak veya mevcut açık anahtarları görmek istiyor musun?")
                        .setPositiveButton("Deneme bilgilerini göster") { _, _ -> reveal() }
                        .setNegativeButton("Vazgeç", null).show()
                } else reveal()
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
            .setMessage("Sana ait HTTPS sunucusu sahip ve cihaz imzanı doğrular. Yalnız canlı yanıtla doğrulanan modeller listelenir. Önceki model sohbetleri ancak ayrı paylaşım anahtarını açarsan gönderilir; varsayılan kapalıdır.")
            .setView(fields)
            .setPositiveButton("Bağlantıyı doğrula") { _, _ ->
                val base = endpoint.text.toString().trim().trimEnd('/')
                val identity = owner.text.toString().trim()
                if (!OwnerGateway.validBase(base) || !OmegaEnvelope.validOwner(identity)) {
                    connectionStatus.text = "Geçerli HTTPS sunucu kökü ve sahip kimliği gerekli."
                } else unlock { refreshModels(base, identity) }
            }
            .setNeutralButton("Bağlantıyı kaldır") { _, _ ->
                OwnerGateway.clear()
                prefs.edit().remove("endpoint").remove("model").remove("owner_id").apply()
                session.resetConnectionStatus("Model bağlantısı yapılandırılmadı")
            }.setNegativeButton("Vazgeç", null).show()
    }

    private fun refreshModels(base: String, identity: String) {
        modelButton.isEnabled = false
        sendButton.isEnabled = false
        connectionStatus.text = "Sahip imzası ve canlı model yanıtı doğrulanıyor…"
        thread {
            val models = try { OwnerGateway.models(base, identity) } catch (_: Exception) { null }
            runOnUiThread {
                if (isFinishing || isDestroyed) return@runOnUiThread
                modelButton.isEnabled = true
                sendButton.isEnabled = true
                if (models == null) {
                    session.resetConnectionStatus("Bağlantı doğrulanamadı. Sunucu kaydını, ekran kilidini ve HTTPS adresini kontrol et.")
                } else {
                    prefs.edit().putString("endpoint", base).putString("owner_id", identity).remove("model").apply()
                    if (models.isEmpty()) {
                        session.resetConnectionStatus("Sunucuya erişildi; canlı yanıtla doğrulanmış model bulunamadı.")
                    } else if (appUnlocked) {
                        val labels = models.map { "${it.provider} / ${it.id} (${it.latencyMs} ms)" }.toTypedArray()
                        AlertDialog.Builder(this).setTitle("Canlı doğrulanan modeli seç").setItems(labels) { _, index ->
                            val selected = models[index]
                            if (appUnlocked && OwnerGateway.verifiedModels(base, identity).any { it == selected }) {
                                prefs.edit().putString("model", selected.id).apply()
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
        if (!appUnlocked && pendingUnlock == null) showLocked()
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
