package com.example.gptasistan

import android.content.Context
import android.content.pm.ApplicationInfo
import android.os.Bundle
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/** Selected explicitly by the fresh-emulator copy job; never part of the normal suite. */
@RunWith(AndroidJUnit4::class)
class BackupInstallationTest {
    @Test
    fun encryptedBackupRestoresAfterFreshInstallation() {
        val arguments = InstrumentationRegistry.getArguments()
        val phase = arguments.getString("backup_phase")
        check(phase in setOf("export", "restore")) { "EXPLICIT_BACKUP_INSTALLATION_PHASE_REQUIRED" }
        val context = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext
        InstrumentationSafety.requireDisposableEmulator(context)
        check(context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) {
            "BACKUP_INSTALLATION_REQUIRES_DEBUG_APP"
        }
        requireFreshStoreAndKeystore(context)
        when (phase) {
            "export" -> exportFixture(context)
            "restore" -> restoreFixture(context, arguments.getString("backup_sha256"))
        }
    }

    private fun requireFreshStoreAndKeystore(context: Context) {
        val main = context.getDatabasePath(KralStore.DATABASE_NAME)
        listOf("", "-wal", "-shm", "-journal", ".plaintext-legacy", ".cipher-staging").forEach {
            check(!File(main.absolutePath + it).exists()) { "EXISTING_DATABASE_REFUSED" }
        }
        listOf(".xml", ".xml.bak").forEach { suffix ->
            check(!File(context.applicationInfo.dataDir, "shared_prefs/$PREFS$suffix").exists()) {
                "EXISTING_DATABASE_KEY_PREFERENCES_REFUSED"
            }
        }
        check(context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).all.isEmpty()) {
            "EXISTING_DATABASE_KEY_PREFERENCES_REFUSED"
        }
        check(!keyExists()) { "EXISTING_DATABASE_KEYSTORE_ALIAS_REFUSED" }
    }

    private fun exportFixture(context: Context) {
        val file = File(context.filesDir, ARCHIVE)
        check(!file.exists()) { "EXISTING_BACKUP_FILE_REFUSED" }
        val password = fixturePassword()
        val store = KralStore(context) // Actual production Android Keystore provider.
        val encrypted: ByteArray
        try {
            val db = store.writableDatabase
            listOf("mem", "tasks", "chat_messages").forEach { table ->
                db.rawQuery("SELECT COUNT(*) FROM $table", null).use {
                    check(it.moveToFirst() && it.getLong(0) == 0L) { "NONEMPTY_SOURCE_REFUSED" }
                }
            }
            db.execSQL("INSERT INTO mem(id,ts,text) VALUES(?,?,?)", arrayOf<Any>(41L, TIMESTAMP, MARKER))
            db.execSQL("INSERT INTO tasks(id,title,done) VALUES(17,'Bekleyen kurulum görevi',0)")
            db.execSQL("INSERT INTO tasks(id,title,done) VALUES(23,'Tamamlanan kurulum görevi',1)")
            listOf(Triple(11L, "system", "Yerel sistem"), Triple(27L, "user", "Özel soru"),
                Triple(35L, "assistant", "Türkçe yanıt")).forEach { (id, role, text) ->
                db.execSQL("INSERT INTO chat_messages(id,ts,role,text) VALUES(?,?,?,?)",
                    arrayOf<Any>(id, TIMESTAMP, role, text))
            }
            verifyRows(store)
            encrypted = KralBackup.export(store, password)
            verifyArchive(encrypted)
            context.openFileOutput(ARCHIVE, Context.MODE_PRIVATE).use { it.write(encrypted) }
            check(keyExists() && context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .contains("wrapped_sqlcipher_key_v1")) { "PRODUCTION_KEY_CREATION_NOT_VERIFIED" }
        } finally { store.close(); password.fill('\u0000') }
        verifyEncryptedDatabase(context)
        publish("export", encrypted, mapOf(
            "source_installation_fresh" to "true", "source_key_created" to "true",
            "source_rows_verified" to "true",
        ))
    }

    private fun restoreFixture(context: Context, expectedHash: String?) {
        check(expectedHash != null && expectedHash.matches(Regex("[0-9a-f]{64}"))) {
            "EXPECTED_BACKUP_HASH_REQUIRED"
        }
        val file = File(context.filesDir, ARCHIVE)
        check(file.isFile && file.length() in 1..KralBackup.MAX_BACKUP_BYTES.toLong()) {
            "BOUNDED_ENCRYPTED_BACKUP_REQUIRED"
        }
        val encrypted = file.readBytes()
        verifyArchive(encrypted)
        check(sha256(encrypted) == expectedHash) { "TRANSFERRED_BACKUP_HASH_MISMATCH" }
        val password = fixturePassword()
        val target = KralStore(context) // Creates a fresh, local Keystore identity; never imports a key.
        try {
            assertEquals(KralBackup.Summary(1, 2, 3), KralBackup.restore(target, encrypted, password))
            verifyRows(target)
        } finally { target.close(); password.fill('\u0000') }
        val reopened = KralStore(context)
        try {
            verifyRows(reopened)
            reopened.saveMessage("user", "Geri yükleme sonrası yeni ileti")
            assertTrue(reopened.history().last().id > 35L)
            assertEquals(4, reopened.history().size)
        } finally { reopened.close() }
        check(keyExists() && context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .contains("wrapped_sqlcipher_key_v1")) { "FRESH_TARGET_KEY_CREATION_NOT_VERIFIED" }
        verifyEncryptedDatabase(context)
        publish("restore", encrypted, mapOf(
            "target_installation_fresh" to "true", "target_key_created" to "true",
            "restore_verified" to "true", "reopen_verified" to "true",
        ))
    }

    private fun verifyRows(store: KralStore) {
        assertEquals(listOf(listOf("41", TIMESTAMP, MARKER)), rows(store, "mem"))
        assertEquals(listOf(listOf("17", "Bekleyen kurulum görevi", "0"),
            listOf("23", "Tamamlanan kurulum görevi", "1")), rows(store, "tasks"))
        assertEquals(listOf(listOf("11", TIMESTAMP, "system", "Yerel sistem"),
            listOf("27", TIMESTAMP, "user", "Özel soru"),
            listOf("35", TIMESTAMP, "assistant", "Türkçe yanıt")), rows(store, "chat_messages"))
    }

    private fun rows(store: KralStore, table: String): List<List<String>> {
        require(table in setOf("mem", "tasks", "chat_messages"))
        val result = mutableListOf<List<String>>()
        store.readableDatabase.rawQuery("SELECT * FROM $table ORDER BY id", null).use { cursor ->
            while (cursor.moveToNext()) result.add((0 until cursor.columnCount).map { cursor.getString(it) })
        }
        return result
    }

    private fun verifyArchive(bytes: ByteArray) {
        check(bytes.size in 80..KralBackup.MAX_BACKUP_BYTES)
        check(bytes.copyOfRange(0, 8).contentEquals("KRALBAK1".toByteArray(Charsets.US_ASCII)))
        check(!String(bytes, Charsets.ISO_8859_1).contains(MARKER_ASCII))
    }

    private fun verifyEncryptedDatabase(context: Context) {
        val file = context.getDatabasePath(KralStore.DATABASE_NAME)
        check(file.isFile && file.length() in 16..(1024 * 1024).toLong())
        val bytes = file.readBytes()
        check(!bytes.copyOfRange(0, 16).contentEquals("SQLite format 3\u0000".toByteArray(Charsets.US_ASCII)))
        check(!String(bytes, Charsets.ISO_8859_1).contains(MARKER_ASCII))
    }

    private fun keyExists(): Boolean = KeyStore.getInstance("AndroidKeyStore").run {
        load(null); containsAlias("kral.database.wrapping.v1")
    }

    private fun publish(phase: String, encrypted: ByteArray, flags: Map<String, String>) {
        val result = Bundle().apply {
            putString("kral_backup_phase", phase)
            putString("kral_backup_archive_sha256", sha256(encrypted))
            putString("kral_backup_archive_encrypted", "true")
            putString("kral_backup_encrypted_db_verified", "true")
            flags.forEach { (key, value) -> putString("kral_backup_$key", value) }
        }
        InstrumentationRegistry.getInstrumentation().addResults(result)
    }

    private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(bytes).joinToString("") { "%02x".format(it.toInt() and 0xff) }

    // Public synthetic fixture password; never an owner credential or database key.
    private fun fixturePassword() = "public-disposable-install-backup-fixture".toCharArray()

    private companion object {
        const val ARCHIVE = "kral-installation-backup.bin"
        const val PREFS = "kral_database_key"
        const val TIMESTAMP = "2026-11-04T17:00:00.123456789Z"
        const val MARKER_ASCII = "INSTALL_BACKUP_PUBLIC_FIXTURE_f319"
        const val MARKER = "$MARKER_ASCII Türkçe hafıza"
    }
}
