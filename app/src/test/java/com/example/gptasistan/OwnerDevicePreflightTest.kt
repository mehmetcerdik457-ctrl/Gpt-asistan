package com.example.gptasistan

import org.junit.Assert.*
import org.junit.Test

class OwnerDevicePreflightTest {
    @Test fun previewWithoutKeysNeverClaimsEnrollment() {
        val text = OwnerDevicePreflight.report(OwnerDevicePreflight.Facts(
            false, OwnerDevicePreflight.KeyState.MISSING,
            OwnerDevicePreflight.KeyState.MISSING, true))
        assertTrue(text.contains("Güvenli ekran kilidi yok"))
        assertTrue(text.contains("otomatik anahtar üretilmedi"))
        assertTrue(text.contains("ÖNİZLEME"))
        assertTrue(text.contains("GERÇEK OWNER KABULÜ DEĞİLDİR"))
    }

    @Test fun evenTwoPresentAuthRequiredKeysAreNotOwnerApproval() {
        val text = OwnerDevicePreflight.report(OwnerDevicePreflight.Facts(
            true, OwnerDevicePreflight.KeyState.AUTH_REQUIRED_P256,
            OwnerDevicePreflight.KeyState.AUTH_REQUIRED_P256, false))
        assertTrue(text.contains("Mevcut P-256"))
        assertTrue(text.contains("GERÇEK OWNER KABULÜ DEĞİLDİR"))
    }

    @Test fun unknownKeystoreStateNeverCountsAsSuccess() {
        val text = OwnerDevicePreflight.report(OwnerDevicePreflight.Facts(
            true, OwnerDevicePreflight.KeyState.UNKNOWN,
            OwnerDevicePreflight.KeyState.MISSING, true))
        assertTrue(text.contains("doğrulanamadı"))
        assertTrue(text.contains("bilgi GÖNDERMEZ"))
    }
}
