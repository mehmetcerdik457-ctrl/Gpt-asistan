package com.example.gptasistan

import java.io.ByteArrayInputStream
import java.io.InputStream
import org.junit.Assert.*
import org.junit.Test

/** Offline-only deterministic proof. No file permissions, device, model or network. */
class LocalSourceEvidenceTest {
    @Test fun hashesKnownBytesWithoutModifyingSource() {
        val bytes = "abc".toByteArray()
        val old = bytes.clone()
        val got = LocalSourceEvidence.scan(ByteArrayInputStream(bytes), "sample.apk", 3)
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", got.sha256)
        assertEquals(3L, got.bytesRead)
        assertArrayEquals(old, bytes)
        assertTrue(got.report().contains("doğrulanmış DEĞİLDİR"))
        assertTrue(got.report().contains("aktarılmadı"))
    }

    @Test fun doesNotAssumeAnyApkIsInstallable() {
        val got = LocalSourceEvidence.scan(ByteArrayInputStream("not an apk".toByteArray()), "old.apk")
        assertEquals("old.apk", got.fileName)
        assertTrue(got.report().contains("APK imzası"))
        assertFalse(got.report().contains("APK İMZASI GEÇERLİ"))
    }

    @Test fun worksWithoutSizeMetadata() {
        val got = LocalSourceEvidence.scan(ByteArrayInputStream(byteArrayOf()), "model.gguf")
        assertEquals(0L, got.bytesRead)
        assertEquals("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855", got.sha256)
    }

    @Test fun rejectsMisleadingProviderSize() {
        for (hint in listOf(-1L, 0L, 2L, LocalSourceEvidence.MAX_BYTES + 1)) {
            assertThrows(IllegalArgumentException::class.java) {
                LocalSourceEvidence.scan(ByteArrayInputStream("abc".toByteArray()), "ref.zip", hint)
            }
        }
    }

    @Test fun enforcesByteLimitEvenWhenProviderDoesNotTellSize() {
        val bytes = ByteArray(48) { it.toByte() }
        assertThrows(IllegalArgumentException::class.java) {
            LocalSourceEvidence.scan(ByteArrayInputStream(bytes), "ref.apk", maxBytes = 40)
        }
        assertEquals(40L, LocalSourceEvidence.scan(
            ByteArrayInputStream(bytes.copyOf(40)), "ref.apk", maxBytes = 40).bytesRead)
    }

    @Test fun rejectsSecretsTraversalAndUnsupportedNames() {
        for (name in listOf("", "../a.apk", "/a.apk", ".env", ".env.dev",
            ".hidden.apk", "id_rsa", "id_ed25519", "credentials.json",
            "service-account.json", "google-services.json",
            "model.p12", "file.jks", "notes.txt", "file.apk\n",
            "folder\\a.apk")) {
            assertFalse(name, LocalSourceEvidence.validDisplayName(name))
            assertThrows(IllegalArgumentException::class.java) {
                LocalSourceEvidence.scan(ByteArrayInputStream(byteArrayOf(1)), name)
            }
        }
    }

    @Test fun supportsKnownArtifactExtensionsCaseInsensitive() {
        for (name in listOf("old.APK", "model.gguf", "folder-copy.ZIP",
            "app.aab", "data.json", "module.kt", "weights.safetensors")) {
            assertTrue(name, LocalSourceEvidence.validDisplayName(name))
        }
    }

    @Test fun rejectsOversizedFilenameAndLimits() {
        assertFalse(LocalSourceEvidence.validDisplayName("x".repeat(161) + ".apk"))
        for (size in listOf(-1L, 0L, LocalSourceEvidence.MAX_BYTES + 1)) {
            assertThrows(IllegalArgumentException::class.java) {
                LocalSourceEvidence.scan(ByteArrayInputStream(byteArrayOf(1)), "a.apk",
                    maxBytes = size)
            }
        }
    }

    @Test fun handlesZeroLengthBulkReadsWithoutLooping() {
        val stalledOnce = object : InputStream() {
            private var index = 0
            private var stall = true
            private val bytes = "abc".toByteArray()
            override fun read(): Int = if (index < bytes.size) bytes[index++].toInt() and 255 else -1
            override fun read(b: ByteArray, off: Int, len: Int): Int {
                if (stall) {
                    stall = false
                    return 0
                }
                return if (index >= bytes.size) -1 else {
                    val n = minOf(len, bytes.size - index)
                    System.arraycopy(bytes, index, b, off, n)
                    index += n
                    n
                }
            }
        }
        assertEquals(3L, LocalSourceEvidence.scan(stalledOnce, "one.apk").bytesRead)
    }
}
