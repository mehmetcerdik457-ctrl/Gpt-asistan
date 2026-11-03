# Owner-approved local tool tasks

The existing owner gateway now provides a bounded tool-policy boundary for two
existing local capabilities. These routes do not call OpenAI, execute model
function calls, run shell commands, or contact external systems. The Android AI
task flow still rejects nonempty `tools`; its `tasks/approve` behavior remains
`approved_not_executed`.

## Fixed capability policy

| Tool | Scope | Exact arguments | Policy |
| --- | --- | --- | --- |
| `status` | `local.status` | `{}` | Execute a local status read after the signed owner request is authorized |
| `memory.save` | `local.memory` | `{"text":"..."}`; nonblank string, at most 8000 characters | Return `awaiting_approval`; write local memory only on exact signed approval |

The server owns this allowlist, input validation and approval class. Client
fields such as `actor`, `approval_class`, handlers, URLs or commands are rejected.
No other tool, scope or argument is accepted. A pending proposal stores its
arguments privately for review; it does not insert the text into memory.

## Signed API flow

All four routes use the existing dual-P256 owner/device signatures, fresh nonce,
exact path/body binding and persistent owner binding. Actor identity comes from
verified owner/device headers and the server's owner-public-key fingerprint,
never from the request body. No OpenAI configuration or model probe is needed.

1. `POST /api/v1/owner/tool-tasks` with:

   ```json
   {"tool":"memory.save","arguments":{"text":"Synthetic local note"},"scope":"local.memory"}
   ```

   The response includes `tool_task_id`, `request_sha256`, the exact arguments,
   scope, actor, policy, creation/expiry times, `awaiting_approval`, and audit
   evidence. The approval expires after 300 seconds. At most 50 proposals may
   await approval.

2. The owner reviews that exact action. `POST .../tool-tasks/approve` must contain
   exactly `tool_task_id`, `request_sha256`, `tool`, `arguments`, and `scope`,
   using the values returned by the proposal. The request must be signed by the
   same enrolled owner/device identity. A model response is not approval.

3. Approval executes the fixed local memory handler and returns `completed`,
   `result: {"id": ...}`, `approved_by`, `approved_at`, and `tools_executed: 1`.
   The memory insertion, approval/completion audit and result commit together in
   one SQLite transaction. The same action cannot execute twice, including with
   a new signed request, concurrent approvals, or a process restart.

`POST .../tool-tasks/status` and `POST .../tool-tasks/cancel` accept exactly
`tool_task_id` and `request_sha256`, under the same identity. Cancellation or
expiry prevents later approval. Approving or cancelling an expired action
returns `TOOL_TASK_EXPIRED` (409); approving a completed/cancelled action returns
`TOOL_TASK_NOT_PENDING` (409).

The SHA-256 digest binds task ID, tool, exact arguments, scope, actor, current
approval class and timestamps. It is an integrity/reference field, not an
authorization token; signatures are still required. Changing an approval's
arguments, tool, scope or digest returns `TOOL_APPROVAL_MISMATCH` (403), and
changing the owner/device/key identity returns `TOOL_ACTOR_DENIED` (403).

## Storage, privacy and checks

The existing private owner SQLite database gains additive `tool_tasks` and
`tool_task_audit` tables. Audit transitions contain only event, timestamp,
public actor identity and proposal digest; they omit memory text. Raw arguments
remain in the private proposal, visible only through the authenticated owner
routes. They are never sent to the provider by this flow. Rejected attempts
return fixed typed errors; only authorized state transitions are stored in this
audit table.

Run from the existing checkout:

```sh
.venv/bin/python -m unittest server.tests.test_tool_tasks -v
.venv/bin/python -m unittest discover -s server/tests -v
git diff --check
```

Tests use synthetic identities and temporary databases. Coverage includes real
signed local HTTP, exact approvals, unauthorized/tampered/replayed requests,
policy overrides, cancellation, expiry, restart persistence, capacity, concurrent
approval and rollback after a handler inserts data and then fails. Provider
calls are forbidden by the local-tool HTTP fixture.

Current workspace verification: the focused suite passed all 15 tests; the full
server suite passed all 121 tests with no failures or skips. `git diff --check`
passed. No paid calls, real owner/device enrollment, deployment, or Android
build/device checks were performed.

General function-calling/resume loops, additional tool capabilities, an Android
approval screen, external actions, deployment and real-device acceptance remain
outside this local backend change. Adding a capability requires implementing
its policy and transaction boundary in server code; an allowlist or approval
field supplied by a model never enables one.
