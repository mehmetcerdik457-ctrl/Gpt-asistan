package com.example.gptasistan

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SourceIntakePolicyTest {
    @Test fun filenameAloneCannotTurnBinaryIntoApk() {
        val x = SourceIntakePolicy.format(byteArrayOf(1, 2, 3, 4), "unknown.apk")
        assertTrue(x.contains("Bilinmeyen"))
    }

    @Test fun validZipMagicClassifiesOnlyAsCandidate() {
        val x = SourceIntakePolicy.format(byteArrayOf(0x50, 0x4b, 0x03, 0x04), "owner.apk")
        assertTrue(x.contains("aday"))
        assertTrue(x.contains("henüz doğrulanmadı"))
    }

    @Test fun androidBundleNotInstallableClaim() {
        val x = SourceIntakePolicy.format(byteArrayOf(0x50, 0x4b, 0x03, 0x04), "bundle.aab")
        assertTrue(x.contains("AAB adayı"))
    }

    @Test fun ggufHeaderDoesNotClaimModelExecution() {
        val x = SourceIntakePolicy.format("GGUF".toByteArray(), "model.gguf")
        assertTrue(x.contains("çalıştırıcı doğrulanmadı"))
    }

    @Test fun unsafePathPartsNeverEnterProtectedPreview() {
        val name = SourceIntakePolicy.displayName("../owner\nsecret\\file.apk")
        assertFalse(name.contains("\n"))
        assertFalse(name.contains("/"))
        assertFalse(name.contains("\\"))
        assertTrue(name.length <= 120)
    }

    @Test fun boundedStreamingLimits() {
        try {
            SourceIntakePolicy.validateBytes(0)
            throw AssertionError("empty source accepted")
        } catch (_: IllegalArgumentException) { }
        SourceIntakePolicy.validateBytes(SourceIntakePolicy.MAX_BYTES)
        try {
            SourceIntakePolicy.validateBytes(SourceIntakePolicy.MAX_BYTES + 1)
            throw AssertionError("oversize source accepted")
        } catch (_: IllegalArgumentException) { }
    }
}
