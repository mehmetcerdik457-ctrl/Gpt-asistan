package com.example.gptasistan

import org.json.JSONObject
import java.util.Locale

/**
 * Explicit, signed read-only source inspection. Never reads the phone filesystem,
 * never enrolls Owner keys, never invokes a model, and never stores source data.
 */
object OwnerSourceInspection {
    private val SHA256 = Regex("[a-f0-9]{64}")
    private val SAFE_EXTENSIONS = setOf(
        "apk", "aab", "apks", "gguf", "onnx", "safetensors", "zip",
        "tar", "gz", "jar", "aar", "so", "kt", "java", "py",
        "js", "json", "md"
    )
    private val FORBIDDEN_COMPONENTS = setOf(
        "secrets", "keyrings", ".git", ".gradle", ".idea", ".ssh",
        ".venv", "__pycache__", "node_modules", "id_rsa", "id_ed25519",
        "credentials.json", "service-account.json", "google-services.json"
    )
    private val FORBIDDEN_ENDINGS = listOf(".pem", ".key", ".p12", ".jks", ".keystore", ".p8")

    data class Evidence(
        val sourceId: String, val sizeBytes: Long, val sha256: String,
        val format: String, val staticStatus: String, val structure: ApkStructure?
    ) {
        fun report(): String = buildString {
            append("SUNUCU KAYNAK İNCELEMESİ (salt okunur)\n\n")
            append("Dosya: ").append(sourceId).append("\n")
            append("SHA-256: ").append(sha256).append("\n")
            append("Boyut: ").append(sizeBytes).append(" bayt\n")
            append("Tür ipucu: ").append(format).append("\n")
            append("Dosya durumu: ").append(staticStatus).append("\n")
            structure?.let { apk ->
                append("APK yapı durumu: ").append(apk.status).append("\n")
                if (apk.status == "ZIP_STRUCTURE_VERIFIED") {
                    append("DEX sayısı: ").append(apk.dexCount).append("\n")
                    append("Native kütüphane sayısı: ").append(apk.nativeCount).append("\n")
                    append("Mimariler: ").append(apk.abis.joinToString(", ").ifBlank { "Yok" }).append("\n")
                }
            }
            append("\nBu yalnızca imzalı isteğe verilen sunucu dosya kanıtıdır. ")
            append("APK imzası, kurulum, gerçek model, Owner üretim kaydı ve ")
            append("entegrasyon doğrulanmış DEĞİLDİR. Telefon hafızasına kaydedilmedi.")
        }
    }

    data class ApkStructure(
        val status: String, val dexCount: Int,
        val nativeCount: Int, val abis: List<String>
    )
    
    data class SourceCandidate(
        val sourceId: String,
        val format: String,
        val sizeBytes: Long,
    ) {
        fun label(): String = "${sourceId} — ${format} (${sizeBytes} bayt)"
    }

    data class SourceList(val entries: List<SourceCandidate>, val truncated: Boolean)

    /** Every listing request is an explicit, user-authenticated Owner action. */
    fun listAvailable(base: String, owner: String): SourceList {
        require(OwnerGateway.validBase(base) && OmegaEnvelope.validOwner(owner))
        return parseSourceList(OwnerGateway.signedSourceListRequest(base, owner))
    }

    internal fun parseSourceList(json: JSONObject): SourceList {
        require(json.get("contract") == OmegaEnvelope.CONTRACT)
        require(json.get("read_only") === true)
        require(json.get("capability_status") == "UNTESTED")
        require(json.get("integration_status") == "NOT_CONNECTED")
        require(json.get("truncated") is Boolean)
        val entries = json.getJSONArray("sources")
        require(entries.length() <= 50)
        val candidates = (0 until entries.length()).map { index ->
            val row = entries.getJSONObject(index)
            val id = row.get("source_id")
            val format = row.get("format_hint")
            val size = row.get("size_bytes")
            require(id is String && validSourceId(id))
            require(format is String && format.length <= 40 &&
                format.matches(Regex("[a-z0-9_]+")))
            require((size is Int || size is Long) &&
                (size as Number).toLong() in 0..134217728L)
            SourceCandidate(id, format, (size as Number).toLong())
        }
        require(candidates.map { it.sourceId }.distinct().size == candidates.size)
        return SourceList(candidates, json.getBoolean("truncated"))
    }


    internal fun validSourceId(sourceId: String): Boolean {
        if (sourceId.isBlank() || sourceId.length > 512 ||
            sourceId.startsWith("/") || '\\' in sourceId ||
            sourceId.any { it.isISOControl() }) return false
        val components = sourceId.split("/")
        if (components.any {
            val lower = it.lowercase(Locale.ROOT)
            it.isEmpty() || it == "." || it == ".." || it.startsWith(".") ||
                lower in FORBIDDEN_COMPONENTS ||
                FORBIDDEN_ENDINGS.any(lower::endsWith)
        }) return false
        return components.last().substringAfterLast('.', "").lowercase(Locale.ROOT) in SAFE_EXTENSIONS
    }

    fun inspect(base: String, owner: String, sourceId: String): Evidence {
        require(OwnerGateway.validBase(base) && OmegaEnvelope.validOwner(owner) && validSourceId(sourceId)) {
            "SOURCE_INPUT_DENIED"
        }
        return parseEvidence(OwnerGateway.signedSourceRequest(base, owner, sourceId), sourceId)
    }

    /** Parser is intentionally strict and never interpolates arbitrary server strings. */
    internal fun parseEvidence(json: JSONObject, requestedId: String): Evidence {
        require(validSourceId(requestedId))
        require(json.get("contract") == OmegaEnvelope.CONTRACT)
        val source = json.getJSONObject("source")
        require(source.get("source_id") == requestedId)
        require(source.get("read_only") === true)
        require(source.get("capability_status") == "UNTESTED")
        require(source.get("integration_status") == "NOT_CONNECTED")
        val size = source.get("size_bytes")
        require((size is Int || size is Long) && (size as Number).toLong() in 0..134217728L)
        val sha = source.get("sha256")
        require(sha is String && SHA256.matches(sha))
        val hint = source.get("format_hint")
        require(hint is String && hint.length <= 40 && hint.matches(Regex("[a-z0-9_]+")))
        val status = source.get("status")
        require(status == "VERIFIED_FILE" || status == "ANALYZED_STATIC")
        val apk = if (hint == "android_apk") {
            val structure = source.getJSONObject("apk_structure")
            val structureStatus = structure.get("status")
            require(structureStatus == "ZIP_STRUCTURE_VERIFIED" ||
                structureStatus == "INVALID_APK_STRUCTURE" || structureStatus == "BLOCKED")
            if (structureStatus == "ZIP_STRUCTURE_VERIFIED") {
                require(structure.get("signature_verified") === false &&
                        structure.get("install_tested") === false &&
                        structure.get("model_inference_tested") === false)
                val dex = structure.get("dex_count")
                val count = structure.get("native_library_count")
                require((dex is Int || dex is Long) && (dex as Number).toLong() in 0..10000L)
                require((count is Int || count is Long) && (count as Number).toLong() in 0..10000L)
                val entries = structure.getJSONArray("native_abis")
                require(entries.length() <= 4)
                val abis = (0 until entries.length()).map { index ->
                    val abi = entries.get(index)
                    require(abi is String && abi in setOf("arm64-v8a", "armeabi-v7a", "x86", "x86_64"))
                    abi
                }
                require(abis.distinct() == abis)
                ApkStructure("ZIP_STRUCTURE_VERIFIED", (dex as Number).toInt(), (count as Number).toInt(), abis)
            } else {
                require(status != "ANALYZED_STATIC")
                ApkStructure(structureStatus as String, 0, 0, emptyList())
            }
        } else {
            require(status == "VERIFIED_FILE")
            null
        }
        if (status == "ANALYZED_STATIC") require(apk?.status == "ZIP_STRUCTURE_VERIFIED")
        return Evidence(requestedId, (size as Number).toLong(), sha, hint, status as String, apk)
    }
}
