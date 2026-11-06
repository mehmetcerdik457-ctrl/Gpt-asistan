package com.example.gptasistan

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.text.InputFilter
import android.text.InputType
import android.widget.EditText
import android.widget.LinearLayout
import androidx.appcompat.app.AlertDialog
import java.io.ByteArrayOutputStream
import kotlin.concurrent.thread

/** User-picked encrypted files only. Passwords and private keys are never saved in Activity state. */
internal class BackupUi(
    private val activity: Activity,
    private val store: () -> KralStore?,
    private val authorize: (() -> Unit) -> Unit,
    private val showDialog: (AlertDialog.Builder, () -> Unit) -> AlertDialog,
    private val notice: (String) -> Unit,
    private val refresh: () -> Unit,
) {
    private var pendingPicker: Int? = null
    private var busy = false

    /** Persist the outstanding operation only, never its URI, password or private records. */
    fun savePendingState(state: Bundle) {
        state.remove(PENDING_PICKER_STATE)
        pendingPicker?.takeIf { it == EXPORT || it == RESTORE }?.let {
            state.putInt(PENDING_PICKER_STATE, it)
        }
    }

    @Suppress("DEPRECATION")
    fun restorePendingState(state: Bundle?) {
        val saved = try { state?.get(PENDING_PICKER_STATE) as? Int } catch (_: RuntimeException) { null }
        pendingPicker = saved?.takeIf {
            it == EXPORT || it == RESTORE
        }
    }

    fun showMenu() {
        if (store() == null || busy || pendingPicker != null) return
        showDialog(AlertDialog.Builder(activity).setTitle(R.string.backup_title)
            .setItems(arrayOf(activity.getString(R.string.backup_export), activity.getString(R.string.backup_restore))) { _, index ->
                authorize { if (store() != null) pickDocument(index == 0) }
            }.setNegativeButton(R.string.action_cancel, null), {})
    }

    private fun pickDocument(export: Boolean) {
        val code = if (export) EXPORT else RESTORE
        val intent = Intent(if (export) Intent.ACTION_CREATE_DOCUMENT else Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/octet-stream"
            if (export) putExtra(Intent.EXTRA_TITLE, "KRAL-Genesis.kralbackup")
        }
        pendingPicker = code
        try {
            activity.startActivityForResult(intent, code)
        } catch (_: ActivityNotFoundException) {
            pendingPicker = null
            notice(activity.getString(R.string.backup_picker_missing))
        } catch (_: SecurityException) {
            pendingPicker = null
            notice(activity.getString(R.string.backup_failed))
        }
    }

    fun onActivityResult(code: Int, result: Int, intent: Intent?): Boolean {
        if (code != EXPORT && code != RESTORE) return false
        val expected = pendingPicker
        pendingPicker = null
        if (expected != code || result != Activity.RESULT_OK) return true
        val uri = intent?.data ?: return true
        if (uri.scheme != "content") {
            notice(activity.getString(R.string.backup_failed))
            return true
        }
        // Returning from a document provider re-locks the application, just like speech input.
        authorize { if (store() != null) askPassword(uri, code == EXPORT) }
        return true
    }

    private fun askPassword(uri: Uri, export: Boolean) {
        if (store() == null || busy) return
        val first = passwordField(R.string.backup_password)
        val second = if (export) passwordField(R.string.backup_repeat_password) else null
        val fields = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 16, 24, 0)
            addView(first)
            second?.let { addView(it) }
        }
        showDialog(AlertDialog.Builder(activity).setTitle(if (export) R.string.backup_export else R.string.backup_restore)
            .setMessage(if (export) R.string.backup_export_explanation else R.string.backup_restore_explanation)
            .setView(fields)
            .setPositiveButton(if (export) R.string.backup_export else R.string.backup_restore) { _, _ ->
                val password = CharArray(first.length()) { first.text[it] }
                val confirmation = second?.let { field -> CharArray(field.length()) { field.text[it] } }
                val valid = password.size in 12..1024 && (confirmation == null || password.contentEquals(confirmation))
                first.text.clear()
                second?.text?.clear()
                confirmation?.fill('\u0000')
                val current = store()
                if (!valid || current == null || busy) {
                    password.fill('\u0000')
                    notice(activity.getString(R.string.backup_password_invalid))
                } else execute(current, uri, export, password)
            }.setNegativeButton(R.string.action_cancel, null), {
                first.text.clear()
                second?.text?.clear()
            })
    }

    private fun passwordField(hint: Int) = EditText(activity).apply {
        setHint(hint)
        inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        filters = arrayOf(InputFilter.LengthFilter(1024))
        importantForAutofill = android.view.View.IMPORTANT_FOR_AUTOFILL_NO
        isSaveEnabled = false
    }

    private fun execute(current: KralStore, uri: Uri, export: Boolean, password: CharArray) {
        busy = true
        thread(name = "kral-backup") {
            val result = runCatching {
                if (export) {
                    val encrypted = KralBackup.export(current, password)
                    try {
                        val output = activity.contentResolver.openOutputStream(uri, "wt")
                            ?: error("BACKUP_OUTPUT_UNAVAILABLE")
                        output.use { it.write(encrypted); it.flush() }
                    } finally { encrypted.fill(0) }
                    activity.getString(R.string.backup_exported)
                } else {
                    val encrypted = readBounded(uri)
                    try {
                        val restored = KralBackup.restore(current, encrypted, password)
                        activity.getString(R.string.backup_restored, restored.memories, restored.tasks, restored.messages)
                    } finally { encrypted.fill(0) }
                }
            }
            password.fill('\u0000')
            activity.runOnUiThread {
                busy = false
                // ChatSession is retained across configuration changes and ignores
                // refresh after onCleared. Its private view stays behind the owner gate.
                if (!export && result.isSuccess) refresh()
                if (activity.isFinishing || activity.isDestroyed || store() == null) return@runOnUiThread
                result.onSuccess {
                    notice(it)
                }.onFailure { notice(activity.getString(R.string.backup_failed)) }
            }
        }
    }

    private fun readBounded(uri: Uri): ByteArray {
        val input = activity.contentResolver.openInputStream(uri) ?: error("BACKUP_INPUT_UNAVAILABLE")
        return input.use { stream ->
            val buffer = ByteArray(8192)
            val output = ByteArrayOutputStream()
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) break
                check(count <= KralBackup.MAX_BACKUP_BYTES - output.size()) { "BACKUP_SIZE_LIMIT" }
                output.write(buffer, 0, count)
            }
            output.toByteArray()
        }
    }

    private companion object {
        const val PENDING_PICKER_STATE = "kral.backup.pending_picker"
        const val EXPORT = 4703
        const val RESTORE = 4704
    }
}
