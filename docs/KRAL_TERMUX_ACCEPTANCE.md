# KRAL Termux local-model acceptance — read-only

This is an on-device evidence check, not a deployment, permission bypass,
proof of 50 model instances, or proof that a particular model binary is genuine.

From a checkout containing server/termux_acceptance.py, with the existing
localhost OpenAI-compatible server started and the model ID matching the
provider configuration, run these commands in Termux:

    python -m unittest server.tests.test_termux_acceptance -v
    python -m server.termux_acceptance --provider missions/local_provider.example.json
    python -m server.termux_acceptance --provider missions/local_provider.example.json --infer

The first probe checks /v1/models on localhost and verifies that the configured
model IDs are advertised by the provider. The --infer form also makes ONE
localhost chat-completion request and reports the byte count and SHA-256 hash
of the returned text, NOT the model's raw response. The --out option can
create a fresh, private (0600) JSON evidence file; it will not overwrite an
existing file.

The probe performs no GitHub writes, shell execution, file modifications
outside the optional evidence file, credit spending, or agent task acceptance.
No endpoint beyond loopback is permitted by the existing local_open_workers
adapter. It never claims physical Android verification from the PREFIX hint.

Interpretation:

- LOCAL_CATALOG_PASS_NO_INFERENCE: advertised models and local endpoint
  reachable; no inference was requested.
- LOCAL_INFERENCE_RESPONSE_PASS_NOT_TASK_COMPLETION: a structurally valid
  response came back; not proof of model weights or repository task completion.
- BLOCKED_LOCAL_PROVIDER: no acceptance. Check actual local service, model
  names, and loopback endpoint before retrying.

Only evidence from the actual Termux environment can validate that device.
CI's fake HTTP server does NOT provide Android or model-weight acceptance.
