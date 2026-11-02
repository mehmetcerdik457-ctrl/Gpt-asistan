package com.example.gptasistan

import android.content.Context
import android.database.sqlite.SQLiteDatabase as PlatformSQLiteDatabase
import net.zetetic.database.sqlcipher.SQLiteDatabase as CipherSQLiteDatabase
import java.io.File
import java.io.FileInputStream

/** Fail-closed plaintext to SQLCipher conversion. The original is never deleted automatically. */
internal object EncryptedDatabaseMigration {
    private const val LEGACY_NAME = "kral_local.db.plaintext-legacy"
    private const val STAGING_NAME = "kral_local.db.cipher-staging"
    private const val TARGET_VERSION = 3

    @Synchronized
    fun migrateIfNeeded(context: Context, key: ByteArray) {
        val appContext = context.applicationContext
        System.loadLibrary("sqlcipher")
        val database = appContext.getDatabasePath(KralStore.DATABASE_NAME)
        val legacy = appContext.getDatabasePath(LEGACY_NAME)
        val staging = appContext.getDatabasePath(STAGING_NAME)

        // Never delete a prior copy, an unrecognized DB, or an interrupted staging file.
        if (database.exists() && !isPlaintextSqlite(database)) {
            verifyEncryptedFile(database, key)
            return
        }
        if (legacy.exists() || staging.exists()) {
            throw IllegalStateException("Önceki migration izleri mevcut; hiçbir dosya değiştirilmedi.")
        }
        if (!database.exists()) return // Fresh installation; SQLCipher helper will create it.
        if (!isPlaintextSqlite(database)) {
            throw IllegalStateException("Veritabanı biçimi tanınmıyor; özgün dosya korunuyor.")
        }
        // The file-only export cannot safely copy uncheckpointed WAL or journal data.
        // Require an explicit, independently verified checkpoint before retrying.
        if (listOf("-wal", "-shm", "-journal").any {
                File(database.absolutePath + it).exists()
            }) {
            throw IllegalStateException("SQLite WAL/journal bulundu; veri tutarlılığı için migration engellendi.")
        }

        val source = database
        val snapshot = readPlaintextSnapshot(source)
        val oldVersion = snapshot.version
        require(oldVersion in 1..2) { "Desteklenmeyen plaintext veritabanı sürümü: $oldVersion" }

        val encrypted = CipherSQLiteDatabase.openOrCreateDatabase(staging, key, null, null)
        try {
            val safePath = source.absolutePath.replace("'", "''")
            encrypted.execSQL("ATTACH DATABASE '$safePath' AS plaintext KEY ''")
            encrypted.rawQuery("SELECT sqlcipher_export('main', 'plaintext')", null).use { result ->
                check(result.moveToFirst()) { "Plaintext veritabanı dışa aktarılamadı." }
            }
            encrypted.execSQL("DETACH DATABASE plaintext")
            if (oldVersion == 1) createChatTable(encrypted)
            encrypted.version = TARGET_VERSION
            verifyDatabase(encrypted, snapshot.counts)
        } finally {
            encrypted.close()
        }

        // Reopen the stage and verify it BEFORE touching the original DB.
        verifyEncryptedFile(staging, key, snapshot.counts)
        check(database.renameTo(legacy)) {
            "Özgün SQLite dosyası taşınamadı; hiçbir veri silinmedi."
        }
        if (!staging.renameTo(database)) {
            // Try to restore the original, preserving both files if restoration fails.
            val restored = legacy.renameTo(database)
            check(restored) {
                "Şifreli staging devreye alınamadı ve eski veritabanı otomatik geri alınamadı."
            }
            throw IllegalStateException("Şifreli staging devreye alınamadı; eski veritabanı geri alındı.")
        }

        // On failed final verification, keep BOTH files intact for owner recovery.
        // The retained plaintext legacy snapshot is intentionally NOT deleted.
        // A later owner-approved cleanup is required for full at-rest privacy.
        verifyEncryptedFile(database, key, snapshot.counts)
    }

    private data class Snapshot(val version: Int, val counts: Map<String, Long>)

    private fun readPlaintextSnapshot(file: File): Snapshot {
        // OPEN_READONLY cannot create/checkpoint a journal or modify the source.
        val database = PlatformSQLiteDatabase.openDatabase(
            file.absolutePath, null, PlatformSQLiteDatabase.OPEN_READONLY,
        )
        return try {
            database.rawQuery("PRAGMA quick_check", null).use { rows ->
                check(rows.moveToFirst() && rows.getString(0) == "ok") {
                    "Özgün SQLite bütünlüğü doğrulanamadı."
                }
            }
            val version = database.version
            require(version in 1..2)
            val tables = mutableSetOf<String>()
            database.rawQuery("SELECT name FROM sqlite_master WHERE type='table'", null).use { rows ->
                while (rows.moveToNext()) tables.add(rows.getString(0))
            }
            check(setOf("mem", "tasks").all(tables::contains)) {
                "Özgün SQLite şeması beklenen tabloları içermiyor."
            }
            if (version == 2) check("chat_messages" in tables)
            val counts = linkedMapOf<String, Long>()
            for (table in listOf("mem", "tasks", "chat_messages")) {
                if (table == "chat_messages" && version == 1) {
                    counts[table] = 0
                } else {
                    database.rawQuery("SELECT COUNT(*) FROM " + table, null).use { rows ->
                        check(rows.moveToFirst())
                        counts[table] = rows.getLong(0)
                    }
                }
            }
            Snapshot(version, counts)
        } finally {
            database.close()
        }
    }

    private fun createChatTable(database: CipherSQLiteDatabase) {
        database.execSQL(
            "CREATE TABLE chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, " +
                "role TEXT NOT NULL CHECK(role IN ('user','assistant','system')), text TEXT NOT NULL)",
        )
    }

    private fun verifyDatabase(database: CipherSQLiteDatabase, expected: Map<String, Long>? = null) {
        database.rawQuery("PRAGMA quick_check", null).use { result ->
            check(result.moveToFirst() && result.getString(0) == "ok") {
                "Şifreli veritabanı bütünlük kontrolü başarısız."
            }
        }
        val tables = mutableSetOf<String>()
        database.rawQuery("SELECT name FROM sqlite_master WHERE type='table'", null).use { result ->
            while (result.moveToNext()) tables.add(result.getString(0))
        }
        check(setOf("mem", "tasks", "chat_messages").all(tables::contains)) {
            "Migration sonrası beklenen tablolar bulunamadı."
        }
        if (expected != null) {
            for ((table, count) in expected) {
                database.rawQuery("SELECT COUNT(*) FROM " + table, null).use { rows ->
                    check(rows.moveToFirst() && rows.getLong(0) == count) {
                        "Migration sonrasında kayıt sayıları eşleşmiyor."
                    }
                }
            }
        }
    }

    private fun verifyEncryptedFile(file: File, key: ByteArray, expected: Map<String, Long>? = null) {
        val database = CipherSQLiteDatabase.openDatabase(
            file.absolutePath, key, null, CipherSQLiteDatabase.OPEN_READWRITE, null, null,
        )
        try {
            check(database.version == TARGET_VERSION) { "Şifreli DB sürümü doğrulanamadı." }
            verifyDatabase(database, expected)
        } finally {
            database.close()
        }
    }

    private fun isPlaintextSqlite(file: File): Boolean {
        if (!file.isFile || file.length() < 16) return false
        val header = ByteArray(16)
        FileInputStream(file).use { input ->
            if (input.read(header) != header.size) return false
        }
        return header.contentEquals("SQLite format 3\u0000".toByteArray(Charsets.US_ASCII))
    }

}
