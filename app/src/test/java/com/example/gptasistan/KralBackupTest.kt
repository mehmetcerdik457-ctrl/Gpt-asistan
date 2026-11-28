package com.example.gptasistan

import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.nio.ByteBuffer
import org.junit.Assert.*
import org.junit.Test

/** Crypto/format tests use in-memory records, never a device store or real credential. */
class KralBackupTest {
    private fun fixture() = KralBackup.Snapshot(
        listOf(KralBackup.MemoryRow(41L, "legacy timestamp", "Özel hafıza 🧭\nİkinci satır")),
        listOf(KralBackup.TaskRow(17L, "Görev başlığı", 1)),
        listOf(KralBackup.ChatRow(35L, "2026-11-04T12:34:56Z", "system", "PRIVATE_BACKUP_FIXTURE_8193")),
    )

    @Test fun encryptedRoundtripPreservesEveryLogicalFieldWithoutPlaintextPayload() {
        val password = "only-disposable-fixture-password".toCharArray()
        try {
            val encrypted = KralBackup.seal(fixture(), password)
            assertFalse(String(encrypted, Charsets.ISO_8859_1).contains("PRIVATE_BACKUP_FIXTURE_8193"))
            assertTrue(encrypted.size < KralBackup.MAX_BACKUP_BYTES)
            assertEquals(fixture(), KralBackup.unseal(encrypted, password))
            assertEquals(KralBackup.Summary(1, 1, 1), fixture().summary())
        } finally { password.fill('\u0000') }
    }

    @Test fun everyBackupGetsFreshSaltAndNonce() {
        val password = "only-disposable-fixture-password".toCharArray()
        try {
            val first = KralBackup.seal(fixture(), password)
            val second = KralBackup.seal(fixture(), password)
            assertFalse(first.contentEquals(second))
            assertFalse(first.copyOfRange(20, 36).contentEquals(second.copyOfRange(20, 36)))
            assertFalse(first.copyOfRange(36, 48).contentEquals(second.copyOfRange(36, 48)))
        } finally { password.fill('\u0000') }
    }

    @Test fun wrongPasswordCiphertextTamperingAndMalformedHeadersShareOneFailure() {
        val password = "only-disposable-fixture-password".toCharArray()
        val wrongPassword = "different-disposable-password".toCharArray()
        try {
            val encrypted = KralBackup.seal(fixture(), password)
            val wrong = assertThrows(KralBackup.BackupException::class.java) {
                KralBackup.unseal(encrypted, wrongPassword)
            }
            val modifications = listOf(
                encrypted.copyOf().apply { this[lastIndex] = (this[lastIndex].toInt() xor 1).toByte() },
                encrypted.copyOf().apply { this[0] = 0 },
                encrypted.copyOf().apply { ByteBuffer.wrap(this).putInt(8, 2) },
                encrypted.copyOf().apply { ByteBuffer.wrap(this).putInt(12, 4) },
                encrypted.copyOf().apply { ByteBuffer.wrap(this).putInt(16, 1) },
                encrypted + byteArrayOf(1),
                ByteArray(3),
            )
            modifications.forEach { changed ->
                val error = assertThrows(KralBackup.BackupException::class.java) {
                    KralBackup.unseal(changed, password)
                }
                assertEquals(wrong.message, error.message)
                assertNull(error.cause)
            }
        } finally { password.fill('\u0000'); wrongPassword.fill('\u0000') }
    }

    @Test fun passwordAndEncryptedInputBoundsAreEnforcedBeforeDerivation() {
        listOf(CharArray(11) { 'x' }, CharArray(1025) { 'x' }).forEach { password ->
            try {
                assertThrows(KralBackup.BackupException::class.java) { KralBackup.seal(fixture(), password) }
            } finally { password.fill('\u0000') }
        }
        val password = "only-disposable-fixture-password".toCharArray()
        try {
            assertThrows(KralBackup.BackupException::class.java) {
                KralBackup.unseal(ByteArray(KralBackup.MAX_BACKUP_BYTES + 1), password)
            }
        } finally { password.fill('\u0000') }
    }

    @Test fun formatRejectsTruncatedTrailingAndInvalidUtf8Data() {
        val valid = KralBackup.encode(fixture())
        try {
            assertEquals(fixture(), KralBackup.decode(valid))
            assertThrows(Exception::class.java) { KralBackup.decode(valid.copyOf(valid.size - 1)) }
            assertThrows(Exception::class.java) { KralBackup.decode(valid + byteArrayOf(0)) }
            val malformed = payload {
                writeInt(1); writeLong(1); writeInt(1); writeByte(0xff)
                writeInt(0); writeInt(0); writeInt(0)
            }
            assertThrows(Exception::class.java) { KralBackup.decode(malformed) }
        } finally { valid.fill(0) }
    }

    @Test fun schemaRejectsInvalidCountsIdsRolesAndTaskFlags() {
        val invalidPayloads = listOf(
            payload { writeInt(-1); writeInt(0); writeInt(0) },
            payload { writeInt(Int.MAX_VALUE); writeInt(0); writeInt(0) },
            payload { writeInt(1); writeLong(0); text("ts"); text("note"); writeInt(0); writeInt(0) },
            payload {
                writeInt(2); writeLong(1); text("ts"); text("one")
                writeLong(1); text("ts"); text("duplicate"); writeInt(0); writeInt(0)
            },
            payload { writeInt(0); writeInt(1); writeLong(1); text("task"); writeByte(2); writeInt(0) },
            payload {
                writeInt(0); writeInt(0); writeInt(1); writeLong(1)
                text("ts"); text("tool"); text("unauthorized role")
            },
            payload { writeInt(1); writeLong(1); writeInt(Int.MAX_VALUE); writeInt(0); writeInt(0) },
        )
        invalidPayloads.forEach { assertThrows(Exception::class.java) { KralBackup.decode(it) } }
    }

    @Test fun exportFormatRejectsUnboundedFieldsDuplicateIdsAndInvalidRoles() {
        val fixture = fixture()
        val bad = listOf(
            fixture.copy(memories = listOf(fixture.memories.single(), fixture.memories.single())),
            fixture.copy(tasks = listOf(KralBackup.TaskRow(1, "task", -1))),
            fixture.copy(messages = listOf(KralBackup.ChatRow(1, "ts", "tool", "text"))),
            fixture.copy(memories = listOf(KralBackup.MemoryRow(1, "ts", "x".repeat(1024 * 1024 + 1)))),
            fixture.copy(memories = listOf(KralBackup.MemoryRow(1, "ts", "\ud800"))),
        )
        bad.forEach { assertThrows(Exception::class.java) { KralBackup.encode(it) } }
    }

    private fun payload(block: DataOutputStream.() -> Unit): ByteArray = ByteArrayOutputStream().let {
        DataOutputStream(it).apply(block).flush()
        it.toByteArray()
    }

    private fun DataOutputStream.text(value: String) {
        val bytes = value.toByteArray(Charsets.UTF_8)
        writeInt(bytes.size); write(bytes)
    }
}
