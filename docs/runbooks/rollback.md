# Runbook: rollback

Use this when a disable or a role grant should be undone, or when a bad build started accepting runs.

## Steps

1. Stop new traffic to the API process. Waiting runs stay interrupted. They do not apply a tool until resume.
2. Identify the request id. If status is `awaiting-approval`, do not resume it. The account is unchanged. Record the request id and leave the checkpoint in place until the incident note is written.
3. If status is `verified` and the directory changed, file a new synthetic request for the compensating operation. This reference has no automatic enable. A second `disable-account` with the same request id returns 409 and does not apply a second effect. A compensating change needs its own `SYN-REQ-` id, its own approval, and its own idempotency key.
4. If the failure is a process crash after the interrupt and before the tool, reopen the same SQLite file and resume only when an approver is present. `recovery_check` is the local rehearsal of that path.
5. Re-run the software slice before calling the rollback done:

   ```bash
   python -m pytest
   ```

   The committed acceptance report must still render as **NO-GO** when `benchmarks/aws-evidence.json` is absent.

## Afterward

Write who stopped traffic, which request ids were left waiting, and which compensating request ids were approved. Do not attach the local replay as a Step Functions execution. Do not widen the IAM document to `Resource: *` to make a rollback faster.
