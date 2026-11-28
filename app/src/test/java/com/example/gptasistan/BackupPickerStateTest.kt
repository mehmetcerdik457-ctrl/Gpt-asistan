package com.example.gptasistan

import android.app.Activity
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Parcel
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowDialog

/** Real picker intents and recreated owner gates; never authorize SQLCipher access in the JVM. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class BackupPickerStateTest {
    @Test fun pendingStateContainsOnlyTheValidatedOperationAndConsumesEachResultOnce() {
        for (export in listOf(true, false)) {
            val first = Robolectric.buildActivity(Activity::class.java).setup()
            val replacement = Robolectric.buildActivity(Activity::class.java).setup()
            try {
                var authorizations = 0
                val original = backup(first.get()) {}
                pickDocument(original, export)
                val picker = shadowOf(first.get()).nextStartedActivityForResult
                assertEquals(if (export) Intent.ACTION_CREATE_DOCUMENT else Intent.ACTION_OPEN_DOCUMENT, picker.intent.action)
                assertTrue(picker.intent.hasCategory(Intent.CATEGORY_OPENABLE))
                assertEquals("application/octet-stream", picker.intent.type)
                val state = Bundle().also(original::savePendingState)
                assertEquals(1, state.size())
                assertEquals(picker.requestCode, state.get(state.keySet().single()))

                val restored = backup(replacement.get()) { authorizations++ }
                restored.restorePendingState(parcelCopy(state))
                val returned = Intent().setData(DOCUMENT)
                assertTrue(restored.onActivityResult(picker.requestCode, Activity.RESULT_OK, returned))
                assertEquals(1, authorizations)
                assertTrue(restored.onActivityResult(picker.requestCode, Activity.RESULT_OK, returned))
                assertEquals(1, authorizations)
                val consumed = Bundle(state).also(restored::savePendingState)
                assertTrue(consumed.isEmpty)
            } finally {
                first.pause().stop().destroy()
                replacement.pause().stop().destroy()
            }
        }
    }

    @Test fun recreatedMainActivityRequiresFreshCredentialBeforeOpeningAnyStoreOrPasswordPrompt() {
        for (export in listOf(true, false)) {
            val original = Robolectric.buildActivity(MainActivity::class.java).create().start().resume().visible()
            pickDocument(backups(original.get()), export)
            val picker = shadowOf(original.get()).nextStartedActivityForResult
            val saved = Bundle()
            original.saveInstanceState(saved).pause().stop().destroy()

            val recreated = Robolectric.buildActivity(MainActivity::class.java)
                .create(parcelCopy(saved)).start().resume().visible()
            val activity = recreated.get()
            try {
                shadowOf(activity.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager)
                    .setIsDeviceSecure(true)
                deliver(activity, picker.requestCode, Activity.RESULT_OK, Intent().setData(DOCUMENT))
                val credential = shadowOf(activity).nextStartedActivityForResult
                assertNotNull(credential)
                assertEquals(4701, credential.requestCode)
                assertLockedWithoutStore(activity)
                val afterResult = Bundle()
                recreated.saveInstanceState(afterResult)
                assertFalse(afterResult.containsKey(pendingStateKey()))

                shadowOf(activity).receiveResult(credential.intent, Activity.RESULT_CANCELED, null)
                assertLockedWithoutStore(activity)
                deliver(activity, picker.requestCode, Activity.RESULT_OK, Intent().setData(DOCUMENT))
                assertNull(shadowOf(activity).nextStartedActivityForResult)
                assertLockedWithoutStore(activity)
            } finally { recreated.pause().stop().destroy() }
        }
    }

    @Test fun forgedCanceledMismatchedAndInvalidUriResultsNeverStartAuthorization() {
        data class Returned(val state: Bundle?, val code: Int, val result: Int, val intent: Intent?)
        val pending = pendingState(export = true)
        val expectedCode = pending.getInt(pending.keySet().single())
        val cases = listOf(
            Returned(null, expectedCode, Activity.RESULT_OK, Intent().setData(DOCUMENT)),
            Returned(pending, expectedCode, Activity.RESULT_CANCELED, Intent().setData(DOCUMENT)),
            Returned(pending, expectedCode + 1, Activity.RESULT_OK, Intent().setData(DOCUMENT)),
            Returned(pending, expectedCode, Activity.RESULT_OK, null),
            Returned(pending, expectedCode, Activity.RESULT_OK, Intent().setData(Uri.parse("file:///private/backup"))),
        )
        for (case in cases) {
            val controller = Robolectric.buildActivity(MainActivity::class.java)
                .create(case.state?.let(::parcelCopy)).start().resume().visible()
            val activity = controller.get()
            try {
                shadowOf(activity.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager)
                    .setIsDeviceSecure(true)
                deliver(activity, case.code, case.result, case.intent)
                assertNull(shadowOf(activity).nextStartedActivityForResult)
                assertLockedWithoutStore(activity)
                deliver(activity, expectedCode, Activity.RESULT_OK, Intent().setData(DOCUMENT))
                assertNull(shadowOf(activity).nextStartedActivityForResult)
            } finally { controller.pause().stop().destroy() }
        }
    }

    @Test fun corruptSavedOperationTypesAndUnknownCodesCannotResumeAResult() {
        val state = pendingState(export = true)
        val key = state.keySet().single()
        val code = state.getInt(key)
        val invalid = listOf(
            Bundle().apply { putString(key, code.toString()) },
            Bundle().apply { putLong(key, code.toLong()) },
            Bundle().apply { putInt(key, 4701) },
            Bundle().apply { putInt(key, -1) },
        )
        for (bad in invalid) {
            val controller = Robolectric.buildActivity(Activity::class.java).setup()
            try {
                var authorizations = 0
                val helper = backup(controller.get()) { authorizations++ }
                helper.restorePendingState(parcelCopy(bad))
                assertTrue(helper.onActivityResult(code, Activity.RESULT_OK, Intent().setData(DOCUMENT)))
                assertEquals(0, authorizations)
                assertTrue(Bundle().also(helper::savePendingState).isEmpty)
            } finally { controller.pause().stop().destroy() }
        }
    }

    @Test fun restoredPickerCannotBypassAnInsecureOrBlockedDevice() {
        for (blocked in listOf(false, true)) {
            val pending = pendingState(export = false)
            val code = pending.getInt(pending.keySet().single())
            val controller = Robolectric.buildActivity(MainActivity::class.java)
                .create(parcelCopy(pending)).start().resume().visible()
            val activity = controller.get()
            try {
                shadowOf(activity.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager)
                    .setIsDeviceSecure(blocked)
                if (blocked) field("storageBlocked").setBoolean(activity, true)
                deliver(activity, code, Activity.RESULT_OK, Intent().setData(DOCUMENT))
                assertNull(shadowOf(activity).nextStartedActivityForResult)
                assertLockedWithoutStore(activity)
            } finally { controller.pause().stop().destroy() }
        }
    }

    @Test fun unsolicitedOrDuplicateCredentialSuccessCannotUnlockARecreatedScreen() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).create().start().resume().visible()
        try {
            deliver(controller.get(), 4701, Activity.RESULT_OK, null)
            assertLockedWithoutStore(controller.get())
            deliver(controller.get(), 4701, Activity.RESULT_OK, null)
            assertLockedWithoutStore(controller.get())
        } finally { controller.pause().stop().destroy() }
    }

    @Test fun recreationDuringCredentialScreenFailsClosedWithAnExplicitRestartMessage() {
        val pending = pendingState(export = true)
        val code = pending.getInt(pending.keySet().single())
        val original = Robolectric.buildActivity(MainActivity::class.java)
            .create(parcelCopy(pending)).start().resume().visible()
        shadowOf(original.get().getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager)
            .setIsDeviceSecure(true)
        deliver(original.get(), code, Activity.RESULT_OK, Intent().setData(DOCUMENT))
        assertEquals(4701, shadowOf(original.get()).nextStartedActivityForResult.requestCode)
        val saved = Bundle()
        original.saveInstanceState(saved).pause().stop().destroy()
        assertFalse(saved.containsKey(pending.keySet().single()))

        val recreated = Robolectric.buildActivity(MainActivity::class.java)
            .create(parcelCopy(saved)).start().resume().visible()
        try {
            deliver(recreated.get(), 4701, Activity.RESULT_OK, null)
            assertLockedWithoutStore(recreated.get())
            assertNull(shadowOf(recreated.get()).nextStartedActivityForResult)
            val dialog = ShadowDialog.getLatestDialog()
            assertTrue(dialog.isShowing)
            fun texts(view: View): List<String> = (if (view is TextView) listOf(view.text.toString()) else emptyList()) +
                if (view is ViewGroup) (0 until view.childCount).flatMap { texts(view.getChildAt(it)) } else emptyList()
            assertTrue(texts(dialog.window!!.decorView).joinToString(" ").contains("yeniden başlat"))
        } finally { recreated.pause().stop().destroy() }
    }

    @Test fun draftAndPendingPickerSurviveRepeatedLockedRecreationsWithoutOpeningAStore() {
        val draft = "Gönderilmemiş özel taslak 🧭\nİkinci satır"
        var state = pendingState(export = true).apply { putString("draft", draft) }
        val operationKey = state.keySet().single { it != "draft" }
        val operation = state.getInt(operationKey)
        repeat(3) {
            val controller = Robolectric.buildActivity(MainActivity::class.java)
                .create(parcelCopy(state)).start().resume().visible()
            try {
                assertLockedWithoutStore(controller.get())
                val next = Bundle()
                controller.saveInstanceState(next)
                assertEquals(draft, next.getString("draft"))
                assertEquals(operation, next.getInt(operationKey))
                state = next
            } finally { controller.pause().stop().destroy() }
        }
    }

    @Test fun lockedDraftFallbackUsesTheInputLimitWithoutSplittingASurrogatePair() {
        val state = Bundle().apply { putString("draft", "x".repeat(15999) + "🧭trailing") }
        val controller = Robolectric.buildActivity(MainActivity::class.java)
            .create(parcelCopy(state)).start().resume().visible()
        try {
            val next = Bundle()
            controller.saveInstanceState(next)
            assertEquals("x".repeat(15999), next.getString("draft"))
            assertLockedWithoutStore(controller.get())
        } finally { controller.pause().stop().destroy() }
    }

    private fun backup(activity: Activity, authorize: () -> Unit) = BackupUi(
        activity, store = { null }, authorize = { authorize() },
        showDialog = { builder, _ -> builder.create() }, notice = {}, refresh = {},
    )

    private fun pendingState(export: Boolean): Bundle {
        val controller = Robolectric.buildActivity(Activity::class.java).setup()
        return try {
            val helper = backup(controller.get()) {}
            pickDocument(helper, export)
            // Robolectric shares this queue through its application shadow.
            // Consume this fixture's picker so later authorization checks see
            // only intents launched by the recreated activity under test.
            assertNotNull(shadowOf(controller.get()).nextStartedActivityForResult)
            Bundle().also(helper::savePendingState)
        } finally { controller.pause().stop().destroy() }
    }

    private fun pendingStateKey() = pendingState(export = true).keySet().single()

    private fun backups(activity: MainActivity): BackupUi {
        val delegate = field("backups\$delegate").get(activity) as Lazy<*>
        return delegate.value as BackupUi
    }

    private fun pickDocument(helper: BackupUi, export: Boolean) {
        BackupUi::class.java.getDeclaredMethod("pickDocument", Boolean::class.javaPrimitiveType).apply {
            isAccessible = true
        }.invoke(helper, export)
    }

    private fun deliver(activity: MainActivity, code: Int, result: Int, intent: Intent?) {
        MainActivity::class.java.getDeclaredMethod("onActivityResult", Int::class.javaPrimitiveType,
            Int::class.javaPrimitiveType, Intent::class.java).apply { isAccessible = true }
            .invoke(activity, code, result, intent)
    }

    private fun field(name: String) = MainActivity::class.java.getDeclaredField(name).apply { isAccessible = true }

    private fun assertLockedWithoutStore(activity: MainActivity) {
        assertFalse(field("appUnlocked").getBoolean(activity))
        assertFalse(field("uiReady").getBoolean(activity))
        assertNull(field("store").get(activity))
        fun texts(view: View): List<String> = (if (view is TextView) listOf(view.text.toString()) else emptyList()) +
            if (view is ViewGroup) (0 until view.childCount).flatMap { texts(view.getChildAt(it)) } else emptyList()
        assertTrue(texts(activity.window.decorView).joinToString(" ").contains("Kilidi aç"))
    }

    private fun parcelCopy(state: Bundle): Bundle {
        val parcel = Parcel.obtain()
        return try {
            parcel.writeBundle(state)
            parcel.setDataPosition(0)
            parcel.readBundle(javaClass.classLoader)!!
        } finally { parcel.recycle() }
    }

    private companion object {
        val DOCUMENT: Uri = Uri.parse("content://fixture.documents/document/backup-9173")
    }
}
