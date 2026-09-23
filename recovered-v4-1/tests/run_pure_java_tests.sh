#!/usr/bin/env bash
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
javac -source 17 -target 17 -d "$W" "$R/bridge/src/main/java/com/mehmetcerdik/ownerbridge/AuditChain.java" "$R/bridge/src/main/java/com/mehmetcerdik/ownerbridge/SecretClassifier.java" "$R/tests/PureSecurityTest.java"
java -cp "$W" com.mehmetcerdik.ownerbridge.PureSecurityTest
