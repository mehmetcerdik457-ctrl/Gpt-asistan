#!/usr/bin/env python3
"""Legacy compatibility smoke test.
This file is intentionally retained for audit history. It is NOT a build/APK/security PASS.
Authoritative source gates are source_lexical_test.py and source_security_invariant_test.py.
"""
from pathlib import Path
R=Path(__file__).resolve().parents[1]
core_manifest=(R/'core/src/main/AndroidManifest.xml').read_text()
bridge_manifest=(R/'bridge/src/main/AndroidManifest.xml').read_text()
acc=(R/'bridge/src/main/res/xml/accessibility_service_config.xml').read_text()
sec=(R/'bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeSecurity.java').read_text()
svc=(R/'bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeAccessibilityService.java').read_text()
prov=(R/'bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeControlProvider.java').read_text()
main=(R/'core/src/main/java/com/mehmetcerdik/ownerai/MainActivity.java').read_text()
def req(x,msg):
    if not x: raise AssertionError(msg)
req('protectionLevel="signature"' in core_manifest,'signature permission missing')
req('android.permission.BIND_ACCESSIBILITY_SERVICE' in bridge_manifest,'accessibility bind permission missing')
req('android.permission.INTERNET' not in bridge_manifest,'bridge INTERNET present')
req('android.permission.QUERY_ALL_PACKAGES' not in bridge_manifest,'QUERY_ALL_PACKAGES must stay absent')
req('android:canPerformGestures="true"' in acc and 'android:canRetrieveWindowContent="true"' in acc,'accessibility capability missing')
for token in ['dispatchGesture','performGlobalAction','ACTION_SET_TEXT','verifyPostcondition']:
    req(token in svc+prov,token+' missing')
for token in ['SystemClock.elapsedRealtime','AUDIT_MAX_RECORDS_PER_SEGMENT','verifyAuditIntegrity','revokePackage','revokeAllNonDefaultPackages']:
    req(token in sec,token+' missing')
for token in ['FLAG_SECURE','createConfirmDeviceCredentialIntent','BİLDİRİMLER']:
    req(token in main,token+' missing')
print('LEGACY_SOURCE_LEXICAL_COMPAT_TEST=PASS')
print('NOTE=SOURCE_SMOKE_ONLY_NOT_BUILD_NOT_APK_NOT_RUNTIME')
