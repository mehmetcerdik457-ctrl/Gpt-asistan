package com.example.gptasistan

import android.content.ContentProvider
import android.content.ContentValues
import android.database.Cursor
import android.database.MatrixCursor
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.provider.OpenableColumns
import kotlin.concurrent.thread

/**
 * Instrumentation-only fixture; present only in the test APK.
 * Serves bytes through Android ContentResolver/ParcelFileDescriptor.
 */
class FixtureSourceProvider : ContentProvider() {
    companion object {
        const val AUTHORITY = "com.example.gptasistan.testfixture"
    }

    override fun onCreate(): Boolean = true

    override fun getType(uri: Uri): String = "application/octet-stream"

    override fun query(
        uri: Uri, projection: Array<out String>?,
        selection: String?, selectionArgs: Array<out String>?,
        sortOrder: String?
    ): Cursor {
        val document = uri.lastPathSegment.orEmpty()
        val cursor = MatrixCursor(arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE))
        when (document) {
            "valid" -> cursor.addRow(arrayOf("reference.apk", 3L))
            "unknown" -> cursor.addRow(arrayOf("model.gguf", null))
            "mismatch" -> cursor.addRow(arrayOf("reference.apk", 2L))
            "secret" -> cursor.addRow(arrayOf("credentials.json", 3L))
            "oversize" -> cursor.addRow(arrayOf("reference.apk", 3L))
        }
        return cursor
    }

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
        require(mode == "r") { "READ_ONLY_FIXTURE" }
        val bytes = "abc".toByteArray(Charsets.UTF_8)
        val ends = ParcelFileDescriptor.createPipe()
        thread(name = "read-only-test-provider", isDaemon = true) {
            ParcelFileDescriptor.AutoCloseOutputStream(ends[1]).use {
                it.write(bytes)
            }
        }
        return ends[0]
    }

    override fun insert(uri: Uri, values: ContentValues?): Uri? =
        throw UnsupportedOperationException("READ_ONLY_FIXTURE")

    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<out String>?): Int =
        throw UnsupportedOperationException("READ_ONLY_FIXTURE")

    override fun update(
        uri: Uri, values: ContentValues?, selection: String?,
        selectionArgs: Array<out String>?
    ): Int = throw UnsupportedOperationException("READ_ONLY_FIXTURE")
}
