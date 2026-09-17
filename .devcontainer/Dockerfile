FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

USER root
ENV DEBIAN_FRONTEND=noninteractive \
    ANDROID_HOME=/opt/android-sdk \
    ANDROID_SDK_ROOT=/opt/android-sdk \
    GRADLE_HOME=/opt/gradle/gradle-8.7 \
    PATH=/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/build-tools/34.0.0:/opt/gradle/gradle-8.7/bin:/opt/jadx/bin:/opt/forensic-venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jdk python3 python3-pip python3-venv \
    git gh jq curl wget ca-certificates unzip zip binutils openssl file \
    build-essential cmake ninja-build pkg-config libicu-dev libcapstone-dev \
    docker.io && rm -rf /var/lib/apt/lists/*

# Android SDK: command-line tools + platform/build tools used by this repository.
RUN mkdir -p /opt/android-sdk/cmdline-tools /tmp/android-cli \
 && curl -fsSL https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip -o /tmp/android-cli.zip \
 && unzip -q /tmp/android-cli.zip -d /tmp/android-cli \
 && mkdir -p /opt/android-sdk/cmdline-tools/latest \
 && mv /tmp/android-cli/cmdline-tools/* /opt/android-sdk/cmdline-tools/latest/ \
 && yes | sdkmanager --licenses >/dev/null \
 && sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" \
 && rm -rf /tmp/android-cli /tmp/android-cli.zip

# Gradle pinned to the version used by current CI.
RUN mkdir -p /opt/gradle \
 && curl -fsSL https://services.gradle.org/distributions/gradle-8.7-bin.zip -o /tmp/gradle.zip \
 && unzip -q /tmp/gradle.zip -d /opt/gradle \
 && rm /tmp/gradle.zip

# JADX 1.5.6.
RUN curl -fsSL https://github.com/skylot/jadx/releases/download/v1.5.6/jadx-1.5.6.zip -o /tmp/jadx.zip \
 && mkdir -p /opt/jadx \
 && unzip -q /tmp/jadx.zip -d /opt/jadx \
 && rm /tmp/jadx.zip

# Apktool 3.0.3, checksum pinned to the upstream release artifact.
RUN curl -fsSL https://github.com/iBotPeaches/Apktool/releases/download/v3.0.3/apktool_3.0.3.jar -o /opt/apktool.jar \
 && echo "dbf930b076c6b9be08d57c449cacefc3bdd6b71ebd59b3066fc0e1f5b14f9423  /opt/apktool.jar" | sha256sum -c - \
 && printf '#!/bin/sh\nexec java -jar /opt/apktool.jar "$@"\n' > /usr/local/bin/apktool \
 && chmod +x /usr/local/bin/apktool

# bundletool 1.18.3, checksum pinned.
RUN curl -fsSL https://github.com/google/bundletool/releases/download/1.18.3/bundletool-all-1.18.3.jar -o /opt/bundletool.jar \
 && echo "a099cfa1543f55593bc2ed16a70a7c67fe54b1747bb7301f37fdfd6d91028e29  /opt/bundletool.jar" | sha256sum -c - \
 && printf '#!/bin/sh\nexec java -jar /opt/bundletool.jar "$@"\n' > /usr/local/bin/bundletool \
 && chmod +x /usr/local/bin/bundletool

# Python forensic libraries isolated from the system interpreter.
RUN python3 -m venv /opt/forensic-venv \
 && /opt/forensic-venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/forensic-venv/bin/pip install --no-cache-dir androguard==4.1.3 capstone==5.0.6

RUN chown -R vscode:vscode /opt/android-sdk /opt/gradle /opt/jadx /opt/forensic-venv
USER vscode
