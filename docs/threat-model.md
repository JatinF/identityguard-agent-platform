# Threat model

The assets are synthetic identities, synthetic login evidence, approval records, and the workflow checkpoint. The seed declares `real_accounts: 0`. Addresses use the documentation range. Email uses `.invalid`.

## Boundaries

| Threat | Control | Result when the control trips |
| --- | --- | --- |
| Prompt tells the model to skip approval | Policy ignores `skip_approval` and pauses for a different approver | `AWAITING_APPROVAL`, no write |
| Caller asks for another tenant | Token tenant is the only scope. Cross-tenant subjects are denied with the same public message as an unknown subject | `DENIED` or 404, no write |
| Reader or same person tries to suspend | Role check and self-approval check live outside the model | No write |
| Approver rejects or the approval expires | `reauthorize` runs again on resume | `REJECTED` or `EXPIRED`, no write |
| Tool returns success and the account is unchanged | Reread compares the account with the approved state | `UNVERIFIED`, completion not claimed |
| Model cites an evidence id that was not retrieved | Citation check before policy | `EVIDENCE_REJECTED`, no write |
| Same request or same decision is delivered twice | Idempotency key on the run, effect key on the suspend | One run, one state transition |
| Model times out | Bounded retry, then an explicit failure | `FAILED` or a later pause, no write |
| Candidate model misses more risks | Release gate | `BLOCK` for that model. Deployment stays NO-GO |

## What the checkpoint holds

The LangGraph checkpoint keeps the investigation goal so a resumed thread can finish the node. Audit rows and tenant memory do not copy the goal. Treat the checkpoint file as local operator data.

## What this does not claim

The mock directory is not an identity provider. Dev tokens are fixtures. A body field named `password`, `secret`, `api_key`, `ssn`, or `private_key` is rejected and the value is not written to the audit log. No hosted model is called by the default path, so identity text is not sent off the machine.
