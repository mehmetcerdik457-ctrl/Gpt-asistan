# MEHMET AI — Owner transport (first working Android-to-Python contract)

This change turns the greeting-only Android Activity into an HTTPS owner client
and exposes a strictly bounded API in front of the existing Kral Python runtime.

## API server (development)

From repository root, set a strong independent token using a secret manager:
KRAL_OWNER_TOKEN must be 32-512 characters and must not be committed.
Configure either OPENAI_API_KEY or HUGGINGFACE_TOKEN separately on the backend.

Run locally:

    python3 kral/safe/server.py

The default bind is 127.0.0.1:8765. GET /health returns only {"status":"alive"}.
This is a liveness check, NOT model availability or inference acceptance.
POST /v1/ask needs Authorization: Bearer <KRAL_OWNER_TOKEN>,
Content-Type: application/json and body {"prompt":"..."}.
The response is {"answer":"...","provider":"...","model":"..."}.
Prompts are limited to 12,000 characters and request bodies to 16 KiB.

To expose this service to a phone, deploy it into an appropriately isolated
backend environment, proxy with **valid HTTPS**, and keep the Python HTTP listener
off the public internet. Non-loopback binding requires --allow-remote-bind as an
explicit override; this toggle does not provide TLS or firewall protection.
The Android client deliberately rejects HTTP, embedded URL credentials, query
strings and redirects. It keeps the owner token only in process memory, not
SharedPreferences, logcat, project files or an APK string.

## Boundaries and acceptance

- This is a single-owner API, NOT multi-user authentication or OAuth.
- It does not autonomously execute shell commands, GitHub writes or arbitrary tools.
- /health is not proof that an external provider can answer a request.
- Both model providers need secrets configured on the backend; this integration
  does not move a ChatGPT connector's credential to Railway/Codespaces.
- Each live question may incur inference charges. There is no claim of a free API.
- No model weights, production deployment, login, installed APK or physical-phone
  test is implied by merging this code.
- For production use add reverse proxy TLS, network restrictions, rate limits at
  the edge, service auth lifecycle/rotation, operational telemetry and monitoring.

Offline API tests:

    python3 -m unittest discover -s kral/safe -p 'test_*.py' -v

Android CI builds the APK on the PR. A successful Gradle build validates compilation
only; installing, logging in, sending a real question and receiving a model answer
are separate gates with separate evidence.
