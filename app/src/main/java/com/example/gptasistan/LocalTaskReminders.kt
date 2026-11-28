package com.example.gptasistan

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobService
import android.app.job.JobScheduler
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import java.io.FileInputStream
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread
import net.zetetic.database.sqlcipher.SQLiteDatabase

/** Explicitly enabled, local-only reminders; no model execution or owner signing. */
internal object LocalTaskReminders {
    const val JOB_ID = 18418
    const val NOTIFICATION_ID = 18419
    const val CHANNEL_ID = "kral_local_tasks_v1"
    const val OPEN_ACTION = "com.example.gptasistan.action.LOCAL_TASK_REMINDER"
    const val PREFS = "kral_local_task_reminders"
    const val ENABLED = "enabled"
    private const val GENERATION = "generation"
    const val INTERVAL_MILLIS = 15 * 60 * 1000L
    private val lock = Any()
    private var epoch = 0L

    data class Status(val enabled: Boolean, val scheduled: Boolean, val notificationsAllowed: Boolean)
    enum class EnableResult { ENABLED, NOTIFICATIONS_BLOCKED, SCHEDULE_FAILED, STORAGE_FAILED }
    internal data class RunToken(val epoch: Long, val generation: Long, val stopped: AtomicBoolean)

    fun status(context: Context): Status = synchronized(lock) {
        val app = context.applicationContext
        val enabled = prefs(app).getBoolean(ENABLED, false)
        val scheduled = runCatching {
            val job = scheduler(app).getPendingJob(JOB_ID)
            job != null && job.service == ComponentName(app, LocalTaskReminderService::class.java) &&
                job.isPeriodic && job.isPersisted && job.intervalMillis >= INTERVAL_MILLIS
        }.getOrDefault(false)
        Status(enabled, scheduled, notificationsAllowed(app))
    }

    /** The caller obtains fresh owner credentials and explains persistent consent first. */
    fun enable(context: Context): EnableResult = synchronized(lock) {
        val app = context.applicationContext
        try { createChannel(app) } catch (_: Exception) { return@synchronized EnableResult.NOTIFICATIONS_BLOCKED }
        if (!notificationsAllowed(app)) return@synchronized EnableResult.NOTIFICATIONS_BLOCKED
        epoch++
        val settings = prefs(app)
        val generation = settings.getLong(GENERATION, 0L) + 1L
        if (!settings.edit().putBoolean(ENABLED, true).putLong(GENERATION, generation).commit()) {
            failClosed(app)
            return@synchronized EnableResult.STORAGE_FAILED
        }
        val accepted = runCatching {
            scheduler(app).schedule(JobInfo.Builder(JOB_ID, ComponentName(app, LocalTaskReminderService::class.java))
                .setPersisted(true).setPeriodic(INTERVAL_MILLIS).build()) == JobScheduler.RESULT_SUCCESS
        }.getOrDefault(false)
        if (!accepted) {
            failClosed(app)
            EnableResult.SCHEDULE_FAILED
        } else EnableResult.ENABLED
    }

    /** Cancels persisted work and its notification even if a prior read is still running. */
    fun disable(context: Context): Boolean = synchronized(lock) {
        val app = context.applicationContext
        epoch++
        val settings = prefs(app)
        val saved = settings.edit().putBoolean(ENABLED, false)
            .putLong(GENERATION, settings.getLong(GENERATION, 0L) + 1L).commit()
        runCatching { scheduler(app).cancel(JOB_ID) }
        runCatching { notifications(app).cancel(NOTIFICATION_ID) }
        saved
    }

    private fun failClosed(context: Context) {
        epoch++
        prefs(context).edit().putBoolean(ENABLED, false).commit()
        runCatching { scheduler(context).cancel(JOB_ID) }
        runCatching { notifications(context).cancel(NOTIFICATION_ID) }
    }

    internal fun begin(context: Context): RunToken? = synchronized(lock) {
        val settings = prefs(context)
        if (!settings.getBoolean(ENABLED, false)) return@synchronized null
        RunToken(epoch, settings.getLong(GENERATION, 0L), AtomicBoolean(false))
    }

    internal fun stop(token: RunToken) = synchronized(lock) { token.stopped.set(true) }

    /** Reading is outside the notification/consent lock; the token is rechecked after it. */
    internal fun run(context: Context, token: RunToken, readCount: () -> Long? = {
        readPendingTaskCount(context)
    }): Boolean {
        val pending = runCatching { readCount() }.getOrNull()
        return synchronized(lock) {
            val app = context.applicationContext
            val settings = prefs(app)
            if (token.stopped.get() || token.epoch != epoch || !settings.getBoolean(ENABLED, false) ||
                token.generation != settings.getLong(GENERATION, 0L)) return@synchronized false
            runCatching { createChannel(app) }
            if (pending == null || pending <= 0 || !notificationsAllowed(app)) {
                runCatching { notifications(app).cancel(NOTIFICATION_ID) }
                return@synchronized false
            }
            try {
                val intent = Intent(app, MainActivity::class.java)
                    .setAction(OPEN_ACTION)
                    .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                val open = PendingIntent.getActivity(app, NOTIFICATION_ID, intent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
                val publicNotice = Notification.Builder(app, CHANNEL_ID)
                    .setSmallIcon(R.mipmap.ic_launcher)
                    .setContentTitle("KRAL")
                    .setContentText("Yerel görev hatırlatması")
                    .setVisibility(Notification.VISIBILITY_PUBLIC)
                    .build()
                val notice = Notification.Builder(app, CHANNEL_ID)
                    .setSmallIcon(R.mipmap.ic_launcher)
                    .setContentTitle("KRAL görev hatırlatması")
                    .setContentText("Bekleyen yerel görevlerini görmek için KRAL kilidini aç.")
                    .setContentIntent(open).setAutoCancel(true).setOnlyAlertOnce(true)
                    .setCategory(Notification.CATEGORY_REMINDER)
                    .setVisibility(Notification.VISIBILITY_PRIVATE).setPublicVersion(publicNotice)
                    .build()
                notifications(app).notify(NOTIFICATION_ID, notice)
                true
            } catch (_: Exception) { false }
        }
    }

    /** No helper constructor, writable connection, migration, key creation, or private row text. */
    internal fun readPendingTaskCount(context: Context, existingKey: () -> ByteArray? = {
        AndroidDatabaseKeyProvider.existingKey(context)
    }): Long? {
        val file = context.applicationContext.getDatabasePath(KralStore.DATABASE_NAME)
        if (!file.isFile || file.length() < 16L) return null
        return try {
            val header = ByteArray(16)
            FileInputStream(file).use { if (it.read(header) != header.size) return null }
            if (header.contentEquals("SQLite format 3\u0000".toByteArray(Charsets.US_ASCII))) return null
            val key = existingKey()?.copyOf() ?: return null
            if (key.size != 32) { key.fill(0); return null }
            try {
                System.loadLibrary("sqlcipher")
                SQLiteDatabase.openDatabase(file.absolutePath, key, null, SQLiteDatabase.OPEN_READONLY, null, null).use { db ->
                    if (db.version != KralStore.DATABASE_VERSION) return null
                    db.rawQuery("SELECT COUNT(*) FROM tasks WHERE done=0", null).use { rows ->
                        if (rows.moveToFirst()) rows.getLong(0).takeIf { it >= 0L } else null
                    }
                }
            } finally { key.fill(0) }
        } catch (_: Exception) { null } catch (_: LinkageError) { null }
    }

    private fun notificationsAllowed(context: Context): Boolean = runCatching {
        if (Build.VERSION.SDK_INT >= 33 && context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED) return@runCatching false
        val manager = notifications(context)
        val channel = manager.getNotificationChannel(CHANNEL_ID)
        manager.areNotificationsEnabled() && channel != null &&
            channel.importance != NotificationManager.IMPORTANCE_NONE
    }.getOrDefault(false)

    private fun createChannel(context: Context) {
        notifications(context).createNotificationChannel(NotificationChannel(CHANNEL_ID,
            "Yerel görev hatırlatmaları", NotificationManager.IMPORTANCE_DEFAULT).apply {
            description = "Açık rızayla, bekleyen yerel görevler için özel içerik göstermeyen hatırlatmalar."
            lockscreenVisibility = Notification.VISIBILITY_PRIVATE
        })
    }

    private fun prefs(context: Context) = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
    private fun scheduler(context: Context) = context.getSystemService(Context.JOB_SCHEDULER_SERVICE) as JobScheduler
    private fun notifications(context: Context) = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
}

/** Android owns scheduling across process death/reboot; force-stop and OS restrictions still apply. */
class LocalTaskReminderService : JobService() {
    private val runs = mutableMapOf<JobParameters, LocalTaskReminders.RunToken>()

    override fun onStartJob(params: JobParameters): Boolean {
        if (params.jobId != LocalTaskReminders.JOB_ID) return false
        val token = LocalTaskReminders.begin(this) ?: return false
        synchronized(runs) { runs[params] = token }
        try {
            thread(name = "kral-local-task-reminder") {
                try { LocalTaskReminders.run(applicationContext, token) } finally {
                    synchronized(runs) { runs.remove(params) }
                    jobFinished(params, false)
                }
            }
        } catch (_: Exception) {
            synchronized(runs) { runs.remove(params) }
            LocalTaskReminders.stop(token)
            return false
        }
        return true
    }

    override fun onStopJob(params: JobParameters): Boolean {
        synchronized(runs) { runs.remove(params) }?.let(LocalTaskReminders::stop)
        return false
    }

    override fun onDestroy() {
        val active = synchronized(runs) { runs.values.toList().also { runs.clear() } }
        active.forEach(LocalTaskReminders::stop)
        super.onDestroy()
    }
}
