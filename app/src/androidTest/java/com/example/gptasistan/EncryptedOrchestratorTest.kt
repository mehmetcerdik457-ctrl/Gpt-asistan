package com.example.gptasistan

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Verify atomic idempotency uses the production SQLCipher database on Android. */
@RunWith(AndroidJUnit4::class)
class EncryptedOrchestratorTest {
    private lateinit var context: Context
    private val stores = mutableListOf<KralStore>()
    private var safe = false

    @Before fun before() {
        context = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext
        InstrumentationSafety.requireDisposableEmulator(context)
        safe = true
        clearFixture()
    }

    @After fun after() {
        stores.forEach { it.close() }
        if (safe) clearFixture()
    }

    private fun clearFixture() {
        for (name in listOf("kral_local.db", "kral_local.db.plaintext-legacy", "kral_local.db.cipher-staging")) {
            context.deleteDatabase(name)
        }
    }

    private fun openStore(): KralStore =
        KralStore(context, TestDatabaseKeyProvider).also { stores.add(it) }

    @Test fun repeatedCommandReturnsPreviousResultEvenAfterReopen() {
        val first = openStore()
        val orchestrator = KralCoreOrchestrator(first)
        val id = "test-0001"
        val original = orchestrator.execute(id, "memory.save", "güvenli") { db ->
            db.execSQL("INSERT INTO mem(ts,text) VALUES('now','güvenli')")
            "ilk sonuç"
        }
        assertEquals("ilk sonuç", original)
        first.close()

        val second = openStore()
        var executedAgain = false
        val replay = KralCoreOrchestrator(second).execute(id, "memory.save", "güvenli") {
            executedAgain = true
            "bu dönmemeli"
        }
        assertFalse(executedAgain)
        assertEquals(original, replay)
        assertTrue(second.memory().contains("güvenli"))
        assertThrows(IllegalArgumentException::class.java) {
            KralCoreOrchestrator(second).execute(id, "memory.save", "değişti") { "bypass" }
        }
        second.readableDatabase.rawQuery("SELECT COUNT(*) FROM mem", null).use {
            assertTrue(it.moveToFirst())
            assertEquals(1L, it.getLong(0))
        }
    }

    @Test fun actionFailureRollsBackBothMemoryAndIdempotency() {
        val store = openStore()
        val engine = KralCoreOrchestrator(store)
        assertThrows(IllegalStateException::class.java) {
            engine.execute("test-0002", "memory.save", "bozuk") { db ->
                db.execSQL("INSERT INTO mem(ts,text) VALUES('now','rollback')")
                throw IllegalStateException("fixture failure")
            }
        }
        store.readableDatabase.rawQuery("SELECT COUNT(*) FROM mem", null).use {
            assertTrue(it.moveToFirst())
            assertEquals(0L, it.getLong(0))
        }
        store.readableDatabase.rawQuery("SELECT COUNT(*) FROM kral_idempotency", null).use {
            assertTrue(it.moveToFirst())
            assertEquals(0L, it.getLong(0))
        }
    }
}
