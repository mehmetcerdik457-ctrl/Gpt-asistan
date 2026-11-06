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

    @Test fun longMemoryAndRecallCommandsProduceBoundedRecordedRepliesWithoutChangingNotes() {
        val store = openStore()
        repeat(3) { store.saveMemory(longUnicodeRecord("İstanbul not-$it ")) }
        store.saveMemory("Ankara korunacak kayıt")
        store.addTask("Korunacak görev")
        val originalNotes = store.memoryEntries()
        val originalTasks = tableRows(store, "SELECT id,title,done FROM tasks ORDER BY id")
        val engine = KralCoreOrchestrator(store)

        val listed = recordRead(engine, store, "read-memory-0001", "/liste") { store.memory() }
        val recalled = recordRead(engine, store, "read-recall-0001", "/hatirla İstanbul") {
            store.recall("İSTANBUL")
        }
        for (reply in listOf(listed, recalled)) {
            assertUsefulBoundedReply(reply)
            assertTrue(reply.contains("İstanbul"))
        }
        assertFalse(recalled.contains("Ankara"))
        assertEquals(originalNotes, store.memoryEntries())
        assertEquals(originalTasks, tableRows(store, "SELECT id,title,done FROM tasks ORDER BY id"))
        assertEquals(4, store.history().size)
        assertEquals(listed, engine.execute("read-memory-0001", "local-command", "/liste") {
            throw AssertionError("A recorded read must not run twice")
        })
        assertEquals(4, store.history().size)
        store.close()

        val reopened = openStore()
        assertEquals(originalNotes, reopened.memoryEntries())
        assertEquals(originalTasks, tableRows(reopened, "SELECT id,title,done FROM tasks ORDER BY id"))
        assertEquals(listOf(listed, recalled), reopened.history().filter { it.role == "assistant" }.map { it.text })
    }

    @Test fun longTaskListProducesABoundedLedgerReplyAndPreservesEveryOriginalTitle() {
        val store = openStore()
        repeat(3) { store.addTask(longUnicodeRecord("Görev-$it ")) }
        assertTrue(store.finishTask(1))
        val originalTasks = tableRows(store, "SELECT id,title,done FROM tasks ORDER BY id")
        val engine = KralCoreOrchestrator(store)
        val reply = recordRead(engine, store, "read-tasks-0001", "/gorevler") { store.tasks() }

        assertUsefulBoundedReply(reply)
        assertTrue(reply.contains("[tamam]"))
        assertTrue(reply.contains("[bekliyor]"))
        assertEquals(originalTasks, tableRows(store, "SELECT id,title,done FROM tasks ORDER BY id"))
        assertEquals(reply, store.history().last().text)
        store.close()
        val reopened = openStore()
        assertEquals(originalTasks, tableRows(reopened, "SELECT id,title,done FROM tasks ORDER BY id"))
    }

    @Test fun memoryRecallAndTaskRowLimitsReportOmittedRowsWithoutDeletingThem() {
        val store = openStore()
        repeat(21) { store.saveMemory("note-${(it + 1).toString().padStart(3, '0')}") }
        repeat(31) { store.addTask("task-${(it + 1).toString().padStart(3, '0')}") }
        val originalNotes = store.memoryEntries()
        val originalTasks = tableRows(store, "SELECT id,title,done FROM tasks ORDER BY id")
        val replies = listOf(store.memory(), store.recall("note", limit = 1), store.tasks())
        replies.forEach { assertTrue(it.endsWith(KralAndroidCore.READ_TRUNCATION_NOTICE)) }
        assertFalse(replies[0].contains("note-001"))
        assertTrue(replies[1].contains("note-021"))
        assertFalse(replies[1].contains("note-020"))
        assertFalse(replies[2].contains("task-001"))
        assertEquals(originalNotes, store.memoryEntries())
        assertEquals(originalTasks, tableRows(store, "SELECT id,title,done FROM tasks ORDER BY id"))
    }

    @Test fun arbitraryOversizedActionStillFailsTheUnchangedLedgerGuardAtomically() {
        val store = openStore()
        val engine = KralCoreOrchestrator(store)
        assertThrows(IllegalArgumentException::class.java) {
            engine.execute("oversized-action-0001", "memory.save", "must roll back") { db ->
                db.execSQL("INSERT INTO mem(ts,text) VALUES('now','must roll back')")
                "x".repeat(KralAndroidCore.MAX_LEDGER_RESULT_CHARS + 1)
            }
        }
        assertTrue(store.memoryEntries().isEmpty())
        assertTrue(tableRows(store, "SELECT operation_id FROM kral_idempotency").isEmpty())
    }

    private fun longUnicodeRecord(prefix: String): String {
        val remaining = 11_000 - prefix.length
        return prefix + "🙂".repeat(remaining / 2) + "x".repeat(remaining % 2)
    }

    private fun recordRead(
        engine: KralCoreOrchestrator,
        store: KralStore,
        operationId: String,
        command: String,
        read: () -> String
    ): String = engine.execute(operationId, "local-command", command) {
        val reply = read()
        store.saveMessage("user", "Sen: $command")
        store.saveMessage("assistant", reply)
        reply
    }

    private fun assertUsefulBoundedReply(reply: String) {
        assertTrue(reply.isNotBlank())
        assertTrue(reply.length <= KralAndroidCore.MAX_LOCAL_READ_REPLY_CHARS)
        assertTrue(reply.length <= KralAndroidCore.MAX_LEDGER_RESULT_CHARS)
        assertTrue(reply.endsWith(KralAndroidCore.READ_TRUNCATION_NOTICE))
        var index = 0
        while (index < reply.length) {
            val char = reply[index]
            if (Character.isHighSurrogate(char)) {
                assertTrue(index + 1 < reply.length && Character.isLowSurrogate(reply[index + 1]))
                index += 2
            } else {
                assertFalse(Character.isLowSurrogate(char))
                index++
            }
        }
    }

    private fun tableRows(store: KralStore, query: String): List<List<String?>> {
        val rows = mutableListOf<List<String?>>()
        store.readableDatabase.rawQuery(query, null).use { cursor ->
            while (cursor.moveToNext()) rows.add((0 until cursor.columnCount).map {
                if (cursor.isNull(it)) null else cursor.getString(it)
            })
        }
        return rows
    }
}
