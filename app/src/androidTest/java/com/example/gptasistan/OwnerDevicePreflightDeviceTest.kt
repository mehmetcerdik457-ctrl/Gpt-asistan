package com.example.gptasistan

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OwnerDevicePreflightDeviceTest {
    @Test fun observationNeverCreatesKeysOrClaimsEnrollment() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val before = OwnerDevicePreflight.readOnlyFacts(ctx)
        val text = OwnerDevicePreflight.readOnlyReport(ctx)
        val after = OwnerDevicePreflight.readOnlyFacts(ctx)
        assertEquals(before.owner, after.owner)
        assertEquals(before.device, after.device)
        assertTrue(after.preview)
        assertTrue(text.contains("GERÇEK OWNER KABULÜ DEĞİLDİR"))
        assertTrue(text.contains("anahtar OLUŞTURMAZ"))
    }
}
