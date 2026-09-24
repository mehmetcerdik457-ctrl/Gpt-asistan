package com.mehmetcerdik.ownerai;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.security.MessageDigest;
import java.util.Locale;

public final class OwnerMemory extends SQLiteOpenHelper {
    private static final String DB = "mehmet_owner_memory.db";
    private static final int VERSION = 1;

    public OwnerMemory(Context c) { super(c, DB, null, VERSION); }

    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE memory(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL)");
        db.execSQL("CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, event TEXT NOT NULL, status TEXT NOT NULL, detail_hash TEXT NOT NULL)");
        db.execSQL("CREATE INDEX idx_memory_ts ON memory(ts DESC)");
        db.execSQL("CREATE INDEX idx_audit_ts ON audit(ts DESC)");
    }

    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {}

    public synchronized long remember(String kind, String text) {
        if (text == null) return -1;
        String clean = text.trim();
        if (clean.isEmpty() || clean.length() > 8000) return -1;
        ContentValues v = new ContentValues();
        v.put("ts", System.currentTimeMillis());
        v.put("kind", kind == null ? "owner" : kind);
        v.put("text", clean);
        return getWritableDatabase().insert("memory", null, v);
    }

    public synchronized JSONArray recent(int limit) {
        int safe = Math.max(1, Math.min(limit, 50));
        JSONArray out = new JSONArray();
        try (Cursor c = getReadableDatabase().rawQuery(
                "SELECT ts,kind,text FROM memory ORDER BY id DESC LIMIT ?", new String[]{String.valueOf(safe)})) {
            while (c.moveToNext()) {
                JSONObject o = new JSONObject();
                o.put("ts", c.getLong(0));
                o.put("kind", c.getString(1));
                o.put("text", c.getString(2));
                out.put(o);
            }
        } catch (Exception ignored) {}
        return out;
    }

    public synchronized void audit(String event, String status, String detail) {
        ContentValues v = new ContentValues();
        v.put("ts", System.currentTimeMillis());
        v.put("event", event == null ? "UNKNOWN" : event);
        v.put("status", status == null ? "UNKNOWN" : status);
        v.put("detail_hash", sha256(detail == null ? "" : detail));
        getWritableDatabase().insert("audit", null, v);
    }

    public synchronized JSONArray recentAudit(int limit) {
        int safe = Math.max(1, Math.min(limit, 100));
        JSONArray out = new JSONArray();
        try (Cursor c = getReadableDatabase().rawQuery(
                "SELECT ts,event,status,detail_hash FROM audit ORDER BY id DESC LIMIT ?", new String[]{String.valueOf(safe)})) {
            while (c.moveToNext()) {
                JSONObject o = new JSONObject();
                o.put("ts", c.getLong(0));
                o.put("event", c.getString(1));
                o.put("status", c.getString(2));
                o.put("detail_hash", c.getString(3));
                out.put(o);
            }
        } catch (Exception ignored) {}
        return out;
    }

    private static String sha256(String s) {
        try {
            byte[] d = MessageDigest.getInstance("SHA-256").digest(s.getBytes(java.nio.charset.StandardCharsets.UTF_8));
            StringBuilder b = new StringBuilder();
            for (byte x : d) b.append(String.format(Locale.ROOT, "%02x", x & 0xff));
            return b.toString();
        } catch (Exception e) {
            return "HASH_ERROR";
        }
    }
}
