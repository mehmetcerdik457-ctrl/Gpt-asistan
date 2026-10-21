package com.example.gptasistan

import android.content.Context
import android.database.sqlite.SQLiteDatabase as PlatformSQLiteDatabase
import net.zetetic.database.sqlcipher.SQLiteDatabase as CipherSQLiteDatabase
import java.io.File
import java.io.FileInputStream

/** One-time plaintext-to-SQLCipher migration with a rollback copy until verification succeeds. */
internal object EncryptedDatabaseMigration {
    private const val LEGACY_NAME = "kral_local.db.plaintext-legacy"
    private const val STAGING_NAME = "kral_local.db.cipher-staging"
    private const val TARGET_VERSION = 3

    fun migrateIfNeeded(context: Context, key: ByteArray) {
        val appContext = context.applicationContext
        System.loadLibrary("sqlcipher")
        val database = appContext.getDatabasePath(KralStore.DATABASE_NAME)
        val legacy = appContext.getDatabasePath(LEGACY_NAME)
        val staging = appContext.getDatabasePath(STAGING_NAME)

        if (database.exists() && !isPlaintextSqlite(database)) {
            appContext.deleteDatabase(LEGACY_NAME)
            appContext.deleteDatabase(STAGING_NAME)
            return
        }

        val source = when {
            isPlaintextSqlite(database) -> database
            isPlaintextSqlite(legacy) -> legacy
            else -> null
        }
        if (source == null) {
            if (database.exists() || legacy.exists()) {
                throw IllegalStateException("Yerel veritabanı biçimi tanınmıyor; özgün dosya korunuyor.")
            }
            appContext.deleteDatabase(STAGING_NAME)
            return
        }
        if (source == database && legacy.exists()) {
            throw IllegalStateException("Önceki migration kopyası bulundu; özgün veriler korunuyor.")
        }

        val oldVersion = readAndRecoverPlaintextVersion(source)
        require(oldVersion in 1..2) { "Desteklenmeyen plaintext veritabanı sürümü: $oldVersion" }
        appContext.deleteDatabase(STAGING_NAME)

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
            verifyDatabase(encrypted)
        } finally {
            encrypted.close()
        }

        val movedOriginal = source == database
        if (movedOriginal && !database.renameTo(legacy)) {
            appContext.deleteDatabase(STAGING_NAME)
            throw IllegalStateException("Özgün veritabanı güvenli migration için taşınamadı; özgün dosya korundu.")
        }
        if (!staging.renameTo(database)) {
            if (movedOriginal) legacy.renameTo(database)
            appContext.deleteDatabase(STAGING_NAME)
            throw IllegalStateException("Şifreli veritabanı devreye alınamadı; geri alma denendi.")
        }

        try {
            verifyEncryptedFile(database, key)
            if (legacy.exists() && !appContext.deleteDatabase(LEGACY_NAME)) {
                throw IllegalStateException("Şifreli DB doğrulandı ancak eski plaintext dosyası silinemedi.")
            }
            deleteSidecars(database)
        } catch (error: Exception) {
            appContext.deleteDatabase(KralStore.DATABASE_NAME)
            if (movedOriginal && legacy.exists()) legacy.renameTo(database)
            throw error
        } finally {
            appContext.deleteDatabase(STAGING_NAME)
        }
    }

    private fun readAndRecoverPlaintextVersion(file: File): Int {
        val database = PlatformSQLiteDatabase.openDatabase(
            file.absolutePath, null, PlatformSQLiteDatabase.OPEN_READWRITE,
        )
        return try {
            database.version
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

    private fun verifyDatabase(database: CipherSQLiteDatabase) {
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
    }

    private fun verifyEncryptedFile(file: File, key: ByteArray) {
        val database = CipherSQLiteDatabase.openDatabase(
            file.absolutePath, key, null, CipherSQLiteDatabase.OPEN_READWRITE, null, null,
        )
        try {
            check(database.version == TARGET_VERSION) { "Şifreli DB sürümü doğrulanamadı." }
            verifyDatabase(database)
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

    private fun deleteSidecars(database: File) {
        listOf("-journal", "-wal", "-shm").forEach { suffix ->
            File(database.absolutePath + suffix).delete()
        }
    }
}
