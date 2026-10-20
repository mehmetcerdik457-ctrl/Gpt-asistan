package com.example.gptasistan

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.time.Instant

// The mem schema intentionally preserves the original Python assistant.py fields.
// The old Termux mem.db is not silently imported; the Android app owns this new DB.
data class ChatEntry(val id: Long, val ts: String, val role: String, val text: String)

class KralStore(context: Context) : SQLiteOpenHelper(context, "kral_local.db", null, 2) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE mem(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, text TEXT NOT NULL)")
        db.execSQL("CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)")
        createChatTable(db)
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        require(oldVersion == 1 && newVersion == 2) { "Desteklenmeyen veritabanı geçişi" }
        createChatTable(db)
    }

    private fun createChatTable(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE chat_messages(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, " +
            "role TEXT NOT NULL CHECK(role IN ('user','assistant','system')), text TEXT NOT NULL)")
    }

    fun saveMessage(role: String, text: String) {
        require(role in setOf("user", "assistant", "system")) { "Geçersiz mesaj rolü" }
        require(text.isNotBlank()) { "Boş mesaj kaydedilemez" }
        val values = android.content.ContentValues().apply {
            put("ts", Instant.now().toString())
            put("role", role)
            put("text", text)
        }
        writableDatabase.insertOrThrow("chat_messages", null, values)
    }

    fun history(limit: Int = 200): List<ChatEntry> {
        require(limit in 1..1000) { "Geçersiz geçmiş sınırı" }
        val entries = mutableListOf<ChatEntry>()
        readableDatabase.rawQuery(
            "SELECT id,ts,role,text FROM chat_messages ORDER BY id DESC LIMIT ?",
            arrayOf(limit.toString())
        ).use { cursor ->
            while (cursor.moveToNext()) entries.add(ChatEntry(
                cursor.getLong(0), cursor.getString(1), cursor.getString(2), cursor.getString(3)
            ))
        }
        return entries.asReversed()
    }

    fun saveMemory(text: String) {
        val values = android.content.ContentValues().apply {
            put("ts", Instant.now().toString())
            put("text", text)
        }
        writableDatabase.insertOrThrow("mem", null, values)
    }
    fun memory(): String {
        val out = mutableListOf<String>()
        readableDatabase.rawQuery("SELECT ts,text FROM mem ORDER BY id DESC LIMIT 20", null).use { c ->
            while (c.moveToNext()) out.add(c.getString(0) + ": " + c.getString(1))
        }
        return if (out.isEmpty()) "(kayıt yok)" else out.asReversed().joinToString("\n")
    }
    /** Local-only recall; Unicode Turkish matching does not send notes to any provider. */
    fun recall(query: String, limit: Int = 20): String {
        require(query.isNotBlank() && query.length <= 16000)
        require(limit in 1..100)
        val locale = java.util.Locale("tr", "TR")
        val terms = query.trim().lowercase(locale).split(Regex("\\s+")).distinct()
        val matches = mutableListOf<String>()
        readableDatabase.rawQuery("SELECT ts,text FROM mem ORDER BY id DESC", null).use { cursor ->
            while (matches.size < limit && cursor.moveToNext()) {
                val note = cursor.getString(1)
                val searchable = note.lowercase(locale)
                if (terms.all { searchable.contains(it) }) matches.add(cursor.getString(0) + ": " + note)
            }
        }
        return if (matches.isEmpty()) "(eşleşen bilgi yok)" else matches.asReversed().joinToString("\n")
    }

    fun addTask(title: String) {
        val values = android.content.ContentValues().apply {
            put("title", title)
            put("done", 0)
        }
        writableDatabase.insertOrThrow("tasks", null, values)
    }
    fun finishTask(id: Long): Boolean {
        val values = android.content.ContentValues().apply { put("done", 1) }
        return writableDatabase.update("tasks", values, "id=? AND done=0", arrayOf(id.toString())) == 1
    }
    fun tasks(): String {
        val out = mutableListOf<String>()
        readableDatabase.rawQuery("SELECT id,title,done FROM tasks ORDER BY id DESC LIMIT 30", null).use { c ->
            while (c.moveToNext()) {
                out.add("#" + c.getLong(0) + " " + if (c.getInt(2) == 1) "[tamam] " + c.getString(1)
                    else "[bekliyor] " + c.getString(1))
            }
        }
        return if (out.isEmpty()) "(görev yok)" else out.asReversed().joinToString("\n")
    }
}
