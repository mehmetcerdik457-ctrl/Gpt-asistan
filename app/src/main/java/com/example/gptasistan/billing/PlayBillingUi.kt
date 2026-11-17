package com.example.gptasistan.billing

import android.app.Activity
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import java.util.concurrent.Executors

internal data class PlayUiScope(val base: String, val owner: String)

/** Owner-protected purchase UI; no product, price, host or account identifier is fabricated. */
internal class PlayBillingUi(
    private val activity: Activity,
    private val scope: PlayUiScope,
    private val currentScope: () -> PlayUiScope?,
    private val showProtected: (AlertDialog.Builder, () -> Unit) -> AlertDialog,
    private val checkoutAccepted: () -> Unit = {}
) {
    private var opened = false
    private var dialog: AlertDialog? = null
    private var flow: PlayBillingFlow? = null
    private val worker = Executors.newSingleThreadExecutor { runnable ->
        Thread(runnable, "orba-play-verification").apply { isDaemon = true }
    }

    private fun authorized() = opened && !activity.isFinishing && !activity.isDestroyed &&
        currentScope() == scope

    fun show() {
        if (opened || currentScope() != scope) return
        opened = true
        val fields = LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 16, 24, 16)
        }
        val status = TextView(activity)
        fields.addView(status)
        fields.addView(TextView(activity).apply {
            text = "Fiyatlar Google Play'den alınır. Ödeme sonucu sunucuda yeniden doğrulanır."
            setPadding(0, 12, 0, 12)
        })
        val offers = LinearLayout(activity).apply { orientation = LinearLayout.VERTICAL }
        fields.addView(offers)
        val refresh = Button(activity).apply { text = "Satın almaları yenile" }
        fields.addView(refresh)
        val scroll = ScrollView(activity).apply {
            addView(fields, ViewGroup.LayoutParams(-1, -2))
        }
        dialog = showProtected(AlertDialog.Builder(activity).setTitle("Google Play aboneliği")
            .setView(scroll).setNegativeButton("Kapat", null), { close() })

        val connector = PlayBillingConnector(activity,
            onPurchased = { purchase -> activity.runOnUiThread { flow?.purchased(purchase) } },
            onFailure = { activity.runOnUiThread { flow?.failed() } },
            onPending = { activity.runOnUiThread { flow?.pending() } },
            onCanceled = { activity.runOnUiThread { flow?.canceled() } })
        val port = object : PlayBillingPort {
            override fun connect(onReady: (Int) -> Unit) = connector.connect(onReady)
            override fun offers(product: String, onResult: (Int, List<PlaySubscriptionOffer>) -> Unit) =
                connector.querySubscriptionOffers(product, onResult)
            override fun restore(onComplete: (Int, Int) -> Unit) = connector.restoreKnownPurchases(onComplete)
            override fun launch(checkout: PlaySubscriptionCheckout, onResult: (Int) -> Unit) =
                connector.launchSelectedSubscription(activity, checkout, ::authorized) { code ->
                    if (code == 0) checkoutAccepted()
                    onResult(code)
                }
            override fun close() = connector.close()
        }
        flow = PlayBillingFlow(activity.packageName,
            OwnerPlayPurchaseTransport(activity, scope.base, scope.owner), port, worker,
            dispatch = { action -> activity.runOnUiThread { action() } },
            authorized = ::authorized,
            render = { state ->
                status.text = message(state.status)
                refresh.isEnabled = !state.busy
                offers.removeAllViews()
                for (offer in state.offers) {
                    offers.addView(Button(activity).apply {
                        text = "${offer.displayName}\n${offer.priceDescription()}\nSatın al"
                        isAllCaps = false
                        isEnabled = !state.busy
                        setOnClickListener {
                            if (!authorized()) return@setOnClickListener
                            showProtected(AlertDialog.Builder(activity).setTitle(offer.displayName)
                                .setMessage("${offer.priceDescription()}\n\nDevam edince Google Play ödeme ekranı açılır.")
                                .setPositiveButton("Google Play'de satın al") { _, _ ->
                                    if (authorized()) flow?.buy(offer)
                                }.setNegativeButton("Vazgeç", null), {})
                        }
                    })
                }
            })
        refresh.setOnClickListener { if (authorized()) flow?.refresh() }
        flow?.start()
    }

    fun close() {
        if (!opened) return
        opened = false
        flow?.close()
        flow = null
        worker.shutdownNow()
        dialog?.dismiss()
        dialog = null
    }

    private fun message(status: PlayBillingStatus): String = when (status) {
        PlayBillingStatus.LOADING -> "Abonelik seçenekleri alınıyor…"
        PlayBillingStatus.READY -> "Bir Google Play teklifini seçebilirsin."
        PlayBillingStatus.NO_OFFERS -> "Şu anda uygun bir abonelik teklifi bulunamadı."
        PlayBillingStatus.RESTORING -> "Mevcut satın almalar kontrol ediliyor…"
        PlayBillingStatus.NO_PURCHASES -> "Mevcut satın alma bulunamadı."
        PlayBillingStatus.VERIFYING -> "Satın alma sunucuda doğrulanıyor…"
        PlayBillingStatus.VERIFIED -> "Abonelik sunucuda doğrulandı. Durumu yeniden kontrol etmek için yenileyebilirsin."
        PlayBillingStatus.DENIED -> "Sunucu bu satın alma için etkin abonelik doğrulamadı."
        PlayBillingStatus.PENDING -> "Google Play'de ödeme bekleniyor. Tamamlandıktan sonra satın almaları yenile."
        PlayBillingStatus.CANCELED -> "Satın alma iptal edildi. Yeni bir işlem başlatılmadı."
        PlayBillingStatus.OPENING_PLAY -> "Google Play ödeme ekranı hazırlanıyor…"
        PlayBillingStatus.PLAY_OPENED -> "Google Play işlemini tamamla. Uygulamaya döndüğünde satın almaları yenile."
        PlayBillingStatus.UNAVAILABLE -> "Abonelik bilgileri doğrulanamadı. Sunucu bağlantısını kontrol et. Kimliğini yeniden doğrulamak için kapatıp Abonelik'i tekrar aç."
    }
}
