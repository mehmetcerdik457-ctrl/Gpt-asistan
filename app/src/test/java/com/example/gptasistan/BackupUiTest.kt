package com.example.gptasistan

import android.app.Activity
import android.content.Intent
import android.net.Uri
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class BackupUiTest {
    @Test fun unsolicitedDocumentResultsCannotStartAnImportOrExport() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).create().start().resume()
        var authentications = 0
        var dialogs = 0
        val backup = BackupUi(controller.get(), store = { null },
            authorize = { authentications++ },
            showDialog = { _, _ -> dialogs++; error("No dialog may be opened") },
            notice = { error("No file may be processed") }, refresh = { error("No store may change") })
        try {
            val forged = Intent().setData(Uri.parse("content://untrusted.example/private-backup"))
            assertTrue(backup.onActivityResult(4703, Activity.RESULT_OK, forged))
            assertTrue(backup.onActivityResult(4704, Activity.RESULT_OK, forged))
            assertFalse(backup.onActivityResult(4701, Activity.RESULT_OK, forged))
            backup.showMenu()
            assertEquals(0, authentications)
            assertEquals(0, dialogs)
        } finally { controller.pause().stop().destroy() }
    }
}
