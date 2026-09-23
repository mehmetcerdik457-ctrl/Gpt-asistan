package com.mehmetcerdik.ownerbridge;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.Intent;
import android.graphics.Path;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class BridgeAccessibilityService extends AccessibilityService {
    private static volatile BridgeAccessibilityService INSTANCE;
    static BridgeAccessibilityService instance(){return INSTANCE;}
    @Override protected void onServiceConnected(){super.onServiceConnected();INSTANCE=this;BridgeSecurity.ensureDefaults(this);BridgeEvidenceStore.record(this,"SERVICE","READY","connected");}
    @Override public void onDestroy(){if(INSTANCE==this)INSTANCE=null;BridgeEvidenceStore.record(this,"SERVICE","STOPPED","");super.onDestroy();}
    @Override public void onInterrupt(){BridgeEvidenceStore.record(this,"SERVICE","INTERRUPTED","");}
    @Override public void onAccessibilityEvent(AccessibilityEvent e){if(e!=null&&e.getPackageName()!=null)BridgeEvidenceStore.record(this,"WINDOW","OBSERVED",e.getPackageName().toString());}

    Bundle status(){Bundle b=ok();b.putString("active_package",activePackage());b.putBoolean("service_connected",true);return b;}
    Bundle screenRead(){AccessibilityNodeInfo r=freshApprovedRoot();if(r==null)return fail("NO_APPROVED_ACTIVE_ROOT");String s=snapshot(r);BridgeEvidenceStore.record(this,"SCREEN_READ","PASS",s);Bundle b=ok();b.putString("status","OBSERVED");b.putString("snapshot",s);b.putString("snapshot_hash",BridgeSecurity.sha256String(s));return b;}
    Bundle clickTextExact(String w){
        if(w==null||w.trim().isEmpty())return fail("EMPTY_SELECTOR");AccessibilityNodeInfo r=freshApprovedRoot();if(r==null)return fail("NO_APPROVED_ACTIVE_ROOT");
        String pkg=pkg(r);List<AccessibilityNodeInfo>m=new ArrayList<>();collectLabel(r,w.trim(),m);if(m.size()!=1)return fail(m.isEmpty()?"CLICK_TARGET_NOT_FOUND":"CLICK_TARGET_AMBIGUOUS");
        AccessibilityNodeInfo t=clickable(m.get(0));if(t==null)return fail("CLICK_TARGET_NOT_CLICKABLE");if(!BridgeSecurity.isPackageApproved(this,pkg)||!pkg.equals(activePackage()))return fail("TOCTOU_PACKAGE_CHANGED");
        boolean x=t.performAction(AccessibilityNodeInfo.ACTION_CLICK);BridgeEvidenceStore.record(this,"CLICK_TEXT",x?"PASS":"FAIL",w);Bundle b=x?ok():fail("CLICK_DISPATCH_FAILED");if(x){b.putString("status","DISPATCHED");b.putBoolean("confirmed",true);}return b;
    }
    Bundle typeText(String selector,String value){
        if(value==null||value.length()>4000)return fail(value==null?"NULL_TEXT":"TEXT_TOO_LONG");AccessibilityNodeInfo r=freshApprovedRoot();if(r==null)return fail("NO_APPROVED_ACTIVE_ROOT");String pkg=pkg(r);
        List<AccessibilityNodeInfo>all=new ArrayList<>();collectEditable(r,all);AccessibilityNodeInfo t=null;
        if(selector==null||selector.trim().isEmpty()){if(all.size()!=1)return fail(all.isEmpty()?"EDITABLE_NOT_FOUND":"EDITABLE_AMBIGUOUS");t=all.get(0);}
        else{List<AccessibilityNodeInfo>f=new ArrayList<>();for(AccessibilityNodeInfo n:all)if(label(n).equalsIgnoreCase(selector.trim()))f.add(n);if(f.size()!=1)return fail(f.isEmpty()?"EDITABLE_SELECTOR_NOT_FOUND":"EDITABLE_SELECTOR_AMBIGUOUS");t=f.get(0);}
        if(t.isPassword())return fail("PASSWORD_FIELD_REFUSED");if(!BridgeSecurity.isPackageApproved(this,pkg)||!pkg.equals(activePackage()))return fail("TOCTOU_PACKAGE_CHANGED");
        Bundle a=new Bundle();a.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);if(!t.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,a))return fail("SET_TEXT_DISPATCH_FAILED");
        SystemClock.sleep(120);AccessibilityNodeInfo r2=freshApprovedRoot();if(r2==null||!pkg.equals(pkg(r2)))return fail("POSTCONDITION_PACKAGE_CHANGED");boolean confirmed=findText(r2,value);
        BridgeEvidenceStore.record(this,"TYPE_TEXT",confirmed?"PASS":"FAIL",selector+"|"+value);Bundle b=ok();b.putString("status",confirmed?"TARGET_POSTCONDITION_CONFIRMED":"DISPATCHED");b.putBoolean("confirmed",confirmed);return b;
    }
    Bundle scroll(boolean forward){AccessibilityNodeInfo r=freshApprovedRoot();if(r==null)return fail("NO_APPROVED_ACTIVE_ROOT");AccessibilityNodeInfo t=scrollable(r);if(t==null)return fail("SCROLLABLE_NOT_FOUND");boolean x=t.performAction(forward?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD);BridgeEvidenceStore.record(this,forward?"SCROLL_FORWARD":"SCROLL_BACKWARD",x?"PASS":"FAIL","");Bundle b=x?ok():fail("SCROLL_DISPATCH_FAILED");if(x)b.putBoolean("confirmed",true);return b;}
    Bundle swipe(float sx,float sy,float ex,float ey,long duration){
        AccessibilityNodeInfo r=freshApprovedRoot();if(r==null)return fail("NO_APPROVED_ACTIVE_ROOT");String p=pkg(r);if(!norm(sx)||!norm(sy)||!norm(ex)||!norm(ey))return fail("SWIPE_COORDINATE_OUT_OF_RANGE");
        long d=Math.max(100,Math.min(duration<=0?350:duration,2000));android.util.DisplayMetrics dm=getResources().getDisplayMetrics();Path path=new Path();path.moveTo(sx*dm.widthPixels,sy*dm.heightPixels);path.lineTo(ex*dm.widthPixels,ey*dm.heightPixels);
        GestureDescription g=new GestureDescription.Builder().addStroke(new GestureDescription.StrokeDescription(path,0,d)).build();CountDownLatch l=new CountDownLatch(1);final boolean[]done={false};
        boolean accepted=dispatchGesture(g,new GestureResultCallback(){@Override public void onCompleted(GestureDescription gd){done[0]=true;l.countDown();}@Override public void onCancelled(GestureDescription gd){l.countDown();}},new Handler(Looper.getMainLooper()));
        if(!accepted)return fail("GESTURE_NOT_ACCEPTED");try{l.await(2500,TimeUnit.MILLISECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();}if(!done[0])return fail("GESTURE_NOT_COMPLETED");
        AccessibilityNodeInfo after=freshApprovedRoot();boolean confirmed=after!=null&&p.equals(pkg(after));BridgeEvidenceStore.record(this,"SWIPE",confirmed?"PASS":"FAIL",sx+","+sy+","+ex+","+ey);Bundle b=confirmed?ok():fail("SWIPE_POSTCONDITION_PACKAGE_CHANGED");if(confirmed){b.putString("status","GESTURE_COMPLETED");b.putBoolean("confirmed",true);}return b;
    }
    Bundle globalAction(String name){
        AccessibilityNodeInfo r=freshApprovedRoot();if(r==null)return fail("GLOBAL_ACTION_PRECONDITION_FAILED");String before=pkg(r),n=name==null?"":name.trim().toUpperCase(Locale.ROOT);int a;
        switch(n){case"BACK":a=GLOBAL_ACTION_BACK;break;case"HOME":a=GLOBAL_ACTION_HOME;break;case"RECENTS":a=GLOBAL_ACTION_RECENTS;break;case"NOTIFICATIONS":a=GLOBAL_ACTION_NOTIFICATIONS;break;default:return fail("UNKNOWN_GLOBAL_ACTION");}
        boolean d=performGlobalAction(a);SystemClock.sleep(250);String after=activePackage();boolean confirmed=d&&after!=null&&!after.isEmpty();BridgeEvidenceStore.record(this,"GLOBAL_"+n,confirmed?"PASS":"FAIL",before+"->"+after);Bundle b=confirmed?ok():fail("GLOBAL_ACTION_POSTCONDITION_FAILED");if(confirmed){b.putString("status","TARGET_POSTCONDITION_CONFIRMED");b.putBoolean("confirmed",true);}return b;
    }
    Bundle launchApp(String packageName){
        if(!BridgeSecurity.validPackageName(packageName)||!BridgeSecurity.isPackageApproved(this,packageName))return fail("PACKAGE_NOT_APPROVED");Intent i=getPackageManager().getLaunchIntentForPackage(packageName);if(i==null)return fail("NO_LAUNCH_INTENT");
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);startActivity(i);SystemClock.sleep(600);boolean confirmed=packageName.equals(activePackage());BridgeEvidenceStore.record(this,"LAUNCH_APP",confirmed?"PASS":"FAIL",packageName);Bundle b=confirmed?ok():fail("LAUNCH_POSTCONDITION_FAILED");if(confirmed){b.putString("status","TARGET_POSTCONDITION_CONFIRMED");b.putBoolean("confirmed",true);}return b;
    }
    private AccessibilityNodeInfo freshApprovedRoot(){AccessibilityNodeInfo r=getRootInActiveWindow();return r!=null&&BridgeSecurity.isPackageApproved(this,pkg(r))?r:null;}
    private String activePackage(){AccessibilityNodeInfo r=getRootInActiveWindow();return r==null?"":pkg(r);} private String pkg(AccessibilityNodeInfo r){return r.getPackageName()==null?"":r.getPackageName().toString();}
    private boolean norm(float v){return v>=0&&v<=1;} private String label(AccessibilityNodeInfo n){StringBuilder s=new StringBuilder();if(n.getText()!=null)s.append(n.getText());if(n.getContentDescription()!=null)s.append(' ').append(n.getContentDescription());return s.toString().trim();}
    private AccessibilityNodeInfo clickable(AccessibilityNodeInfo n){for(int i=0;i<8&&n!=null;i++,n=n.getParent())if(n.isClickable()&&n.isEnabled())return n;return null;}
    private void collectLabel(AccessibilityNodeInfo n,String w,List<AccessibilityNodeInfo>o){if(n==null||o.size()>8)return;if(label(n).equalsIgnoreCase(w))o.add(n);for(int i=0;i<n.getChildCount();i++)collectLabel(n.getChild(i),w,o);}
    private void collectEditable(AccessibilityNodeInfo n,List<AccessibilityNodeInfo>o){if(n==null||o.size()>16)return;if(n.isVisibleToUser()&&n.isEnabled()&&n.isEditable())o.add(n);for(int i=0;i<n.getChildCount();i++)collectEditable(n.getChild(i),o);}
    private AccessibilityNodeInfo scrollable(AccessibilityNodeInfo r){ArrayDeque<AccessibilityNodeInfo>q=new ArrayDeque<>();q.add(r);for(int seen=0;!q.isEmpty()&&seen<400;seen++){AccessibilityNodeInfo n=q.remove();if(n.isVisibleToUser()&&n.isScrollable())return n;for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null)q.add(c);}}return null;}
    private boolean findText(AccessibilityNodeInfo n,String v){if(n==null)return false;if(n.getText()!=null&&v.contentEquals(n.getText()))return true;for(int i=0;i<n.getChildCount();i++)if(findText(n.getChild(i),v))return true;return false;}
    private String snapshot(AccessibilityNodeInfo r){StringBuilder s=new StringBuilder();ArrayDeque<AccessibilityNodeInfo>q=new ArrayDeque<>();q.add(r);for(int seen=0;!q.isEmpty()&&seen<400;seen++){AccessibilityNodeInfo n=q.remove();s.append(n.getClassName()).append('|').append(label(n)).append('|').append(n.isClickable()).append('|').append(n.isEditable()).append('|').append(n.isScrollable()).append('\n');for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null)q.add(c);}}return s.toString();}
    private Bundle ok(){Bundle b=new Bundle();b.putBoolean("ok",true);return b;} private Bundle fail(String r){BridgeEvidenceStore.record(this,"FAIL","FAIL",r);Bundle b=new Bundle();b.putBoolean("ok",false);b.putString("status","FAILED");b.putString("failure",r);return b;}
}