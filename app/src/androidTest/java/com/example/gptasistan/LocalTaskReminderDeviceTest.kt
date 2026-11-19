package com.example.gptasistan

import android.Manifest
import android.app.Notification
import android.app.NotificationManager
import android.app.job.JobScheduler
import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.view.View
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import java.security.KeyStore
import java.security.MessageDigest
import java.util.UUID
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Real OS scheduling and notification evidence; never dispatches a model or owner request. */
@RunWith(AndroidJUnit4::class)
class LocalTaskReminderDeviceTest {
    private lateinit var context: Context
    private lateinit var fixtureRoot: File
    private var safe = false
    private var reminderPreferences: Map<String, *>? = null
    private var createdChannel = false
    private var ownsProductionFixture = false
    private var initialKeyPreferences: Map<String, *>? = null
    private var keyAliasExisted = false

    @Before
    fun before() {
        context = InstrumentationRegistry.getInstrumentation().targetContext.applicationContext
        InstrumentationSafety.requireDisposableEmulator(context)
        safe = true
        fixtureRoot = File(context.cacheDir, "kral-reminder-native-${UUID.randomUUID()}")
        check(fixtureRoot.mkdir())
    }

    @After
    fun after() {
        if (!safe) return
        if (reminderPreferences != null) {
            LocalTaskReminders.disable(context)
            restorePreferences(context.getSharedPreferences(LocalTaskReminders.PREFS, Context.MODE_PRIVATE),
                checkNotNull(reminderPreferences))
        }
        if (createdChannel) notifications().deleteNotificationChannel(LocalTaskReminders.CHANNEL_ID)
        if (ownsProductionFixture) {
            // Ownership was established before creating anything. Never remove a pre-existing DB/key.
            databaseFiles(context).forEach { if (it.exists()) check(it.delete()) }
            val original = checkNotNull(initialKeyPreferences)
            if (original.isEmpty()) {
                val preferences = context.getSharedPreferences(KEY_PREFS, Context.MODE_PRIVATE)
                check(preferences.all.keys.all { it == KEY_PREFERENCE })
                restorePreferences(preferences, original)
            } else assertEquals(original, context.getSharedPreferences(KEY_PREFS, Context.MODE_PRIVATE).all)
            if (!keyAliasExisted) {
                KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(KEY_ALIAS)
            }
        }
        if (::fixtureRoot.isInitialized) {
            check(fixtureRoot.canonicalFile.parentFile == context.cacheDir.canonicalFile)
            check(fixtureRoot.name.startsWith("kral-reminder-native-"))
            check(fixtureRoot.deleteRecursively())
        }
    }

    @Test
    fun scheduledJobPostsPrivateNotificationAndOpensLockedActivity() {
        prepareReminderState()
        prepareProductionDatabase()
        if (Build.VERSION.SDK_INT >= 33) {
            assertEquals("CI must grant notification permission before instrumentation starts",
                PackageManager.PERMISSION_GRANTED, context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS))
        }
        val store = KralStore(context)
        try {
            store.addTask(PRIVATE_MARKER)
            store.addTask("completed public task")
            assertTrue(store.finishTask(2L))
            store.saveMemory(PRIVATE_MARKER)
        } finally { store.close() }
        val encryptedBefore = sha256(context.getDatabasePath(KralStore.DATABASE_NAME))
        assertEquals(LocalTaskReminders.EnableResult.ENABLED, LocalTaskReminders.enable(context))
        val job = jobs().getPendingJob(LocalTaskReminders.JOB_ID)
        assertNotNull(job)
        assertTrue(checkNotNull(job).isPersisted)
        assertTrue(job.isPeriodic)

        // Ask Android's scheduler to dispatch the registered production JobService.
        // No onStartJob/worker method is invoked by this test.
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val descriptor = instrumentation.uiAutomation.executeShellCommand(
            "cmd jobscheduler run -f ${context.packageName} ${LocalTaskReminders.JOB_ID}")
        val dispatch = ParcelFileDescriptor.AutoCloseInputStream(descriptor).bufferedReader().use { it.readText() }
        assertTrue("Real JobScheduler dispatch failed: $dispatch", dispatch.contains("Running job"))
        assertFalse(dispatch.contains("Error"))
        await("JobService did not post an actual notification") {
            notifications().activeNotifications.any { it.id == LocalTaskReminders.NOTIFICATION_ID }
        }
        val notification = notifications().activeNotifications.single {
            it.id == LocalTaskReminders.NOTIFICATION_ID
        }.notification
        assertEquals(LocalTaskReminders.CHANNEL_ID, notification.channelId)
        assertEquals(Notification.VISIBILITY_PRIVATE, notification.visibility)
        assertFalse(notification.extras.toString().contains(PRIVATE_MARKER))
        assertFalse(notification.publicVersion?.extras.toString().contains(PRIVATE_MARKER))
        assertNotNull(notification.contentIntent)
        if (Build.VERSION.SDK_INT >= 31) assertTrue(notification.contentIntent.isImmutable)
        assertEquals(encryptedBefore, sha256(context.getDatabasePath(KralStore.DATABASE_NAME)))

        val monitor = instrumentation.addMonitor(MainActivity::class.java.name, null, false)
        try {
            notification.contentIntent.send()
            val activity = instrumentation.waitForMonitorWithTimeout(monitor, 5000)
                ?: throw AssertionError("Notification did not open MainActivity")
            try {
                instrumentation.runOnMainSync {
                    val unlock = activity.findViewById<View>(R.id.unlock_button)
                    assertNotNull("Notification bypassed the owner lock", unlock)
                    assertEquals(View.VISIBLE, unlock.visibility)
                }
            } finally { instrumentation.runOnMainSync { activity.finish() } }
        } finally { instrumentation.removeMonitor(monitor) }

        instrumentation.addResults(Bundle().apply {
            putString("kral_reminder_real_job_dispatch", "true")
            putString("kral_reminder_actual_notification", "true")
            putString("kral_reminder_notification_opens_locked_activity", "true")
        })
    }

    @Test
    fun encryptedPendingTaskCountIsReadOnlyAndIgnoresCompletedRows() {
        val fixture = isolatedContext("encrypted")
        val key = ByteArray(32) { (it + 51).toByte() }
        KralStore(fixture, DatabaseKeyProvider { key.copyOf() }).use { store ->
            store.addTask(PRIVATE_MARKER)
            store.addTask("completed fixture task")
            assertTrue(store.finishTask(2L))
        }
        val file = fixture.getDatabasePath(KralStore.DATABASE_NAME)
        val before = sha256(file)
        val supplied = key.copyOf()
        assertEquals(1L, LocalTaskReminders.readPendingTaskCount(fixture) { supplied })
        assertArrayEquals(key, supplied)
        assertEquals(before, sha256(file))
        KralStore(fixture, DatabaseKeyProvider { key.copyOf() }).use { store ->
            assertTrue(store.finishTask(1L))
        }
        val completed = sha256(file)
        assertEquals(0L, LocalTaskReminders.readPendingTaskCount(fixture) { key.copyOf() })
        assertEquals(completed, sha256(file))
    }

    @Test
    fun missingOrWrongKeyNeverReplacesEncryptedDatabase() {
        val fixture = isolatedContext("key-failures")
        val key = ByteArray(32) { (it + 65).toByte() }
        KralStore(fixture, DatabaseKeyProvider { key.copyOf() }).use { it.addTask(PRIVATE_MARKER) }
        val files = databaseFiles(fixture).filter { it.exists() }.associate { it.name to sha256(it) }
        assertNull(LocalTaskReminders.readPendingTaskCount(fixture) { null })
        assertNull(LocalTaskReminders.readPendingTaskCount(fixture) { throw IllegalStateException("fixture missing key") })
        assertNull(LocalTaskReminders.readPendingTaskCount(fixture) { ByteArray(32) { 7 } })
        assertEquals(files, databaseFiles(fixture).filter { it.exists() }.associate { it.name to sha256(it) })
        KralStore(fixture, DatabaseKeyProvider { key.copyOf() }).use {
            assertTrue(it.tasks().contains(PRIVATE_MARKER))
        }
    }

    @Test
    fun missingOrPlaintextDatabaseIsNotCreatedOrMigrated() {
        val missing = isolatedContext("missing")
        val absent = missing.getDatabasePath(KralStore.DATABASE_NAME)
        var keyRequests = 0
        assertNull(LocalTaskReminders.readPendingTaskCount(missing) {
            keyRequests++
            error("Missing DB must not request a key")
        })
        assertEquals(0, keyRequests)
        assertFalse(absent.exists())
        val plaintext = isolatedContext("plaintext")
        val file = plaintext.getDatabasePath(KralStore.DATABASE_NAME)
        file.writeBytes("SQLite format 3\u0000public disposable plaintext sentinel".toByteArray())
        val before = file.readBytes()
        assertNull(LocalTaskReminders.readPendingTaskCount(plaintext) {
            keyRequests++
            error("Plaintext DB must not request a key")
        })
        assertEquals(0, keyRequests)
        assertArrayEquals(before, file.readBytes())
        assertFalse(File(file.absolutePath + ".plaintext-legacy").exists())
        assertFalse(File(file.absolutePath + ".cipher-staging").exists())
    }

    @Test
    fun disablingRemindersCancelsScheduledJobAndNotification() {
        prepareReminderState()
        assertEquals(LocalTaskReminders.EnableResult.ENABLED, LocalTaskReminders.enable(context))
        assertNotNull(jobs().getPendingJob(LocalTaskReminders.JOB_ID))
        LocalTaskReminders.disable(context)
        assertFalse(LocalTaskReminders.status(context).enabled)
        assertNull(jobs().getPendingJob(LocalTaskReminders.JOB_ID))
        assertFalse(notifications().activeNotifications.any { it.id == LocalTaskReminders.NOTIFICATION_ID })
        // A stale OS dispatch cannot recreate a job which the owner disabled.
        val descriptor = InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand(
            "cmd jobscheduler run -f ${context.packageName} ${LocalTaskReminders.JOB_ID}")
        val output = ParcelFileDescriptor.AutoCloseInputStream(descriptor).bufferedReader().use { it.readText() }
        assertFalse("A cancelled job was dispatched: $output", output.contains("Running job"))
        assertNull(jobs().getPendingJob(LocalTaskReminders.JOB_ID))
        assertFalse(notifications().activeNotifications.any { it.id == LocalTaskReminders.NOTIFICATION_ID })
    }

    private fun prepareReminderState() {
        check(jobs().getPendingJob(LocalTaskReminders.JOB_ID) == null) { "EXISTING_REMINDER_JOB_REFUSED" }
        check(notifications().activeNotifications.none { it.id == LocalTaskReminders.NOTIFICATION_ID }) {
            "EXISTING_REMINDER_NOTIFICATION_REFUSED"
        }
        val preferences = context.getSharedPreferences(LocalTaskReminders.PREFS, Context.MODE_PRIVATE)
        check(!preferences.getBoolean("enabled", false)) { "EXISTING_ENABLED_REMINDERS_REFUSED" }
        reminderPreferences = preferences.all.toMap()
        createdChannel = notifications().getNotificationChannel(LocalTaskReminders.CHANNEL_ID) == null
    }

    private fun prepareProductionDatabase() {
        check(databaseFiles(context).none { it.exists() }) { "EXISTING_DATABASE_REFUSED" }
        val preferences = context.getSharedPreferences(KEY_PREFS, Context.MODE_PRIVATE)
        initialKeyPreferences = preferences.all.toMap()
        keyAliasExisted = KeyStore.getInstance("AndroidKeyStore").run { load(null); containsAlias(KEY_ALIAS) }
        // A mismatched existing key is preserved and refused rather than reset.
        check(preferences.contains(KEY_PREFERENCE) == keyAliasExisted) { "INCONSISTENT_EXISTING_KEY_REFUSED" }
        ownsProductionFixture = true
    }

    private fun isolatedContext(label: String): Context {
        val directory = File(fixtureRoot, label)
        check(directory.mkdir())
        return object : ContextWrapper(context) {
            override fun getApplicationContext(): Context = this
            override fun getDatabasePath(name: String): File {
                require(name.matches(Regex("[A-Za-z0-9_.-]+")) && name !in setOf(".", ".."))
                return File(directory, name)
            }
        }
    }

    private fun databaseFiles(ctx: Context): List<File> {
        val main = ctx.getDatabasePath(KralStore.DATABASE_NAME)
        return listOf("", "-wal", "-shm", "-journal", ".plaintext-legacy", ".cipher-staging")
            .map { File(main.absolutePath + it) }
    }

    private fun restorePreferences(preferences: SharedPreferences, snapshot: Map<String, *>) {
        val editor = preferences.edit().clear()
        snapshot.forEach { (key, value) ->
            when (value) {
                is Boolean -> editor.putBoolean(key, value)
                is Long -> editor.putLong(key, value)
                is Int -> editor.putInt(key, value)
                is Float -> editor.putFloat(key, value)
                is String -> editor.putString(key, value)
                is Set<*> -> editor.putStringSet(key, value.map { it as String }.toSet())
                else -> error("Unexpected preference type")
            }
        }
        check(editor.commit())
    }

    private fun jobs() = context.getSystemService(JobScheduler::class.java)
    private fun notifications() = context.getSystemService(NotificationManager::class.java)
    private fun sha256(file: File) = MessageDigest.getInstance("SHA-256").digest(file.readBytes())
        .joinToString("") { "%02x".format(it.toInt() and 255) }

    private fun await(message: String, condition: () -> Boolean) {
        val end = SystemClock.elapsedRealtime() + 8000
        while (SystemClock.elapsedRealtime() < end) {
            if (condition()) return
            SystemClock.sleep(25)
        }
        assertTrue(message, condition())
    }

    private companion object {
        const val PRIVATE_MARKER = "REMINDER_PRIVATE_FIXTURE_521a"
        const val KEY_PREFS = "kral_database_key"
        const val KEY_PREFERENCE = "wrapped_sqlcipher_key_v1"
        const val KEY_ALIAS = "kral.database.wrapping.v1"
    }
}
