package com.example.gptasistan

import java.io.InputStream
import java.security.MessageDigest
import java.util.Locale

/**
 * A user-selected local document is hashed *only*; never installed, executed,
 * decompressed, uploaded, or recorded in the chat database.
 * SAF grants access to one picked document and no general storage permission.
 */
object LocalSourceEvidence {
    const val MAX_BYTES: Long = 128L * 1024L * 1024L

    private val SAFE_EXTENSIONS = setOf(
        "apk", "aab", "apks", "gguf", "onnx", "safetensors", "zip",
        "tar", "gz", "jar", "aar", "so", "kt", "java", "py",
        "js", "json", "md"
    )
    private val PRIVATE_NAMES = setOf(
        "id_rsa", "id_ed25519", "credentials.json",
        "service-account.json", "google-services.json"
    )
    private val PRIVATE_SUFFIXES = listOf(".pem", ".key", ".p12", ".jks", ".keystore", ".p8")

    data class Evidence(val fileName: String, val bytesRead: Long, val sha256: String) {
        fun report(): String =
            "TELEFON KAYNAK DOSYASI (yalnızca yerel SHA-256)\n\n" +
            "Adı: $fileName\n" +
            "Boyut: $bytesRead bayt\n" +
            "SHA-256: $sha256\n\n" +
            "Yalnızca senin Android dosya seçiciden seçtiğin belge okundu. " +
            "Sunucuya, modele veya hafızaya aktarılmadı. " +
            "APK imzası, kurulum, lisans, gerçek model ve entegrasyon " +
            "doğrulanmış DEĞİLDİR. Hiçbir dosya değiştirilmedi."
    }

    internal fun validDisplayName(value: String): Boolean {
        if (value.isBlank() || value.length > 160 ||
            value == "." || value == ".." ||
            value.contains('/') || value.contains('\\') ||
            value.any { it.isISOControl() }) return false
        val lower = value.lowercase(Locale.ROOT)
        if (lower.startsWith(".") || lower.startsWith("id_rsa") ||
            lower.startsWith("id_ed25519") || lower.startsWith(".env") ||
            lower in PRIVATE_NAMES || PRIVATE_SUFFIXES.any(lower::endsWith)) return false
        return lower.substringAfterLast('.', "") in SAFE_EXTENSIONS
    }

    /**
     * Caller must open the Android SAF-selected content URI with read access.
     * No buffer contains more than 32 KiB; reads are counted regardless of
     * provider-supplied Content-Length (which may be absent or dishonest).
     */
    internal fun scan(
        stream: InputStream,
        name: String,
        declaredSize: Long? = null,
        maxBytes: Long = MAX_BYTES
    ): Evidence {
        require(validDisplayName(name)) { "LOCAL_SOURCE_NAME_DENIED" }
        require(maxBytes in 1..MAX_BYTES) { "LOCAL_SOURCE_LIMIT_INVALID" }
        require(declaredSize == null || declaredSize in 0..maxBytes) {
            "LOCAL_SOURCE_DECLARED_SIZE_DENIED"
        }
        val sha = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(32768)
        var count = 0L
        while (true) {
            val n = stream.read(buffer, 0, minOf(buffer.size.toLong(), maxBytes - count + 1).toInt())
            if (n < 0) break
            if (n == 0) {
                val next = stream.read()
                if (next < 0) break
                if (++count > maxBytes) throw IllegalArgumentException("LOCAL_SOURCE_SIZE_LIMIT")
                sha.update(next.toByte())
                continue
            }
            count += n
            if (count > maxBytes) throw IllegalArgumentException("LOCAL_SOURCE_SIZE_LIMIT")
            sha.update(buffer, 0, n)
        }
        require(declaredSize == null || count == declaredSize) {
            "LOCAL_SOURCE_DECLARED_SIZE_MISMATCH"
        }
        return Evidence(name, count,
            sha.digest().joinToString("") { "%02x".format(it.toInt() and 255) })
    }
}
