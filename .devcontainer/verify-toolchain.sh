#!/usr/bin/env bash
set -eu

first_line() {
  "$@" 2>&1 | sed -n '1p'
}

printf 'JAVA='; first_line java -version
printf 'GRADLE='; gradle --version | awk '$1=="Gradle"{print $2; found=1} END{if(!found) exit 1}'
printf 'PYTHON='; python3 --version
printf 'PIP='; pip --version | awk '{print $2}'
printf 'GIT='; git --version
printf 'GH='; first_line gh --version
printf 'JQ='; jq --version
printf 'CURL='; first_line curl --version
printf 'UNZIP='; unzip -v | sed -n '1p'
printf 'READELF='; readelf --version | sed -n '1p'
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
printf 'TOOLCHAIN_VERIFY=PASS\n'
