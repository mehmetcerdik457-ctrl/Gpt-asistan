package com.example.gptasistan

import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneActionPolicyTest {
    @Test fun explicitUiActionsAreAllowed() {
        PhoneActionType.values().forEach { assertTrue(PhoneActionPolicy.isAllowed(it)) }
    }

    @Test fun sensitiveNamesAreNotRecognizedActions() {
        assertNull(PhoneActionPolicy.parse("EXPORT_CREDENTIALS"))
        assertNull(PhoneActionPolicy.parse("INSTALL_APK"))
        assertNull(PhoneActionPolicy.parse("ROOT_DEVICE"))
    }
}
