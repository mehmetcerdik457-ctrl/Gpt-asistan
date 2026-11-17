package com.example.gptasistan.billing

import android.content.Context
import android.os.Looper
import com.example.gptasistan.OwnerGateway
import com.example.gptasistan.OmegaEnvelope

/** Uses existing enrolled owner/device P-256 signatures; no client assertion grants access. */
internal class OwnerPlayPurchaseTransport(
    context: Context,
    private val base: String,
    private val owner: String
) : AuthenticatedPlayPurchaseTransport {
    private val application = context.applicationContext

    private fun checkScope() {
        check(Looper.myLooper() != Looper.getMainLooper()) { "PLAY_WORKER_REQUIRED" }
        val prefs = application.getSharedPreferences("kral_model", Context.MODE_PRIVATE)
        check(OwnerGateway.validBase(base) && OmegaEnvelope.validOwner(owner) &&
            prefs.getString("endpoint", "").orEmpty().trimEnd('/') == base.trimEnd('/') &&
            prefs.getString("owner_id", "") == owner) { "PLAY_BACKEND_SCOPE_CHANGED" }
    }

    override fun account(): PlayAccountConfiguration {
        checkScope()
        return OwnerGateway.playAccountConfiguration(application, base)
    }

    override fun submit(submission: PlayPurchaseSubmission): Boolean {
        checkScope()
        return OwnerGateway.verifyPlayPurchase(application, base, submission)
    }
}
