package com.example.gptasistan

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class OwnerBridgeIdentityDeviceTest {
    @Test fun inspectionIsReadOnlyAndNeverAuthorizesAnyAction() {
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        val before = OwnerStatus.inspect(ctx, OwnerStatus.OWNER)
        val report = OwnerStatus.readOnlyReport(ctx)
        val after = OwnerStatus.inspect(ctx, OwnerStatus.OWNER)
        assertEquals(before.verdict, after.verdict)
        assertTrue(report.contains("Owner yetkisi verilmedi"))
        assertTrue(report.contains(OwnerStatus.OWNER_PACKAGE))
        assertTrue(report.contains(OwnerStatus.BRIDGE_PACKAGE))
    }
}
