package com.example.gptasistan

/** Pure fail-closed MIME/magic helper; a filename is not proof of an APK/model. */
internal object SourceIntakePolicy {
    const val MAX_BYTES: Long = 512L * 1024 * 1024

    fun validateBytes(size: Long) {
        require(size in 1..MAX_BYTES) { "SOURCE_SIZE_OUT_OF_BOUNDS" }
    }

    fun displayName(raw: String?): String =
        raw.orEmpty().take(160)
            .filter { it.code >= 32 && it != '\u007f' }
            .replace('/', '_').replace('\\', '_')
            .trim().take(120).ifBlank { "Seçilen dosya" }

    fun format(header: ByteArray, filename: String): String {
        val isZip = header.size >= 4 &&
            header[0] == 0x50.toByte() && header[1] == 0x4b.toByte() &&
            header[2] in byteArrayOf(0x03, 0x05, 0x07) && header[3] in byteArrayOf(0x04, 0x06, 0x08)
        if (isZip) return when {
            filename.endsWith(".apk", ignoreCase = true) -> "ZIP / APK adayı (henüz doğrulanmadı)"
            filename.endsWith(".aab", ignoreCase = true) -> "ZIP / AAB adayı (henüz doğrulanmadı)"
            else -> "ZIP arşivi (henüz doğrulanmadı)"
        }
        if (header.size >= 4 && header.take(4).toByteArray().contentEquals("GGUF".toByteArray()))
            return "GGUF model başlığı adayı (çalıştırıcı doğrulanmadı)"
        if (header.size >= 4 && header.take(4).toByteArray().contentEquals(byteArrayOf(0x7f, 0x45, 0x4c, 0x46)))
            return "ELF dosyası (çalıştırılmadı)"
        return "Bilinmeyen tür; dosya uzantısı kimlik kanıtı değildir"
    }
}
