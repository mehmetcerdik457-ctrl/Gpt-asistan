#!/usr/bin/env python3
from pathlib import Path
R=Path(__file__).resolve().parents[1]
texts={str(p.relative_to(R)):p.read_text(errors='ignore') for p in R.rglob('*') if p.is_file() and p.suffix in {'.java','.xml','.gradle','.properties'} and 'tests/' not in str(p.relative_to(R)) }
alltext='\n'.join(texts.values()).lower()
def req(v,m):
    if not v: raise AssertionError(m)
svc=texts['bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeAccessibilityService.java']
sec=texts['bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeSecurity.java']
prov=texts['bridge/src/main/java/com/mehmetcerdik/ownerbridge/BridgeControlProvider.java']
main=texts['core/src/main/java/com/mehmetcerdik/ownerai/MainActivity.java']
for token in ['dispatchGesture','performGlobalAction','ACTION_SET_TEXT','verifyPostcondition','TARGET_POSTCONDITION_CONFIRMED']:
    req(token in svc+prov, token+' missing')
for token in ['SystemClock.elapsedRealtime','forceFailClosed','revokePackage','revokeAllNonDefaultPackages','verifyAuditIntegrity','AUDIT_MAX_RECORDS_PER_SEGMENT']:
    req(token in sec, token+' missing')
for token in ['FLAG_SECURE','createConfirmDeviceCredentialIntent','BİLDİRİMLER','Seçili Paketi Onayla']:
    req(token in main, token+' missing')
for bad in ['runtime.exec','processbuilder','shizuku','purchase-verifier','billingclient','is_settings_paywall_active','free_trial_enabled']:
    req(bad not in alltext, 'forbidden source token: '+bad)
print('SOURCE_LEXICAL_TEST=PASS')
