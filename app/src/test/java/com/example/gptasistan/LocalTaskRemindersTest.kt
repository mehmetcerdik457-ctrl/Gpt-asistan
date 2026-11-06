package com.example.gptasistan

import android.Manifest
import android.app.Notification
import android.app.NotificationManager
import android.app.job.JobScheduler
import android.content.ComponentName
import android.content.Context
import android.content.ContextWrapper
import java.io.File
import java.nio.file.Files
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class LocalTaskRemindersTest {
    private val app get() = RuntimeEnvironment.getApplication()
    private val scheduler get() = app.getSystemService(Context.JOB_SCHEDULER_SERVICE) as JobScheduler
    private val manager get() = app.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    @Before fun reset() {
        LocalTaskReminders.disable(app)
        app.getSharedPreferences(LocalTaskReminders.PREFS, Context.MODE_PRIVATE).edit().clear().commit()
        scheduler.cancelAll()
        manager.cancelAll()
        shadowOf(manager).setNotificationsEnabled(true)
    }

    @After fun cleanup() { LocalTaskReminders.disable(app) }

    @Test fun disabledByDefaultAndEnableSchedulesOnePersistentLocalJob() {
        assertFalse(LocalTaskReminders.status(app).enabled)
        assertNull(LocalTaskReminders.begin(app))
        assertNull(scheduler.getPendingJob(LocalTaskReminders.JOB_ID))
        assertEquals(LocalTaskReminders.EnableResult.ENABLED, LocalTaskReminders.enable(app))
        val job = requireNotNull(scheduler.getPendingJob(LocalTaskReminders.JOB_ID))
        assertEquals(ComponentName(app, LocalTaskReminderService::class.java), job.service)
        assertTrue(job.isPeriodic)
        assertTrue(job.isPersisted)
        assertEquals(LocalTaskReminders.INTERVAL_MILLIS, job.intervalMillis)
        assertEquals(android.app.job.JobInfo.NETWORK_TYPE_NONE, job.networkType)
        assertTrue(LocalTaskReminders.status(app).scheduled)
        assertEquals(LocalTaskReminders.EnableResult.ENABLED, LocalTaskReminders.enable(app))
        assertEquals(1, scheduler.allPendingJobs.size)
    }

    @Test fun blockedNotificationsAndSchedulingRejectionDoNotClaimEnabled() {
        shadowOf(manager).setNotificationsEnabled(false)
        assertEquals(LocalTaskReminders.EnableResult.NOTIFICATIONS_BLOCKED, LocalTaskReminders.enable(app))
        assertFalse(LocalTaskReminders.status(app).enabled)
        assertNull(scheduler.getPendingJob(LocalTaskReminders.JOB_ID))
        shadowOf(manager).setNotificationsEnabled(true)
        shadowOf(scheduler).failOnJob(LocalTaskReminders.JOB_ID)
        assertEquals(LocalTaskReminders.EnableResult.SCHEDULE_FAILED, LocalTaskReminders.enable(app))
        assertFalse(LocalTaskReminders.status(app).enabled)
        assertFalse(LocalTaskReminders.status(app).scheduled)
        assertNull(LocalTaskReminders.begin(app))
    }

    @Test fun genericPrivateNotificationHasImmutableExplicitLockedEntryPoint() {
        assertEquals(LocalTaskReminders.EnableResult.ENABLED, LocalTaskReminders.enable(app))
        val token = requireNotNull(LocalTaskReminders.begin(app))
        assertTrue(LocalTaskReminders.run(app, token) { 3L })
        val notice = shadowOf(manager).getNotification(LocalTaskReminders.NOTIFICATION_ID)
        assertNotNull(notice)
        assertEquals(Notification.VISIBILITY_PRIVATE, notice.visibility)
        assertEquals("KRAL görev hatırlatması", notice.extras.getString(Notification.EXTRA_TITLE))
        assertEquals("Bekleyen yerel görevlerini görmek için KRAL kilidini aç.",
            notice.extras.getString(Notification.EXTRA_TEXT))
        assertNotNull(notice.publicVersion)
        val pending = shadowOf(notice.contentIntent)
        assertTrue(pending.isImmutable)
        assertTrue(pending.isActivity)
        assertEquals(ComponentName(app, MainActivity::class.java), pending.savedIntent.component)
        assertEquals(LocalTaskReminders.OPEN_ACTION, pending.savedIntent.action)
        assertNull(pending.savedIntent.extras)
    }

    @Test fun disablingAndReenablingWhileAReadWaitsCannotPostTheOldResult() {
        assertEquals(LocalTaskReminders.EnableResult.ENABLED, LocalTaskReminders.enable(app))
        val old = requireNotNull(LocalTaskReminders.begin(app))
        val reading = CountDownLatch(1)
        val proceed = CountDownLatch(1)
        var posted = true
        val worker = thread {
            posted = LocalTaskReminders.run(app, old) {
                reading.countDown()
                check(proceed.await(3, TimeUnit.SECONDS))
                1L
            }
        }
        try {
            assertTrue(reading.await(3, TimeUnit.SECONDS))
            assertTrue(LocalTaskReminders.disable(app))
            assertEquals(LocalTaskReminders.EnableResult.ENABLED, LocalTaskReminders.enable(app))
        } finally { proceed.countDown() }
        worker.join(3000)
        assertFalse(worker.isAlive)
        assertFalse(posted)
        assertNull(shadowOf(manager).getNotification(LocalTaskReminders.NOTIFICATION_ID))
        assertTrue(LocalTaskReminders.run(app, requireNotNull(LocalTaskReminders.begin(app))) { 1L })
    }

    @Test fun stoppedTokensAndRevokedNotificationsCannotPublishAndEmptyTasksRemoveOldNotice() {
        assertEquals(LocalTaskReminders.EnableResult.ENABLED, LocalTaskReminders.enable(app))
        val token = requireNotNull(LocalTaskReminders.begin(app))
        LocalTaskReminders.stop(token)
        assertFalse(LocalTaskReminders.run(app, token) { 1L })
        val next = requireNotNull(LocalTaskReminders.begin(app))
        assertTrue(LocalTaskReminders.run(app, next) { 1L })
        assertFalse(LocalTaskReminders.run(app, next) { 0L })
        assertNull(shadowOf(manager).getNotification(LocalTaskReminders.NOTIFICATION_ID))
        shadowOf(manager).setNotificationsEnabled(false)
        assertFalse(LocalTaskReminders.run(app, next) { 1L })
        assertNull(shadowOf(manager).getNotification(LocalTaskReminders.NOTIFICATION_ID))
        LocalTaskReminders.disable(app)
        assertFalse(LocalTaskReminders.status(app).enabled)
        assertFalse(LocalTaskReminders.status(app).scheduled)
    }

    @Test fun absentPlaintextAndKeylessFilesAreNeverCreatedMigratedOrGivenNewKeys() {
        val dir = Files.createTempDirectory("kral-reminder-readonly").toFile()
        val database = File(dir, "fixture.db")
        val isolated = object : ContextWrapper(app) {
            override fun getApplicationContext(): Context = this
            override fun getDatabasePath(name: String): File = database
        }
        var keyCalls = 0
        try {
            assertNull(LocalTaskReminders.readPendingTaskCount(isolated) { keyCalls++; null })
            assertEquals(0, keyCalls)
            assertFalse(database.exists())
            val plaintext = "SQLite format 3\u0000".toByteArray() + ByteArray(64)
            database.writeBytes(plaintext)
            assertNull(LocalTaskReminders.readPendingTaskCount(isolated) { keyCalls++; null })
            assertEquals(0, keyCalls)
            assertArrayEquals(plaintext, database.readBytes())
            val cipherLike = ByteArray(80) { 42 }
            database.writeBytes(cipherLike)
            assertNull(LocalTaskReminders.readPendingTaskCount(isolated) { keyCalls++; null })
            assertEquals(1, keyCalls)
            assertArrayEquals(cipherLike, database.readBytes())
            assertEquals(listOf("fixture.db"), dir.list()?.toList())
        } finally { dir.deleteRecursively() }
    }

    @Test @Config(sdk = [33]) fun android13PermissionDenialPreventsScheduling() {
        shadowOf(app).denyPermissions(Manifest.permission.POST_NOTIFICATIONS)
        assertEquals(LocalTaskReminders.EnableResult.NOTIFICATIONS_BLOCKED, LocalTaskReminders.enable(app))
        assertFalse(LocalTaskReminders.status(app).enabled)
        assertNull(scheduler.getPendingJob(LocalTaskReminders.JOB_ID))
    }
}
