package com.example.gptasistan

import android.database.sqlite.SQLiteDatabase
import java.nio.charset.StandardCharsets
import java.security.MessageDigest

/** Deterministic local primitives. No network or provider calls are made here. */
object KralAndroidCore {
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
                require(result.length <= 32_000)
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
