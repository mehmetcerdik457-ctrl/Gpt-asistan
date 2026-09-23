package com.mehmetcerdik.ownerbridge;
import android.content.ContentProvider;import android.content.ContentValues;import android.content.Context;import android.content.pm.PackageManager;import android.database.Cursor;import android.net.Uri;import android.os.Binder;import android.os.Bundle;
public final class BridgeControlProvider extends ContentProvider {
 @Override public boolean onCreate(){Context c=getContext();if(c!=null)BridgeSecurity.ensureDefaults(c);return true;}
 @Override public String getType(Uri u){return null;}@Override public Cursor query(Uri u,String[]p,String s,String[]a,String o){return null;}@Override public Uri insert(Uri u,ContentValues v){return null;}@Override public int delete(Uri u,String s,String[]a){return 0;}@Override public int update(Uri u,ContentValues v,String s,String[]a){return 0;}
 @Override public Bundle call(String m,String a,Bundle x){Context c=getContext();if(c==null)return fail("NO_CONTEXT");if(!auth(c))return fail("CALLER_UID_PACKAGE_SIGNER_AUTH_FAILED");if(m==null)return fail("NULL_METHOD");BridgeAccessibilityService s=BridgeAccessibilityService.instance();
  switch(m){
   case"status":return status(c,s);
   case"arm":{long ttl=x==null?BridgeSecurity.DEFAULT_ARM_MS:x.getLong("ttl_ms",BridgeSecurity.DEFAULT_ARM_MS);long until=BridgeSecurity.arm(c,ttl);Bundle b=status(c,s);b.putLong("armed_until_elapsed",until);return b;}
   case"stop":BridgeSecurity.stop(c);return status(c,s);
   case"approvePackage":{if(!BridgeSecurity.isArmed(c))return fail("NOT_ARMED_OR_EMERGENCY_STOP");String p=x==null?null:x.getString("package");String sig=BridgeSecurity.approveInstalledPackage(c,p);if(sig==null)return fail("PACKAGE_APPROVAL_FAILED");Bundle b=ok();b.putString("status","CONFIRMED");b.putString("package",p);b.putString("signer",sig);return b;}
   case"revokePackage":{if(!BridgeSecurity.isArmed(c))return fail("NOT_ARMED_OR_EMERGENCY_STOP");String p=x==null?null:x.getString("package");Bundle b=ok();b.putString("status",BridgeSecurity.revokePackage(c,p)?"CONFIRMED":"NOOP");return b;}
   case"screenRead":if(!ready(c,s))return fail("BRIDGE_NOT_READY");return s.screenRead();
   case"clickText":if(!ready(c,s))return fail("BRIDGE_NOT_READY");return s.clickTextExact(x==null?null:x.getString("text"));
   case"typeText":if(!ready(c,s))return fail("BRIDGE_NOT_READY");return s.typeText(x==null?null:x.getString("selector"),x==null?null:x.getString("text"));
   case"scroll":if(!ready(c,s))return fail("BRIDGE_NOT_READY");return s.scroll(x==null||x.getBoolean("forward",true));
   case"swipe":if(!ready(c,s))return fail("BRIDGE_NOT_READY");if(x==null)return fail("MISSING_EXTRAS");return s.swipe(x.getFloat("sx",-1),x.getFloat("sy",-1),x.getFloat("ex",-1),x.getFloat("ey",-1),x.getLong("duration_ms",350));
   case"globalAction":if(!ready(c,s))return fail("BRIDGE_NOT_READY");return s.globalAction(x==null?null:x.getString("action"));
   case"launchApp":if(!ready(c,s))return fail("BRIDGE_NOT_READY");return s.launchApp(x==null?null:x.getString("package"));
   case"clearEvidence":if(!BridgeSecurity.isArmed(c))return fail("NOT_ARMED_OR_EMERGENCY_STOP");BridgeEvidenceStore.clear(c);return ok();
   default:return fail("UNKNOWN_OR_INVALID_METHOD");
  }}
 private boolean ready(Context c,BridgeAccessibilityService s){return s!=null&&BridgeSecurity.isArmed(c)&&!BridgeSecurity.isEmergencyStopped(c);}
 private boolean auth(Context c){String[]p=c.getPackageManager().getPackagesForUid(Binder.getCallingUid());return p!=null&&p.length==1&&BridgeSecurity.CORE_PACKAGE.equals(p[0])&&BridgeSecurity.verifyCore(c);}
 private Bundle status(Context c,BridgeAccessibilityService s){Bundle b=ok();b.putBoolean("core_ok",BridgeSecurity.verifyCore(c));b.putBoolean("service_connected",s!=null);b.putBoolean("armed",BridgeSecurity.isArmed(c));b.putBoolean("emergency_stop",BridgeSecurity.isEmergencyStopped(c));b.putString("status",s==null?"SERVICE_NOT_CONNECTED":"READY");if(s!=null)b.putAll(s.status());return b;}
 private Bundle ok(){Bundle b=new Bundle();b.putBoolean("ok",true);return b;}private Bundle fail(String r){Bundle b=new Bundle();b.putBoolean("ok",false);b.putString("status","FAILED");b.putString("failure",r);return b;}
}