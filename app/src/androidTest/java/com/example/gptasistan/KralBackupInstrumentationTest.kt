package com.example.gptasistan

import android.content.Context
import android.content.ContextWrapper
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.util.UUID
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Real SQLCipher restore exercises only isolated fixtures on disposable emulators. */
@RunWith(AndroidJUnit4::class)
class KralBackupInstrumentationTest {
    private lateinit var baseContext: Context
    private lateinit var fixtureRoot: File
    private val openedStores = mutableListOf<KralStore>()
    private val contexts = mutableMapOf<String, Context>()
    private var disposableEmulatorVerified = false

    @Before
    fun setUp() {
        baseContext = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext
        // Refuse every filesystem operation until the existing emulator/package guard succeeds.
        InstrumentationSafety.requireDisposableEmulator(baseContext)
        disposableEmulatorVerified = true
        fixtureRoot = File(baseContext.cacheDir, "kral-backup-test-${UUID.randomUUID()}")
        check(fixtureRoot.mkdir())
    }

    @After
    fun tearDown() {
        openedStores.asReversed().forEach { it.close() }
        if (disposableEmulatorVerified && ::fixtureRoot.isInitialized) {
            check(fixtureRoot.canonicalFile.parentFile == baseContext.cacheDir.canonicalFile)
            check(fixtureRoot.name.startsWith("kral-backup-test-"))
            check(fixtureRoot.deleteRecursively())
        }
    }

    @Test
    fun encryptedLogicalBackupRestoresExactRowsWithDifferentKeyAndSurvivesReopen() {
        val source = sourceFixture()
        val original = snapshot(source)
        val password = fixturePassword()
        try {
            val encrypted = KralBackup.export(source, password)
            assertFalse(String(encrypted, Charsets.ISO_8859_1).contains(PRIVATE_MARKER))
            val target = openStore("restored", 93)
            val restored = KralBackup.restore(target, encrypted, password)

            assertEquals(2, restored.memories)
            assertEquals(2, restored.tasks)
            assertEquals(3, restored.messages)
            assertEquals(original, snapshot(target))
            assertEquals(original, snapshot(source))
            target.close()

            val reopened = openStore("restored", 93)
            assertEquals(original, snapshot(reopened))
            reopened.saveMessage("user", "Geri yüklemeden sonraki yeni ileti")
            assertTrue(reopened.history().last().id > 35L)
            assertEquals(original, snapshot(source))
            reopened.close()

            val disk = contextFor("restored").getDatabasePath(KralStore.DATABASE_NAME).readBytes()
            assertFalse(String(disk, Charsets.ISO_8859_1).startsWith("SQLite format 3\u0000"))
            assertFalse(String(disk, Charsets.ISO_8859_1).contains(PRIVATE_MARKER))
        } finally {
            password.fill('\u0000')
        }
    }

    @Test
    fun wrongPasswordAndTamperingFailGenericallyBeforeTargetDatabaseIsCreated() {
        val source = sourceFixture()
        val original = snapshot(source)
        val target = openStore("invalid-input-target", 94)
        val targetFile = contextFor("invalid-input-target").getDatabasePath(KralStore.DATABASE_NAME)
        val password = fixturePassword()
        val wrongPassword = "different-fixture-password".toCharArray()
        try {
            val encrypted = KralBackup.export(source, password)
            assertFalse(targetFile.exists())
            val wrong = assertThrows(KralBackup.BackupException::class.java) {
                KralBackup.restore(target, encrypted, wrongPassword)
            }
            assertFalse(targetFile.exists())
            val changed = encrypted.copyOf().apply {
                this[lastIndex] = (this[lastIndex].toInt() xor 1).toByte()
            }
            val tampered = assertThrows(KralBackup.BackupException::class.java) {
                KralBackup.restore(target, changed, password)
            }
            assertEquals(wrong.message, tampered.message)
            assertFalse(targetFile.exists())
            assertEquals(original, snapshot(source))
            assertTrue(snapshot(target).values.all { it.isEmpty() })
        } finally {
            password.fill('\u0000')
            wrongPassword.fill('\u0000')
        }
    }

    @Test
    fun anyNonemptyApplicationTableRejectsRestoreWithoutReplacingItsRows() {
        val source = sourceFixture()
        val original = snapshot(source)
        val password = fixturePassword()
        try {
            val encrypted = KralBackup.export(source, password)
            // sqlitex_local is an application table, not SQLite's reserved sqlite_* prefix.
            for ((index, table) in listOf("mem", "tasks", "chat_messages", "sqlitex_local").withIndex()) {
                val target = openStore("nonempty-$table", 100 + index)
                val db = target.writableDatabase
                when (table) {
                    "mem" -> db.execSQL("INSERT INTO mem(id,ts,text) VALUES(501,'original-time','existing memory')")
                    "tasks" -> db.execSQL("INSERT INTO tasks(id,title,done) VALUES(502,'existing task',1)")
                    "chat_messages" -> db.execSQL(
                        "INSERT INTO chat_messages(id,ts,role,text) VALUES(503,'original-time','system','existing chat')",
                    )
                    else -> {
                        db.execSQL("CREATE TABLE sqlitex_local(id INTEGER PRIMARY KEY,text TEXT NOT NULL)")
                        db.execSQL("INSERT INTO sqlitex_local(id,text) VALUES(504,'unrelated data remains')")
                    }
                }
                val before = snapshot(target)
                val unrelatedBefore = if (table == "sqlitex_local") rows(target, table) else emptyList()

                assertThrows(KralBackup.BackupException::class.java) {
                    KralBackup.restore(target, encrypted, password)
                }

                assertEquals(before, snapshot(target))
                if (table == "sqlitex_local") assertEquals(unrelatedBefore, rows(target, table))
                assertEquals(original, snapshot(source))
            }
        } finally {
            password.fill('\u0000')
        }
    }

    @Test
    fun legitimateAndroidLocaleMetadataIsPreservedButLookalikeDataBlocksRestore() {
        val source = sourceFixture()
        val original = snapshot(source)
        val password = fixturePassword()
        try {
            val encrypted = KralBackup.export(source, password)
            val target = openStore("supported-metadata", 98)
            val db = target.writableDatabase
            // This is only the isolated fixture database; no installed-app metadata is touched.
            db.execSQL("CREATE TABLE IF NOT EXISTS android_metadata(locale TEXT)")
            db.execSQL("DELETE FROM android_metadata")
            db.execSQL("INSERT INTO android_metadata(locale) VALUES('tr_TR')")

            KralBackup.restore(target, encrypted, password)

            assertEquals(original, snapshot(target))
            db.rawQuery("SELECT locale FROM android_metadata", null).use { rows ->
                assertTrue(rows.moveToFirst())
                assertEquals("tr_TR", rows.getString(0))
                assertFalse(rows.moveToNext())
            }

            val malformedTarget = openStore("malformed-metadata", 99)
            val malformedDb = malformedTarget.writableDatabase
            malformedDb.execSQL("CREATE TABLE IF NOT EXISTS android_metadata(locale TEXT)")
            malformedDb.execSQL("DELETE FROM android_metadata")
            malformedDb.execSQL("ALTER TABLE android_metadata RENAME COLUMN locale TO secret")
            malformedDb.execSQL("INSERT INTO android_metadata(secret) VALUES('fixture metadata must remain')")
            val before = snapshot(malformedTarget)

            assertThrows(KralBackup.BackupException::class.java) {
                KralBackup.restore(malformedTarget, encrypted, password)
            }

            assertEquals(before, snapshot(malformedTarget))
            malformedDb.rawQuery("SELECT secret FROM android_metadata", null).use { rows ->
                assertTrue(rows.moveToFirst())
                assertEquals("fixture metadata must remain", rows.getString(0))
                assertFalse(rows.moveToNext())
            }
            assertEquals(original, snapshot(source))
        } finally {
            password.fill('\u0000')
        }
    }

    @Test
    fun constraintFailureRollsBackAllRestoredTablesAndPreservesExistingSchema() {
        val source = sourceFixture()
        val original = snapshot(source)
        val target = openStore("transaction-failure", 97)
        val db = target.writableDatabase
        // Alter only this isolated fixture: the second source task violates the CHECK.
        db.execSQL("DROP TABLE tasks")
        db.execSQL("CREATE TABLE tasks(id INTEGER PRIMARY KEY,title TEXT NOT NULL," +
            "done INTEGER NOT NULL DEFAULT 0 CHECK(done=0))")
        val schemaBefore = schemaSql(target, "table", "tasks")
        val password = fixturePassword()
        try {
            val encrypted = KralBackup.export(source, password)
            assertThrows(KralBackup.BackupException::class.java) {
                KralBackup.restore(target, encrypted, password)
            }
            assertTrue(snapshot(target).values.all { it.isEmpty() })
            assertEquals(schemaBefore, schemaSql(target, "table", "tasks"))
            assertEquals(original, snapshot(source))

            db.execSQL("DROP TABLE tasks")
            db.execSQL("CREATE TABLE tasks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0)")
            KralBackup.restore(target, encrypted, password)
            assertEquals(original, snapshot(target))
        } finally {
            password.fill('\u0000')
        }
    }

    @Test
    fun targetTriggersCannotSilentlyIgnoreOrMutateRestoredRows() {
        val source = sourceFixture()
        val original = snapshot(source)
        val password = fixturePassword()
        try {
            val encrypted = KralBackup.export(source, password)
            val triggers = listOf(
                "skip_fixture_task" to "CREATE TRIGGER skip_fixture_task BEFORE INSERT ON tasks " +
                    "BEGIN SELECT RAISE(IGNORE); END",
                "mutate_fixture_task" to "CREATE TRIGGER mutate_fixture_task AFTER INSERT ON tasks " +
                    "BEGIN UPDATE tasks SET title='changed by trigger' WHERE id=NEW.id; END",
            )
            for ((index, fixture) in triggers.withIndex()) {
                val (name, statement) = fixture
                val target = openStore("trigger-$index", 110 + index)
                target.writableDatabase.execSQL(statement)
                val before = snapshot(target)
                val triggerBefore = schemaSql(target, "trigger", name)

                assertThrows(KralBackup.BackupException::class.java) {
                    KralBackup.restore(target, encrypted, password)
                }

                assertEquals(before, snapshot(target))
                assertEquals(triggerBefore, schemaSql(target, "trigger", name))
                assertEquals(original, snapshot(source))
            }
        } finally {
            password.fill('\u0000')
        }
    }

    @Test
    fun silentlyIgnoredConstraintRowsFailExactCopyVerificationAndRollBack() {
        val source = sourceFixture()
        source.writableDatabase.execSQL("UPDATE tasks SET title='same public title'")
        val original = snapshot(source)
        val target = openStore("constraint-ignore", 112)
        val db = target.writableDatabase
        // These columns have the production PRAGMA shape, but the extra constraint
        // silently discards the second restored task instead of raising an error.
        db.execSQL("DROP TABLE tasks")
        db.execSQL("CREATE TABLE tasks(id INTEGER PRIMARY KEY," +
            "title TEXT NOT NULL UNIQUE ON CONFLICT IGNORE,done INTEGER NOT NULL DEFAULT 0)")
        val schemaBefore = schemaSql(target, "table", "tasks")
        val password = fixturePassword()
        try {
            val encrypted = KralBackup.export(source, password)

            assertThrows(KralBackup.BackupException::class.java) {
                KralBackup.restore(target, encrypted, password)
            }

            assertTrue(snapshot(target).values.all { it.isEmpty() })
            assertEquals(schemaBefore, schemaSql(target, "table", "tasks"))
            assertEquals(original, snapshot(source))
        } finally {
            password.fill('\u0000')
        }
    }

    private fun sourceFixture(): KralStore = openStore("source", 31).also { store ->
        val db = store.writableDatabase
        db.execSQL("INSERT INTO mem(id,ts,text) VALUES(?,?,?)", arrayOf<Any>(
            41L, "2026-11-04T12:34:56.123456789Z", "$PRIVATE_MARKER Türkçe hafıza: İ, ı, ş, ç.\nİkinci satır.",
        ))
        db.execSQL("INSERT INTO mem(id,ts,text) VALUES(?,?,?)", arrayOf<Any>(
            99L, "legacy timestamp preserved exactly", "Tırnak: ' ve \"; simge: 🧭",
        ))
        db.execSQL("INSERT INTO tasks(id,title,done) VALUES(17,'Bekleyen görev',0)")
        db.execSQL("INSERT INTO tasks(id,title,done) VALUES(23,'Tamamlanan görev',1)")
        for ((id, role, text) in listOf(
            Triple(11L, "system", "Yerel sistem iletisi"),
            Triple(27L, "user", "Kişisel soru"),
            Triple(35L, "assistant", "Türkçe yanıt"),
        )) {
            db.execSQL("INSERT INTO chat_messages(id,ts,role,text) VALUES(?,?,?,?)", arrayOf<Any>(
                id, "2026-11-04T12:34:56Z", role, text,
            ))
        }
    }

    private fun snapshot(store: KralStore): Map<String, List<List<String?>>> =
        listOf("mem", "tasks", "chat_messages").associateWith { rows(store, it) }

    private fun schemaSql(store: KralStore, type: String, name: String): String {
        store.readableDatabase.rawQuery("SELECT sql FROM sqlite_master WHERE type=? AND name=?", arrayOf(type, name)).use {
            assertTrue(it.moveToFirst())
            val sql = it.getString(0)
            assertFalse(it.moveToNext())
            return sql
        }
    }

    private fun rows(store: KralStore, table: String): List<List<String?>> {
        require(table in setOf("mem", "tasks", "chat_messages", "sqlitex_local"))
        val result = mutableListOf<List<String?>>()
        store.readableDatabase.rawQuery("SELECT * FROM $table ORDER BY id", null).use { cursor ->
            while (cursor.moveToNext()) result.add((0 until cursor.columnCount).map {
                if (cursor.isNull(it)) null else cursor.getString(it)
            })
        }
        return result
    }

    private fun openStore(label: String, keySeed: Int): KralStore = KralStore(
        contextFor(label), DatabaseKeyProvider { ByteArray(32) { (keySeed + it).toByte() } },
    ).also { openedStores.add(it) }

    private fun contextFor(label: String): Context = contexts.getOrPut(label) {
        require(disposableEmulatorVerified && label.matches(Regex("[A-Za-z0-9_-]+")))
        val directory = File(fixtureRoot, label)
        check(directory.mkdir())
        object : ContextWrapper(baseContext) {
            override fun getApplicationContext(): Context = this
            override fun getDatabasePath(name: String): File {
                require(name !in setOf(".", "..") && name.matches(Regex("[A-Za-z0-9_.-]+")))
                return File(directory, name)
            }
        }
    }

    private fun fixturePassword(): CharArray = "disposable-backup-fixture-password".toCharArray()

    private companion object {
        const val PRIVATE_MARKER = "BACKUP_PRIVATE_SENTINEL_f73b"
    }
}
