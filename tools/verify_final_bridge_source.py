#!/usr/bin/env python3
from pathlib import Path
import re, sys
root=Path(__file__).resolve().parents[1]
manifest=(root/"bridge/src/main/AndroidManifest.xml").read_text()
xml=(root/"bridge/src/main/res/xml/accessibility_service_config.xml").read_text()
gradle=(root/"bridge/build.gradle.kts").read_text()
svc=(root/"bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeAccessibilityService.java").read_text()
provider=(root/"bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeControlProvider.java").read_text()
security=(root/"bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeSecurity.java").read_text()
client=(root/"app/src/main/java/com/mehmetcerdik/ownerai/BridgeClient.java").read_text()
req={
"NO_INTERNET":"android.permission.INTERNET" not in manifest,
"NO_QUERY_ALL":"QUERY_ALL_PACKAGES" not in manifest,
"PACKAGE":"applicationId = \"com.mehmetcerdik.ownerbridge\"" in gradle,
"VERSION":"versionCode = 2" in gradle and 'versionName = "1.1.0"' in gradle,
"GESTURES":'android:canPerformGestures="true"' in xml and "dispatchGesture(" in svc,
"TYPE":"ACTION_SET_TEXT" in svc and "ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE" in svc,
"GLOBAL":"performGlobalAction(" in svc,
"LAUNCH":"getLaunchIntentForPackage" in svc,
"CALLER_PIN":"CORE_SIGNER" in security and "verifyCore" in security and "getPackagesForUid" in provider,
"WORKER_PIN":"WORKER_SIGNER" in security and "com.codespaceapps.aichat" in security,
"SIGNATURE_PERMISSION":'android:permission="com.mehmetcerdik.ownerai.permission.BRIDGE"' in manifest,
"METHOD_SURFACE":all(('case"'+m+'"') in provider for m in ["status","arm","stop","approvePackage","screenRead","clickText","typeText","scroll","swipe","globalAction","launchApp"]),
"OWNER_CLIENT_COMPAT":all(('"'+m+'"') in client and ('case"'+m+'"') in provider for m in ["status","arm","stop","approvePackage","screenRead","clickText","typeText","scroll","swipe","globalAction","launchApp"]),
"EVIDENCE":all(x in svc for x in ['"LAUNCH_APP"','"SWIPE"','"TYPE_TEXT"'])
}
bad=[k for k,v in req.items() if not v]
for k,v in req.items(): print(f"{k}={'PASS' if v else 'FAIL'}")
if bad: print("FAILED="+",".join(bad));sys.exit(2)
print("BRIDGE_SOURCE_CONTRACT=PASS")
