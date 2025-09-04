from pathlib import Path

def _w(p, s): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8")

def create(kind:str, name:str)->str:
    if kind=="html-landing": return create_html_landing(name)
    if kind=="python-lib":   return create_python_lib(name)
    if kind=="fastapi-app":  return create_fastapi_app(name)
    raise ValueError("desteklenmeyen tür")

def create_html_landing(name:str)->str:
    base = Path.home()/ "repos" / name
    _w(base/"index.html", "<!doctype html><meta charset='utf-8'><title>"+name+"</title><h1>"+name+"</h1><p>Merhaba!</p>")
    return str(base)

def create_python_lib(name:str)->str:
    base = Path.home()/ "repos" / name
    _w(base/"pyproject.toml", f"[project]\nname='{name}'\nversion='0.1.0'\n")
    _w(base/f"{name}/__init__.py", "__all__=['hi']\nhi=lambda:'ok'\n")
    return str(base)

def create_fastapi_app(name:str)->str:
    base = Path.home()/ "repos" / name
    _w(base/"pyproject.toml", "[project]\nname='app'\nversion='0.1.0'\n")
    _w(base/"app.py", "from fastapi import FastAPI\napp=FastAPI()\n@app.get('/')\ndef hi(): return {'ok':True}\n")
    return str(base)

def create_android_min(name:str)->str:
    base = Path.home()/ "repos" / name
    pkg  = "com.example."+name.replace("-","").replace("_","")
    # settings/build
    _w(base/"settings.gradle.kts", f'rootProject.name = "{name}"\ninclude(":app")\n')
    _w(base/"build.gradle.kts", """plugins { id("com.android.application") version "8.7.0" apply false; kotlin("android") version "2.0.0" apply false }""")
    # app gradle
    _w(base/"app/build.gradle.kts", f"""
plugins {{
  id("com.android.application")
  kotlin("android")
}}
android {{
  namespace = "{pkg}"
  compileSdk = 34
  defaultConfig {{
    applicationId = "{pkg}"
    minSdk = 24
    targetSdk = 34
    versionCode = 1
    versionName = "1.0"
  }}
  buildTypes {{
    debug {{ debuggable = true }}
    release {{
      isMinifyEnabled = false
      proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
    }}
  }}
}}
dependencies {{
  implementation("androidx.core:core-ktx:1.13.1")
  implementation("androidx.appcompat:appcompat:1.7.0")
  implementation("com.google.android.material:material:1.12.0")
}}
""")
    _w(base/"app/proguard-rules.pro", "")
    # AndroidManifest + Activity
    _w(base/"app/src/main/AndroidManifest.xml", f"""<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{pkg}">
  <application android:label="{name}" android:icon="@mipmap/ic_launcher">
    <activity android:name=".MainActivity">
      <intent-filter>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
      </intent-filter>
    </activity>
  </application>
</manifest>""")
    _w(base/"app/src/main/java/MainActivity.kt", f"""package {pkg}
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import android.widget.TextView
class MainActivity: AppCompatActivity() {{
  override fun onCreate(b: Bundle?) {{
    super.onCreate(b)
    val tv = TextView(this)
    tv.text = "Merhaba {name}!"
    setContentView(tv)
  }}
}}""")
    # Gradle wrapper'ı GH runner indirecek (gradle/actions kullanacağız)
    _w(base/".github/workflows/android.yml", """name: Android Debug APK
on:
  workflow_dispatch:
  push:
    branches: [ main ]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: 'temurin', java-version: '17' }
      - name: Install Gradle
        uses: gradle/actions/setup-gradle@v3
        with:
          gradle-version: 8.7
      - name: Build debug
        run: |
          mkdir -p ~/.android && echo 'count=0' > ~/.android/repositories.cfg
          yes | sdkmanager --licenses || true
          gradle help || true
          gradle :app:assembleDebug
      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: debug-apk
          path: app/build/outputs/apk/debug/*.apk
""")
    return str(base)
