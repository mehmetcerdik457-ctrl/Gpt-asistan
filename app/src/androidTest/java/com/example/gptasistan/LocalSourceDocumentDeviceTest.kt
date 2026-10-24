package com.example.gptasistan

import android.net.Uri
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Actual Android ContentResolver + content:// pipe checks.
 * Does not unlock a real Owner phone or claim physical SAF picker acceptance.
 */
@RunWith(AndroidJUnit4::class)
class LocalSourceDocumentDeviceTest {
    private val resolver = InstrumentationRegistry.getInstrumentation().context.contentResolver
    private fun uri(name: String) =
        Uri.parse("content://" + FixtureSourceProvider.AUTHORITY + "/" + name)

    @Test fun selectedProviderDocumentIsHashedWithoutNetwork() {
        val report = LocalSourceDocument.inspect(resolver, uri("valid"))
        assertEquals("reference.apk", report.fileName)
        assertEquals(3L, report.bytesRead)
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            report.sha256)
        assertTrue(report.report().contains("doğrulanmış DEĞİLDİR"))
    }

    @Test fun unknownDeclaredSizeReadsBoundedContent() {
        val report = LocalSourceDocument.inspect(resolver, uri("unknown"))
        assertEquals("model.gguf", report.fileName)
        assertEquals(3L, report.bytesRead)
    }

    @Test fun misleadingProviderSizeFailsClosed() {
        assertThrows(IllegalArgumentException::class.java) {
            LocalSourceDocument.inspect(resolver, uri("mismatch"))
        }
    }

    @Test fun secretDisplayNameIsDeniedBeforeHashing() {
        assertThrows(IllegalArgumentException::class.java) {
            LocalSourceDocument.inspect(resolver, uri("secret"))
        }
    }

    @Test fun actualReadCannotExceedConfiguredCap() {
        assertThrows(IllegalArgumentException::class.java) {
            LocalSourceDocument.inspect(resolver, uri("oversize"), maxBytes = 2)
        }
    }

    @Test fun rejectsNonContentUrisWithoutReading() {
        assertThrows(IllegalArgumentException::class.java) {
            LocalSourceDocument.inspect(resolver, Uri.parse("file:///sdcard/reference.apk"))
        }
    }
}
