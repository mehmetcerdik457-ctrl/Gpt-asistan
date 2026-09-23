package com.mehmetcerdik.ownerai;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;

import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Locale;

public final class BridgeClient {
    public static final String BRIDGE_PACKAGE="com.mehmetcerdik.ownerbridge";
    public static final String BRIDGE_AUTHORITY="com.mehmetcerdik.ownerbridge.control";
    public static final String EXPECTED_SIGNER="279084a36b7c17a1663bfba5fe1c5bdac974f8ef4ce56b21000d882493e39448";
    private BridgeClient(){}

    public static String getBridgeSigner(Context c){try{PackageManager pm=c.getPackageManager();Signature[] sigs;if(Build.VERSION.SDK_INT>=28){PackageInfo pi=pm.getPackageInfo(BRIDGE_PACKAGE,PackageManager.GET_SIGNING_CERTIFICATES);SigningInfo si=pi.signingInfo;if(si==null)return null;sigs=si.getApkContentsSigners();}else{@SuppressWarnings("deprecation") PackageInfo pi=pm.getPackageInfo(BRIDGE_PACKAGE,PackageManager.GET_SIGNATURES);@SuppressWarnings("deprecation") Signature[] legacy=pi.signatures;sigs=legacy;}if(sigs==null||sigs.length!=1)return null;MessageDigest md=MessageDigest.getInstance("SHA-256");byte[] hash=md.digest(sigs[0].toByteArray());StringBuilder sb=new StringBuilder(hash.length*2);for(byte b:hash)sb.append(String.format(Locale.ROOT,"%02x",b&0xff));return sb.toString();}catch(Throwable t){return null;}}
    public static boolean verifyBridge(Context c){String s=getBridgeSigner(c);return s!=null&&EXPECTED_SIGNER.equalsIgnoreCase(s);}
    public static Bundle call(Context c,String method,Bundle extras){if(!verifyBridge(c))return fail("BRIDGE_SIGNER_MISMATCH_OR_NOT_INSTALLED");try{Bundle out=c.getContentResolver().call(Uri.parse("content://"+BRIDGE_AUTHORITY),method,null,extras);return out==null?fail("NULL_PROVIDER_RESULT"):out;}catch(Throwable t){return fail("BRIDGE_CALL_FAILED");}}
    public static Bundle status(Context c){return call(c,"status",null);} public static Bundle arm(Context c,long ttlMs){Bundle x=new Bundle();x.putLong("ttl_ms",ttlMs);return call(c,"arm",x);} public static Bundle stop(Context c){return call(c,"stop",null);}
    public static Bundle listPackages(Context c){return call(c,"listPackages",null);} public static Bundle inspectPackage(Context c,String pkg){Bundle x=new Bundle();x.putString("package",pkg);return call(c,"inspectPackage",x);} public static Bundle approvePackage(Context c,String pkg){Bundle x=new Bundle();x.putString("package",pkg);return call(c,"approvePackage",x);}
    public static Bundle listApprovedPackages(Context c){return call(c,"listApprovedPackages",null);} public static Bundle revokePackage(Context c,String pkg){Bundle x=new Bundle();x.putString("package",pkg);return call(c,"revokePackage",x);} public static Bundle revokeAllNonDefaultPackages(Context c){return call(c,"revokeAllNonDefaultPackages",null);} public static Bundle verifyAudit(Context c){return call(c,"verifyAudit",null);}
    public static Bundle screenRead(Context c){return call(c,"screenRead",null);} public static Bundle clickText(Context c,String text){Bundle x=new Bundle();x.putString("text",text);return call(c,"clickText",x);} public static Bundle typeText(Context c,String selector,String text,boolean secret){Bundle x=new Bundle();x.putString("selector",selector);x.putString("text",text);x.putBoolean("secret",secret);return call(c,"typeText",x);}
    public static Bundle scroll(Context c,boolean forward){Bundle x=new Bundle();x.putBoolean("forward",forward);return call(c,"scroll",x);} public static Bundle swipe(Context c,float sx,float sy,float ex,float ey,long durationMs){Bundle x=new Bundle();x.putFloat("sx",sx);x.putFloat("sy",sy);x.putFloat("ex",ex);x.putFloat("ey",ey);x.putLong("duration_ms",durationMs);return call(c,"swipe",x);} public static Bundle globalAction(Context c,String action){Bundle x=new Bundle();x.putString("action",action);return call(c,"globalAction",x);} public static Bundle launchApp(Context c,String pkg){Bundle x=new Bundle();x.putString("package",pkg);return call(c,"launchApp",x);} public static Bundle verifyPostcondition(Context c,String kind,String expected){Bundle x=new Bundle();x.putString("kind",kind);x.putString("expected",expected);return call(c,"verifyPostcondition",x);}
    public static ArrayList<String> packageList(Bundle b){return b==null?null:b.getStringArrayList("packages");}
    private static Bundle fail(String reason){Bundle b=new Bundle();b.putBoolean("ok",false);b.putString("status","FAILED");b.putString("failure",reason);return b;}
}
