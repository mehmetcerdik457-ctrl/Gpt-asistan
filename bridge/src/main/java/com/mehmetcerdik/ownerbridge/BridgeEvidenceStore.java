package com.mehmetcerdik.ownerbridge;

import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;

final class BridgeEvidenceStore {
    private static final String PREFS="bridge_final_evidence", KEY="events";
    private static final int MAX=120;
    private BridgeEvidenceStore(){}
    static synchronized void clear(Context c){ c.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY,"[]").commit(); }
    static synchronized void record(Context c,String action,String status,String detail){
        JSONArray old=read(c), out=new JSONArray(); int start=Math.max(0,old.length()-(MAX-1));
        for(int i=start;i<old.length();i++) out.put(old.opt(i));
        JSONObject e=new JSONObject();
        try{e.put("timestamp_ms",System.currentTimeMillis());e.put("action",action==null?"":action);
            e.put("status",status==null?"":status);e.put("detail_hash",BridgeSecurity.sha256String(detail));}catch(Throwable ignored){}
        out.put(e); c.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY,out.toString()).commit();
    }
    static synchronized JSONArray read(Context c){
        try{return new JSONArray(c.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString(KEY,"[]"));}catch(Throwable t){return new JSONArray();}
    }
    static boolean hasPass(Context c,String action){
        JSONArray a=read(c); for(int i=0;i<a.length();i++){JSONObject e=a.optJSONObject(i);
            if(e!=null&&action.equals(e.optString("action"))&&"PASS".equals(e.optString("status"))) return true;}
        return false;
    }
}