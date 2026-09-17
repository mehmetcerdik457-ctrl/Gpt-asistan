#!/usr/bin/env bash
set -euo pipefail

printf 'JAVA='; java -version 2>&1 | head -1
printf 'GRADLE='; gradle --version | awk '/Gradle /{print $2; exit}'
printf 'PYTHON='; python3 --version
printf 'PIP='; pip --version | awk '{print $2}'
printf 'GIT='; git --version
printf 'GH='; gh --version | head -1
printf 'JQ='; jq --version
printf 'CURL='; curl --version | head -1
printf 'UNZIP='; unzip -v | head -1
printf 'READELF='; readelf --version | head -1
printf 'OPENSSL='; openssl version
printf 'DOCKER_CLIENT='; docker --version || true
printf 'ADB='; adb --version | head -1
printf 'AAPT2='; aapt2 version
printf 'APKSIGNER='; apksigner version
printf 'APKANALYZER='; apkanalyzer --version
printf 'JADX='; jadx --version
printf 'APKTOOL='; apktool --version
printf 'BUNDLETOOL='; bundletool version
printf 'ANDROGUARD='; python -c 'import androguard; print(androguard.__version__)'
printf 'CAPSTONE='; python -c 'import capstone; print(capstone.__version__)'

printf 'TOOLCHAIN_VERIFY=PASS\n'
