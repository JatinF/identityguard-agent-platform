# Runbook: run waiting on approval

Use this when a high-risk run stays in `awaiting-approval`.

The local status means LangGraph interrupted before the tool. The Step Functions equivalent is `WaitForApproval` with a task token. That state machine has not been executed from this repository. Do not start it as the first response to a waiting local run.

## Confirm

1. `GET /v1/runs/{request_id}` with a token from the same tenant. `status` is `awaiting-approval`, `interrupted` is true, and `mutated` is false.
2. Read the account. For a disable of `SYN-USER-014` in the fixture directory, `target_status` is still `active`.
3. Read the audit. A waiting run has not reached Close, so there may be no `run` line yet. Do not treat a missing line as success or failure.
4. Confirm the caller who would resume is an approver in that tenant and is not the actor on the run.

## Resume

Send `POST /v1/runs/{request_id}/resume` with the approver's bearer token and a body of `{"approval_id": "APR-..."}`. The approver name is taken from the token. A name in the body does not change it.

A reader, the original actor, and an approver from another tenant do not clear the pause. The other-tenant response is 404.

## If the tool is down

A harness opened with `force_tool_down` returns `failed` after a valid approval and does not change the account. Leave the account as it is. Open a fresh request after the tool path is restored. Do not edit the checkpoint to set `decision` to `allow`.

## Do not

- Copy the replay report into `benchmarks/aws-evidence.json`.
- Call a hosted model with the request body to "decide" the approval.
- Delete the SQLite file while the run is the system of record for that request id. Recovery reopens that file.
