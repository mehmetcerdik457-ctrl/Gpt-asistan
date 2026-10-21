package com.example.gptasistan

import org.junit.Assert.*
import org.junit.Test

class CihatHandoffTest {
    @Test fun packageIsExistingForensicManifestPackage() {
        assertEquals("com.codespaceapps.aichat", CihatHandoff.PACKAGE_NAME)
    }

    @Test fun onlyCurrentTypedDraftMayBeCopied() {
        assertEquals("merhaba", CihatHandoff.copyableDraft("  merhaba  "))
        assertNull(CihatHandoff.copyableDraft("  "))
        assertNull(CihatHandoff.copyableDraft(""))
    }

    @Test fun clipboardSizeIsLimited() {
        assertEquals("x".repeat(2000), CihatHandoff.copyableDraft("x".repeat(2000)))
        assertNull(CihatHandoff.copyableDraft("x".repeat(2001)))
    }

    @Test fun multilineInputIsPlainTextOnly() {
        assertEquals("satır 1\nsatır 2", CihatHandoff.copyableDraft("\nsatır 1\nsatır 2\n"))
    }
}
