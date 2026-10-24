package com.example.gptasistan

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns

/**
 * Production SAF boundary shared by Android UI and instrumented tests.
 * Only a single explicitly selected content URI is read; no persisted grant,
 * copying, source execution, remote request or database write.
 */
object LocalSourceDocument {
    fun inspect(
        resolver: ContentResolver,
        uri: Uri,
        maxBytes: Long = LocalSourceEvidence.MAX_BYTES
    ): LocalSourceEvidence.Evidence {
        require(uri.scheme == ContentResolver.SCHEME_CONTENT) { "LOCAL_SOURCE_URI_DENIED" }
        require(maxBytes in 1..LocalSourceEvidence.MAX_BYTES) { "LOCAL_SOURCE_LIMIT_INVALID" }
        val columns = arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE)
        val metadata = resolver.query(uri, columns, null, null, null)?.use { cursor ->
            if (!cursor.moveToFirst()) null else {
                val nameCol = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                val sizeCol = cursor.getColumnIndex(OpenableColumns.SIZE)
                if (nameCol < 0 || cursor.isNull(nameCol)) null else {
                    Pair(cursor.getString(nameCol),
                        if (sizeCol >= 0 && !cursor.isNull(sizeCol)) cursor.getLong(sizeCol)
                        else null)
                }
            }
        } ?: throw SecurityException("LOCAL_SOURCE_METADATA_DENIED")
        require(LocalSourceEvidence.validDisplayName(metadata.first)) {
            "LOCAL_SOURCE_NAME_DENIED"
        }
        require(metadata.second == null || metadata.second in 0..maxBytes) {
            "LOCAL_SOURCE_DECLARED_SIZE_DENIED"
        }
        val source = resolver.openInputStream(uri)
            ?: throw SecurityException("LOCAL_SOURCE_READ_DENIED")
        return source.use { LocalSourceEvidence.scan(it, metadata.first, metadata.second, maxBytes) }
    }
}
