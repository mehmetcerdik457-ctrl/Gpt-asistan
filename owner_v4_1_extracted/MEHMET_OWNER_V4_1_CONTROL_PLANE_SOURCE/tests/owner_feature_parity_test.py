from pathlib import Path
root=Path(__file__).resolve().parents[1]
core=root/"core"
main=(core/"src/main/java/com/mehmetcerdik/ownerai/MainActivity.java").read_text()
activity=(core/"src/main/java/com/mehmetcerdik/ownerai/OwnerFeaturesActivity.java").read_text()
profile=(core/"src/main/java/com/mehmetcerdik/ownerai/OwnerFeatureProfile.java").read_text()
store=(core/"src/main/java/com/mehmetcerdik/ownerai/OwnerFeatureStore.java").read_text()
manifest=(core/"src/main/AndroidManifest.xml").read_text()
gradle=(core/"build.gradle").read_text()
bridge_manifest=(root/"bridge/src/main/AndroidManifest.xml").read_text()
for token in ["MODEL_SELECTOR","REASONING","AUTO_ROUTING","WEB_SEARCH","DEEP_RESEARCH","MEMORY","PERSONALIZATION","CUSTOM_INSTRUCTIONS","VOICE_REALTIME","MULTIMODAL_INPUT","OCR","TOOLS","LANGUAGE","VOICE_SELECTION","DIAGNOSTICS"]:
    assert token in profile, token
assert "LOCAL_DESIRED_PROFILE_ONLY" in profile
assert "NO_BACKEND_MUTATION|NO_ENTITLEMENT_BYPASS|PUBLIC_WORKER_IMMUTABLE" in profile
assert "AndroidKeyStore" in store and "AES/GCM/NoPadding" in store
assert "setUserAuthenticationRequired(true)" in store
assert "OwnerFeaturesActivity" in main
assert 'android:name=".OwnerFeaturesActivity"' in manifest and 'android:exported="false"' in manifest
assert "versionCode 5" in gradle and "versionName '1.3.0'" in gradle
assert "android.permission.INTERNET" not in manifest
assert "android.permission.INTERNET" not in bridge_manifest
assert "com.codespaceapps.aichat" in activity
print("OWNER_FEATURE_PARITY_SOURCE_TEST=PASS")
