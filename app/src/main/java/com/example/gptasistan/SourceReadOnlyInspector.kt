package com.example.gptasistan

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import java.security.MessageDigest

/**
 * Reads only the single URI chosen through Android's document picker.
 * No app execution, archive extraction, file writes, API calls or permission
 * persistence. Provider-backed cloud documents may be fetched by Android's
 * own document provider under the user's explicit selection.
 */
internal object SourceReadOnlyInspector {
    data class Report(val name: String, val bytes: Long, val sha256: String, val format: String) {
        fun toDisplayText(): String = buildString {
            append("Dosya: ").append(name)
            append("\nBoyut: ").append(bytes).append(" bayt")
            append("\nSHA-256: ").append(sha256)
            append("\nTür: ").append(format)
            append("\nDurum: YALNIZ STATİK KAYNAK OKUMASI")
            append("\n\nKod çalıştırılmadı, APK kurulmadı, arşiv açılmadı,")
            append(" hizmet/API ve lisans hakkı doğrulanmadı.")
            append("\nBir beceri otomatik etkinleştirilmedi.")
        }
    }

    private data class DigestResult(val sha256: String, val bytes: Long, val firstBytes: ByteArray)

    private fun digest(resolver: ContentResolver, uri: Uri): DigestResult {
        val hash = MessageDigest.getInstance("SHA-256")
        val prefix = ByteArray(8)
        var filled = 0
        var total = 0L
        val bytes = ByteArray(32 * 1024)
        val input = resolver.openInputStream(uri) ?: error("SOURCE_UNREADABLE")
        input.use { stream ->
            var noProgress = 0
            while (true) {
                val count = stream.read(bytes)
                if (count < 0) break
                if (count == 0) {
                    if (++noProgress > 8) error("SOURCE_READ_STALLED")
                    continue
                }
                noProgress = 0
                total += count.toLong()
                SourceIntakePolicy.validateBytes(total)
                hash.update(bytes, 0, count)
                if (filled < prefix.size) {
                    val take = minOf(prefix.size - filled, count)
                    System.arraycopy(bytes, 0, prefix, filled, take)
                    filled += take
                }
            }
        }
        SourceIntakePolicy.validateBytes(total)
        val digest = hash.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
        return DigestResult(digest, total, prefix.copyOf(filled))
    }

    fun inspect(resolver: ContentResolver, uri: Uri): Report {
        require(uri.scheme == ContentResolver.SCHEME_CONTENT) { "SOURCE_URI_DENIED" }
        val fileName = runCatching {
            resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else null
            }
        }.getOrNull()
        val safeName = SourceIntakePolicy.displayName(fileName)
        val first = digest(resolver, uri)
        val second = digest(resolver, uri)
        check(first.bytes == second.bytes && first.sha256 == second.sha256 &&
            first.firstBytes.contentEquals(second.firstBytes)
        ) { "SOURCE_CHANGED_DURING_READ" }
        return Report(safeName, first.bytes, first.sha256,
            SourceIntakePolicy.format(first.firstBytes, safeName))
    }
}
