package com.mehmetcerdik.ownerbridge;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.os.Build;
import android.os.Process;
import android.os.SystemClock;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

final class BridgeSecurity {
    static final String CORE_PACKAGE="com.mehmetcerdik.ownerai";
    static final String CORE_SIGNER="279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448";
    static final String WORKER_PACKAGE="com.codespaceapps.aichat";
    static final String WORKER_SIGNER="7b4a4b483ad4fdfa7bcab3c4ba9fd5a0461cab208fc7120a4d8d2f4901b3a097";
    static final long MAX_ARM_MS=10*60*1000L, DEFAULT_ARM_MS=5*60*1000L;
    private static final String PREFS="mehm_owner_bridge_state_v41", KEY_APPROVED="approved_package_signers",
        KEY_UNTIL="armed_until_elapsed", KEY_SESSION="armed_session", KEY_PID="armed_pid", KEY_EMERGENCY="emergency_stop";
    private static final String SESSION=UUID.randomUUID().toString();
    private BridgeSecurity(){}
    static SharedPreferences prefs(Context c){return c.getSharedPreferences(PREFS,Context.MODE_PRIVATE);}
    static void ensureDefaults(Context c){
        SharedPreferences p=prefs(c); if(p.getStringSet(KEY_APPROVED,null)==null){
            HashSet<String>s=new HashSet<>();s.add(WORKER_PACKAGE+"|"+WORKER_SIGNER);
            p.edit().putStringSet(KEY_APPROVED,s).putBoolean(KEY_EMERGENCY,true).putLong(KEY_UNTIL,0)
             .putString(KEY_SESSION,"").putInt(KEY_PID,-1).commit();
        }
    }
    static String getSigner(Context c,String pkg){
        try{
            PackageManager pm=c.getPackageManager(); Signature[] sigs;
            if(Build.VERSION.SDK_INT>=28){PackageInfo pi=pm.getPackageInfo(pkg,PackageManager.GET_SIGNING_CERTIFICATES);
                SigningInfo si=pi.signingInfo;if(si==null)return null;sigs=si.getApkContentsSigners();}
            else{@SuppressWarnings("deprecation") PackageInfo pi=pm.getPackageInfo(pkg,PackageManager.GET_SIGNATURES);
                @SuppressWarnings("deprecation") Signature[] legacy=pi.signatures;sigs=legacy;}
            if(sigs==null||sigs.length!=1)return null;return sha256Bytes(sigs[0].toByteArray());
        }catch(Throwable t){return null;}
    }
    static boolean verifyCore(Context c){String s=getSigner(c,CORE_PACKAGE);return s!=null&&CORE_SIGNER.equalsIgnoreCase(s);}
    static boolean isEmergencyStopped(Context c){return prefs(c).getBoolean(KEY_EMERGENCY,true);}
    static boolean isArmed(Context c){
        SharedPreferences p=prefs(c);return !p.getBoolean(KEY_EMERGENCY,true)&&SESSION.equals(p.getString(KEY_SESSION,""))
          &&Process.myPid()==p.getInt(KEY_PID,-1)&&p.getLong(KEY_UNTIL,0)>0&&SystemClock.elapsedRealtime()<=p.getLong(KEY_UNTIL,0);
    }
    static long arm(Context c,long requested){
        long ttl=requested<=0?DEFAULT_ARM_MS:Math.min(requested,MAX_ARM_MS), until=SystemClock.elapsedRealtime()+ttl;
        prefs(c).edit().putBoolean(KEY_EMERGENCY,false).putLong(KEY_UNTIL,until).putString(KEY_SESSION,SESSION)
         .putInt(KEY_PID,Process.myPid()).commit();BridgeEvidenceStore.record(c,"ARM","PASS","ttl="+ttl);return until;
    }
    static void stop(Context c){prefs(c).edit().putBoolean(KEY_EMERGENCY,true).putLong(KEY_UNTIL,0).putString(KEY_SESSION,"")
      .putInt(KEY_PID,-1).commit();BridgeEvidenceStore.record(c,"EMERGENCY_STOP","PASS","");}
    static String approveInstalledPackage(Context c,String pkg){
        if(!validPackageName(pkg))return null;String signer=getSigner(c,pkg);if(signer==null)return null;
        HashSet<String> set=new HashSet<>(prefs(c).getStringSet(KEY_APPROVED,new HashSet<>()));set.removeIf(v->v.startsWith(pkg+"|"));
        set.add(pkg+"|"+signer.toLowerCase(Locale.ROOT));prefs(c).edit().putStringSet(KEY_APPROVED,set).commit();
        BridgeEvidenceStore.record(c,"APPROVE_PACKAGE","PASS",pkg+"|"+signer);return signer;
    }
    static boolean revokePackage(Context c,String pkg){
        if(WORKER_PACKAGE.equals(pkg))return false;HashSet<String>set=new HashSet<>(prefs(c).getStringSet(KEY_APPROVED,new HashSet<>()));
        boolean ch=set.removeIf(v->v.startsWith(pkg+"|"));if(ch)prefs(c).edit().putStringSet(KEY_APPROVED,set).commit();
        BridgeEvidenceStore.record(c,"REVOKE_PACKAGE",ch?"PASS":"NOOP",pkg);return ch;
    }
    static boolean isPackageApproved(Context c,String pkg){
        if(!validPackageName(pkg))return false;String s=getSigner(c,pkg);if(s==null)return false;
        Set<String> set=prefs(c).getStringSet(KEY_APPROVED,new HashSet<>());return set.contains(pkg+"|"+s.toLowerCase(Locale.ROOT));
    }
    static boolean validPackageName(String p){return p!=null&&p.length()>=3&&p.length()<=255&&p.matches("[A-Za-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+");}
    static String sha256String(String s){return sha256Bytes((s==null?"":s).getBytes(StandardCharsets.UTF_8));}
    static String sha256Bytes(byte[] data){try{byte[]o=MessageDigest.getInstance("SHA-256").digest(data);StringBuilder b=new StringBuilder();
      for(byte x:o)b.append(String.format(Locale.ROOT,"%02x",x&255));return b.toString();}catch(Throwable t){return "HASH_ERROR";}}
}