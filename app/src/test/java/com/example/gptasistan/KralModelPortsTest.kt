package com.example.gptasistan

import android.content.Context
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [30])
class KralModelPortsTest {
    private val context: Context get() = RuntimeEnvironment.getApplication()

    @Before fun resetRegistry() {
        OwnerGateway.clear()
        context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
            .edit().clear().commit()
    }

    @After fun forgetRegistry() {
        OwnerGateway.clear()
    }

    @Test fun rejectsCleartextOrInvalidOwnerEndpoint() {
        assertThrows(IllegalArgumentException::class.java) {
            SignedOwnerModelPort("http://localhost:9000", "owner")
        }
        assertThrows(IllegalArgumentException::class.java) {
            SignedOwnerModelPort("https://owner.example", "")
        }
    }

    @Test fun remotePortDoesNotGenerateWhenRegistryIsUnverified() {
        context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
            .edit().putString("owner_id", "test-owner").commit()
        val port = SignedOwnerModelPort("https://owner.example", "test-owner")
        assertTrue(port.verifiedModels().isEmpty())
        val exception = assertThrows(SecurityException::class.java) {
            port.reply(context, "unknown", "Merhaba")
        }
        assertEquals("MODEL_NOT_VERIFIED", exception.message)
    }

    @Test fun mismatchedOwnerIsDeniedBeforeModelLookup() {
        context.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
            .edit().putString("owner_id", "device-owner").commit()
        val port = SignedOwnerModelPort("https://owner.example", "other-owner")
        val exception = assertThrows(SecurityException::class.java) {
            port.reply(context, "unknown", "Merhaba")
        }
        assertEquals("OWNER_MISMATCH", exception.message)
    }

    @Test fun localRuntimeNeverClaimsAvailableModelsOrGenerates() {
        assertTrue(UnavailableLocalModelPort.verifiedModels().isEmpty())
        val exception = assertThrows(SecurityException::class.java) {
            UnavailableLocalModelPort.reply(context, "local-llm", "Merhaba")
        }
        assertEquals("LOCAL_RUNTIME_NOT_CONFIGURED", exception.message)
    }
}
