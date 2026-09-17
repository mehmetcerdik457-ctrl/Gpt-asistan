FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    GRADLE_HOME=/opt/gradle/gradle-8.7 \
    PATH=/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/build-tools/34.0.0:/opt/gradle/gradle-8.7/bin:/opt/jadx/bin:/opt/r2flutter/bin:/opt/forensic-venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk openjdk-21-jdk python3 python3-pip python3-venv \
    git gh jq curl wget ca-certificates unzip zip binutils openssl file \
    build-essential cmake make meson ninja-build pkg-config libicu-dev libcapstone-dev \
    docker.io && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/android-sdk/cmdline-tools /tmp/android-cli \
 && curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o /tmp/android-cli.zip \
 && unzip -q /tmp/android-cli.zip -d /tmp/android-cli \
 && mkdir -p /opt/android-sdk/cmdline-tools/latest \
 && mv /tmp/android-cli/cmdline-tools/* /opt/android-sdk/cmdline-tools/latest/ \
 && yes | sdkmanager --licenses >/dev/null \
 && sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" \
 && rm -rf /tmp/android-cli /tmp/android-cli.zip

RUN mkdir -p /opt/gradle \
 && curl -fsSL https://services.gradle.org/distributions/gradle-8.7-bin.zip -o /tmp/gradle.zip \
 && unzip -q /tmp/gradle.zip -d /opt/gradle \
 && rm /tmp/gradle.zip

RUN curl -fsSL https://github.com/skylot/jadx/releases/download/v1.5.6/jadx-1.5.6.zip -o /tmp/jadx.zip \
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

RUN python3 -m venv /opt/forensic-venv \
 && /opt/forensic-venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/forensic-venv/bin/pip install --no-cache-dir androguard==4.1.3 capstone==5.0.7 requests pyelftools

# radare2 + r2flutter: build the current upstream toolchain and retain exact Git SHAs in the image.
RUN git clone --depth 1 https://github.com/radareorg/radare2.git /opt/radare2 \
 && cd /opt/radare2 \
 && sys/install.sh \
 && git rev-parse HEAD > /opt/RADARE2_GIT_SHA \
 && git clone --depth 1 https://github.com/radareorg/r2flutter.git /opt/r2flutter \
 && cd /opt/r2flutter \
 && make \
 && git rev-parse HEAD > /opt/R2FLUTTER_GIT_SHA

# Blutter is retained as a source-analysis tool; no target APK is embedded in this image.
RUN git clone --depth 1 https://github.com/worawit/blutter.git /opt/blutter \
 && git -C /opt/blutter rev-parse HEAD > /opt/BLUTTER_GIT_SHA

# Ghidra headless. The resolved release and installation path are recorded for evidence.
RUN url=$(curl -fsSL https://api.github.com/repos/NationalSecurityAgency/ghidra/releases/latest | jq -r '.assets[] | select(.name|test("PUBLIC.*\\.zip$")) | .browser_download_url' | head -1) \
 && test -n "$url" \
 && curl -fsSL "$url" -o /tmp/ghidra.zip \
 && mkdir -p /opt/ghidra-unpack \
 && unzip -q /tmp/ghidra.zip -d /opt/ghidra-unpack \
 && GH=$(find /opt/ghidra-unpack -maxdepth 4 -type f -path '*/support/analyzeHeadless' -print -quit) \
 && test -x "$GH" \
 && dirname "$GH" > /opt/GHIDRA_SUPPORT_DIR \
 && printf '#!/bin/sh\nexport JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64\nexec "$(cat /opt/GHIDRA_SUPPORT_DIR)/analyzeHeadless" "$@"\n' > /usr/local/bin/ghidra-headless \
 && chmod +x /usr/local/bin/ghidra-headless \
 && rm /tmp/ghidra.zip

RUN chown -R vscode:vscode /opt/android-sdk /opt/gradle /opt/jadx /opt/forensic-venv /opt/radare2 /opt/r2flutter /opt/blutter /opt/ghidra-unpack
USER vscode
