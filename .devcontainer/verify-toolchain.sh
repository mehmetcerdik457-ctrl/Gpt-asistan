#!/usr/bin/env bash
set -eu

first_line() {
  "$@" 2>&1 | sed -n '1p'
}

printf 'JAVA='; first_line java -version
printf 'JAVAC='; javac -version
printf 'GRADLE='; gradle --version | awk '$1=="Gradle"{print $2; found=1} END{if(!found) exit 1}'
printf 'PYTHON='; python3 --version
printf 'PIP='; pip --version | awk '{print $2}'
printf 'GIT='; git --version
printf 'GH='; first_line gh --version
printf 'JQ='; jq --version
printf 'CURL='; first_line curl --version
printf 'UNZIP='; unzip -v | sed -n '1p'
printf 'READELF='; readelf --version | sed -n '1p'
printf 'OBJDUMP='; objdump --version | sed -n '1p'
printf 'NM='; nm --version | sed -n '1p'
printf 'STRINGS='; strings --version | sed -n '1p'
printf 'OPENSSL='; openssl version
printf 'DOCKER_CLIENT='; docker --version || true
printf 'ADB='; adb --version | sed -n '1p'
printf 'AAPT2='; aapt2 version
printf 'APKSIGNER='; apksigner version
printf 'APKANALYZER='; apkanalyzer --version
printf 'JADX='; jadx --version
printf 'APKTOOL='; apktool --version
printf 'BUNDLETOOL='; bundletool version
printf 'ANDROGUARD='; python -c 'import androguard; print(androguard.__version__)'
printf 'CAPSTONE='; python -c 'import capstone; print(capstone.__version__)'
printf 'RADARE2='; r2 -v | sed -n '1p'
printf 'RADARE2_GIT_SHA='; cat /opt/RADARE2_GIT_SHA
printf 'R2FLUTTER='; /opt/r2flutter/bin/r2flutter -V
printf 'R2FLUTTER_GIT_SHA='; cat /opt/R2FLUTTER_GIT_SHA
python3 /opt/blutter/blutter.py --help >/tmp/blutter-help.txt 2>&1
printf 'BLUTTER_GIT_SHA='; cat /opt/BLUTTER_GIT_SHA
mkdir -p /tmp/ghidra-project
rm -rf /tmp/ghidra-project/*
ghidra-headless /tmp/ghidra-project DevcontainerSmoke -import /bin/ls -deleteProject >/tmp/ghidra-smoke.log 2>&1
printf 'GHIDRA_HEADLESS=PASS TARGET=/bin/ls\n'
sample=$(find /opt/r2flutter/test/bins -type f -name 'libapp.so' -print -quit 2>/dev/null || true)
if [ -z "$sample" ]; then
  echo 'R2FLUTTER_SAMPLE_TARGET=NOT_FOUND'
  exit 1
fi
/opt/r2flutter/bin/r2flutter -HH -l 16 "$sample" >/tmp/r2flutter-sample.log 2>&1
/opt/r2flutter/bin/r2flutter -D 3.10.7 -H "$sample" >/tmp/r2flutter-dart3107.log 2>&1
printf 'R2FLUTTER_SAMPLE_TARGET=%s RC=0\n' "$sample"
printf 'DART_3_10_7_PROFILE_CAPABILITY=VERIFIED SAMPLE_TARGET=%s RC=0\n' "$sample"
printf 'TARGET_CHATBOT_OBJECTPOOL_XREF=NOT_TESTED\n'
printf 'TOOLCHAIN_VERIFY=PASS\n'
