#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
TinyFish CLI bootstrap (runs only on the machine where this script is executed).

Usage:
  bash scripts/tinyfish_setup.sh --install   Install @tiny-fish/cli globally
  bash scripts/tinyfish_setup.sh --login     Start the official interactive login

This script never launches an agent, browser automation, monitor, dataset, or research run.
USAGE
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

ACTION="$1"

if ! command -v node >/dev/null 2>&1; then
  echo "BLOCKED: Node.js is not installed."
  exit 1
fi

NODE_VERSION="$(node --version)"
NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if [[ "$NODE_MAJOR" -lt 24 ]]; then
  echo "BLOCKED: TinyFish CLI currently requires Node.js 24 or newer; found $NODE_VERSION."
  exit 1
fi

case "$ACTION" in
  --install)
    if ! command -v npm >/dev/null 2>&1; then
      echo "BLOCKED: npm is not available."
      exit 1
    fi
    npm install --global @tiny-fish/cli
    echo "CLI install command completed. No login or paid task was started."
    ;;
  --login)
    if ! command -v tinyfish >/dev/null 2>&1; then
      echo "BLOCKED: tinyfish CLI is not installed. Run --install first."
      exit 1
    fi
    tinyfish auth login
    echo "Interactive login command returned. No agent task was started."
    ;;
  *)
    usage
    exit 2
    ;;
esac
