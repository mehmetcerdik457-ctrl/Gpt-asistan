FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04@sha256:d94c97dd9cacf183d0a6fd12a8e87b526e9e928307674ae9c94139139c0c6eae

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    GRADLE_HOME=/opt/gradle/gradle-8.7 \
    PATH=/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/build-tools/34.0.0:/opt/gradle/gradle-8.7/bin:/opt/jadx/bin:/opt/r2flutter/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk openjdk-21-jdk python3 python3-venv androguard python3-capstone python3-requests python3-pyelftools \
    git gh jq curl wget ca-certificates unzip zip binutils openssl file \
    build-essential cmake make meson ninja-build pkg-config libicu-dev libcapstone-dev \
    docker.io && rm -rf /var/lib/apt/lists/*

# Android command-line tools 12.0. Version and SHA-256 are fixed.
RUN mkdir -p /opt/android-sdk/cmdline-tools /tmp/android-cli \
 && curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o /tmp/android-cli.zip \
 && echo "2d2d50857e4eb553af5a6dc3ad507a17adf43d115264b1afc116f95c92e5e258  /tmp/android-cli.zip" | sha256sum -c - \
 && unzip -q /tmp/android-cli.zip -d /tmp/android-cli \
 && mkdir -p /opt/android-sdk/cmdline-tools/latest \
 && mv /tmp/android-cli/cmdline-tools/* /opt/android-sdk/cmdline-tools/latest/ \
 && yes | sdkmanager --licenses >/dev/null \
 && sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" \
 && rm -rf /tmp/android-cli /tmp/android-cli.zip

RUN mkdir -p /opt/gradle \
 && curl -fsSL https://services.gradle.org/distributions/gradle-8.7-bin.zip -o /tmp/gradle.zip \
 && echo "544c35d6bd849ae8a5ed0bcea39ba677dc40f49df7d1835561582da2009b961d  /tmp/gradle.zip" | sha256sum -c - \
 && unzip -q /tmp/gradle.zip -d /opt/gradle \
 && rm /tmp/gradle.zip

RUN curl -fsSL https://github.com/skylot/jadx/releases/download/v1.5.6/jadx-1.5.6.zip -o /tmp/jadx.zip \
 && echo "545ea2be9c242511bc145755cf4bda2485ade42966e096f8b4d3da2a230e8974  /tmp/jadx.zip" | sha256sum -c - \
 && mkdir -p /opt/jadx \
 && unzip -q /tmp/jadx.zip -d /opt/jadx \
 && rm /tmp/jadx.zip

RUN curl -fsSL https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar -o /opt/apktool.jar \
 && echo "dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423  /opt/apktool.jar" | sha256sum -c - \
 && printf '#!/bin/sh\nexec java -jar /opt/apktool.jar "$@"\n' > /usr/local/bin/apktool \
 && chmod +x /usr/local/bin/apktool

RUN curl -fsSL https://github.com/google/bundletool/releases/download/1.18.3/bundletool-all-1.18.3.jar -o /opt/bundletool.jar \
 && echo "a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29  /opt/bundletool.jar" | sha256sum -c - \
 && printf '#!/bin/sh\nexec java -jar /opt/bundletool.jar "$@"\n' > /usr/local/bin/bundletool \
 && chmod +x /usr/local/bin/bundletool

# Python forensic libraries come from Ubuntu's signed package repository.
# Avoid runtime pip resolution in the devcontainer supply chain.
RUN python3 - <<'PY'
import androguard, capstone, requests
import elftools
print("androguard=" + getattr(androguard, "__version__", "unknown"))
print("capstone=" + getattr(capstone, "__version__", "unknown"))
print("requests=" + requests.__version__)
print("pyelftools=system-package")
PY

# Native-analysis source tools are fetched by immutable commit, not mutable branch HEAD.
RUN git init -q /opt/radare2 \
 && git -C /opt/radare2 remote add origin https://github.com/radareorg/radare2.git \
 && git -C /opt/radare2 fetch --depth 1 origin 39b18895dc5fd85177959d4af90434e975866d56 \
 && git -C /opt/radare2 checkout --detach FETCH_HEAD \
 && test "$(git -C /opt/radare2 rev-parse HEAD)" = "39b18895dc5fd85177959d4af90434e975866d56" \
 && cd /opt/radare2 \
 && sys/install.sh \
 && git rev-parse HEAD > /opt/RADARE2_GIT_SHA \
 && git init -q /opt/r2flutter \
 && git -C /opt/r2flutter remote add origin https://github.com/radareorg/r2flutter.git \
 && git -C /opt/r2flutter fetch --depth 1 origin 67935055e5a113ede14b4e410264fc8ee62e0c37 \
 && git -C /opt/r2flutter checkout --detach FETCH_HEAD \
 && test "$(git -C /opt/r2flutter rev-parse HEAD)" = "67935055e5a113ede14b4e410264fc8ee62e0c37" \
 && cd /opt/r2flutter \
 && make \
 && git rev-parse HEAD > /opt/R2FLUTTER_GIT_SHA

RUN git init -q /opt/blutter \
 && git -C /opt/blutter remote add origin https://github.com/worawit/blutter.git \
 && git -C /opt/blutter fetch --depth 1 origin 4a60ac648bf448c5a7596437243bcd0b9376fdf0 \
 && git -C /opt/blutter checkout --detach FETCH_HEAD \
 && test "$(git -C /opt/blutter rev-parse HEAD)" = "4a60ac648bf448c5a7596437243bcd0b9376fdf0" \
 && git -C /opt/blutter rev-parse HEAD > /opt/BLUTTER_GIT_SHA

RUN curl -fsSL https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.3_build/ghidra_12.1.3_PUBLIC_20260817.zip -o /tmp/ghidra.zip \
 && echo "93a5d11a9ad510622acaaf908c556a7b9b764d338e78a7567f3689bf5081fd54  /tmp/ghidra.zip" | sha256sum -c - \
 && mkdir -p /opt/ghidra-unpack \
 && unzip -q /tmp/ghidra.zip -d /opt/ghidra-unpack \
 && GH=$(find /opt/ghidra-unpack -maxdepth 4 -type f -path '*/support/analyzeHeadless' -print -quit) \
 && test -x "$GH" \
 && dirname "$GH" > /opt/GHIDRA_SUPPORT_DIR \
 && printf '#!/bin/sh\nexport JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64\nexec "$(cat /opt/GHIDRA_SUPPORT_DIR)/analyzeHeadless" "$@"\n' > /usr/local/bin/ghidra-headless \
 && chmod +x /usr/local/bin/ghidra-headless \
 && rm /tmp/ghidra.zip

RUN chown -R vscode:vscode /opt/android-sdk /opt/gradle /opt/jadx /opt/radare2 /opt/r2flutter /opt/blutter /opt/ghidra-unpack
USER vscode
