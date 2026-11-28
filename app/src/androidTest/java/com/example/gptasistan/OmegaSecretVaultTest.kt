package com.example.gptasistan

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.*
import org.junit.Test

class OmegaSecretVaultTest {
    @Test fun secretRoundTripsThroughKeystoreCiphertext() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        OmegaSecretVault.delete(context, "test_secret")
        val secret = "local-test-secret-value-123456789"
        OmegaSecretVault.save(context, "test_secret", secret)
        assertEquals(secret, OmegaSecretVault.read(context, "test_secret"))
        val stored = context.getSharedPreferences("omega_secret_vault", Context.MODE_PRIVATE)
            .getString("test_secret", null)
        assertNotNull(stored)
        assertFalse(stored!!.contains(secret))
        OmegaSecretVault.delete(context, "test_secret")
    }
}
