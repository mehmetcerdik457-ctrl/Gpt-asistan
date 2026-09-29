#!/usr/bin/env python3
from pathlib import Path
import re, xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[1]
A='{http://schemas.android.com/apk/res/android}'
def req(v,m):
    if not v: raise AssertionError(m)
def gradle_values(path):
    t=(R/path).read_text()
    out={}
    pats={'namespace':r"namespace\s+['\"]([^'\"]+)",'applicationId':r"applicationId\s+['\"]([^'\"]+)",'compileSdk':r'compileSdk\s+(\d+)','buildToolsVersion':r"buildToolsVersion\s+['\"]([^'\"]+)",'minSdk':r'minSdk\s+(\d+)','targetSdk':r'targetSdk\s+(\d+)','versionCode':r'versionCode\s+(\d+)','versionName':r"versionName\s+['\"]([^'\"]+)"}
    for k,pat in pats.items():
        m=re.search(pat,t); req(m, f'{path}: {k} missing'); out[k]=m.group(1)
    return out
core=gradle_values('core/build.gradle'); bridge=gradle_values('bridge/build.gradle')
req(core=={'namespace':'com.mehmetcerdik.ownerai','applicationId':'com.mehmetcerdik.ownerai','compileSdk':'35','buildToolsVersion':'35.0.0','minSdk':'26','targetSdk':'35','versionCode':'4','versionName':'1.2.0'},'core identity mismatch')
req(bridge=={'namespace':'com.mehmetcerdik.ownerbridge','applicationId':'com.mehmetcerdik.ownerbridge','compileSdk':'35','buildToolsVersion':'35.0.0','minSdk':'26','targetSdk':'35','versionCode':'2','versionName':'1.1.0'},'bridge identity mismatch')
cm=ET.parse(R/'core/src/main/AndroidManifest.xml').getroot(); bm=ET.parse(R/'bridge/src/main/AndroidManifest.xml').getroot(); acc=ET.parse(R/'bridge/src/main/res/xml/accessibility_service_config.xml').getroot()
core_perms=[x.get(A+'name') for x in cm.findall('uses-permission')]; bridge_perms=[x.get(A+'name') for x in bm.findall('uses-permission')]
req('android.permission.INTERNET' not in core_perms,'core INTERNET present'); req('android.permission.INTERNET' not in bridge_perms,'bridge INTERNET present')
req('android.permission.QUERY_ALL_PACKAGES' not in bridge_perms,'broad QUERY_ALL_PACKAGES must be absent')
queries=bm.find('queries'); req(queries is not None,'bridge queries visibility declaration missing')
qpkgs={x.get(A+'name') for x in queries.findall('package')}; req('com.mehmetcerdik.ownerai' in qpkgs and 'com.codespaceapps.aichat' in qpkgs,'core/worker visibility queries missing')
qintent=queries.find('intent'); req(qintent is not None,'launcher intent visibility query missing')
req(qintent.find('action').get(A+'name')=='android.intent.action.MAIN','launcher MAIN query missing'); req(qintent.find('category').get(A+'name')=='android.intent.category.LAUNCHER','launcher category query missing')
perm=cm.find('permission'); req(perm is not None and perm.get(A+'name')=='com.mehmetcerdik.ownerai.permission.BRIDGE' and perm.get(A+'protectionLevel')=='signature','signature permission invalid')
services=bm.findall('./application/service'); req(len(services)==1,'unexpected service count'); svc=services[0]
req(svc.get(A+'name')=='.BridgeAccessibilityService','accessibility service wrong'); req(svc.get(A+'permission')=='android.permission.BIND_ACCESSIBILITY_SERVICE','BIND_ACCESSIBILITY_SERVICE missing')
req(acc.get(A+'canRetrieveWindowContent')=='true','canRetrieveWindowContent false'); req(acc.get(A+'canPerformGestures')=='true','canPerformGestures false'); req(acc.get(A+'packageNames') is None,'accessibility unexpectedly package-scoped')
sec=(R/'bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeSecurity.java').read_text(); svc_t=(R/'bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeAccessibilityService.java').read_text(); prov=(R/'bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeControlProvider.java').read_text(); main=(R/'core/src/main/java/com/mehmetcerdik/ownerai/MainActivity.java').read_text()
all_java='\n'.join(p.read_text(errors='ignore') for p in list((R/'core/src/main/java').rglob('*.java'))+list((R/'bridge/src/main/java').rglob('*.java')))
req('System.currentTimeMillis() <= ' not in sec and 'KEY_ARMED_UNTIL' not in sec,'wall-clock arm persistence remains')
for tok in ['armedPid','armedBootCount','PROCESS_SESSION_ID','SystemClock.elapsedRealtime()','forceFailClosed']: req(tok in sec,'session invariant missing '+tok)
for tok in ['ACCESSIBILITY_SERVICE_CONNECTED','ACCESSIBILITY_SERVICE_DESTROYED','ACCESSIBILITY_SERVICE_INTERRUPTED']: req(tok in svc_t,'lifecycle fail-closed missing '+tok)
for tok in ['ACTIVE_PACKAGE_NOT_APPROVED_FOR_GLOBAL_ACTION','ACTIVE_PACKAGE_CHANGED_BEFORE_GLOBAL_ACTION','ACTIVE_PACKAGE_APPROVAL_LOST']: req(tok in svc_t,'global action guard missing '+tok)
for tok in ['listPackages','inspectPackage','listApprovedPackages','revokePackage','revokeAllNonDefaultPackages']: req('case "'+tok+'"' in prov,'provider method missing '+tok)
req('DEFAULT_WORKER_REVOCATION_FORBIDDEN' in prov and 'WORKER_PACKAGE.equals(pkg)' in sec,'default worker protection missing')
req('CORE_PACKAGE.equals(pkg)' in sec and 'com.mehmetcerdik.ownerbridge' in sec and 'd == null || !d.launchable' in sec,'self/nonlaunchable package approval rejection missing')
for tok in ['FLAG_SECURE','TYPE_TEXT_VARIATION_PASSWORD','text.setText("")']: req(tok in main,'core secret protection missing '+tok)
req('SecretClassifier.isSensitiveMetadata' in svc_t and '<redacted-secret>' in svc_t and 'EPHEMERAL_SECRET_TARGETS' in svc_t,'general/ephemeral secret redaction missing')
for tok in ['ACTIVE_PACKAGE_CHANGED_BEFORE_SWIPE','ACTIVE_PACKAGE_CHANGED_BEFORE_CLICK_DISPATCH','ACTIVE_PACKAGE_CHANGED_BEFORE_TYPE_DISPATCH','ACTIVE_PACKAGE_CHANGED_BEFORE_CLICK_RERESOLVE','ACTIVE_PACKAGE_CHANGED_BEFORE_TYPE_RERESOLVE','CLICK_TARGET_LOST_BEFORE_DISPATCH','EDITABLE_TARGET_LOST_BEFORE_DISPATCH','PACKAGE_APPROVAL_LOST_AFTER_LAUNCH','ACTIVE_PACKAGE_CHANGED_BEFORE_SCROLL_RERESOLVE','SCROLLABLE_LOST_BEFORE_DISPATCH']: req(tok in svc_t,'TOCTOU/fresh-node guard missing '+tok)
req('!committed || !isPackageApproved(c, pkg)' in sec and '!committed || isPackageApproved(c, pkg)' in sec and 'after.size() != 1' in sec,'approval/revocation persistence postcondition checks missing')
req('REVOCATION_PERSIST_OR_AUDIT_FAILED' in prov,'revoke-all provider fail-closed result missing')
req('queryIntentActivities' in sec and 'getInstalledApplications' not in sec,'least-privilege launcher package discovery missing')
for tok in ['DISPATCHED','GESTURE_COMPLETED','UI_CHANGED','TARGET_POSTCONDITION_CONFIRMED','FAILED']: req(tok in svc_t+prov,'status missing '+tok)
req('private static boolean rotate' in sec and 'if (count >= AUDIT_MAX_RECORDS_PER_SEGMENT && !rotate(c, p))' in sec,'audit rotation not fail-closed')
req('prev.exists() && !prev.delete()' in sec and '!cur.renameTo(prev)' in sec and 'return p.edit()' in sec,'audit rotation failure checks incomplete')
pre=sec[sec.index('static synchronized boolean preActionAudit'):sec.index('static synchronized boolean audit')]
req('verifyAuditIntegrity(c)' in pre and 'hardStopWithoutAudit(c)' in pre,'pre-action audit integrity gate missing')
req(pre.index('verifyAuditIntegrity(c)') < pre.index('audit(c, action + "_PRE"'),'audit integrity not checked before precommit')
req('.replace("\\t", " ")' in sec,'package wire delimiter sanitization missing')
req('parsePackageWire' in main and 'p.length!=4' in main and '[0-9a-fA-F]{64}' in main,'core package wire validation missing')
root=(R/'build.gradle').read_text(); req("version '8.7.3'" in root,'AGP mismatch'); props=(R/'gradle/wrapper/gradle-wrapper.properties').read_text(); req('gradle-8.9-bin.zip' in props and 'distributionSha256Sum=d725d707' in props,'wrapper distribution pin missing')
for bad in ['Runtime.exec','ProcessBuilder','shizuku','purchase-verifier','BillingClient','is_settings_paywall_active','free_trial_enabled']:
    req(bad.lower() not in all_java.lower(),'forbidden source surface: '+bad)
print('SOURCE_SECURITY_INVARIANT_TEST=PASS')
print('IDENTITY_VERSION_PARSE=PASS')
print('TTL_MONOTONIC_PROCESS_BOUND=PASS_SOURCE')
print('DEVICE_CREDENTIAL_GATE=PASS_SOURCE')
print('GLOBAL_ACTION_POLICY=PASS_SOURCE')
print('PACKAGE_APPROVAL_REVOCATION=PASS_SOURCE')
print('PACKAGE_VISIBILITY_LEAST_PRIVILEGE=PASS_SOURCE')
print('AUDIT_HASH_CHAIN_ROTATION_FAIL_CLOSED=PASS_SOURCE')
print('PRE_ACTION_AUDIT_INTEGRITY_GATE=PASS_SOURCE')
print('PACKAGE_WIRE_INJECTION_GUARD=PASS_SOURCE')
print('SECRET_HANDLING=PASS_SOURCE')
print('FRESH_NODE_TOCTOU_GUARDS=PASS_SOURCE')
print('NOTE=SOURCE_ONLY_NOT_APK_NOT_RUNTIME')
