package com.example.gptasistan

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.time.Instant

// The mem schema intentionally preserves the original Python assistant.py fields.
// The old Termux mem.db is not silently imported; the Android app owns this new DB.
class KralStore(context: Context) : SQLiteOpenHelper(context, "kral_local.db", null, 1) {
    override fun onCreate(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE mem(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, text TEXT NOT NULL)")
        db.execSQL("CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT NOT NULL, done INTEGER NOT NULL DEFAULT 0)")
    }
    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        // No destructive migration. Explicit migrations are required for new versions.
        require(oldVersion == newVersion)
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
