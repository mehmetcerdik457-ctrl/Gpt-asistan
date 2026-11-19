package com.example.gptasistan

import net.zetetic.database.sqlcipher.SQLiteDatabase
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

/** Deterministic local primitives. No network or provider calls are made here. */
object KralAndroidCore {
    const val MAX_LEDGER_RESULT_CHARS = 32_000
    // Leave room for a caller's short label while keeping the ledger guard strict.
    internal const val MAX_LOCAL_READ_REPLY_CHARS = 30_000
    internal const val READ_TRUNCATION_NOTICE =
        "\n… [Gösterim kısaltıldı; tüm kayıtlar korunuyor.]"

    /** Bound only the displayed read result; persisted source records stay intact. */
    internal fun localReadReply(lines: List<String>, empty: String, moreRows: Boolean = false): String {
        if (lines.isEmpty()) return empty
        val length = lines.sumOf { it.length.toLong() } + lines.size - 1L
        val shortened = moreRows || length > MAX_LOCAL_READ_REPLY_CHARS
        val budget = MAX_LOCAL_READ_REPLY_CHARS - if (shortened) READ_TRUNCATION_NOTICE.length else 0
        val reply = StringBuilder(minOf(length, MAX_LOCAL_READ_REPLY_CHARS.toLong()).toInt())
        for ((index, line) in lines.withIndex()) {
            if (index > 0) {
                if (reply.length == budget) break
                reply.append('\n')
            }
            val available = budget - reply.length
            if (line.length <= available) {
                reply.append(line)
            } else {
                var end = available
                if (end > 0 && Character.isHighSurrogate(line[end - 1]) &&
                    Character.isLowSurrogate(line[end])) end--
                reply.append(line, 0, end)
                break
            }
        }
        if (shortened) reply.append(READ_TRUNCATION_NOTICE)
        return reply.toString()
    }

    fun sha256Hex(value: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(value)
            .joinToString("") { "%02x".format(it) }

    fun sha256Hex(value: String): String =
        sha256Hex(value.toByteArray(StandardCharsets.UTF_8))

    fun canonicalPayload(operation: String, payload: String): String {
        require(operation.matches(Regex("[A-Za-z0-9._:-]{1,96}")))
        require(payload.length <= 64_000)
        return "$operation\n${payload.length}\n$payload"
    }
}

/**
 * Executes local actions once per operation ID.
 * Ledger insertion and action DB writes are atomic when action uses this same SQLiteDatabase.
 */
class KralCoreOrchestrator(private val store: KralStore) {
    private val lock = Any()

    init {
        store.writableDatabase.execSQL(
            """CREATE TABLE IF NOT EXISTS kral_idempotency(
                operation_id TEXT PRIMARY KEY,
                payload_sha256 TEXT NOT NULL,
                result_text TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )"""
        )
    }

    fun execute(
        operationId: String,
        operation: String,
        payload: String,
        action: (SQLiteDatabase) -> String
    ): String {
        require(operationId.matches(Regex("[A-Za-z0-9._:-]{8,128}")))
        val digest = KralAndroidCore.sha256Hex(
            KralAndroidCore.canonicalPayload(operation, payload)
        )
        synchronized(lock) {
            val db = store.writableDatabase
            db.beginTransaction()
            try {
                db.rawQuery(
                    "SELECT payload_sha256,result_text FROM kral_idempotency WHERE operation_id=?",
                    arrayOf(operationId)
                ).use { cursor ->
                    if (cursor.moveToFirst()) {
                        require(cursor.getString(0) == digest) {
                            "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD"
                        }
                        val saved = cursor.getString(1)
                        db.setTransactionSuccessful()
                        return saved
                    }
                }
                val result = action(db)
                require(result.length <= KralAndroidCore.MAX_LEDGER_RESULT_CHARS)
                db.execSQL(
                    "INSERT INTO kral_idempotency(operation_id,payload_sha256,result_text,created_at) VALUES(?,?,?,?)",
                    arrayOf<Any>(operationId, digest, result, System.currentTimeMillis() / 1000L)
                )
                db.setTransactionSuccessful()
                return result
            } finally {
                db.endTransaction()
            }
        }
    }
}
