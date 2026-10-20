# Threat model

This document is the isolation model for the reference harness. It is not a penetration test and it is not a statement that a site identity provider has been connected.

## Assets

| Asset | Where it lives | What a caller gets back |
| --- | --- | --- |
| Synthetic accounts | In-memory directory for the process | Status and roles for the caller's tenant |
| Run checkpoint | SQLite file for that process | Status view for the owning tenant |
| Approval | Resume payload built from the approver token | Approval id and resulting status |
| Audit log | JSONL path chosen at startup | Operation, actor, tenant, decision, status |
| Free text | Request body only | Not stored in the graph, the memory, or the audit |
| Dev tokens | Source fixture | Nothing outside this process |

The seed declares `real_accounts: 0`. There are no passwords in the directory.

## Actors

| Actor | Intended power |
| --- | --- |
| Unauthenticated caller | No run route |
| Reader | Lookup inside the tenant on the token |
| Operator | Lookup, and a request for a high-risk tool that waits |
| Approver | Approve a waiting run in that tenant when the approver is not the requester |
| Other tenant | A different token. Same request id returns 404 |

## Boundaries

1. **Token binding.** Tenant and role are read from the token map. Intake writes those values into state and clears any approval that arrived with the input.
2. **Structured tool choice.** `evaluate` uses `operation`. A justification that names another operation leaves the tool unchanged. The golden case `injection-ignored` checks that the fixture phrase is absent from the audit, the checkpoint values, the memory record, and the API view.
3. **Credential channel.** Keys named `password`, `secret`, `api_key`, `ssn`, or `private_key` stop the run with HTTP 422. The audit line says `credential material` and does not contain the value.
4. **Approval.** High-risk tools interrupt. Resume requires role `approver`, the same tenant, a different actor, and an id starting with `APR-`. A forged resume payload that names the requester is denied inside the graph, and the directory fingerprint stays the same.
5. **Re-evaluation.** Recheck and execute both call `evaluate`. A checkpoint that has already passed the first policy node still has to pass again before `apply`.
6. **Tenant memory and export.** Memory has no cross-tenant read. Export filters audit rows by tenant. A marker written for tenant-b is absent from tenant-a's export view.
7. **Fail closed tools.** An unknown operation, a bad target, a reader asking for disable, or a down tool produces deny or failed. The account status does not change.
8. **AWS document.** The state machine defaults every choice to Close. Task failures are caught into Close. The IAM document names four functions in account `000000000000`.

## What an operator must replace

| Fixture | Replacement before any site use |
| --- | --- |
| `dev-reader-a` and the other dev tokens | Site identity provider. The `idp-provider-binding` gate records that cutover |
| SQLite checkpoint in the API process | A store the site already accepts for identity workflow state |
| In-memory directory | The site's account system, behind the same idempotency key |
| Placeholder Lambda ARNs | Functions that call this package's `evaluate`, `apply`, and postcondition checks |
| Hosted model | Not part of this path. A later xAI call uses `XAI_API_KEY` and `https://api.x.ai/v1`, server-side, after the policy gate, and only with identity attributes removed |

## Residual risks

- The directory and the approval live in the process that holds the checkpoint. A second API process with a new directory does not see effects applied by the first. The recovery test covers a reopened checkpoint against a fresh seed, which matches the pre-tool pause. It does not cover a crash after `apply` and before `close`.
- Dev tokens are in source so the tests can run. They authorize nothing outside this process.
- The target check hides cross-tenant existence behind `unknown target`. The caller still learns that this tenant does not have that id.
- Audit lines contain the synthetic user id and the actor name. Treat that file as operational data.
- Publishing the local replay as a Step Functions execution would misstate the system. The acceptance report stays NO-GO to prevent that.

## Evidence classes

| Class | Use here |
| --- | --- |
| `EXAMPLE` | Directory seed and golden cases |
| `GATE` | The three external rows in the acceptance report |
| `MEASURED` | Only a complete row in `benchmarks/aws-evidence.json` |
