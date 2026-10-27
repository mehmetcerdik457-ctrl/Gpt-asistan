# KRAL — OpenAI privacy case evidence packet

This is an **offline, local-only** tool for preparing a follow-up to an **existing privacy/data-access request**. It does **not** make OpenAI appeals, send emails, create support tickets, re-enable accounts, or bypass account restrictions. It does not override the final outcome of a deactivation appeal.

## Run (Termux / Python 3.10+)

```bash
python3 tools/kral_openai_case_packet.py --case 17185949 --linked-case 16940096
```

Optional account details must be provided at runtime through local environment variables, not committed to GitHub:

```bash
export KRAL_OPENAI_ACCOUNT_EMAIL='your-account@example.com'
export KRAL_OPENAI_ACCOUNT_USER_ID='user-id-if-relevant'
python3 tools/kral_openai_case_packet.py --case 17185949 --linked-case 16940096
unset KRAL_OPENAI_ACCOUNT_EMAIL KRAL_OPENAI_ACCOUNT_USER_ID
```

By default the JSON goes into `~/.local/share/kral/openai_cases` and is created with restricted permissions (`0600` on POSIX; its parent directory is `0700`). The tool refuses to overwrite a packet with the same name. It prints SHA-256 of the exact local file content, **not a digital signature**. Account data is never included in public source code.

If a message needs sending, verify the details and use the already existing official OpenAI support/privacy conversation or an authenticated official portal manually. Avoid duplicating a closed account-deactivation appeal. OpenAI links in the packet are references, not destinations used by the program.

## Offline tests

```bash
python3 -m unittest discover -s tests -p 'test_kral_openai_case_packet.py' -v
```

No dependencies beyond the Python standard library. Network calls: **none**.
