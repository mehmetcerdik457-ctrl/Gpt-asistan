package com.mehmetcerdik.ownerai;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import org.json.JSONArray;
import org.json.JSONObject;

public final class OwnerMemory extends SQLiteOpenHelper {
    private static final String DB = "mehmet_owner_memory.db";
    private static final int VERSION = 3;

    public OwnerMemory(Context c) { super(c, DB, null, VERSION); }

    @Override public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE memory(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL)");
        db.execSQL("CREATE TABLE audit_chain(id INTEGER PRIMARY KEY AUTOINCREMENT, seq INTEGER NOT NULL UNIQUE, ts INTEGER NOT NULL, event TEXT NOT NULL, status TEXT NOT NULL, detail_hash TEXT NOT NULL, previous_record_hash TEXT NOT NULL, record_hash TEXT NOT NULL, record_mac TEXT NOT NULL)");
        db.execSQL("CREATE INDEX idx_memory_ts ON memory(ts DESC)");
        db.execSQL("CREATE INDEX idx_audit_chain_seq ON audit_chain(seq)");
    }

    @Override public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
        if (oldVersion < 2) {
            db.beginTransaction();
            try (Cursor c = db.rawQuery("SELECT id,text FROM memory", null)) {
                while (c.moveToNext()) {
                    long id = c.getLong(0);
                    String stored = c.getString(1);
                    if (SecureSecrets.isEncryptedMemoryBlob(stored)) continue;
                    ContentValues v = new ContentValues();
                    v.put("text", SecureSecrets.encryptMemory(stored == null ? "" : stored));
                    db.update("memory", v, "id=?", new String[]{String.valueOf(id)});
                }
                db.setTransactionSuccessful();
            } finally {
                db.endTransaction();
            }
        }
        if (oldVersion < 3) {
            db.execSQL("CREATE TABLE IF NOT EXISTS audit_chain(id INTEGER PRIMARY KEY AUTOINCREMENT, seq INTEGER NOT NULL UNIQUE, ts INTEGER NOT NULL, event TEXT NOT NULL, status TEXT NOT NULL, detail_hash TEXT NOT NULL, previous_record_hash TEXT NOT NULL, record_hash TEXT NOT NULL, record_mac TEXT NOT NULL)");
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_audit_chain_seq ON audit_chain(seq)");
        }
    }

    public synchronized long remember(String kind, String text) {
        if (text == null) return -1;
        String clean = text.trim();
        if (clean.isEmpty() || clean.length() > 8000) return -1;
        ContentValues v = new ContentValues();
        v.put("ts", System.currentTimeMillis());
        v.put("kind", kind == null ? "owner" : kind);
        v.put("text", SecureSecrets.encryptMemory(clean));
        return getWritableDatabase().insert("memory", null, v);
    }

    public synchronized JSONArray recent(int limit) {
        int safe = Math.max(1, Math.min(limit, 50));
        JSONArray out = new JSONArray();
        try (Cursor c = getReadableDatabase().rawQuery(
                "SELECT ts,kind,text FROM memory ORDER BY id DESC LIMIT ?", new String[]{String.valueOf(safe)})) {
            while (c.moveToNext()) {
                String decrypted = SecureSecrets.decryptMemory(c.getString(2));
                if (decrypted == null) continue;
                JSONObject o = new JSONObject();
                o.put("ts", c.getLong(0));
                o.put("kind", c.getString(1));
                o.put("text", decrypted);
                out.put(o);
            }
        } catch (Exception ignored) {}
        return out;
    }

    public synchronized void audit(String event, String status, String detail) {
        SQLiteDatabase db = getWritableDatabase();
        db.beginTransaction();
        try {
            long seq = 1L;
            String previous = "GENESIS";
            try (Cursor c = db.rawQuery("SELECT seq,record_hash FROM audit_chain ORDER BY seq DESC LIMIT 1", null)) {
                if (c.moveToFirst()) {
                    seq = c.getLong(0) + 1L;
                    previous = c.getString(1);
                }
            }
            long ts = System.currentTimeMillis();
            String cleanEvent = event == null ? "UNKNOWN" : event;
            String cleanStatus = status == null ? "UNKNOWN" : status;
            String detailHash = AuditIntegrity.sha256(detail == null ? "" : detail);
            String recordHash = AuditIntegrity.recordHash(seq, ts, cleanEvent, cleanStatus, detailHash, previous);
            ContentValues v = new ContentValues();
            v.put("seq", seq);
            v.put("ts", ts);
            v.put("event", cleanEvent);
            v.put("status", cleanStatus);
            v.put("detail_hash", detailHash);
            v.put("previous_record_hash", previous);
            v.put("record_hash", recordHash);
            v.put("record_mac", AuditIntegrity.mac(recordHash));
            if (db.insertOrThrow("audit_chain", null, v) < 0) throw new IllegalStateException("AUDIT_INSERT_FAILED");
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    public synchronized boolean verifyAuditChain() {
        long expectedSeq = 1L;
        String previous = "GENESIS";
        try (Cursor c = getReadableDatabase().rawQuery(
                "SELECT seq,ts,event,status,detail_hash,previous_record_hash,record_hash,record_mac FROM audit_chain ORDER BY seq ASC", null)) {
            while (c.moveToNext()) {
                long seq = c.getLong(0);
                long ts = c.getLong(1);
                String event = c.getString(2);
                String status = c.getString(3);
                String detailHash = c.getString(4);
                String storedPrevious = c.getString(5);
                String storedHash = c.getString(6);
                String storedMac = c.getString(7);
                if (seq != expectedSeq || !previous.equals(storedPrevious)) return false;
                String expectedHash = AuditIntegrity.recordHash(seq, ts, event, status, detailHash, previous);
                if (!expectedHash.equals(storedHash) || !AuditIntegrity.verifyMac(storedHash, storedMac)) return false;
                previous = storedHash;
                expectedSeq++;
            }
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public synchronized JSONArray recentAudit(int limit) {
        int safe = Math.max(1, Math.min(limit, 100));
        JSONArray out = new JSONArray();
        try (Cursor c = getReadableDatabase().rawQuery(
                "SELECT seq,ts,event,status,detail_hash,previous_record_hash,record_hash FROM audit_chain ORDER BY seq DESC LIMIT ?",
                new String[]{String.valueOf(safe)})) {
            while (c.moveToNext()) {
                JSONObject o = new JSONObject();
                o.put("sequence", c.getLong(0));
                o.put("timestamp", c.getLong(1));
                o.put("event", c.getString(2));
                o.put("status", c.getString(3));
                o.put("detail_hash", c.getString(4));
                o.put("previous_record_hash", c.getString(5));
                o.put("record_hash", c.getString(6));
                out.put(o);
            }
        } catch (Exception ignored) {}
        return out;
    }
}
