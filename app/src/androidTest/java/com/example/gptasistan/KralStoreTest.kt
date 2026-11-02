package com.example.gptasistan

import android.content.Context
import java.io.File
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Tests the production SQLCipher store and plaintext migration on an Android runtime. */
@RunWith(AndroidJUnit4::class)
class KralStoreTest {
    private lateinit var context: Context
    private val openedStores = mutableListOf<KralStore>()

    @Before
    fun setUp() {
        context = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext
        deleteTestDatabases()
    }

    @After
    fun tearDown() {
        openedStores.forEach { it.close() }
        deleteTestDatabases()
    }

    @Test
    fun userAndAssistantMessagesSurviveClosingAndReopeningInConversationOrder() {
        val original = openStore()
        original.saveMessage("user", "Adım Mehmet. Türkçe konuşalım.")
        original.saveMessage("assistant", "Merhaba Mehmet, seni hatırlayacağım.")
        original.saveMessage("user", "Sonraki mesajım da korunmalı.")
        original.close()

        val reopened = openStore()

        assertEquals(
            listOf(
                "user" to "Adım Mehmet. Türkçe konuşalım.",
                "assistant" to "Merhaba Mehmet, seni hatırlayacağım.",
                "user" to "Sonraki mesajım da korunmalı.",
            ),
            reopened.history().map { it.role to it.text },
        )
    }

    @Test
    fun upgradingRealVersionOneDatabasePreservesMemoryAndTasksAndAllowsChat() {
        // This is the pre-existing v1 plaintext schema, not a substitute for the v2 helper.
        val legacy = context.openOrCreateDatabase(DATABASE_NAME, Context.MODE_PRIVATE, null)
        try {
            legacy.execSQL("CREATE TABLE mem(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, text TEXT NOT NULL)")
            legacy.execSQL("CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)")
            legacy.execSQL(
                "INSERT INTO mem(id,ts,text) VALUES(?,?,?)",
                arrayOf<Any>(41L, "2026-10-19T09:30:00Z", "Eski kişisel hafızam"),
            )
            legacy.execSQL(
                "INSERT INTO tasks(id,title,done) VALUES(?,?,?)",
                arrayOf<Any>(17L, "Eski bekleyen görev", 0),
            )
            legacy.execSQL(
                "INSERT INTO tasks(id,title,done) VALUES(?,?,?)",
                arrayOf<Any>(23L, "Eski tamamlanan görev", 1),
            )
            legacy.version = 1
        } finally {
            legacy.close()
        }

        val upgraded = openStore()
        assertTrue(upgraded.history().isEmpty())
        assertEquals(KralStore.DATABASE_VERSION, upgraded.readableDatabase.version)
        // The original pre-migration data is deliberately retained for owner recovery.
        // This plaintext copy MUST be handled by an explicit follow-up cleanup policy.
        val preserved = context.getDatabasePath("$DATABASE_NAME.plaintext-legacy")
        assertTrue(preserved.exists())
        assertTrue(preserved.readBytes().copyOfRange(0, 16)
            .contentEquals("SQLite format 3\u0000".toByteArray(Charsets.US_ASCII)))

        upgraded.readableDatabase.rawQuery("SELECT id,ts,text FROM mem ORDER BY id", null).use { rows ->
            assertTrue(rows.moveToNext())
            assertEquals(41L, rows.getLong(0))
            assertEquals("2026-10-19T09:30:00Z", rows.getString(1))
            assertEquals("Eski kişisel hafızam", rows.getString(2))
            assertFalse(rows.moveToNext())
        }
        upgraded.readableDatabase.rawQuery("SELECT id,title,done FROM tasks ORDER BY id", null).use { rows ->
            assertTrue(rows.moveToNext())
            assertEquals(17L, rows.getLong(0))
            assertEquals("Eski bekleyen görev", rows.getString(1))
            assertEquals(0, rows.getInt(2))
            assertTrue(rows.moveToNext())
            assertEquals(23L, rows.getLong(0))
            assertEquals("Eski tamamlanan görev", rows.getString(1))
            assertEquals(1, rows.getInt(2))
            assertFalse(rows.moveToNext())
        }

        upgraded.saveMessage("user", "Yükseltmeden sonra yazılan mesaj")
        upgraded.saveMessage("assistant", "Eski veriler korunarak sohbet açıldı.")
        upgraded.close()

        val reopened = openStore()
        assertEquals(
            listOf(
                "user" to "Yükseltmeden sonra yazılan mesaj",
                "assistant" to "Eski veriler korunarak sohbet açıldı.",
            ),
            reopened.history().map { it.role to it.text },
        )
        assertTrue(reopened.memory().contains("Eski kişisel hafızam"))
        assertTrue(reopened.tasks().contains("Eski bekleyen görev"))
        assertTrue(reopened.tasks().contains("Eski tamamlanan görev"))
        val raw = String(context.getDatabasePath(DATABASE_NAME).readBytes(), Charsets.ISO_8859_1)
        assertFalse(raw.contains("Eski kişisel hafızam"))
        assertFalse(raw.contains("Eski bekleyen görev"))
    }

    @Test
    fun plaintextVersionTwoChatAndTaskRowsArePreservedInCipherDatabase() {
        val original = context.openOrCreateDatabase(DATABASE_NAME, Context.MODE_PRIVATE, null)
        try {
            original.execSQL("CREATE TABLE mem(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, text TEXT NOT NULL)")
            original.execSQL("CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)")
            original.execSQL(
                "CREATE TABLE chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, " +
                    "role TEXT NOT NULL CHECK(role IN ('user','assistant','system')), text TEXT NOT NULL)",
            )
            original.execSQL("INSERT INTO mem(id,ts,text) VALUES(1,'time','Kişisel not')")
            original.execSQL("INSERT INTO tasks(id,title,done) VALUES(3,'Görev üç',1)")
            original.execSQL(
                "INSERT INTO chat_messages(id,ts,role,text) VALUES(4,'time','user','Korumalı sohbet')",
            )
            original.version = 2
        } finally {
            original.close()
        }
        val sourceBytes = context.getDatabasePath(DATABASE_NAME).readBytes()
        val migrated = openStore()
        assertEquals(KralStore.DATABASE_VERSION, migrated.readableDatabase.version)
        assertTrue(migrated.memory().contains("Kişisel not"))
        assertTrue(migrated.tasks().contains("Görev üç"))
        assertEquals("Korumalı sohbet", migrated.history().single().text)
        assertTrue(
            context.getDatabasePath("$DATABASE_NAME.plaintext-legacy")
                .readBytes().contentEquals(sourceBytes),
        )
        migrated.close()
        assertEquals("Korumalı sohbet", openStore().history().single().text)
    }

    @Test
    fun interruptedStagingFileBlocksMigrationWithoutRemovingOriginal() {
        val plain = createLegacyVersionOne()
        val staged = context.getDatabasePath("$DATABASE_NAME.cipher-staging")
        staged.writeText("PREVIOUS_MIGRATION_EVIDENCE")
        val before = plain.readBytes()
        assertThrows(IllegalStateException::class.java) { openStore() }
        assertTrue(plain.readBytes().contentEquals(before))
        assertEquals("PREVIOUS_MIGRATION_EVIDENCE", staged.readText())
        assertFalse(context.getDatabasePath("$DATABASE_NAME.plaintext-legacy").exists())
    }

    @Test
    fun oldPlaintextWalOrJournalBlocksMigrationWithoutDeletingFiles() {
        for (suffix in listOf("-wal", "-journal", "-shm")) {
            deleteTestDatabases()
            val plain = createLegacyVersionOne()
            val before = plain.readBytes()
            val sidecar = File(plain.absolutePath + suffix)
            sidecar.writeText("PRESERVE_SIDECAR")
            assertThrows(IllegalStateException::class.java) { openStore() }
            assertTrue(plain.readBytes().contentEquals(before))
            assertEquals("PRESERVE_SIDECAR", sidecar.readText())
            assertFalse(context.getDatabasePath("$DATABASE_NAME.cipher-staging").exists())
        }
    }

    @Test
    fun oldPlaintextSnapshotSurvivesMigrationAndFailedReopen() {
        val source = createLegacyVersionOne()
        val before = source.readBytes()
        val converted = openStore()
        assertEquals(KralStore.DATABASE_VERSION, converted.readableDatabase.version)
        converted.close()
        val preserved = context.getDatabasePath("$DATABASE_NAME.plaintext-legacy")
        assertTrue(preserved.readBytes().contentEquals(before))
        assertFalse(context.getDatabasePath("$DATABASE_NAME.cipher-staging").exists())

        val otherKey = DatabaseKeyProvider { ByteArray(32) { 99.toByte() } }
        assertThrows(Exception::class.java) {
            KralStore(context, otherKey)
        }
        assertTrue(preserved.readBytes().contentEquals(before))
        assertEquals(KralStore.DATABASE_VERSION, openStore().readableDatabase.version)
    }

    private fun createLegacyVersionOne(): File {
        val legacy = context.openOrCreateDatabase(DATABASE_NAME, Context.MODE_PRIVATE, null)
        try {
            legacy.execSQL("CREATE TABLE mem(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, text TEXT NOT NULL)")
            legacy.execSQL("CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)")
            legacy.execSQL(
                "INSERT INTO mem(id,ts,text) VALUES(?,?,?)",
                arrayOf<Any>(8L, "2026-10-19T09:30:00Z", "İlk kayıt korunmalı"),
            )
            legacy.version = 1
        } finally {
            legacy.close()
        }
        return context.getDatabasePath(DATABASE_NAME)
    }

    @Test
    fun limitedHistoryReturnsNewestMessagesInChronologicalOrder() {
        val store = openStore()
        (1..6).forEach { number ->
            store.saveMessage(if (number % 2 == 1) "user" else "assistant", "Mesaj $number")
        }

        assertEquals(
            listOf("assistant" to "Mesaj 4", "user" to "Mesaj 5", "assistant" to "Mesaj 6"),
            store.history(3).map { it.role to it.text },
        )
        assertEquals(listOf("Mesaj 6"), store.history(1).map { it.text })
        assertEquals((1..6).map { "Mesaj $it" }, store.history(20).map { it.text })
    }

    @Test
    fun invalidRoleIsRejectedWithoutChangingSavedHistory() {
        val store = openStore()
        store.saveMessage("user", "Geçerli mesaj korunmalı")

        assertThrows(IllegalArgumentException::class.java) {
            store.saveMessage("invalid-role", "Bu mesaj kaydedilmemeli")
        }

        assertEquals(
            listOf("user" to "Geçerli mesaj korunmalı"),
            store.history().map { it.role to it.text },
        )
    }

    @Test
    fun recallSurvivesReopenAndMatchesTurkishLettersWithoutUploadingHistory() {
        val store = openStore()
        store.saveMemory("İstanbul seyahatim cuma günü")
        store.saveMemory("Ankara seyahatim pazartesi")
        store.saveMessage("user", "Sohbet tek başına hafıza kaydı değildir")
        store.close()
        val reopened = openStore()
        assertTrue(reopened.recall("İSTANBUL CUMA").contains("İstanbul seyahatim"))
        assertFalse(reopened.recall("İSTANBUL CUMA").contains("Ankara"))
        assertEquals("(eşleşen bilgi yok)", reopened.recall("tek başına"))
        assertEquals("(eşleşen bilgi yok)", reopened.recall("%' OR 1=1 --"))
        assertEquals(1, reopened.history().size)
    }

    @Test
    fun privateContentIsNotStoredInThePlaintextDatabaseFile() {
        val marker = "AT_REST_ENCRYPTION_SENTINEL_7f1b"
        val store = openStore()
        store.saveMessage("user", marker)
        store.saveMemory("hafıza $marker")
        store.addTask("görev $marker")
        store.close()

        val file = context.getDatabasePath(DATABASE_NAME)
        val raw = String(file.readBytes(), Charsets.ISO_8859_1)
        assertFalse(raw.startsWith("SQLite format 3\u0000"))
        assertFalse(raw.contains(marker))
        assertEquals(marker, openStore().history().single().text)
    }

    private fun openStore(): KralStore = KralStore(context, TestDatabaseKeyProvider).also { openedStores.add(it) }

    private fun deleteTestDatabases() {
        listOf(
            DATABASE_NAME,
            "$DATABASE_NAME.plaintext-legacy",
            "$DATABASE_NAME.cipher-staging",
        ).forEach { context.deleteDatabase(it) }
        listOf("-journal", "-wal", "-shm").forEach { suffix ->
            File(context.getDatabasePath(DATABASE_NAME).absolutePath + suffix).delete()
        }
    }

    private companion object {
        const val DATABASE_NAME = "kral_local.db"
    }
}

internal object TestDatabaseKeyProvider : DatabaseKeyProvider {
    private val testKey = ByteArray(32) { (it + 1).toByte() }
    override fun getKey(context: Context): ByteArray = testKey.copyOf()
}
