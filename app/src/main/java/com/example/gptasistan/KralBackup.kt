package com.example.gptasistan

import android.content.ContentValues
import android.database.Cursor
import net.zetetic.database.sqlcipher.SQLiteDatabase
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

/**
 * Portable encrypted logical backup of mem/tasks/chat. Database keys never leave
 * KralStore; plaintext exists only in bounded process memory, never a temp file.
 * Restoring deliberately cannot merge with or replace an existing local store.
 */
object KralBackup {
    const val MAX_BACKUP_BYTES = 16 * 1024 * 1024
    private const val FORMAT_VERSION = 1
    private const val STORE_SCHEMA_VERSION = 3
    private const val ITERATIONS = 310_000
    private const val SALT_BYTES = 16
    private const val NONCE_BYTES = 12
    private const val TAG_BYTES = 16
    private const val HEADER_BYTES = 8 + 4 + 4 + 4 + SALT_BYTES + NONCE_BYTES + 4
    private const val MAX_PLAIN_BYTES = MAX_BACKUP_BYTES - HEADER_BYTES - TAG_BYTES
    private const val MAX_FIELD_BYTES = 1024 * 1024
    private const val MAX_TABLE_ROWS = 10_000
    private const val MAX_TOTAL_ROWS = 20_000
    private val MAGIC = "KRALBAK1".toByteArray(Charsets.US_ASCII)
    private const val UNREADABLE = "Yedek açılamadı. Parola veya dosya geçersiz."
    private const val NONEMPTY = "Geri yükleme yalnızca boş yerel depoya yapılabilir."

    class BackupException(message: String) : Exception(message)

    data class Summary(val memories: Int, val tasks: Int, val messages: Int) {
        override fun toString() = "Hafıza: $memories, görev: $tasks, mesaj: $messages"
    }

    internal data class MemoryRow(val id: Long, val ts: String, val text: String)
    internal data class TaskRow(val id: Long, val title: String, val done: Int)
    internal data class ChatRow(val id: Long, val ts: String, val role: String, val text: String)
    internal data class Snapshot(
        val memories: List<MemoryRow>, val tasks: List<TaskRow>, val messages: List<ChatRow>,
    ) {
        fun summary() = Summary(memories.size, tasks.size, messages.size)
    }

    /** Call off the UI thread. The caller owns and should clear its password array. */
    fun export(store: KralStore, password: CharArray): ByteArray {
        checkPassword(password)
        try {
            val db = store.readableDatabase
            val snapshot: Snapshot
            db.beginTransaction()
            try {
                checkSchema(db)
                preflight(db)
                snapshot = readSnapshot(db)
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
            return seal(snapshot, password)
        } catch (error: BackupException) {
            throw error
        } catch (_: Exception) {
            throw BackupException("Yerel kayıtlar güvenli biçimde yedeklenemedi.")
        }
    }

    /** Decrypt/validate before opening the target, then insert everything atomically. */
    fun restore(store: KralStore, encrypted: ByteArray, password: CharArray): Summary {
        checkPassword(password)
        val snapshot = unseal(encrypted, password)
        try {
            val db = store.writableDatabase
            db.beginTransaction()
            try {
                checkSchema(db)
                requireEmpty(db)
                snapshot.memories.forEach { row ->
                    db.insertOrThrow("mem", null, ContentValues().apply {
                        put("id", row.id); put("ts", row.ts); put("text", row.text)
                    })
                }
                snapshot.tasks.forEach { row ->
                    db.insertOrThrow("tasks", null, ContentValues().apply {
                        put("id", row.id); put("title", row.title); put("done", row.done)
                    })
                }
                snapshot.messages.forEach { row ->
                    db.insertOrThrow("chat_messages", null, ContentValues().apply {
                        put("id", row.id); put("ts", row.ts); put("role", row.role); put("text", row.text)
                    })
                }
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
            return snapshot.summary()
        } catch (error: BackupException) {
            throw error
        } catch (_: Exception) {
            throw BackupException("Yedek geri yüklenemedi; mevcut kayıtlar değiştirilmedi.")
        }
    }

    private fun checkPassword(password: CharArray) {
        if (password.size !in 12..1024) {
            throw BackupException("Yedek parolası 12–1024 karakter olmalı.")
        }
    }

    private fun checkSchema(db: SQLiteDatabase) {
        check(db.version == STORE_SCHEMA_VERSION)
        val columns = mapOf(
            "mem" to listOf("id:INTEGER:0:1", "ts:TEXT:1:0", "text:TEXT:1:0"),
            "tasks" to listOf("id:INTEGER:0:1", "title:TEXT:1:0", "done:INTEGER:1:0"),
            "chat_messages" to listOf("id:INTEGER:0:1", "ts:TEXT:1:0", "role:TEXT:1:0", "text:TEXT:1:0"),
        )
        columns.forEach { (table, expected) ->
            val actual = mutableListOf<String>()
            db.rawQuery("PRAGMA table_info($table)", null).use { rows ->
                while (rows.moveToNext()) actual.add(
                    "${rows.getString(1)}:${rows.getString(2)}:${rows.getInt(3)}:${rows.getInt(5)}",
                )
            }
            check(actual == expected)
        }
    }

    /** Bound total bytes and row counts inside the snapshot transaction before row allocation. */
    private fun preflight(db: SQLiteDatabase) {
        var totalRows = 0L
        var totalBytes = 0L
        mapOf("mem" to listOf("ts", "text"), "tasks" to listOf("title"),
            "chat_messages" to listOf("ts", "role", "text")).forEach { (table, fields) ->
            val lengths = fields.map { "length(CAST($it AS BLOB))" }
            val query = "SELECT COUNT(*),COALESCE(SUM(${lengths.joinToString("+")}),0)," +
                lengths.joinToString(",") { "COALESCE(MAX($it),0)" } + " FROM $table"
            db.rawQuery(query, null).use { rows ->
                check(rows.moveToFirst())
                val count = rows.getLong(0)
                val bytes = rows.getLong(1)
                check(count in 0..MAX_TABLE_ROWS.toLong() && bytes in 0..MAX_PLAIN_BYTES.toLong())
                totalRows += count
                totalBytes += bytes + count * 32L
                check(totalRows <= MAX_TOTAL_ROWS && totalBytes <= MAX_PLAIN_BYTES)
                fields.indices.forEach { check(rows.getLong(it + 2) in 0..MAX_FIELD_BYTES.toLong()) }
            }
        }
    }

    private fun readSnapshot(db: SQLiteDatabase): Snapshot {
        val memories = mutableListOf<MemoryRow>()
        val tasks = mutableListOf<TaskRow>()
        val messages = mutableListOf<ChatRow>()
        val budget = TextBudget()
        db.rawQuery("SELECT id,ts,text FROM mem ORDER BY id", null).use { rows ->
            while (rows.moveToNext()) memories.add(MemoryRow(
                integer(rows, 0), text(rows, 1, budget), text(rows, 2, budget),
            ))
        }
        db.rawQuery("SELECT id,title,done FROM tasks ORDER BY id", null).use { rows ->
            while (rows.moveToNext()) {
                val id = integer(rows, 0)
                val title = text(rows, 1, budget)
                val done = integer(rows, 2)
                check(done in 0L..1L)
                tasks.add(TaskRow(id, title, done.toInt()))
            }
        }
        db.rawQuery("SELECT id,ts,role,text FROM chat_messages ORDER BY id", null).use { rows ->
            while (rows.moveToNext()) messages.add(ChatRow(
                integer(rows, 0), text(rows, 1, budget), text(rows, 2, budget), text(rows, 3, budget),
            ))
        }
        return Snapshot(memories, tasks, messages)
    }

    private fun integer(rows: Cursor, column: Int): Long {
        check(rows.getType(column) == Cursor.FIELD_TYPE_INTEGER)
        return rows.getLong(column)
    }

    private fun text(rows: Cursor, column: Int, budget: TextBudget): String {
        check(rows.getType(column) == Cursor.FIELD_TYPE_STRING)
        return rows.getString(column).also { budget.add(it).fill(0) }
    }

    private fun requireEmpty(db: SQLiteDatabase) {
        val tables = mutableListOf<String>()
        db.rawQuery("SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'sqlite_*'", null).use {
            while (it.moveToNext()) tables.add(it.getString(0))
        }
        tables.forEach { table ->
            // Android's platform helper may have left this locale row during a
            // previous plaintext migration. It is not user data and is never
            // restored/replaced. Permit only its exact, bounded system shape.
            if (table == "android_metadata") {
                val columns = mutableListOf<String>()
                db.rawQuery("PRAGMA table_info(android_metadata)", null).use { rows ->
                    while (rows.moveToNext()) columns.add(
                        "${rows.getString(1)}:${rows.getString(2)}:${rows.getInt(3)}:${rows.getInt(5)}",
                    )
                }
                check(columns == listOf("locale:TEXT:0:0"))
                db.rawQuery("SELECT typeof(locale),length(CAST(locale AS BLOB)) FROM android_metadata LIMIT 2", null).use { rows ->
                    if (rows.moveToFirst()) {
                        check(rows.getString(0) == "text" && rows.getLong(1) in 0L..128L)
                        check(!rows.moveToNext())
                    }
                }
                return@forEach
            }
            val quoted = "\"" + table.replace("\"", "\"\"") + "\""
            db.rawQuery("SELECT 1 FROM $quoted LIMIT 1", null).use { rows ->
                if (rows.moveToFirst()) throw BackupException(NONEMPTY)
            }
        }
    }

    private class TextBudget {
        private var used = 0L
        fun add(value: String): ByteArray {
            val encoded = encodeText(value)
            if (encoded.size > MAX_FIELD_BYTES || used + encoded.size > MAX_PLAIN_BYTES) {
                encoded.fill(0)
                error("BACKUP_TEXT_LIMIT")
            }
            used += encoded.size
            return encoded
        }
    }

    private fun encodeText(value: String): ByteArray {
        check(value.length <= MAX_FIELD_BYTES)
        val encoded = Charsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value))
        return ByteArray(encoded.remaining()).also { encoded.get(it) }
    }

    private class BoundedOutput : ByteArrayOutputStream() {
        override fun write(value: Int) {
            check(count < MAX_PLAIN_BYTES)
            super.write(value)
        }
        override fun write(value: ByteArray, offset: Int, length: Int) {
            check(length >= 0 && count.toLong() + length <= MAX_PLAIN_BYTES)
            super.write(value, offset, length)
        }
        fun clear() { buf.fill(0); reset() }
    }

    internal fun encode(snapshot: Snapshot): ByteArray {
        check(snapshot.memories.size <= MAX_TABLE_ROWS && snapshot.tasks.size <= MAX_TABLE_ROWS &&
            snapshot.messages.size <= MAX_TABLE_ROWS)
        check(snapshot.memories.size + snapshot.tasks.size + snapshot.messages.size <= MAX_TOTAL_ROWS)
        val output = BoundedOutput()
        val data = DataOutputStream(output)
        val budget = TextBudget()
        fun writeText(value: String) {
            val bytes = budget.add(value)
            try { data.writeInt(bytes.size); data.write(bytes) } finally { bytes.fill(0) }
        }
        fun checkId(id: Long, previous: Long) { check(id > previous && id > 0) }
        try {
            data.writeInt(snapshot.memories.size)
            var previous = 0L
            snapshot.memories.forEach {
                checkId(it.id, previous); previous = it.id
                data.writeLong(it.id); writeText(it.ts); writeText(it.text)
            }
            data.writeInt(snapshot.tasks.size)
            previous = 0L
            snapshot.tasks.forEach {
                checkId(it.id, previous); previous = it.id; check(it.done in 0..1)
                data.writeLong(it.id); writeText(it.title); data.writeByte(it.done)
            }
            data.writeInt(snapshot.messages.size)
            previous = 0L
            snapshot.messages.forEach {
                checkId(it.id, previous); previous = it.id
                check(it.role in setOf("user", "assistant", "system"))
                data.writeLong(it.id); writeText(it.ts); writeText(it.role); writeText(it.text)
            }
            data.flush()
            return output.toByteArray()
        } finally { output.clear() }
    }

    internal fun decode(plain: ByteArray): Snapshot {
        check(plain.size in 12..MAX_PLAIN_BYTES)
        val data = DataInputStream(ByteArrayInputStream(plain))
        var totalRows = 0
        var remainingText = MAX_PLAIN_BYTES
        fun count(): Int = data.readInt().also {
            check(it in 0..MAX_TABLE_ROWS)
            totalRows += it; check(totalRows <= MAX_TOTAL_ROWS)
            // Every row contains an id plus at least one length and one flag/length.
            check(it.toLong() * 12 <= data.available())
        }
        fun readText(): String {
            val size = data.readInt()
            check(size in 0..MAX_FIELD_BYTES && size <= data.available() && size <= remainingText)
            remainingText -= size
            val bytes = ByteArray(size)
            try {
                data.readFully(bytes)
                return Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
            } finally { bytes.fill(0) }
        }
        fun readId(previous: Long): Long = data.readLong().also { check(it > 0 && it > previous) }
        var previous = 0L
        val memories = List(count()) {
            val id = readId(previous); previous = id
            MemoryRow(id, readText(), readText())
        }
        previous = 0L
        val tasks = List(count()) {
            val id = readId(previous); previous = id
            val title = readText()
            val done = data.readUnsignedByte(); check(done in 0..1)
            TaskRow(id, title, done)
        }
        previous = 0L
        val messages = List(count()) {
            val id = readId(previous); previous = id
            val ts = readText()
            val role = readText(); check(role in setOf("user", "assistant", "system"))
            ChatRow(id, ts, role, readText())
        }
        check(data.available() == 0)
        return Snapshot(memories, tasks, messages)
    }

    internal fun seal(snapshot: Snapshot, password: CharArray): ByteArray {
        checkPassword(password)
        val plain = encode(snapshot)
        val salt = ByteArray(SALT_BYTES).also { SecureRandom().nextBytes(it) }
        val nonce = ByteArray(NONCE_BYTES).also { SecureRandom().nextBytes(it) }
        val header = ByteArrayOutputStream(HEADER_BYTES).also { bytes ->
            DataOutputStream(bytes).apply {
                write(MAGIC); writeInt(FORMAT_VERSION); writeInt(STORE_SCHEMA_VERSION); writeInt(ITERATIONS)
                write(salt); write(nonce); writeInt(plain.size + TAG_BYTES)
            }
        }.toByteArray()
        try {
            return crypt(Cipher.ENCRYPT_MODE, plain, password, salt, nonce, header).let { header + it }
        } finally { plain.fill(0) }
    }

    internal fun unseal(encrypted: ByteArray, password: CharArray): Snapshot {
        checkPassword(password)
        try {
            check(encrypted.size in (HEADER_BYTES + TAG_BYTES + 12)..MAX_BACKUP_BYTES)
            val input = DataInputStream(ByteArrayInputStream(encrypted))
            val magic = ByteArray(MAGIC.size).also { input.readFully(it) }
            check(magic.contentEquals(MAGIC))
            check(input.readInt() == FORMAT_VERSION && input.readInt() == STORE_SCHEMA_VERSION &&
                input.readInt() == ITERATIONS)
            val salt = ByteArray(SALT_BYTES).also { input.readFully(it) }
            val nonce = ByteArray(NONCE_BYTES).also { input.readFully(it) }
            val size = input.readInt()
            check(size == input.available())
            val plain = crypt(Cipher.DECRYPT_MODE, encrypted.copyOfRange(HEADER_BYTES, encrypted.size),
                password, salt, nonce, encrypted.copyOfRange(0, HEADER_BYTES))
            try { return decode(plain) } finally { plain.fill(0) }
        } catch (_: Exception) {
            throw BackupException(UNREADABLE)
        }
    }

    private fun crypt(mode: Int, input: ByteArray, password: CharArray, salt: ByteArray,
                      nonce: ByteArray, header: ByteArray): ByteArray {
        val spec = PBEKeySpec(password, salt, ITERATIONS, 256)
        val key = try { SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded }
        finally { spec.clearPassword() }
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(mode, SecretKeySpec(key, "AES"), GCMParameterSpec(TAG_BYTES * 8, nonce))
            cipher.updateAAD(header)
            return cipher.doFinal(input)
        } finally { key.fill(0) }
    }
}
