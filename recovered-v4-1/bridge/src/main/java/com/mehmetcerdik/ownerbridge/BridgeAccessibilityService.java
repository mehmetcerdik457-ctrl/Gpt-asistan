package com.mehmetcerdik.ownerbridge;

import android.accessibilityservice.AccessibilityService;
import android.accessibilityservice.GestureDescription;
import android.content.Intent;
import android.graphics.Path;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.text.InputType;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public final class BridgeAccessibilityService extends AccessibilityService {
    private static volatile BridgeAccessibilityService INSTANCE;
    private static final int MAX_NODES=250;
    private static final int MAX_FIELD=180;
    private static final Set<String> EPHEMERAL_SECRET_TARGETS = java.util.Collections.synchronizedSet(new HashSet<>());
    private static final Set<String> EPHEMERAL_SECRET_PACKAGES = java.util.Collections.synchronizedSet(new HashSet<>());

    static BridgeAccessibilityService instance(){ return INSTANCE; }

    @Override protected void onServiceConnected(){
        super.onServiceConnected(); INSTANCE=this; EPHEMERAL_SECRET_TARGETS.clear(); EPHEMERAL_SECRET_PACKAGES.clear(); BridgeSecurity.ensureDefaults(this); BridgeSecurity.forceFailClosed(this,"ACCESSIBILITY_SERVICE_CONNECTED");
        BridgeSecurity.saveState(this,"ACCESSIBILITY_SERVICE","OBSERVED","connected","");
    }

    @Override public void onDestroy(){ EPHEMERAL_SECRET_TARGETS.clear(); EPHEMERAL_SECRET_PACKAGES.clear(); BridgeSecurity.forceFailClosed(this,"ACCESSIBILITY_SERVICE_DESTROYED"); if(INSTANCE==this) INSTANCE=null; super.onDestroy(); }
    @Override public void onInterrupt(){ EPHEMERAL_SECRET_TARGETS.clear(); EPHEMERAL_SECRET_PACKAGES.clear(); BridgeSecurity.forceFailClosed(this,"ACCESSIBILITY_SERVICE_INTERRUPTED"); }

    @Override public void onAccessibilityEvent(AccessibilityEvent event){
        if(event==null || event.getPackageName()==null) return;
        BridgeSecurity.prefs(this).edit().putString("last_event_package",event.getPackageName().toString()).putLong("last_event_elapsed",SystemClock.elapsedRealtime()).commit();
    }

    Bundle status(){ Bundle b=ok(); b.putString("active_package",activePackage()); b.putBoolean("service_connected",true); return b; }

    Bundle screenRead(){
        AccessibilityNodeInfo root=getRootInActiveWindow(); if(root==null) return fail("NO_ACTIVE_ROOT");
        String pkg=packageName(root); if(!BridgeSecurity.isPackageApproved(this,pkg)) return fail("ACTIVE_PACKAGE_NOT_APPROVED");
        String snapshot=snapshot(root); Bundle b=ok(); b.putString("status","OBSERVED"); b.putString("package",pkg); b.putString("snapshot",snapshot); b.putString("snapshot_hash",BridgeSecurity.sha256String(snapshot)); return b;
    }

    Bundle clickTextExact(String wanted){
        if(wanted==null || wanted.trim().isEmpty()) return fail("EMPTY_SELECTOR");
        String selector=wanted.trim(); AccessibilityNodeInfo initial=getRootInActiveWindow(); if(initial==null) return fail("NO_ACTIVE_ROOT");
        String expectedPkg=packageName(initial); if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_NOT_APPROVED");
        String before=BridgeSecurity.sha256String(snapshot(initial));
        AccessibilityNodeInfo fresh=getRootInActiveWindow(); if(fresh==null || !expectedPkg.equals(packageName(fresh))) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_CLICK");
        if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_APPROVAL_LOST");
        List<AccessibilityNodeInfo> matches=new ArrayList<>(); collectExactLabel(fresh,selector,matches);
        if(matches.isEmpty()) return fail("CLICK_TARGET_NOT_FOUND"); if(matches.size()!=1) return fail("CLICK_TARGET_AMBIGUOUS");
        AccessibilityNodeInfo dispatchRoot=getRootInActiveWindow(); if(dispatchRoot==null || !expectedPkg.equals(packageName(dispatchRoot))) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_CLICK_RERESOLVE");
        if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_APPROVAL_LOST_BEFORE_CLICK_DISPATCH");
        List<AccessibilityNodeInfo> dispatchMatches=new ArrayList<>(); collectExactLabel(dispatchRoot,selector,dispatchMatches);
        if(dispatchMatches.isEmpty()) return fail("CLICK_TARGET_LOST_BEFORE_DISPATCH"); if(dispatchMatches.size()!=1) return fail("CLICK_TARGET_AMBIGUOUS_BEFORE_DISPATCH");
        AccessibilityNodeInfo click=nearestClickable(dispatchMatches.get(0)); if(click==null) return fail("CLICK_TARGET_NOT_CLICKABLE_BEFORE_DISPATCH");
        if(!expectedPkg.equals(activePackage())) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_CLICK_DISPATCH");
        if(!click.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return fail("CLICK_DISPATCH_FAILED");
        SystemClock.sleep(350); AccessibilityNodeInfo afterRoot=getRootInActiveWindow(); String afterPkg=afterRoot==null?"":packageName(afterRoot);
        String after=afterRoot==null?"":BridgeSecurity.sha256String(snapshot(afterRoot));
        Bundle b=ok(); b.putBoolean("dispatched",true); b.putString("package",afterPkg);
        if(!expectedPkg.equals(afterPkg)){ b.putString("status","UI_CHANGED"); b.putBoolean("package_transition",true); return b; }
        boolean changed=!before.equals(after) && !after.isEmpty(); b.putString("status",changed?"UI_CHANGED":"DISPATCHED"); b.putBoolean("ui_changed",changed); return b;
    }

    Bundle typeText(String selector, String value, boolean secret){
        if(value==null) return fail("NULL_TEXT"); if(value.length()>4000) return fail("TEXT_TOO_LONG");
        AccessibilityNodeInfo initial=getRootInActiveWindow(); if(initial==null) return fail("NO_ACTIVE_ROOT");
        String expectedPkg=packageName(initial); if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_NOT_APPROVED");
        AccessibilityNodeInfo fresh=getRootInActiveWindow(); if(fresh==null || !expectedPkg.equals(packageName(fresh))) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_TYPE");
        AccessibilityNodeInfo preliminaryTarget=resolveEditable(fresh,selector); if(preliminaryTarget==null) return fail(lastResolveFailure);
        AccessibilityNodeInfo dispatchRoot=getRootInActiveWindow(); if(dispatchRoot==null || !expectedPkg.equals(packageName(dispatchRoot))) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_TYPE_RERESOLVE");
        if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_APPROVAL_LOST_BEFORE_TYPE_DISPATCH");
        AccessibilityNodeInfo target=resolveEditable(dispatchRoot,selector); if(target==null) return fail("EDITABLE_TARGET_LOST_BEFORE_DISPATCH:"+lastResolveFailure);
        if(!expectedPkg.equals(activePackage())) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_TYPE_DISPATCH");
        if(secret) rememberSecretTarget(expectedPkg,target);
        Bundle args=new Bundle(); args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,value);
        if(!target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args)) return fail("SET_TEXT_DISPATCH_FAILED");
        SystemClock.sleep(140); AccessibilityNodeInfo post=getRootInActiveWindow(); if(post==null) return state("DISPATCHED",expectedPkg);
        if(!expectedPkg.equals(packageName(post))) return state("UI_CHANGED",packageName(post));
        if(secret) return state("DISPATCHED",expectedPkg);
        AccessibilityNodeInfo verify=resolveEditable(post,selector); CharSequence now=verify==null?null:verify.getText();
        if(now!=null && value.contentEquals(now)){ Bundle b=state("TARGET_POSTCONDITION_CONFIRMED",expectedPkg); b.putBoolean("target_postcondition_confirmed",true); return b; }
        return state("DISPATCHED",expectedPkg);
    }

    private String lastResolveFailure="EDITABLE_NOT_FOUND";
    private AccessibilityNodeInfo resolveEditable(AccessibilityNodeInfo root,String selector){
        List<AccessibilityNodeInfo> nodes=new ArrayList<>(); collectEditable(root,nodes);
        if(selector==null || selector.trim().isEmpty()){
            if(nodes.isEmpty()){lastResolveFailure="EDITABLE_NOT_FOUND";return null;} if(nodes.size()!=1){lastResolveFailure="EDITABLE_AMBIGUOUS";return null;} return nodes.get(0);
        }
        String s=selector.trim(); List<AccessibilityNodeInfo> filtered=new ArrayList<>(); for(AccessibilityNodeInfo n:nodes) if(rawNodeLabel(n).equalsIgnoreCase(s)) filtered.add(n);
        if(filtered.isEmpty()){lastResolveFailure="EDITABLE_SELECTOR_NOT_FOUND";return null;} if(filtered.size()!=1){lastResolveFailure="EDITABLE_SELECTOR_AMBIGUOUS";return null;} return filtered.get(0);
    }

    Bundle scroll(boolean forward){
        AccessibilityNodeInfo initial=getRootInActiveWindow(); if(initial==null) return fail("NO_ACTIVE_ROOT"); String expectedPkg=packageName(initial);
        if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_NOT_APPROVED"); String before=BridgeSecurity.sha256String(snapshot(initial));
        AccessibilityNodeInfo fresh=getRootInActiveWindow(); if(fresh==null || !expectedPkg.equals(packageName(fresh))) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_SCROLL");
        List<AccessibilityNodeInfo> nodes=new ArrayList<>(); collectScrollable(fresh,nodes); if(nodes.isEmpty()) return fail("SCROLLABLE_NOT_FOUND"); if(nodes.size()!=1) return fail("SCROLLABLE_AMBIGUOUS");
        AccessibilityNodeInfo dispatchRoot=getRootInActiveWindow(); if(dispatchRoot==null || !expectedPkg.equals(packageName(dispatchRoot))) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_SCROLL_RERESOLVE");
        if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_APPROVAL_LOST_BEFORE_SCROLL_DISPATCH");
        List<AccessibilityNodeInfo> dispatchNodes=new ArrayList<>(); collectScrollable(dispatchRoot,dispatchNodes); if(dispatchNodes.isEmpty()) return fail("SCROLLABLE_LOST_BEFORE_DISPATCH"); if(dispatchNodes.size()!=1) return fail("SCROLLABLE_AMBIGUOUS_BEFORE_DISPATCH");
        if(!expectedPkg.equals(activePackage())) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_SCROLL_DISPATCH");
        int action=forward?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD;
        if(!dispatchNodes.get(0).performAction(action)) return fail("SCROLL_DISPATCH_FAILED"); SystemClock.sleep(300);
        AccessibilityNodeInfo afterRoot=getRootInActiveWindow(); String afterPkg=afterRoot==null?"":packageName(afterRoot); String after=afterRoot==null?"":BridgeSecurity.sha256String(snapshot(afterRoot));
        Bundle b=state("DISPATCHED",afterPkg); b.putBoolean("dispatched",true); boolean changed=!before.equals(after)&&!after.isEmpty();
        if(changed || !expectedPkg.equals(afterPkg)){b.putString("status","UI_CHANGED");b.putBoolean("ui_changed",true);} return b;
    }

    Bundle swipe(float sx,float sy,float ex,float ey,long durationMs){
        AccessibilityNodeInfo initial=getRootInActiveWindow(); if(initial==null) return fail("NO_ACTIVE_ROOT"); String expectedPkg=packageName(initial);
        if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_NOT_APPROVED");
        if(!norm(sx)||!norm(sy)||!norm(ex)||!norm(ey)) return fail("SWIPE_COORDINATE_OUT_OF_RANGE");
        long d=Math.max(100L,Math.min(durationMs<=0?350L:durationMs,2000L)); android.util.DisplayMetrics dm=getResources().getDisplayMetrics();
        String before=BridgeSecurity.sha256String(snapshot(initial));
        AccessibilityNodeInfo preDispatch=getRootInActiveWindow(); if(preDispatch==null || !expectedPkg.equals(packageName(preDispatch))) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_SWIPE");
        if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_APPROVAL_LOST");
        Path path=new Path(); path.moveTo(sx*dm.widthPixels,sy*dm.heightPixels); path.lineTo(ex*dm.widthPixels,ey*dm.heightPixels);
        GestureDescription gesture=new GestureDescription.Builder().addStroke(new GestureDescription.StrokeDescription(path,0,d)).build();
        CountDownLatch latch=new CountDownLatch(1); final boolean[] completed={false};
        boolean accepted=dispatchGesture(gesture,new GestureResultCallback(){@Override public void onCompleted(GestureDescription g){completed[0]=true;latch.countDown();}@Override public void onCancelled(GestureDescription g){latch.countDown();}},new Handler(Looper.getMainLooper()));
        if(!accepted) return fail("GESTURE_NOT_ACCEPTED"); try{latch.await(2500L,TimeUnit.MILLISECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();}
        if(!completed[0]) return fail("GESTURE_NOT_COMPLETED"); SystemClock.sleep(250);
        AccessibilityNodeInfo afterRoot=getRootInActiveWindow(); String afterPkg=afterRoot==null?"":packageName(afterRoot); String after=afterRoot==null?"":BridgeSecurity.sha256String(snapshot(afterRoot));
        Bundle b=state("GESTURE_COMPLETED",afterPkg); b.putBoolean("gesture_completed",true);
        if(!expectedPkg.equals(afterPkg)){b.putBoolean("package_transition",true); return b;}
        boolean changed=!before.equals(after)&&!after.isEmpty(); if(changed){b.putString("status","UI_CHANGED");b.putBoolean("ui_changed",true);} return b;
    }

    Bundle globalAction(String actionName){
        int action; String n=actionName==null?"":actionName.trim().toUpperCase(Locale.ROOT);
        switch(n){case "BACK":action=GLOBAL_ACTION_BACK;break;case "HOME":action=GLOBAL_ACTION_HOME;break;case "RECENTS":action=GLOBAL_ACTION_RECENTS;break;case "NOTIFICATIONS":action=GLOBAL_ACTION_NOTIFICATIONS;break;default:return fail("UNKNOWN_GLOBAL_ACTION");}
        AccessibilityNodeInfo initial=getRootInActiveWindow(); if(initial==null) return fail("NO_ACTIVE_ROOT"); String expectedPkg=packageName(initial);
        if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_NOT_APPROVED_FOR_GLOBAL_ACTION"); String before=BridgeSecurity.sha256String(snapshot(initial));
        AccessibilityNodeInfo pre=getRootInActiveWindow(); if(pre==null || !expectedPkg.equals(packageName(pre))) return fail("ACTIVE_PACKAGE_CHANGED_BEFORE_GLOBAL_ACTION");
        if(!BridgeSecurity.isPackageApproved(this,expectedPkg)) return fail("ACTIVE_PACKAGE_APPROVAL_LOST");
        if(!performGlobalAction(action)) return fail("GLOBAL_ACTION_DISPATCH_FAILED"); SystemClock.sleep(400);
        String afterPkg=activePackage(), after=currentSnapshotHash(); Bundle b=state("GESTURE_COMPLETED",afterPkg); b.putBoolean("gesture_completed",true);
        boolean changed=!before.equals(after)||!expectedPkg.equals(afterPkg); if(changed){b.putString("status","UI_CHANGED");b.putBoolean("ui_changed",true);} return b;
    }

    Bundle launchApp(String pkg){
        if(!BridgeSecurity.isPackageApproved(this,pkg)) return fail("PACKAGE_NOT_APPROVED"); Intent i=getPackageManager().getLaunchIntentForPackage(pkg); if(i==null) return fail("NO_LAUNCH_INTENT");
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); try{startActivity(i);}catch(Throwable t){return fail("LAUNCH_FAILED");}
        long end=SystemClock.uptimeMillis()+3000L; while(SystemClock.uptimeMillis()<end){if(pkg.equals(activePackage())){if(!BridgeSecurity.isPackageApproved(this,pkg)) return fail("PACKAGE_APPROVAL_LOST_AFTER_LAUNCH");Bundle b=state("TARGET_POSTCONDITION_CONFIRMED",pkg);b.putBoolean("target_postcondition_confirmed",true);return b;}SystemClock.sleep(100);}
        return state("DISPATCHED",activePackage());
    }

    Bundle verifyPostcondition(String kind,String expected){
        String k=kind==null?"":kind.trim(); String e=expected==null?"":expected.trim(); AccessibilityNodeInfo root=getRootInActiveWindow(); if(root==null) return fail("NO_ACTIVE_ROOT");
        String pkg=packageName(root); if(!BridgeSecurity.isPackageApproved(this,pkg)) return fail("ACTIVE_PACKAGE_NOT_APPROVED"); boolean matched;
        if("activePackageEquals".equals(k)) matched=pkg.equals(e);
        else if("textPresent".equals(k)){List<AccessibilityNodeInfo> x=new ArrayList<>();collectExactLabel(root,e,x);matched=!x.isEmpty();}
        else if("textAbsent".equals(k)){List<AccessibilityNodeInfo> x=new ArrayList<>();collectExactLabel(root,e,x);matched=x.isEmpty();}
        else return fail("UNKNOWN_POSTCONDITION_KIND");
        if(!matched) return fail("TARGET_POSTCONDITION_NOT_MET"); Bundle b=state("TARGET_POSTCONDITION_CONFIRMED",pkg); b.putBoolean("target_postcondition_confirmed",true); return b;
    }

    private String activePackage(){AccessibilityNodeInfo root=getRootInActiveWindow();return root==null?"":packageName(root);} private String currentSnapshotHash(){AccessibilityNodeInfo root=getRootInActiveWindow();return root==null?"":BridgeSecurity.sha256String(snapshot(root));}
    private String packageName(AccessibilityNodeInfo root){CharSequence p=root.getPackageName();return p==null?"":p.toString();} private static boolean norm(float v){return v>=0f&&v<=1f;}
    private AccessibilityNodeInfo nearestClickable(AccessibilityNodeInfo n){AccessibilityNodeInfo cur=n;for(int i=0;i<5&&cur!=null;i++){if(cur.isClickable()&&cur.isEnabled())return cur;cur=cur.getParent();}return null;}
    private void collectExactLabel(AccessibilityNodeInfo n,String wanted,List<AccessibilityNodeInfo> out){if(n==null||out.size()>8)return;if(n.isVisibleToUser()&&rawNodeLabel(n).equalsIgnoreCase(wanted))out.add(n);for(int i=0;i<n.getChildCount();i++)collectExactLabel(n.getChild(i),wanted,out);}
    private void collectEditable(AccessibilityNodeInfo n,List<AccessibilityNodeInfo> out){if(n==null||out.size()>16)return;if(n.isVisibleToUser()&&n.isEnabled()&&n.isEditable())out.add(n);for(int i=0;i<n.getChildCount();i++)collectEditable(n.getChild(i),out);}
    private void collectScrollable(AccessibilityNodeInfo n,List<AccessibilityNodeInfo> out){if(n==null||out.size()>16)return;if(n.isVisibleToUser()&&n.isEnabled()&&n.isScrollable())out.add(n);for(int i=0;i<n.getChildCount();i++)collectScrollable(n.getChild(i),out);}
    private String snapshot(AccessibilityNodeInfo root){StringBuilder sb=new StringBuilder();int[] count={0};appendNode(root,sb,count,0);return sb.toString();}
    private void appendNode(AccessibilityNodeInfo n,StringBuilder sb,int[] count,int depth){
        if(n==null||count[0]>=MAX_NODES)return;int idx=count[0]++;Rect r=new Rect();n.getBoundsInScreen(r);
        String rawText=clip(cs(n.getText())),rawDesc=clip(cs(n.getContentDescription())),rawHint=clip(cs(n.getHintText())),id=clip(n.getViewIdResourceName()),clazz=clip(cs(n.getClassName()));
        boolean secret=isSecretNode(n,rawText,rawDesc,rawHint,id) || EPHEMERAL_SECRET_TARGETS.contains(secretTargetKey(packageNameForNode(n),n)) || (n.isEditable() && EPHEMERAL_SECRET_PACKAGES.contains(packageNameForNode(n)));String text=secret?"<redacted-secret>":rawText,desc=secret?"<redacted-secret>":rawDesc,hint=secret?"<redacted-secret>":rawHint;
        sb.append(idx).append('|').append(depth).append("|text=").append(escape(text)).append("|desc=").append(escape(desc)).append("|hint=").append(escape(hint)).append("|id=").append(escape(id)).append("|class=").append(escape(clazz)).append("|secret=").append(secret).append("|click=").append(n.isClickable()).append("|edit=").append(n.isEditable()).append("|scroll=").append(n.isScrollable()).append("|bounds=").append(r.left).append(',').append(r.top).append(',').append(r.right).append(',').append(r.bottom).append('\n');
        for(int i=0;i<n.getChildCount()&&count[0]<MAX_NODES;i++)appendNode(n.getChild(i),sb,count,depth+1);
    }
    private boolean isSecretNode(AccessibilityNodeInfo n,String text,String desc,String hint,String id){if(n.isPassword())return true;int t=n.getInputType();int variation=t & InputType.TYPE_MASK_VARIATION;int clazz=t & InputType.TYPE_MASK_CLASS;if(clazz==InputType.TYPE_CLASS_TEXT&&(variation==InputType.TYPE_TEXT_VARIATION_PASSWORD||variation==InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD||variation==InputType.TYPE_TEXT_VARIATION_WEB_PASSWORD))return true;if(clazz==InputType.TYPE_CLASS_NUMBER&&variation==InputType.TYPE_NUMBER_VARIATION_PASSWORD)return true;return SecretClassifier.isSensitiveMetadata(text,desc,hint,id);}
    private void rememberSecretTarget(String pkg, AccessibilityNodeInfo n){ if(pkg!=null&&!pkg.isEmpty()) EPHEMERAL_SECRET_PACKAGES.add(pkg); if(n!=null) EPHEMERAL_SECRET_TARGETS.add(secretTargetKey(pkg,n)); }
    private String packageNameForNode(AccessibilityNodeInfo n){ CharSequence p=n==null?null:n.getPackageName(); return p==null?"":p.toString(); }
    private String secretTargetKey(String pkg, AccessibilityNodeInfo n){ Rect r=new Rect(); if(n!=null)n.getBoundsInScreen(r); return (pkg==null?"":pkg)+"|"+clip(n==null?"":n.getViewIdResourceName())+"|"+clip(cs(n==null?null:n.getClassName()))+"|"+r.left+","+r.top+","+r.right+","+r.bottom; }
    private String rawNodeLabel(AccessibilityNodeInfo n){if(n==null)return"";String t=cs(n.getText()).trim();if(!t.isEmpty())return t;String d=cs(n.getContentDescription()).trim();if(!d.isEmpty())return d;return cs(n.getHintText()).trim();}
    private static String cs(CharSequence s){return s==null?"":s.toString();} private static String clip(String s){return s==null?"":(s.length()<=MAX_FIELD?s:s.substring(0,MAX_FIELD));} private static String escape(String s){return s.replace("\\","\\\\").replace("\n","\\n").replace("\r","\\r").replace("|","\\|");}
    private Bundle state(String status,String pkg){Bundle b=ok();b.putString("status",status);b.putString("package",pkg==null?"":pkg);return b;} private Bundle ok(){Bundle b=new Bundle();b.putBoolean("ok",true);return b;} private Bundle fail(String reason){Bundle b=new Bundle();b.putBoolean("ok",false);b.putString("status","FAILED");b.putString("failure",reason);return b;}
}
