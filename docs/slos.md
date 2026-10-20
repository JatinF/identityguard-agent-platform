# Service objectives

Software objectives are checks this repository executes on every test run. External objectives are gates. A gate has no result until `benchmarks/aws-evidence.json` carries a `MEASURED` pass with an execution identifier and a log. A green GitHub Actions run is not a Step Functions service objective.

## Software objectives exercised by pytest

| Objective | Pass condition in this repo |
| --- | --- |
| Lookup | Reader lookup of `SYN-USER-014` returns `verified` and does not mutate the directory |
| High-risk pause | Disable without a resume stays `awaiting-approval` and the account stays active |
| Approval | A different approver produces `verified` and status `disabled` |
| Separation of duties | The requester's resume returns 403 and the account stays active. A forged self-approval inside the graph is `denied` |
| Role limit | A reader disable is `denied` and containment is verified |
| Tenant binding | A body tenant of `tenant-b` on a tenant-a token is ignored. The other tenant's fingerprint is unchanged |
| Tool choice | Free text that names another operation does not change the tool, and the phrase is absent from stored state |
| Idempotency | A second start of the same request id returns 409 and the account stays disabled |
| Recovery | A reopened SQLite file resumes the waiting thread and disables the account once |
| Export isolation | An export view does not contain another tenant's audit marker |
| Tool outage | `force_tool_down` finishes `failed` with the account still active |
| Release honesty | The committed acceptance report matches a fresh render and the decision is NO-GO |
| Document hygiene | The state machine and the IAM document pass `asl_problems` and `iam_problems` |

These checks protect the repository. They do not measure an AWS account.

## External gates

| Gate id | What must be true before production identity operations | Status in this repo |
| --- | --- | --- |
| `stepfunctions-execution` | The placeholder state machine ran, and a deny path closed without Execute | not-run |
| `idp-provider-binding` | The site identity provider replaced the dev token map | not-run |
| `hosted-model-run` | A hosted model trace exists only if the site enabled one, with the policy gate in front | not-run |

This repository does not publish a latency millisecond target for those gates. The local replay's wall time is not that target.

## Error budget while the decision is NO-GO

There is no production error budget. The harness is not accepted for production identity traffic. Creating the state machine in a real account, or pointing the token map at a production directory, does not create one. The budget starts after every external gate is a measured pass on the account that will run the workflow.
